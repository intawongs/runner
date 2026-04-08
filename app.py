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

# --- 0. CONFIG (5 STATIONS) ---
CP_COORDINATES = {
     "Start": {"lat": 13.6470, "lon": 100.3206},
    "Checkpoint 1": {"lat": 13.3859, "lon": 100.1904},
    "Checkpoint 2": {"lat": 13.3901, "lon": 100.1913},
    "Checkpoint 3": {"lat": 13.3901, "lon": 100.1917},
    "Finish": {"lat": 13.3849, "lon": 100.1914} # จุดเดียวกับ Start
}
CHECKPOINT_LIST = list(CP_COORDINATES.keys())
tz = pytz.timezone('Asia/Bangkok')
START_TIME_RUN = dt_time(7, 30)

st.set_page_config(page_title="RCI RACING 2026", layout="wide", initial_sidebar_state="collapsed")

# --- 1. CONNECTION ---
def init_connection():
    try:
        return create_client(st.secrets["SUPABASE_URL"], st.secrets["SUPABASE_KEY"])
    except:
        st.error("❌ เชื่อมต่อ Database ล้มเหลว"); st.stop()

supabase = init_connection()

# --- 2. HELPERS ---
def clean_bib(text):
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

# --- HOME ---
if st.session_state.page == "HOME":
    st.markdown("<h1 style='text-align: center;'>🏃‍♂️ RCI AI RACING 2026</h1>", unsafe_allow_html=True)
    st.divider()
    st.button("📝 ลงทะเบียนนักวิ่ง", on_click=change_page, args=("REGISTER",), use_container_width=True, type="primary")
    st.button("🏁 สแกนเช็คอิน", on_click=change_page, args=("SCAN",), use_container_width=True)
    st.button("🏆 กระดานคะแนน (Racing)", on_click=change_page, args=("LEADERBOARD",), use_container_width=True)
    st.button("🎁 รับรางวัล & สรุปผล", on_click=change_page, args=("REWARD",), use_container_width=True)
    if st.session_state.my_bib: st.success(f"BIB: {st.session_state.my_bib}")

# --- REGISTER ---
elif st.session_state.page == "REGISTER":
    if st.session_state.reg_step == "FORM":
        next_bib = get_next_bib()
        with st.form("reg"):
            st.info(f"BIB: {next_bib}")
            n = st.text_input("ชื่อ-นามสกุล")
            d = st.selectbox("แผนก", ["Production", "R&D", "QA", "Logistics", "Office", "Maintenance"])
            if st.form_submit_button("📸 ถัดไป: ถ่ายรูป"):
                if n: 
                    st.session_state.temp = {"bib": next_bib, "name": n, "dept": d}
                    st.session_state.reg_step = "PHOTO"; st.rerun()
    elif st.session_state.reg_step == "PHOTO":
        img = st.camera_input("ถ่ายรูปโปรไฟล์")
        if img:
            with st.spinner("บันทึก..."):
                url = upload_photo(img.getvalue(), st.session_state.temp['bib'])
                supabase.table("runners").insert({"bib_number": st.session_state.temp['bib'], "name": st.session_state.temp['name'], "department": st.session_state.temp['dept'], "profile_url": url}).execute()
                st.session_state.my_bib = st.session_state.temp['bib']; st.session_state.reg_step = "DONE"; st.rerun()
    elif st.session_state.reg_step == "DONE":
        st.success(f"ลงทะเบียนสำเร็จ! BIB: {st.session_state.my_bib}")
        st.button("🏠 กลับหน้าหลัก", on_click=change_page, args=("HOME",), use_container_width=True)
        st.session_state.reg_step = "FORM"

