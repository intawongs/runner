import streamlit as st
import pandas as pd
from supabase import create_client, Client
from streamlit_qrcode_scanner import qrcode_scanner
from streamlit_js_eval import get_geolocation
from streamlit_autorefresh import st_autorefresh
import qrcode
from io import BytesIO
import time
from datetime import datetime
import pytz
import math

# --- 0. GLOBAL CONFIG & COORDINATES ---
# ** สำคัญ: เดินไปเก็บพิกัดจริง Lat, Lon มาใส่ตรงนี้เพื่อให้ GPS แม่นยำ **
CP_COORDINATES = {
    "Start": {"lat": 13.5950, "lon": 100.6050},
    "Checkpoint 1": {"lat": 13.5960, "lon": 100.6060},
    "Checkpoint 2": {"lat": 13.5970, "lon": 100.6070},
    "Checkpoint 3": {"lat": 13.5980, "lon": 100.6080},
    "Checkpoint 4": {"lat": 13.5990, "lon": 100.6090},
    "Checkpoint 5": {"lat": 13.6000, "lon": 100.6100},
    "Finish": {"lat": 13.6010, "lon": 100.6110}
}
CHECKPOINT_LIST = list(CP_COORDINATES.keys())
tz = pytz.timezone('Asia/Bangkok')

# --- 1. CONFIG & CONNECTION ---
st.set_page_config(page_title="RCI Runner 2026", layout="wide", initial_sidebar_state="collapsed")

def init_connection():
    try:
        return create_client(st.secrets["SUPABASE_URL"], st.secrets["SUPABASE_KEY"])
    except Exception as e:
        st.error(f"❌ Connection Error: {e}")
        st.stop()

supabase = init_connection()

# --- 2. SESSION STATE MANAGEMENT ---
if "page" not in st.session_state:
    st.session_state.page = "HOME"
if "my_bib" not in st.session_state:
    st.session_state.my_bib = ""
if "reg_step" not in st.session_state:
    st.session_state.reg_step = "FORM"

def change_page(target):
    st.session_state.page = target
    st.rerun()

# --- 3. HELPER FUNCTIONS ---
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

def upload_photo(file_bytes, filename):
    try:
        path = f"profile_{filename}.jpg"
        supabase.storage.from_("runner_photos").upload(path, file_bytes, {"content-type": "image/jpeg"})
        return supabase.storage.from_("runner_photos").get_public_url(path)
    except: return None

def format_thai_time(utc_time_str):
    try:
        utc_dt = datetime.fromisoformat(utc_time_str.replace('Z', '+00:00'))
        return utc_dt.astimezone(tz).strftime("%H:%M:%S")
    except: return utc_time_str[11:19]

# ---------------------------------------------------------
# --- MAIN INTERFACE (UI) ---
# ---------------------------------------------------------

# --- [ หน้า HOME ] ---
if st.session_state.page == "HOME":
    st.title("🏃 RCI AI Tracker 2026")
    st.write("---")
    
    st.button("📝 ลงทะเบียนนักวิ่งใหม่", on_click=change_page, args=("REGISTER",), use_container_width=True, type="primary")
    st.write("")
    st.button("🏁 สแกนเช็คอินประจำจุด", on_click=change_page, args=("SCAN",), use_container_width=True)
    st.write("")
    st.button("🏆 ดูอันดับ Leaderboard", on_click=change_page, args=("LEADERBOARD",), use_container_width=True)
    
    if st.session_state.my_bib:
        st.success(f"ล็อกอินในชื่อ BIB: {st.session_state.my_bib}")

# --- [ หน้า REGISTER ] ---
elif st.session_state.page == "REGISTER":
    st.header("📝 ลงทะเบียนนักวิ่ง")
    
    if st.session_state.reg_step == "FORM":
        next_bib = get_next_bib()
        with st.form("reg_form"):
            st.info(f"BIB ที่คุณจะได้รับ: **{next_bib}**")
            name = st.text_input("ชื่อ-นามสกุล")
            dept = st.selectbox("แผนก", ["Production", "R&D", "QA", "Logistics", "Office", "Maintenance"])
            if st.form_submit_button("📸 ถัดไป: ถ่ายรูปโปรไฟล์"):
                if name:
                    st.session_state.temp_user = {"bib": next_bib, "name": name, "dept": dept}
                    st.session_state.reg_step = "PHOTO"
                    st.rerun()
                else: st.warning("กรุณากรอกชื่อ")
        
        if st.button("🏠 กลับหน้าหลัก", use_container_width=True):
            change_page("HOME")

    elif st.session_state.reg_step == "PHOTO":
        st.subheader(f"📸 ถ่ายรูปโปรไฟล์: {st.session_state.temp_user['name']}")
        img = st.camera_input("กดถ่ายรูปหน้าตรง")
        if img:
            with st.spinner("กำลังบันทึกข้อมูล..."):
                p_url = upload_photo(img.getvalue(), st.session_state.temp_user['bib'])
                supabase.table("runners").insert({
                    "bib_number": st.session_state.temp_user['bib'], 
                    "name": st.session_state.temp_user['name'],
                    "department": st.session_state.temp_user['dept'],
                    "profile_url": p_url
                }).execute()
                st.session_state.my_bib = st.session_state.temp_user['bib']
                st.session_state.reg_step = "DONE"
                st.rerun()

    elif st.session_state.reg_step == "DONE":
        st.success(f"🎉 ลงทะเบียนสำเร็จ! BIB: {st.session_state.my_bib}")
        if st.button("🏁 เริ่มวิ่ง (ไปหน้าเช็คอิน)", use_container_width=True, type="primary"):
            st.session_state.reg_step = "FORM"
            change_page("SCAN")
        if st.button("🏠 กลับหน้าหลัก", use_container_width=True):
            st.session_state.reg_step = "FORM"
            change_page("HOME")

