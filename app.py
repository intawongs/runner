import streamlit as st
import pandas as pd
from supabase import create_client, Client
from streamlit_qrcode_scanner import qrcode_scanner
from streamlit_js_eval import get_geolocation
from streamlit_autorefresh import st_autorefresh
import time
from datetime import datetime, time as dt_time
import pytz
import math

# --- 0. GLOBAL CONFIG (5 STATIONS - LOOP RUN) ---
# Start และ Finish คือพิกัดเดียวกัน (Loop)
CP_COORDINATES = {
    "Start": {"lat": 13.3849, "lon": 100.1914},
    "Checkpoint 1": {"lat": 13.3859, "lon": 100.1904},
    "Checkpoint 2": {"lat": 13.3901, "lon": 100.1913},
    "Checkpoint 3": {"lat": 13.3901, "lon": 100.1917},
    "Finish": {"lat": 13.3849, "lon": 100.1914}
}
CHECKPOINT_LIST = list(CP_COORDINATES.keys())
tz = pytz.timezone('Asia/Bangkok')
START_TIME_RUN = dt_time(7, 30) # เวลาเริ่มนับคะแนนกลาง

st.set_page_config(page_title="RCI AI RACING 2026", layout="wide", initial_sidebar_state="collapsed")

# --- 1. CONNECTION ---
@st.cache_resource
def init_connection():
    try:
        return create_client(st.secrets["SUPABASE_URL"], st.secrets["SUPABASE_KEY"])
    except:
        st.error("❌ Connection Error: ตรวจสอบ Secrets ใน Streamlit Dashboard")
        st.stop()

supabase = init_connection()

# --- 2. HELPERS ---
def clean_bib(text):
    if not text: return ""
    c = text.replace("-", "").replace(" ", "").upper()
    if c.startswith("RCI") and len(c) > 3: return f"RCI-{c[3:]}"
    return c

def get_next_bib():
    try:
        res = supabase.table("runners").select("bib_number").order("bib_number", desc=True).limit(1).execute()
        if not res.data: return "RCI-001"
        last_num = int(res.data[0]['bib_number'].split("-")[1])
        return f"RCI-{last_num + 1:03d}"
    except: return "RCI-001"

def haversine(lat1, lon1, lat2, lon2):
    R = 6371000 
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi, dlambda = math.radians(lat2-lat1), math.radians(lon2-lon1)
    a = math.sin(dphi/2)**2 + math.cos(phi1)*math.cos(phi2)*math.sin(dlambda/2)**2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))

def upload_photo(file_bytes, bib):
    path = f"profile_{bib}.jpg"
    bucket = "runner_photos"
    try: supabase.storage.from_(bucket).remove([path])
    except: pass
    supabase.storage.from_(bucket).upload(path, file_bytes, {"content-type": "image/jpeg"})
    return f"{st.secrets['SUPABASE_URL']}/storage/v1/object/public/{bucket}/{path}"

def parse_iso_to_thai(iso_str):
    try: return datetime.fromisoformat(iso_str.replace('Z', '+00:00')).astimezone(tz)
    except: return datetime.now(tz)

# --- 3. SESSION STATE ---
if "page" not in st.session_state: st.session_state.page = "HOME"
if "my_bib" not in st.session_state: st.session_state.my_bib = ""
if "reg_step" not in st.session_state: st.session_state.reg_step = "FORM"

def change_page(t):
    st.session_state.page = t; st.rerun()

# ---------------------------------------------------------
# --- MAIN UI ---
# ---------------------------------------------------------

# --- หน้า HOME ---
if st.session_state.page == "HOME":
    st.markdown("<h1 style='text-align: center;'>🏃‍♂️ RCI AI RACING 2026 🏁</h1>", unsafe_allow_html=True)
    st.write("---")
    
    if not st.session_state.my_bib:
        st.info("👋 สวัสดี! กรุณาลงทะเบียนเพื่อรับ BIB ก่อนเริ่มวิ่ง")
        st.button("📝 ลงทะเบียนนักวิ่งใหม่", on_click=change_page, args=("REGISTER",), use_container_width=True, type="primary")
        with st.expander("มี BIB แล้ว? คลิกเพื่อล็อกอินเข้าสู่เครื่องนี้"):
            old_bib = st.text_input("กรอกเลข BIB (เช่น RCI-001)")
            if st.button("ตกลง ล็อกอิน"):
                st.session_state.my_bib = clean_bib(old_bib)
                st.rerun()
    else:
        st.success(f"📟 ล็อกอินในชื่อ BIB: **{st.session_state.my_bib}**")
        st.button("🏁 ไปหน้าสแกนเช็คอิน (One-Click)", on_click=change_page, args=("SCAN",), use_container_width=True, type="primary")
        st.button("🎁 ดูสรุปผล & รับรางวัล", on_click=change_page, args=("REWARD",), use_container_width=True)
        st.divider()
        st.button("🏆 กระดานคะแนน (Racing Lanes)", on_click=change_page, args=("LEADERBOARD",), use_container_width=True)
        if st.button("Logout (เปลี่ยนเลข BIB)"):
            st.session_state.my_bib = ""; st.rerun()

