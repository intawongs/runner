import streamlit as st
import pandas as pd
from supabase import create_client, Client
from streamlit_qrcode_scanner import qrcode_scanner
from streamlit_js_eval import get_geolocation
from streamlit_autorefresh import st_autorefresh
import time
from datetime import datetime
import pytz
import math

# --- 0. GLOBAL CONFIG & COORDINATES ---
# พิกัดจริงของแต่ละจุด (เพื่อเช็คว่าพนักงานอยู่ใกล้จุดจริงไหมก่อนให้สแกน)
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
st.set_page_config(page_title="RCI Hybrid Tracker 2026", layout="wide")

def init_connection():
    try:
        return create_client(st.secrets["SUPABASE_URL"], st.secrets["SUPABASE_KEY"])
    except:
        st.error("❌ เชื่อมต่อ Database ไม่สำเร็จ")
        st.stop()

supabase = init_connection()

# --- 2. HELPER FUNCTIONS ---
def haversine(lat1, lon1, lat2, lon2):
    R = 6371000 
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi, dlambda = math.radians(lat2-lat1), math.radians(lon2-lon1)
    a = math.sin(dphi/2)**2 + math.cos(phi1)*math.cos(phi2)*math.sin(dlambda/2)**2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))

def format_thai_time(utc_time_str):
    try:
        utc_dt = datetime.fromisoformat(utc_time_str.replace('Z', '+00:00'))
        return utc_dt.astimezone(tz).strftime("%H:%M:%S")
    except: return utc_time_str

def upload_photo(file_bytes, filename):
    try:
        path = f"profile_{filename}.jpg"
        supabase.storage.from_("runner_photos").upload(path, file_bytes, {"content-type": "image/jpeg"})
        return supabase.storage.from_("runner_photos").get_public_url(path)
    except: return None

# --- 3. SIDEBAR MENU ---
st.sidebar.title("🏃 RCI Hybrid Tracker")
menu = st.sidebar.radio("เมนูหลัก", ["📝 ลงทะเบียน", "🏁 สแกนเช็คอิน", "🏆 Leaderboard"])

# --- [ หน้า 1: ลงทะเบียนพนักงาน ] ---
if menu == "📝 ลงทะเบียน":
    st.header("📝 ลงทะเบียนนักวิ่ง (พนักงานทำเอง)")
    if "reg_step" not in st.session_state: st.session_state.reg_step = "FORM"

    if st.session_state.reg_step == "FORM":
        with st.form("reg_form"):
            name = st.text_input("ชื่อ-นามสกุล")
            bib = st.text_input("กำหนดเลข BIB (เช่น RCI-001)").upper()
            if st.form_submit_button("ถัดไป: ถ่ายรูปโปรไฟล์"):
                if name and bib:
                    st.session_state.temp_user = {"bib": bib, "name": name}
                    st.session_state.reg_step = "PHOTO"; st.rerun()
                else: st.warning("กรุณากรอกข้อมูลให้ครบ")

    elif st.session_state.reg_step == "PHOTO":
        st.subheader("📸 ถ่ายรูปโปรไฟล์ของคุณ")
        img = st.camera_input("กดถ่ายรูปหน้าตรง")
        if img:
            with st.spinner("กำลังบันทึกข้อมูล..."):
                p_url = upload_photo(img.getvalue(), st.session_state.temp_user['bib'])
                supabase.table("runners").insert({
                    "bib_number": st.session_state.temp_user['bib'], 
                    "name": st.session_state.temp_user['name'],
                    "profile_url": p_url
                }).execute()
                st.session_state.my_bib = st.session_state.temp_user['bib']
                st.session_state.reg_step = "DONE"; st.rerun()

    elif st.session_state.reg_step == "DONE":
        st.success(f"✅ ลงทะเบียนสำเร็จ! BIB ของคุณคือ: {st.session_state.my_bib}")
        if st.button("ไปหน้าเช็คอิน"):
            st.session_state.reg_step = "FORM"
            # ย้ายหน้าไปเมนูสแกน
            st.info("กรุณาเลือกเมนู '🏁 สแกนเช็คอิน' ที่แถบด้านซ้าย")

