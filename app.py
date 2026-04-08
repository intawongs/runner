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

# --- 0. GLOBAL CONFIG & COORDINATES ---
# ** สำคัญ: กรุณาเปลี่ยนพิกัด Lat, Lon เป็นค่าจริงของแต่ละจุดหน้างาน **
CP_COORDINATES = {
    "Start": {"lat": 13.3849, "lon": 100.1914},
    "Checkpoint 1": {"lat": 13.3849, "lon": 100.1914},
    "Checkpoint 2": {"lat": 13.5970, "lon": 100.6070},
    "Checkpoint 3": {"lat": 13.5980, "lon": 100.6080},
    "Checkpoint 4": {"lat": 13.5990, "lon": 100.6090},
    "Checkpoint 5": {"lat": 13.6000, "lon": 100.6100},
    "Finish": {"lat": 13.6010, "lon": 100.6110}
}
CHECKPOINT_LIST = list(CP_COORDINATES.keys())
tz = pytz.timezone('Asia/Bangkok')
START_TIME_RUN = dt_time(7, 30) # เวลาเริ่มงาน 07:30 น.

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
if "page" not in st.session_state: st.session_state.page = "HOME"
if "my_bib" not in st.session_state: st.session_state.my_bib = ""
if "reg_step" not in st.session_state: st.session_state.reg_step = "FORM"

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

def get_thai_now():
    return datetime.now(tz)

def parse_iso_to_thai(iso_str):
    try:
        dt = datetime.fromisoformat(iso_str.replace('Z', '+00:00'))
        return dt.astimezone(tz)
    except: return get_thai_now()

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
    st.write("")
    st.button("🎁 สรุปผล & รับรางวัล", on_click=change_page, args=("REWARD",), use_container_width=True)
    
    if st.session_state.my_bib:
        st.success(f"ล็อกอิน BIB: {st.session_state.my_bib}")

# --- [ หน้า REGISTER ] ---
elif st.session_state.page == "REGISTER":
    st.header("📝 ลงทะเบียน")
    if st.session_state.reg_step == "FORM":
        next_bib = get_next_bib()
        with st.form("reg_form"):
            st.info(f"BIB ที่คุณจะได้รับ: **{next_bib}**")
            name = st.text_input("ชื่อ-นามสกุล")
            dept = st.selectbox("แผนก", ["Production", "R&D", "QA", "Logistics", "Office", "Maintenance"])
            if st.form_submit_button("📸 ถัดไป: ถ่ายรูปโปรไฟล์"):
                if name:
                    st.session_state.temp_user = {"bib": next_bib, "name": name, "dept": dept}
                    st.session_state.reg_step = "PHOTO"; st.rerun()
                else: st.warning("กรุณากรอกชื่อ")
        if st.button("🏠 กลับหน้าหลัก", use_container_width=True): change_page("HOME")

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
                st.session_state.reg_step = "DONE"; st.rerun()

    elif st.session_state.reg_step == "DONE":
        st.success(f"🎉 ลงทะเบียนสำเร็จ! BIB: {st.session_state.my_bib}")
        if st.button("🏁 เริ่มวิ่ง", use_container_width=True, type="primary"):
            st.session_state.reg_step = "FORM"; change_page("SCAN")
        if st.button("🏠 กลับหน้าหลัก", use_container_width=True):
            st.session_state.reg_step = "FORM"; change_page("HOME")

# --- [ หน้า SCAN ] ---
elif st.session_state.page == "SCAN":
    st.header("🏁 สแกนเช็คอิน")
    my_bib = st.text_input("เลข BIB ของคุณ", value=st.session_state.my_bib).upper()
    if my_bib:
        st.session_state.my_bib = my_bib
        st.info("🛰️ ตรวจสอบพิกัด GPS...")
        loc = get_geolocation()
        if loc:
            curr_lat, curr_lon = loc['coords']['latitude'], loc['coords']['longitude']
            nearest_cp = None; min_dist = 9999
            for cp, pos in CP_COORDINATES.items():
                d = haversine(curr_lat, curr_lon, pos['lat'], pos['lon'])
                if d < min_dist: min_dist = d; nearest_cp = cp
            
            if min_dist <= 100:
                st.success(f"📍 จุดเช็คอิน: **{nearest_cp}** (ระยะ {min_dist:.1f} ม.)")
                qr_val = qrcode_scanner(key=f"scan_{nearest_cp}")
                if qr_val and qr_val == nearest_cp:
                    try:
                        # --- 🔒 Logic: บังคับลำดับ ---
                        current_idx = CHECKPOINT_LIST.index(qr_val)
                        can_proceed = True
                        if current_idx > 0:
                            prev_cp = CHECKPOINT_LIST[current_idx - 1]
                            check_prev = supabase.table("run_logs").select("id").eq("bib_number", my_bib).eq("checkpoint_name", prev_cp).execute()
                            if len(check_prev.data) == 0:
                                can_proceed = False
                                st.error(f"❌ ห้ามข้ามจุด! กรุณาเช็คอินที่จุด **{prev_cp}** ก่อน")

                        if can_proceed:
                            check_dup = supabase.table("run_logs").select("id").eq("bib_number", my_bib).eq("checkpoint_name", qr_val).execute()
                            if len(check_dup.data) > 0:
                                st.warning(f"คุณเช็คอินจุด {qr_val} ไปแล้ว")
                            else:
                                supabase.table("run_logs").insert({"bib_number": my_bib, "checkpoint_name": qr_val}).execute()
                                st.success(f"🎉 บันทึกสำเร็จ! ผ่านจุด {qr_val}"); st.balloons()
                    except Exception as e: st.error(f"Error: {e}")
            else: st.error("❌ คุณยังไม่อยู่ในจุดเช็คอิน (รัศมี 100 เมตร)")
        else: st.warning("⚠️ โปรดเปิด GPS และอนุญาตให้เข้าถึงตำแหน่ง")
    if st.button("🏠 กลับหน้าหลัก", use_container_width=True): change_page("HOME")