# --- หน้า REGISTER ---
elif st.session_state.page == "REGISTER":
    st.header("📝 ลงทะเบียน")
    if st.session_state.reg_step == "FORM":
        next_bib = get_next_bib()
        with st.form("reg"):
            st.info(f"BIB ที่คุณจะได้รับ: **{next_bib}**")
            n = st.text_input("ชื่อ-นามสกุล")
            d = st.selectbox("แผนก", ["Production", "R&D", "QA", "Logistics", "Office", "Maintenance"])
            if st.form_submit_button("📸 ถัดไป: ถ่ายรูปโปรไฟล์"):
                if n: 
                    st.session_state.temp = {"bib": next_bib, "name": n, "dept": d}
                    st.session_state.reg_step = "PHOTO"; st.rerun()
                else: st.warning("กรุณากรอกชื่อ")
    elif st.session_state.reg_step == "PHOTO":
        st.subheader("📸 ถ่ายรูปโปรไฟล์")
        img = st.camera_input("กดถ่ายรูปหน้าตรง")
        if img:
            with st.spinner("กำลังบันทึกข้อมูล..."):
                url = upload_photo(img.getvalue(), st.session_state.temp['bib'])
                supabase.table("runners").insert({
                    "bib_number": st.session_state.temp['bib'], 
                    "name": st.session_state.temp['name'], 
                    "department": st.session_state.temp['dept'], 
                    "profile_url": url
                }).execute()
                st.session_state.my_bib = st.session_state.temp['bib']
                st.session_state.reg_step = "DONE"; st.rerun()
    elif st.session_state.reg_step == "DONE":
        st.success(f"🎉 ลงทะเบียนสำเร็จ! BIB: {st.session_state.my_bib}")
        st.button("🏠 กลับหน้าหลัก", on_click=change_page, args=("HOME",), use_container_width=True)
        st.session_state.reg_step = "FORM"

# --- หน้า SCAN (One-Click + Smart Loop Logic) ---
elif st.session_state.page == "SCAN":
    if not st.session_state.my_bib:
        st.error("กรุณาลงทะเบียนก่อน")
        st.button("🏠 กลับหน้าหลัก", on_click=change_page, args=("HOME",), use_container_width=True)
    else:
        st.header("🏁 สแกนเช็คอิน")
        st.info(f"BIB: **{st.session_state.my_bib}** | กำลังค้นหา GPS...")
        
        loc = get_geolocation()
        if loc:
            lat, lon = loc['coords']['latitude'], loc['coords']['longitude']
            near = None; min_d = 9999
            for cp, pos in CP_COORDINATES.items():
                d = haversine(lat, lon, pos['lat'], pos['lon'])
                if d < min_d: min_d = d; near = cp
            
            # Smart Loop Logic: Start/Finish พิกัดเดียวกัน
            if near in ["Start", "Finish"]:
                c_start = supabase.table("run_logs").select("id").eq("bib_number", st.session_state.my_bib).eq("checkpoint_name", "Start").execute()
                c_middle = supabase.table("run_logs").select("checkpoint_name").eq("bib_number", st.session_state.my_bib).in_("checkpoint_name", ["Checkpoint 1", "Checkpoint 2", "Checkpoint 3"]).execute()
                near = "Finish" if (len(c_start.data) > 0 and len(c_middle.data) >= 3) else "Start"

            if min_d <= 100:
                st.success(f"🎯 คุณอยู่ใกล้จุด: **{near}** (ห่าง {min_d:.1f} ม.)")
                qr = qrcode_scanner(key=f"sc_{near}")
                if qr == near:
                    idx = CHECKPOINT_LIST.index(qr)
                    can = True
                    if idx > 0:
                        prev = CHECKPOINT_LIST[idx-1]
                        c = supabase.table("run_logs").select("id").eq("bib_number", st.session_state.my_bib).eq("checkpoint_name", prev).execute()
                        if not c.data: can = False; st.error(f"❌ ห้ามข้ามจุด! ต้องสแกนจุด {prev} ก่อน")
                    
                    if can:
                        dup = supabase.table("run_logs").select("id").eq("bib_number", st.session_state.my_bib).eq("checkpoint_name", qr).execute()
                        if not dup.data:
                            supabase.table("run_logs").insert({"bib_number": st.session_state.my_bib, "checkpoint_name": qr}).execute()
                            st.success(f"🎉 บันทึกสำเร็จ!"); st.balloons()
                            time.sleep(2); change_page("HOME")
                        else: st.warning("เช็คอินจุดนี้ไปแล้ว")
            else: st.error(f"❌ คุณยังไม่อยู่ในจุดเช็คอิน (ห่างจากจุด {near} {min_d:.1f} ม.)")
    st.button("🏠 กลับหน้าหลัก", on_click=change_page, args=("HOME",), use_container_width=True)

