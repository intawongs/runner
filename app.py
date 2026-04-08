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

# --- 0. CONFIG ---
# แก้ไขพิกัดให้เป็นจุดจริงหน้างาน
CP_COORDINATES = {
    "Start": {"lat": 13.6468, "lon": 100.3205},
    "Checkpoint 1": {"lat": 13.6468, "lon": 100.3205},
    "Checkpoint 2": {"lat": 13.6468, "lon": 100.3205},
    "Checkpoint 3": {"lat": 13.6468, "lon": 100.3205},
    "Checkpoint 4": {"lat": 13.6468, "lon": 100.3205},
    "Checkpoint 5": {"lat": 13.6468, "lon": 100.3205},
    "Finish": {"lat": 13.6468, "lon": 100.3205}
}
CHECKPOINT_LIST = list(CP_COORDINATES.keys())
tz = pytz.timezone('Asia/Bangkok')
START_TIME_RUN = dt_time(7, 30)

st.set_page_config(page_title="RCI AI Tracker", layout="wide", initial_sidebar_state="collapsed")

# --- 1. CONNECTION ---
def init_connection():
    return create_client(st.secrets["SUPABASE_URL"], st.secrets["SUPABASE_KEY"])

supabase = init_connection()

# --- 2. HELPERS ---
def clean_bib(text):
    c = text.replace("-", "").replace(" ", "").upper()
    if c.startswith("RCI") and len(c) > 3:
        return f"RCI-{c[3:]}"
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

def upload_photo(file_bytes, bib_number):
    try:
        path = f"profile_{bib_number}.jpg"
        bucket = "runner_photos" # ต้องตรงกับใน Supabase
        
        # ลบไฟล์เก่าออกก่อนถ้ามี (ป้องกันปัญหาทับไฟล์แล้ว URL เดิมไม่เปลี่ยน)
        try: supabase.storage.from_(bucket).remove([path])
        except: pass
        
        supabase.storage.from_(bucket).upload(path, file_bytes, {"content-type": "image/jpeg"})
        
        # สร้าง URL แบบ Public ตรงๆ
        proj_url = st.secrets["SUPABASE_URL"]
        return f"{proj_url}/storage/v1/object/public/{bucket}/{path}"
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

def change_page(t):
    st.session_state.page = t; st.rerun()

# --- 4. MAIN UI ---
if st.session_state.page == "HOME":
    st.title("🏃 RCI AI Tracker 2026")
    st.write("---")
    st.button("📝 ลงทะเบียนนักวิ่งใหม่", on_click=change_page, args=("REGISTER",), use_container_width=True, type="primary")
    st.button("🏁 สแกนเช็คอินประจำจุด", on_click=change_page, args=("SCAN",), use_container_width=True)
    st.button("🏆 ดูอันดับ Leaderboard", on_click=change_page, args=("LEADERBOARD",), use_container_width=True)
    st.button("🎁 สรุปผล & รับรางวัล", on_click=change_page, args=("REWARD",), use_container_width=True)
    if st.session_state.my_bib: st.success(f"ล็อกอิน BIB: {st.session_state.my_bib}")

elif st.session_state.page == "REGISTER":
    st.header("📝 ลงทะเบียน")
    if st.session_state.reg_step == "FORM":
        next_bib = get_next_bib()
        with st.form("reg"):
            st.info(f"BIB ที่จะได้รับ: {next_bib}")
            n = st.text_input("ชื่อ-นามสกุล")
            d = st.selectbox("แผนก", ["Production", "R&D", "QA", "Logistics", "Office", "Maintenance"])
            if st.form_submit_button("📸 ถัดไป: ถ่ายรูป"):
                if n: 
                    st.session_state.temp = {"bib": next_bib, "name": n, "dept": d}
                    st.session_state.reg_step = "PHOTO"; st.rerun()
                else: st.warning("กรุณาใส่ชื่อ")
    elif st.session_state.reg_step == "PHOTO":
        img = st.camera_input("ถ่ายรูปหน้าตรง")
        if img:
            with st.spinner("กำลังบันทึก..."):
                url = upload_photo(img.getvalue(), st.session_state.temp['bib'])
                supabase.table("runners").insert({"bib_number": st.session_state.temp['bib'], "name": st.session_state.temp['name'], "department": st.session_state.temp['dept'], "profile_url": url}).execute()
                st.session_state.my_bib = st.session_state.temp['bib']
                st.session_state.reg_step = "DONE"; st.rerun()
    elif st.session_state.reg_step == "DONE":
        st.success(f"สำเร็จ! BIB: {st.session_state.my_bib}")
        st.button("🏠 กลับหน้าหลัก", on_click=change_page, args=("HOME",), use_container_width=True)