# --- [ หน้า REWARD ] ---
elif st.session_state.page == "REWARD":
    st.header("🎁 สรุปผล & รับรางวัล")
    my_bib = st.text_input("เลข BIB ของคุณ", value=st.session_state.my_bib).upper()
    if my_bib:
        res = supabase.table("run_logs").select("*").eq("bib_number", my_bib).execute()
        logs = pd.DataFrame(res.data)
        if not logs.empty:
            checked_points = logs['checkpoint_name'].tolist()
            st.subheader("📍 สถานะการเช็คอิน")
            st.progress(len(checked_points) / len(CHECKPOINT_LIST))
            
            for cp in CHECKPOINT_LIST:
                status = "✅" if cp in checked_points else "⚪"
                st.write(f"{status} {cp}")
            
            if "Finish" in checked_points:
                finish_row = logs[logs['checkpoint_name'] == "Finish"].iloc[0]
                finish_time = parse_iso_to_thai(finish_row['scanned_at'])
                start_dt = finish_time.replace(hour=START_TIME_RUN.hour, minute=START_TIME_RUN.minute, second=0, microsecond=0)
                
                duration = finish_time - start_dt
                hours, remainder = divmod(duration.seconds, 3600)
                minutes, seconds = divmod(remainder, 60)
                
                st.divider()
                st.success("🎉 ยินดีด้วย! คุณวิ่งครบทุกจุดแล้ว")
                st.metric("เวลาที่ใช้ (เริ่ม 07:30 น.)", f"{hours:02d}:{minutes:02d}:{seconds:02d}")
                st.info("💡 แสดงหน้านี้ให้กรรมการเพื่อรับของรางวัล")
                if st.button("🎫 แสดงรหัสรางวัล"):
                    st.image(f"https://api.qrserver.com/v1/create-qr-code/?size=150x150&data=REWARD_{my_bib}")
            else:
                st.warning(f"ยังขาดอีก {len(CHECKPOINT_LIST) - len(checked_points)} จุด")
        else: st.info("ยังไม่มีข้อมูลการวิ่ง")
    if st.button("🏠 กลับหน้าหลัก", use_container_width=True): change_page("HOME")

# --- [ หน้า LEADERBOARD ] ---
elif st.session_state.page == "LEADERBOARD":
    st.header("🏆 Leaderboard (Real-time)")
    st_autorefresh(interval=5000, key="refresh")
    if st.button("🏠 กลับหน้าหลัก", use_container_width=True): change_page("HOME")
    
    res = supabase.table("run_logs").select("*, runners(*)").order("scanned_at", desc=True).execute()
    if res.data:
        df = pd.DataFrame(res.data)
        latest = df.sort_values("scanned_at", ascending=False).groupby("bib_number").first().reset_index()
        cols = st.columns(len(CHECKPOINT_LIST))
        for idx, cp in enumerate(CHECKPOINT_LIST):
            with cols[idx]:
                st.markdown(f"**📍 {cp}**")
                st.divider()
                runners = latest[latest['checkpoint_name'] == cp]
                for _, r in runners.iterrows():
                    if r['runners'] and r['runners']['profile_url']: st.image(r['runners']['profile_url'], width=70)
                    st.write(f"🏃 {r['runners']['name']}")
                    st.caption(f"⏱️ {parse_iso_to_thai(r['scanned_at']).strftime('%H:%M:%S')}")
                    st.divider()