# --- หน้า LEADERBOARD (Auto-Refresh 10 วินาที) ---
elif st.session_state.page == "LEADERBOARD":
    # รีเฟรชหน้าอัตโนมัติทุก 10,000 มิลลิวินาที (10 วินาที)
    st_autorefresh(interval=10000, limit=None, key="leaderboard_racing_refresh")
    
    st.markdown("<h2 style='text-align: center;'>🏎️ RCI RACING LANES</h2>", unsafe_allow_html=True)
    if st.button("🏠 กลับหน้าหลัก", on_click=change_page, args=("HOME",), use_container_width=True): pass

    res = supabase.table("run_logs").select("*, runners(*)").order("scanned_at", desc=True).execute()
    if res.data:
        df = pd.DataFrame(res.data)
        latest = df.sort_values("scanned_at", ascending=False).groupby("bib_number").first().reset_index()
        lanes = st.columns(len(CHECKPOINT_LIST), gap="small")
        for idx, cp in enumerate(CHECKPOINT_LIST):
            with lanes[idx]:
                st.markdown(f"<div style='background:#2E86C1; color:white; border-radius:10px; text-align:center; padding:5px; font-size:12px; font-weight:bold;'>{cp}</div>", unsafe_allow_html=True)
                runners = latest[latest['checkpoint_name'] == cp]
                img_sz = 60 if len(runners) <= 3 else 40
                for _, r in runners.iterrows():
                    img = r['runners']['profile_url'] if r['runners'] and r['runners']['profile_url'] else ""
                    name = (r['runners']['name'] if r['runners'] else r['bib_number']).split(" ")[0]
                    st.markdown(f"""
                        <div style='text-align:center; margin-top:10px; animation: bounce 0.8s infinite alternate;'>
                            <img src='{img}' style='width:{img_sz}px; height:{img_sz}px; border-radius:50%; border:2px solid gold; object-fit:cover;'>
                            <p style='font-size:10px; font-weight:bold; margin:0;'>{name}</p>
                        </div>
                        <style>@keyframes bounce {{ from {{transform:translateY(0);}} to {{transform:translateY(-8px);}} }}</style>
                    """, unsafe_allow_html=True)
    else: st.info("ยังไม่มีข้อมูลการวิ่ง")

# --- หน้า REWARD ---
elif st.session_state.page == "REWARD":
    if not st.session_state.my_bib:
        st.error("กรุณาล็อกอินก่อน")
    else:
        st.header("🎁 สรุปผลการวิ่ง")
        res = supabase.table("run_logs").select("*").eq("bib_number", st.session_state.my_bib).execute()
        logs = pd.DataFrame(res.data)
        if not logs.empty:
            checked = logs['checkpoint_name'].tolist()
            st.progress(len(checked) / len(CHECKPOINT_LIST))
            for cp in CHECKPOINT_LIST: st.write(f"{'✅' if cp in checked else '⚪'} {cp}")
            if "Finish" in checked:
                finish_t = parse_iso_to_thai(logs[logs['checkpoint_name'] == "Finish"].iloc[0]['scanned_at'])
                start_f = finish_t.replace(hour=7, minute=30, second=0, microsecond=0)
                dur = finish_t - start_f
                st.success(f"🎉 วิ่งครบแล้ว! เวลา: {str(dur).split('.')[0]} ชม.")
                st.image(f"https://api.qrserver.com/v1/create-qr-code/?size=150x150&data=REWARD_{st.session_state.my_bib}")
    st.button("🏠 กลับหน้าหลัก", on_click=change_page, args=("HOME",), use_container_width=True)