elif st.session_state.page == "SCAN":
    st.header("🏁 สแกนเช็คอิน")
    bib_in = st.text_input("ยืนยัน BIB", value=st.session_state.my_bib).upper()
    if bib_in:
        st.session_state.my_bib = clean_bib(bib_in)
        loc = get_geolocation()
        if loc:
            lat, lon = loc['coords']['latitude'], loc['coords']['longitude']
            st.write(f"📡 พิกัด: `{lat:.6f}, {lon:.6f}`")
            near = None; min_d = 9999
            for cp, pos in CP_COORDINATES.items():
                d = haversine(lat, lon, pos['lat'], pos['lon'])
                if d < min_d: min_d = d; near = cp
            
            if min_d <= 100:
                st.success(f"📍 คุณอยู่ที่: **{near}**")
                qr = qrcode_scanner(key=f"sc_{near}")
                if qr == near:
                    idx = CHECKPOINT_LIST.index(qr)
                    can = True
                    if idx > 0:
                        prev = CHECKPOINT_LIST[idx-1]
                        c = supabase.table("run_logs").select("id").eq("bib_number", st.session_state.my_bib).eq("checkpoint_name", prev).execute()
                        if not c.data: can = False; st.error(f"❌ ต้องเช็คอินจุด {prev} ก่อน")
                    if can:
                        dup = supabase.table("run_logs").select("id").eq("bib_number", st.session_state.my_bib).eq("checkpoint_name", qr).execute()
                        if dup.data: st.warning("เช็คอินไปแล้ว")
                        else:
                            supabase.table("run_logs").insert({"bib_number": st.session_state.my_bib, "checkpoint_name": qr}).execute()
                            st.success(f"🎉 บันทึกจุด {qr} สำเร็จ!"); st.balloons()
            else: st.error(f"❌ ยังไม่อยู่ในระยะ (ห่างจาก {near} {min_d:.1f} ม.)")
    st.button("🏠 กลับหน้าหลัก", on_click=change_page, args=("HOME",), use_container_width=True)

# --- [ หน้า LEADERBOARD: ฉบับปรับปรุงแนวตั้ง (Vertical List) ] ---
elif st.session_state.page == "LEADERBOARD":
    st.header("🏆 อันดับนักวิ่งประจำจุด (Real-time)")
    st_autorefresh(interval=5000, key="lb_refresh")
    
    if st.button("🏠 กลับหน้าหลัก", use_container_width=True):
        change_page("HOME")
    
    # ดึงข้อมูลพร้อม Join กับตาราง runners
    res = supabase.table("run_logs").select("*, runners(*)").order("scanned_at", desc=True).execute()
    
    if res.data:
        df = pd.DataFrame(res.data)
        # หาตำแหน่งล่าสุดของแต่ละ BIB
        latest = df.sort_values("scanned_at", ascending=False).groupby("bib_number").first().reset_index()
        
        # วนลูปแสดงทีละจุดเช็คอิน (เรียงจาก Finish ถอยกลับมา Start เพื่อให้คนชนะอยู่บนสุด)
        for cp in reversed(CHECKPOINT_LIST):
            runners_at_cp = latest[latest['checkpoint_name'] == cp]
            
            # แสดงหัวข้อจุดเช็คอินถ้ามีคนอยู่
            if not runners_at_cp.empty:
                st.subheader(f"📍 {cp} ({len(runners_at_cp)} คน)")
                
                for _, r in runners_at_cp.iterrows():
                    # สร้างกล่องสำหรับนักวิ่งแต่ละคน (ใช้ columns ภายในเพื่อให้รูปอยู่ซ้าย ข้อความอยู่ขวา)
                    with st.container():
                        c1, c2 = st.columns([1, 4]) # อัตราส่วนรูป 1 ส่วน : ข้อความ 4 ส่วน
                        
                        with c1:
                            img_url = r['runners']['profile_url'] if r['runners'] and r['runners']['profile_url'] else None
                            if img_url:
                                st.image(img_url, width=80)
                            else:
                                st.write("👤") # ไอคอนแทนถ้าไม่มีรูป
                        
                        with c2:
                            name = r['runners']['name'] if r['runners'] else r['bib_number']
                            dept = r['runners']['department'] if r['runners'] else "ทั่วไป"
                            scan_time = parse_iso_to_thai(r['scanned_at']).strftime('%H:%M:%S')
                            
                            st.markdown(f"**{name}** ({r['bib_number']})")
                            st.caption(f"🏢 แผนก: {dept} | ⏱️ เวลา: {scan_time}")
                        
                        st.divider() # เส้นคั่นระหว่างคน
    else:
        st.info("ยังไม่มีข้อมูลการวิ่งในขณะนี้")

elif st.session_state.page == "REWARD":
    st.header("🎁 รับรางวัล")
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
                start_dt = finish_t.replace(hour=7, minute=30, second=0)
                dur = finish_t - start_dt
                h, r = divmod(dur.seconds, 3600); m, s = divmod(r, 60)
                st.success("🎉 ครบแล้ว!"); st.metric("เวลาที่ใช้ (เริ่ม 07:30)", f"{h:02d}:{m:02d}:{s:02d}")
                st.image(f"https://api.qrserver.com/v1/create-qr-code/?size=150x150&data=REWARD_{my_bib}")
    st.button("🏠 กลับหน้าหลัก", on_click=change_page, args=("HOME",), use_container_width=True)