# --- SCAN (WITH SMART LOOP LOGIC) ---
elif st.session_state.page == "SCAN":
    bib_in = st.text_input("เลข BIB", value=st.session_state.my_bib).upper()
    if bib_in:
        st.session_state.my_bib = clean_bib(bib_in)
        loc = get_geolocation()
        if loc:
            lat, lon = loc['coords']['latitude'], loc['coords']['longitude']
            near = None; min_d = 9999
            for cp, pos in CP_COORDINATES.items():
                d = haversine(lat, lon, pos['lat'], pos['lon'])
                if d < min_d: min_d = d; near = cp
            
            # Smart Logic: จัดการจุด Start/Finish ที่พิกัดเดียวกัน
            if near in ["Start", "Finish"]:
                # เช็คว่าเคยสแกน Start หรือยัง
                c_start = supabase.table("run_logs").select("id").eq("bib_number", st.session_state.my_bib).eq("checkpoint_name", "Start").execute()
                # เช็คว่าเก็บ CP ครบหรือยัง
                c_middle = supabase.table("run_logs").select("checkpoint_name").eq("bib_number", st.session_state.my_bib).in_("checkpoint_name", ["Checkpoint 1", "Checkpoint 2", "Checkpoint 3"]).execute()
                
                if len(c_start.data) > 0 and len(c_middle.data) >= 3:
                    near = "Finish"
                else:
                    near = "Start"

            if min_d <= 100:
                st.success(f"📍 อยู่ใกล้จุด: **{near}**")
                qr = qrcode_scanner(key=f"sc_{near}")
                if qr == near:
                    idx = CHECKPOINT_LIST.index(qr)
                    can = True
                    if idx > 0:
                        prev = CHECKPOINT_LIST[idx-1]
                        c = supabase.table("run_logs").select("id").eq("bib_number", st.session_state.my_bib).eq("checkpoint_name", prev).execute()
                        if not c.data: 
                            can = False; st.error(f"❌ ห้ามข้ามจุด! ต้องสแกนจุด {prev} ก่อน")
                    
                    if can:
                        dup = supabase.table("run_logs").select("id").eq("bib_number", st.session_state.my_bib).eq("checkpoint_name", qr).execute()
                        if not dup.data:
                            supabase.table("run_logs").insert({"bib_number": st.session_state.my_bib, "checkpoint_name": qr}).execute()
                            st.success(f"🎉 บันทึกจุด {qr} สำเร็จ!"); st.balloons()
                        else: st.warning("คุณเช็คอินจุดนี้ไปแล้ว")
            else: st.error(f"❌ ไม่อยู่ในระยะ (ห่างจาก {near} {min_d:.1f} ม.)")
    st.button("🏠 กลับหน้าหลัก", on_click=change_page, args=("HOME",), use_container_width=True)

# --- LEADERBOARD (5-LANE RACING) ---
elif st.session_state.page == "LEADERBOARD":
    st.markdown("<h2 style='text-align: center;'>🏎️ RCI RACING LANES</h2>", unsafe_allow_html=True)
    st_autorefresh(interval=5000, key="race")
    
    res = supabase.table("run_logs").select("*, runners(*)").order("scanned_at", desc=True).execute()
    if res.data:
        df = pd.DataFrame(res.data)
        latest = df.sort_values("scanned_at", ascending=False).groupby("bib_number").first().reset_index()
        lanes = st.columns(len(CHECKPOINT_LIST), gap="small")

        for idx, cp in enumerate(CHECKPOINT_LIST):
            with lanes[idx]:
                st.markdown(f"<div style='background:#2E86C1; color:white; border-radius:10px; text-align:center; padding:5px; font-size:12px;'>{cp}</div>", unsafe_allow_html=True)
                runners = latest[latest['checkpoint_name'] == cp]
                img_size = 60 if len(runners) <= 3 else 40
                for _, r in runners.iterrows():
                    img = r['runners']['profile_url'] if r['runners'] and r['runners']['profile_url'] else ""
                    name = (r['runners']['name'] if r['runners'] else r['bib_number']).split(" ")[0]
                    st.markdown(f"""
                        <div style='text-align:center; margin-top:10px; animation: bounce 0.8s infinite alternate;'>
                            <img src='{img}' style='width:{img_size}px; height:{img_size}px; border-radius:50%; border:2px solid gold; object-fit:cover;'>
                            <p style='font-size:10px; margin:0;'>{name}</p>
                        </div>
                        <style>@keyframes bounce {{ from {{transform:translateY(0);}} to {{transform:translateY(-8px);}} }}</style>
                    """, unsafe_allow_html=True)
    st.button("🏠 กลับหน้าหลัก", on_click=change_page, args=("HOME",), use_container_width=True)

# --- REWARD ---
elif st.session_state.page == "REWARD":
    bib_in = st.text_input("เลข BIB", value=st.session_state.my_bib)
    if bib_in:
        my_bib = clean_bib(bib_in)
        res = supabase.table("run_logs").select("*").eq("bib_number", my_bib).execute()
        logs = pd.DataFrame(res.data)
        if not logs.empty:
            checked = logs['checkpoint_name'].tolist()
            st.progress(len(checked)/len(CHECKPOINT_LIST))
            for cp in CHECKPOINT_LIST: st.write(f"{'✅' if cp in checked else '⚪'} {cp}")
            if "Finish" in checked:
                finish_t = parse_iso_to_thai(logs[logs['checkpoint_name']=="Finish"].iloc[0]['scanned_at'])
                start_fixed = finish_t.replace(hour=7, minute=30, second=0, microsecond=0)
                dur = finish_t - start_fixed
                st.success(f"🎉 วิ่งครบแล้ว! เวลาที่ใช้: {str(dur).split('.')[0]}")
                st.image(f"https://api.qrserver.com/v1/create-qr-code/?size=150x150&data=REWARD_{my_bib}")
    st.button("🏠 กลับหน้าหลัก", on_click=change_page, args=("HOME",), use_container_width=True)