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
START_TIME_RUN = dt_time(7, 30)

st.set_page_config(page_title="RCI AI RACING 2026", layout="wide", initial_sidebar_state="collapsed")

# --- 1. CONNECTION ---
@st.cache_resource
def init_connection():
    try:
        return create_client(st.secrets["SUPABASE_URL"], st.secrets["SUPABASE_KEY"])
    except:
        st.error("❌ Connection Error: โปรดตรวจสอบ Secrets"); st.stop()

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
        last_bib = res.data[0]['bib_number']
        last_num = int(last_bib.split("-")[1])
        return f"RCI-{last_num + 1:03d}"
    except: return "RCI-001"

def haversine(lat1, lon1, lat2, lon2):
    R = 6371000 
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi, dlambda = math.radians(lat2-lat1), math.radians(lon2-lon1)
    a = math.sin(dphi/2)**2 + math.cos(phi1)*math.cos(phi2)*math.sin(dlambda/2)**2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))

def upload_photo(file_bytes, bib_number):
    try:
        path = f"profile_{bib_number}.jpg"
        bucket = "runner_photos"
        try: supabase.storage.from_(bucket).remove([path])
        except: pass
        supabase.storage.from_(bucket).upload(path, file_bytes, {"content-type": "image/jpeg"})
        return f"{st.secrets['SUPABASE_URL']}/storage/v1/object/public/{bucket}/{path}"
    except Exception as e:
        st.error(f"Upload Error: {e}")
        return None

def parse_iso_to_thai(iso_str):
    try:
        dt = datetime.fromisoformat(iso_str.replace('Z', '+00:00'))
        return dt.astimezone(tz)
    except: return datetime.now(tz)

# --- 3. SESSION STATE ---
if "page" not in st.session_state: st.session_state.page = "HOME"
if "my_bib" not in st.session_state: st.session_state.my_bib = ""
if "reg_step" not in st.session_state: st.session_state.reg_step = "FORM"

def change_page(target):
    st.session_state.page = target
    st.rerun()

# ---------------------------------------------------------
# --- MAIN UI ---
# ---------------------------------------------------------

# --- หน้า HOME ---
if st.session_state.page == "HOME":
    st.markdown("<h1 style='text-align: center;'>🏃‍♂️ RCI AI RACING 2026 🏁</h1>", unsafe_allow_html=True)
    st.write("---")
    
    if not st.session_state.my_bib:
        st.info("👋 ยินดีต้อนรับ! กรุณาลงทะเบียนก่อนเริ่มวิ่ง")
        st.button("📝 ลงทะเบียนนักวิ่งใหม่", on_click=change_page, args=("REGISTER",), use_container_width=True, type="primary")
        with st.expander("มี BIB แล้ว? คลิกเพื่อล็อกอิน"):
            old_bib = st.text_input("กรอกเลข BIB (เช่น RCI-001)")
            if st.button("ตกลง ล็อกอิน"):
                st.session_state.my_bib = clean_bib(old_bib); st.rerun()
    else:
        st.success(f"📟 ล็อกอิน BIB: **{st.session_state.my_bib}**")
        st.button("🏁 ไปหน้าสแกนเช็คอิน (One-Click)", on_click=change_page, args=("SCAN",), use_container_width=True, type="primary")
        st.button("🏆 กระดานคะแนน (Leaderboard)", on_click=change_page, args=("LEADERBOARD",), use_container_width=True)
        st.button("🎁 ดูสรุปผล & รับรางวัล", on_click=change_page, args=("REWARD",), use_container_width=True)
        st.divider()
        if st.button("Logout"):
            st.session_state.my_bib = ""; st.rerun()