# --- [ หน้า 2: Hybrid Check-in (GPS + QR) ] ---
elif menu == "🏁 สแกนเช็คอิน":
    st.header("🏁 สแกน QR Code ประจำจุด")
    
    # ดึง BIB จาก session หรือให้กรอก
    my_bib = st.text_input("เลข BIB ของคุณ", value=st.session_state.get('my_bib', "")).upper()
    
    if my_bib:
        st.session_state.my_bib = my_bib
        st.info("🛰️ ตรวจสอบพิกัด GPS เพื่อเปิดใช้งานกล้อง...")
        loc = get_geolocation()
        
        if loc:
            curr_lat, curr_lon = loc['coords']['latitude'], loc['coords']['longitude']
            
            # ตรวจสอบว่าใกล้จุดไหนที่สุด
            nearest_cp = None
            min_dist = 9999
            for cp, pos in CP_COORDINATES.items():
                d = haversine(curr_lat, curr_lon, pos['lat'], pos['lon'])
                if d < min_dist:
                    min_dist = d
                    nearest_cp = cp
            
            # เงื่อนไข: ต้องอยู่ใกล้จุดใดจุดหนึ่งไม่เกิน 100 เมตร ถึงจะเปิดกล้องสแกนได้
            if min_dist <= 100:
                st.success(f"📍 คุณอยู่ใกล้จุด: **{nearest_cp}** (ระยะ {min_dist:.1f} ม.)")
                st.markdown("### 📷 สแกน QR Code ที่แปะไว้ที่จุดนี้")
                
                # เปิดกล้องสแกน QR
                qr_val = qrcode_scanner(key="hybrid_scanner")
                
                if qr_val:
                    # ตรวจสอบว่า QR ที่สแกน ตรงกับชื่อจุดหรือไม่ (กันคนเอา QR จุดอื่นมาสแกน)
                    if qr_val == nearest_cp:
                        # บันทึกลง Database
                        try:
                            # เช็คซ้ำ
                            check = supabase.table("run_logs").select("id").eq("bib_number", my_bib).eq("checkpoint_name", qr_val).execute()
                            if len(check.data) > 0:
                                st.warning(f"คุณเช็คอินที่ {qr_val} เรียบร้อยแล้ว")
                            else:
                                supabase.table("run_logs").insert({"bib_number": my_bib, "checkpoint_name": qr_val}).execute()
                                st.success(f"🎉 เช็คอินสำเร็จ! จุด: {qr_val}")
                                st.balloons()
                        except: st.error("ไม่พบข้อมูลนักวิ่ง")
                    else:
                        st.error(f"❌ QR Code ไม่ถูกต้อง! นี่คือจุด {nearest_cp}")
            else:
                st.error("❌ คุณยังไม่อยู่ในรัศมีจุดเช็คอินใดๆ (ต้องเข้าใกล้ป้ายมากกว่านี้)")
        else:
            st.warning("⚠️ กรุณาเปิด GPS และอนุญาตให้ Browser เข้าถึงตำแหน่ง")

# --- [ หน้า 3: Leaderboard ] ---
elif menu == "🏆 Leaderboard":
    st.header("🏆 อันดับนักวิ่ง Real-time")
    st_autorefresh(interval=5000, key="lb_refresh")

    res = supabase.table("run_logs").select("*, runners(name, profile_url)").order("scanned_at", desc=True).execute()
    
    if res.data:
        df = pd.DataFrame(res.data)
        latest = df.sort_values("scanned_at", ascending=False).groupby("bib_number").first().reset_index()
        
        cols = st.columns(len(CHECKPOINT_LIST))
        for idx, cp_name in enumerate(CHECKPOINT_LIST):
            with cols[idx]:
                st.markdown(f"##### 📍 {cp_name}")
                st.divider()
                runners_here = latest[latest['checkpoint_name'] == cp_name]
                for _, r in runners_here.iterrows():
                    if r['runners'] and r['runners']['profile_url']:
                        st.image(r['runners']['profile_url'], width=70)
                    st.write(f"🏃 **{r['runners']['name'] if r['runners'] else 'Unknown'}**")
                    st.caption(f"⏱️ {format_thai_time(r['scanned_at'])}")
                    st.divider()