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

# --- 0. GLOBAL CONFIG & 5 STATIONS (LOOP RUN) ---
# พิกัดตามที่คุณกำหนด (Start และ Finish คือจุดเดียวกัน)
CP_COORDINATES = {
    "Start": {"lat": 13.3849, "lon": 100.1914},
    "Checkpoint 1": {"lat": 13.3859, "lon": 100.1904},
    "Checkpoint 2": {"lat": 13.3901, "lon": 100.1913},
    "Checkpoint 3": {"lat": 13.3901, "lon": 100.1917},
    "Finish": {"lat": 13.3849, "lon": 100.1914}
}
CHECKPOINT_LIST = list(CP_COORDINATES.keys())
tz = pytz.timezone('Asia/Bangkok')
START_TIME_RUN = dt_time(7, 30) # เวลาเริ่มงานส่วนกลาง

# --- 1. CONFIG & CONNECTION ---
st.set_page_config(page_title="RCI AI RACING 2026", layout="wide", initial_sidebar_state="collapsed")

def init_connection():
    try:
        return create_client(st.secrets["SUPABASE_URL"], st.secrets["SUPABASE_KEY"])
    except Exception as e:
        st.error(f"❌ Connection Error: {e}")
        st.stop()

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

# --- [ หน้า HOME ] ---
if st.session_state.page == "HOME":
    st.markdown("<h1 style='text-align: center;'>🏃‍♂️ RCI AI RACING 2026 🏁</h1>", unsafe_allow_html=True)
    st.write("---")
    st.button("📝 ลงทะเบียนนักวิ่งใหม่", on_click=change_page, args=("REGISTER",), use_container_width=True, type="primary")
    st.write("")
    st.button("🏁 สแกนเช็คอิน (Check-in)", on_click=change_page, args=("SCAN",), use_container_width=True)
    st.write("")
    st.button("🏆 กระดานคะแนน (Racing Lanes)", on_click=change_page, args=("LEADERBOARD",), use_container_width=True)
    st.write("")
    st.button("🎁 สรุปผล & รับรางวัล", on_click=change_page, args=("REWARD",), use_container_width=True)
    
    if st.session_state.my_bib:
        st.success(f"ล็อกอิน BIB: {st.session_state.my_bib}")

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
                    st.session_state.reg_step = "PHOTO"; st.rerun()
                else: st.warning("กรุณากรอกชื่อ")
        st.button("🏠 กลับหน้าหลัก", on_click=change_page, args=("HOME",), use_container_width=True)
    
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
        st.button("🏁 ไปหน้าสแกนเช็คอิน", on_click=change_page, args=("SCAN",), use_container_width=True, type="primary")
        st.button("🏠 กลับหน้าหลัก", on_click=change_page, args=("HOME",), use_container_width=True)
        st.session_state.reg_step = "FORM"

# --- [ หน้า SCAN (SMART LOOP LOGIC) ] ---
elif st.session_state.page == "SCAN":
    st.header("🏁 สแกนเช็คอินประจำจุด")
    bib_in = st.text_input("ยืนยัน BIB ของคุณ", value=st.session_state.my_bib).upper()
    
    if bib_in:
        st.session_state.my_bib = clean_bib(bib_in)
        st.info("📡 กำลังตรวจสอบตำแหน่ง GPS...")
        loc = get_geolocation()
        
        if loc:
            curr_lat, curr_lon = loc['coords']['latitude'], loc['coords']['longitude']
            
            near = None; min_d = 9999
            for cp, pos in CP_COORDINATES.items():
                d = haversine(curr_lat, curr_lon, pos['lat'], pos['lon'])
                if d < min_d: min_d = d; near = cp
            
            # --- Smart Logic: กรณี Start/Finish อยู่ที่เดียวกัน ---
            if near in ["Start", "Finish"]:
                # เช็คว่าเคยสแกน Start หรือยัง
                c_start = supabase.table("run_logs").select("id").eq("bib_number", st.session_state.my_bib).eq("checkpoint_name", "Start").execute()
                # เช็คว่าเก็บ CP กลางครบหรือยัง (CP 1, 2, 3)
                c_middle = supabase.table("run_logs").select("checkpoint_name").eq("bib_number", st.session_state.my_bib).in_("checkpoint_name", ["Checkpoint 1", "Checkpoint 2", "Checkpoint 3"]).execute()
                
                if len(c_start.data) > 0 and len(c_middle.data) >= 3:
                    near = "Finish"
                else:
                    near = "Start"

            if min_d <= 100:
                st.success(f"🎯 คุณอยู่ที่จุด: **{near}** (ห่าง {min_d:.1f} ม.)")
                qr_val = qrcode_scanner(key=f"scan_{near}")
                
                if qr_val and qr_val == near:
                    try:
                        current_idx = CHECKPOINT_LIST.index(qr_val)
                        can_proceed = True
                        
                        if current_idx > 0:
                            prev_cp = CHECKPOINT_LIST[current_idx - 1]
                            check_prev = supabase.table("run_logs").select("id").eq("bib_number", st.session_state.my_bib).eq("checkpoint_name", prev_cp).execute()
                            if len(check_prev.data) == 0:
                                can_proceed = False
                                st.error(f"❌ ห้ามข้ามจุด! กรุณาสแกนจุด **{prev_cp}** ก่อน")
                        
                        if can_proceed:
                            check_dup = supabase.table("run_logs").select("id").eq("bib_number", st.session_state.my_bib).eq("checkpoint_name", qr_val).execute()
                            if check_dup.data:
                                st.warning(f"จุด {qr_val} เช็คอินไปแล้วจ้า")
                            else:
                                supabase.table("run_logs").insert({"bib_number": st.session_state.my_bib, "checkpoint_name": qr_val}).execute()
                                st.success(f"🎉 บันทึกจุด {qr_val} สำเร็จ!"); st.balloons()
                    except Exception as e: st.error(f"Error: {e}")
            else:
                st.error(f"❌ ไม่อยู่ในรัศมีจุด {near}")
        else:
            st.warning("⚠️ โปรดเปิด GPS และอนุญาตให้เข้าถึงตำแหน่ง")
    
    st.button("🏠 กลับหน้าหลัก", on_click=change_page, args=("HOME",), use_container_width=True)