# --- หน้า REGISTER ---
elif st.session_state.page == "REGISTER":
    st.header("📝 ลงทะเบียน")
    if st.session_state.reg_step == "FORM":
        next_bib = get_next_bib()
        with st.form("reg"):
            st.info(f"BIB: {next_bib}")
            name = st.text_input("ชื่อ-นามสกุล")
            dept = st.selectbox("แผนก", ["Production", "R&D", "QA", "Logistics", "Office", "Maintenance"])
            if st.form_submit_button("📸 ถัดไป"):
                if name:
                    st.session_state.temp_user = {"bib": next_bib, "name": name, "dept": dept}
                    st.session_step = "PHOTO"; st.session_state.reg_step = "PHOTO"; st.rerun()
    elif st.session_state.reg_step == "PHOTO":
        img = st.camera_input("ถ่ายรูปโปรไฟล์")
        if img:
            with st.spinner("บันทึกข้อมูล..."):
                p_url = upload_photo(img.getvalue(), st.session_state.temp_user['bib'])
                supabase.table("runners").insert({"bib_number": st.session_state.temp_user['bib'], "name": st.session_state.temp_user['name'], "department": st.session_state.temp_user['dept'], "profile_url": p_url}).execute()
                st.session_state.my_bib = st.session_state.temp_user['bib']
                st.session_state.reg_step = "DONE"; st.rerun()
    elif st.session_state.reg_step == "DONE":
        st.success("🎉 ลงทะเบียนสำเร็จ!"); st.button("🏠 กลับหน้าหลัก", on_click=change_page, args=("HOME",))
        st.session_state.reg_step = "FORM"

# --- [ หน้า SCAN: ฉบับเน้นพิกัดโชว์แน่นอน ] ---
elif st.session_state.page == "SCAN":
    if not st.session_state.my_bib:
        st.error("กรุณาล็อกอินก่อน"); st.button("🏠 กลับ", on_click=change_page, args=("HOME",))
    else:
        st.header(f"🏁 เช็คอิน ({st.session_state.my_bib})")
        
        # แสดงพิกัดปัจจุบัน
        st.write("📡 **ตรวจสอบตำแหน่ง GPS:**")
        loc = get_geolocation()
        
        if loc and 'coords' in loc:
            lat, lon = loc['coords']['latitude'], loc['coords']['longitude']
            st.success(f"✅ ตรวจพบพิกัด: `{lat:.6f}, {lon:.6f}`")
            
            near = None; min_d = 9999
            for cp, pos in CP_COORDINATES.items():
                d = haversine(lat, lon, pos['lat'], pos['lon'])
                if d < min_d: min_d = d; near = cp
            
            # Smart Loop Logic
            if near in ["Start", "Finish"]:
                c_start = supabase.table("run_logs").select("id").eq("bib_number", st.session_state.my_bib).eq("checkpoint_name", "Start").execute()
                c_middle = supabase.table("run_logs").select("checkpoint_name").eq("bib_number", st.session_state.my_bib).in_("checkpoint_name", ["Checkpoint 1", "Checkpoint 2", "Checkpoint 3"]).execute()
                near = "Finish" if (len(c_start.data) > 0 and len(c_middle.data) >= 3) else "Start"

            if min_d <= 100:
                st.info(f"📍 อยู่ใกล้จุด: **{near}** (ห่าง {min_d:.1f} ม.)")
                qr = qrcode_scanner(key=f"sc_{near}_{time.time()}")
                if qr == near:
                    idx = CHECKPOINT_LIST.index(qr)
                    if idx > 0:
                        prev = CHECKPOINT_LIST[idx-1]
                        c = supabase.table("run_logs").select("id").eq("bib_number", st.session_state.my_bib).eq("checkpoint_name", prev).execute()
                        if not c.data: st.error(f"❌ ต้องสแกนจุด {prev} ก่อน"); st.stop()
                    
                    dup = supabase.table("run_logs").select("id").eq("bib_number", st.session_state.my_bib).eq("checkpoint_name", qr).execute()
                    if not dup.data:
                        supabase.table("run_logs").insert({"bib_number": st.session_state.my_bib, "checkpoint_name": qr}).execute()
                        st.success("🎉 บันทึกสำเร็จ!"); st.balloons()
                        time.sleep(2); change_page("HOME")
                    else: st.warning("คุณเช็คอินจุดนี้ไปแล้ว")
            else:
                st.error(f"❌ ไม่อยู่ในระยะ (จุดที่ใกล้ที่สุด {near} ห่าง {min_d:.1f} ม.)")
        else:
            st.warning("⏳ กำลังค้นหาสัญญาณ GPS... โปรดอนุญาต Browser")
            if st.button("🔄 รีเฟรชพิกัด"): st.rerun()

    st.button("🏠 กลับหน้าหลัก", on_click=change_page, args=("HOME",), use_container_width=True)