# --- [ หน้า SCAN ] ---
elif st.session_state.page == "SCAN":
    st.header("🏁 สแกนเช็คอิน")
    
    my_bib = st.text_input("เลข BIB ของคุณ", value=st.session_state.my_bib).upper()
    if my_bib:
        st.session_state.my_bib = my_bib
        st.info("🛰️ ตรวจสอบพิกัด GPS เพื่อเปิดใช้งานกล้อง...")
        loc = get_geolocation()
        
        if loc:
            curr_lat, curr_lon = loc['coords']['latitude'], loc['coords']['longitude']
            
            # ตรวจสอบจุดที่ใกล้ที่สุด
            nearest_cp = None
            min_dist = 9999
            for cp, pos in CP_COORDINATES.items():
                d = haversine(curr_lat, curr_lon, pos['lat'], pos['lon'])
                if d < min_dist:
                    min_dist = d
                    nearest_cp = cp
            
            if min_dist <= 100:
                st.success(f"📍 คุณอยู่ใกล้: **{nearest_cp}** (ระยะ {min_dist:.1f} ม.)")
                st.write("---")
                qr_val = qrcode_scanner(key=f"hybrid_scan_{nearest_cp}")
                
                if qr_val:
                    if qr_val == nearest_cp:
                        try:
                            check = supabase.table("run_logs").select("id").eq("bib_number", my_bib).eq("checkpoint_name", qr_val).execute()
                            if len(check.data) > 0:
                                st.warning(f"คุณเช็คอินที่ {qr_val} ไปแล้ว")
                            else:
                                supabase.table("run_logs").insert({"bib_number": my_bib, "checkpoint_name": qr_val}).execute()
                                st.success(f"🎉 บันทึกสำเร็จ! ผ่านจุด {qr_val}")
                                st.balloons()
                        except: st.error("ไม่พบข้อมูล BIB")
                    else:
                        st.error(f"❌ QR ไม่ถูกต้อง! กรุณาสแกน QR ของจุด {nearest_cp}")
            else:
                st.error("❌ คุณยังไม่อยู่ในรัศมีเช็คอิน (เดินไปที่ป้าย Checkpoint)")
        else:
            st.warning("⚠️ โปรดเปิด GPS และอนุญาตให้เข้าถึงตำแหน่ง")

    st.write("---")
    if st.button("🏠 กลับหน้าหลัก", use_container_width=True):
        change_page("HOME")

# --- [ หน้า LEADERBOARD ] ---
elif st.session_state.page == "LEADERBOARD":
    st.header("🏆 Leaderboard (Real-time)")
    st_autorefresh(interval=5000, key="lb_refresh")
    
    if st.button("🏠 กลับหน้าหลัก", use_container_width=True):
        change_page("HOME")
    
    res = supabase.table("run_logs").select("*, runners(name, profile_url, department)").order("scanned_at", desc=True).execute()
    
    if res.data:
        df = pd.DataFrame(res.data)
        latest = df.sort_values("scanned_at", ascending=False).groupby("bib_number").first().reset_index()
        
        cols = st.columns(len(CHECKPOINT_LIST))
        for idx, cp in enumerate(CHECKPOINT_LIST):
            with cols[idx]:
                st.markdown(f"##### 📍 {cp}")
                st.divider()
                runners_here = latest[latest['checkpoint_name'] == cp]
                for _, r in runners_here.iterrows():
                    if r['runners'] and r['runners']['profile_url']:
                        st.image(r['runners']['profile_url'], width=70)
                    st.write(f"🏃 **{r['runners']['name'] if r['runners'] else 'Unknown'}**")
                    st.caption(f"⏱️ {format_thai_time(r['scanned_at'])}")
                    st.divider()
    else:
        st.info("ยังไม่มีข้อมูล")