# --- [ หน้า LEADERBOARD (5-Lane Racing UI) ] ---
elif st.session_state.page == "LEADERBOARD":
    st.markdown("<h2 style='text-align: center;'>🏎️ RCI RACING LANES</h2>", unsafe_allow_html=True)
    st_autorefresh(interval=5000, key="lb_refresh")
    
    if st.button("🏠 กลับหน้าหลัก", use_container_width=True): change_page("HOME")
    
    res = supabase.table("run_logs").select("*, runners(*)").order("scanned_at", desc=True).execute()
    if res.data:
        df = pd.DataFrame(res.data)
        latest = df.sort_values("scanned_at", ascending=False).groupby("bib_number").first().reset_index()
        
        lanes = st.columns(len(CHECKPOINT_LIST), gap="small")
        for idx, cp in enumerate(CHECKPOINT_LIST):
            with lanes[idx]:
                st.markdown(f"<div style='background:#2E86C1; color:white; border-radius:10px; text-align:center; padding:5px; font-size:12px; font-weight:bold;'>{cp}</div>", unsafe_allow_html=True)
                
                runners_here = latest[latest['checkpoint_name'] == cp]
                img_size = 60 if len(runners_here) <= 3 else 40
                
                for _, r in runners_here.iterrows():
                    img_url = r['runners']['profile_url'] if r['runners'] and r['runners']['profile_url'] else ""
                    name = (r['runners']['name'] if r['runners'] else r['bib_number']).split(" ")[0]
                    
                    st.markdown(f"""
                        <div style='text-align:center; margin-top:10px; animation: bounce 0.8s infinite alternate;'>
                            <img src='{img_url}' style='width:{img_size}px; height:{img_size}px; border-radius:50%; border:2px solid gold; object-fit:cover;'>
                            <p style='font-size:10px; font-weight:bold; margin:0;'>{name}</p>
                        </div>
                        <style>
                            @keyframes bounce {{ 
                                from {{ transform: translateY(0px); }} 
                                to {{ transform: translateY(-8px); }} 
                            }}
                        </style>
                    """, unsafe_allow_html=True)
    else:
        st.info("รอสัญญาณปล่อยตัว... ยังไม่มีนักวิ่งในระบบ")

# --- [ หน้า REWARD ] ---
elif st.session_state.page == "REWARD":
    st.header("🎁 สรุปผล & รับรางวัล")
    bib_in = st.text_input("ระบุเลข BIB ของคุณ", value=st.session_state.my_bib).upper()
    
    if bib_in:
        my_bib = clean_bib(bib_in)
        res = supabase.table("run_logs").select("*").eq("bib_number", my_bib).execute()
        logs = pd.DataFrame(res.data)
        
        if not logs.empty:
            checked = logs['checkpoint_name'].tolist()
            st.progress(len(checked) / len(CHECKPOINT_LIST))
            
            for cp in CHECKPOINT_LIST:
                st.write(f"{'✅' if cp in checked else '⚪'} {cp}")
            
            if "Finish" in checked:
                finish_t = parse_iso_to_thai(logs[logs['checkpoint_name'] == "Finish"].iloc[0]['scanned_at'])
                # คำนวณเวลาจาก 07:30 น. ของวันปัจจุบัน
                start_fixed = finish_t.replace(hour=7, minute=30, second=0, microsecond=0)
                duration = finish_t - start_fixed
                
                st.divider()
                st.success("🎉 ยินดีด้วย! คุณวิ่งครบทุกจุดแล้ว")
                st.metric("เวลาที่ใช้ (เริ่ม 07:30 น.)", f"{str(duration).split('.')[0]} ชม.")
                
                st.info("💡 แสดงหน้านี้ให้กรรมการเพื่อรับรางวัล")
                st.image(f"https://api.qrserver.com/v1/create-qr-code/?size=150x150&data=REWARD_{my_bib}")
            else:
                st.warning(f"ยังขาดอีก {len(CHECKPOINT_LIST) - len(checked)} จุด สู้ๆ!")
        else:
            st.info("ไม่พบข้อมูลการวิ่งของ BIB นี้")
            
    if st.button("🏠 กลับหน้าหลัก", use_container_width=True): change_page("HOME")