# --- [ หน้า LEADERBOARD: ฉบับเลนไม่ซ้อน + Auto 10s + Manual ] ---
elif st.session_state.page == "LEADERBOARD":
    st_autorefresh(interval=10000, key="lb_race_refresh")
    st.markdown("<h2 style='text-align: center;'>🏎️ RCI RACING LANES</h2>", unsafe_allow_html=True)
    
    # ปุ่มควบคุมด้านบน
    c_back, c_ref = st.columns([5, 1])
    with c_back:
        if st.button("🏠 กลับหน้าหลัก", use_container_width=True): change_page("HOME")
    with c_ref:
        if st.button("🔄", use_container_width=True): st.rerun()

    res = supabase.table("run_logs").select("*, runners(*)").order("scanned_at", desc=True).execute()
    if res.data:
        df = pd.DataFrame(res.data)
        latest = df.sort_values("scanned_at", ascending=False).groupby("bib_number").first().reset_index()
        
        # แบ่ง 5 คอลัมน์ตายตัว บังคับพื้นที่
        lanes = st.columns(len(CHECKPOINT_LIST))
        for idx, cp in enumerate(CHECKPOINT_LIST):
            with lanes[idx]:
                st.markdown(f"<div style='background:#2E86C1; color:white; border-radius:10px; text-align:center; padding:8px; font-size:14px; font-weight:bold; min-height:40px;'>{cp}</div>", unsafe_allow_html=True)
                runners = latest[latest['checkpoint_name'] == cp]
                if not runners.empty:
                    sz = 50 if len(runners) <= 3 else 35
                    for _, r in runners.iterrows():
                        img = r['runners']['profile_url'] if r['runners'] and r['runners']['profile_url'] else ""
                        name = (r['runners']['name'] if r['runners'] else r['bib_number']).split(" ")[0]
                        st.markdown(f"""
                            <div style='text-align:center; margin-top:15px; animation: bounce 0.8s infinite alternate;'>
                                <img src='{img}' style='width:{sz}px; height:{sz}px; border-radius:50%; border:2px solid gold; object-fit:cover;'>
                                <p style='font-size:10px; font-weight:bold; margin:0;'>{name}</p>
                            </div>
                            <style>@keyframes bounce {{ from {{transform:translateY(0);}} to {{transform:translateY(-8px);}} }}</style>
                        """, unsafe_allow_html=True)
                else:
                    st.markdown("<div style='height:200px;'></div>", unsafe_allow_html=True) # ป้องกันเลนยุบ
    else: st.info("ยังไม่มีข้อมูลนักวิ่ง")

# --- หน้า REWARD ---
elif st.session_state.page == "REWARD":
    st.header("🎁 สรุปผลการวิ่ง")
    res = supabase.table("run_logs").select("*").eq("bib_number", st.session_state.my_bib).execute()
    logs = pd.DataFrame(res.data)
    if not logs.empty:
        checked = logs['checkpoint_name'].tolist(); st.progress(len(checked) / len(CHECKPOINT_LIST))
        if "Finish" in checked:
            finish_t = parse_iso_to_thai(logs[logs['checkpoint_name'] == "Finish"].iloc[0]['scanned_at'])
            dur = finish_t - finish_t.replace(hour=7, minute=30, second=0, microsecond=0)
            st.success(f"🎉 สำเร็จ! เวลา: {str(dur).split('.')[0]} ชม.")
            st.image(f"https://api.qrserver.com/v1/create-qr-code/?size=150x150&data=REWARD_{st.session_state.my_bib}")
    st.button("🏠 กลับหน้าหลัก", on_click=change_page, args=("HOME",), use_container_width=True)