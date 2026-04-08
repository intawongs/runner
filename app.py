import streamlit as st
import pandas as pd
from supabase import create_client, Client
from streamlit_qrcode_scanner import qrcode_scanner
from streamlit_js_eval import get_geolocation
from streamlit_autorefresh import st_autorefresh
import math
import pytz
from datetime import datetime
import time

# --- 0. CONFIG & STYLES ---
CP_COORDINATES = {
    "Start": {"lat": 13.6470, "lon": 100.3206},
    "Checkpoint 1": {"lat": 13.3859, "lon": 100.1904},
    "Checkpoint 2": {"lat": 13.3901, "lon": 100.1913},
    "Checkpoint 3": {"lat": 13.3901, "lon": 100.1917},
    "Finish": {"lat": 13.3849, "lon": 100.1914}
}
CP_COORDINATES = {
    "Start": {"lat": 13.6470, "lon": 100.3206},
    "Checkpoint 1": {"lat": 13.6470, "lon": 100.3206},
    "Checkpoint 2": {"lat": 13.6470, "lon": 100.3206},
    "Checkpoint 3": {"lat": 13.6470, "lon": 100.3206},
    "Finish": {"lat": 13.6470, "lon": 100.3206},
}
CHECKPOINT_LIST = list(CP_COORDINATES.keys())
tz = pytz.timezone('Asia/Bangkok')

st.set_page_config(page_title="RCI RACING 2026", layout="wide", initial_sidebar_state="collapsed")

# CSS สำหรับตกแต่ง UI
st.markdown("""
    <style>
    .main { background-color: #f5f7f9; }
    .stButton>button { border-radius: 8px; font-weight: bold; }
    @keyframes bounce { from {transform:translateY(0);} to {transform:translateY(-10px);} }
    .runner-card { text-align:center; margin-bottom:15px; animation: bounce 0.8s infinite alternate; }
    .cp-header { background:#2E86C1; color:white; border-radius:10px; text-align:center; padding:10px; font-size:12px; font-weight:bold; min-height:50px; display:flex; align-items:center; justify-content:center; }
    </style>
""", unsafe_allow_html=True)

# --- 1. CONNECTION ---
def init_connection():
    try:
        return create_client(st.secrets["SUPABASE_URL"], st.secrets["SUPABASE_KEY"])
    except:
        st.error("❌ เชื่อมต่อ Database ล้มเหลว"); st.stop()

supabase = init_connection()

# --- 2. AUTH & STATE MANAGEMENT ---
if "my_bib" not in st.session_state:
    # ดึง BIB จาก URL (Query Params) เพื่อ Auto-Login
    st.session_state.my_bib = st.query_params.get("bib", "")

if "page" not in st.session_state:
    st.session_state.page = "HOME"

def login_user(bib):
    st.session_state.my_bib = bib
    st.query_params["bib"] = bib  # ฝัง BIB ลงใน URL
    st.rerun()

def logout_user():
    st.session_state.my_bib = ""
    st.query_params.clear()
    st.session_state.page = "HOME"
    st.rerun()

def change_page(t):
    st.session_state.page = t; st.rerun()

# --- 3. HELPERS ---
def clean_bib(text):
    c = text.replace("-", "").replace(" ", "").upper()
    if c.startswith("RCI") and len(c) > 3: return f"RCI-{c[3:]}"
    return c

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

# --- 4. NAVIGATION LOGIC ---

# --- PAGE: HOME ---
if st.session_state.page == "HOME":
    st.markdown("<h1 style='text-align: center;'>🏃‍♂️ RCI AI RACING 2026</h1>", unsafe_allow_html=True)
    
    if not st.session_state.my_bib:
        st.info("กรุณาลงทะเบียนหรือเข้าสู่ระบบเพื่อเริ่มวิ่ง")
        col1, col2 = st.columns(2)
        with col1:
            if st.button("📝 ลงทะเบียนใหม่", use_container_width=True, type="primary"):
                change_page("REGISTER")
        with col2:
            existing_bib = st.text_input("มี BIB แล้ว? (เช่น RCI-001)").upper()
            if st.button("เข้าสู่ระบบ", use_container_width=True):
                if existing_bib:
                    res = supabase.table("runners").select("bib_number").eq("bib_number", clean_bib(existing_bib)).execute()
                    if res.data:
                        login_user(clean_bib(existing_bib))
                    else: st.error("ไม่พบหมายเลข BIB นี้")
    else:
        st.success(f"BIB ปัจจุบัน: **{st.session_state.my_bib}**")
        st.button("🏁 สแกนเช็คพอยท์ (GPS)", on_click=change_page, args=("SCAN",), use_container_width=True, type="primary")
        st.button("🏆 กระดานคะแนน (Leaderboard)", on_click=change_page, args=("LEADERBOARD",), use_container_width=True)
        st.button("🎁 รับรางวัล / สรุปผล", on_click=change_page, args=("REWARD",), use_container_width=True)
        st.write("---")
        if st.button("🚪 ออกจากระบบ / เปลี่ยน BIB", use_container_width=True):
            logout_user()

# --- PAGE: REGISTER ---
elif st.session_state.page == "REGISTER":
    st.subheader("📝 ลงทะเบียนนักวิ่ง")
    if "reg_step" not in st.session_state: st.session_state.reg_step = "FORM"

    if st.session_state.reg_step == "FORM":
        with st.form("reg_form"):
            name = st.text_input("ชื่อ-นามสกุล")
            dept = st.selectbox("แผนก", ["Production", "R&D", "QA", "Logistics", "Office", "Maintenance"])
            if st.form_submit_button("ถัดไป: ถ่ายรูป"):
                if name:
                    # Gen Next BIB
                    res = supabase.table("runners").select("bib_number").order("bib_number", desc=True).limit(1).execute()
                    last_num = int(res.data[0]['bib_number'].split("-")[1]) if res.data else 0
                    st.session_state.temp_user = {"bib": f"RCI-{last_num+1:03d}", "name": name, "dept": dept}
                    st.session_state.reg_step = "PHOTO"; st.rerun()
    
    elif st.session_state.reg_step == "PHOTO":
        img = st.camera_input("ถ่ายรูปโปรไฟล์")
        if img:
            with st.spinner("กำลังบันทึกข้อมูล..."):
                url = upload_photo(img.getvalue(), st.session_state.temp_user['bib'])
                supabase.table("runners").insert({
                    "bib_number": st.session_state.temp_user['bib'],
                    "name": st.session_state.temp_user['name'],
                    "department": st.session_state.temp_user['dept'],
                    "profile_url": url
                }).execute()
                login_user(st.session_state.temp_user['bib'])
                st.session_state.reg_step = "FORM"
                st.success("ลงทะเบียนสำเร็จ!")
                st.button("ไปหน้าหลัก", on_click=change_page, args=("HOME",))

# --- PAGE: SCAN (Smart GPS) ---
# --- PAGE: SCAN (เวอร์ชันบังคับเปิดกล้องทุกจุด) ---
elif st.session_state.page == "SCAN":
    st.subheader(f"📍 บันทึกจุดเช็คพอยท์ (BIB: {st.session_state.my_bib})")
    
    res_logs = supabase.table("run_logs").select("checkpoint_name").eq("bib_number", st.session_state.my_bib).execute()
    already_scanned = [log['checkpoint_name'] for log in res_logs.data] if res_logs.data else []
    
    next_cp = None
    for cp in CHECKPOINT_LIST:
        if cp not in already_scanned:
            next_cp = cp
            break

    if not next_cp:
        st.success("🏁 คุณสแกนครบทุกจุดแล้ว!")
        st.button("🏠 กลับหน้าหลัก", on_click=change_page, args=("HOME",))
    else:
        loc = get_geolocation()
        if loc:
            lat, lon = loc['coords']['latitude'], loc['coords']['longitude']
            target_coords = CP_COORDINATES[next_cp]
            dist = haversine(lat, lon, target_coords['lat'], target_coords['lon'])
            
            if dist <= 100:
                st.info(f"✅ คุณมาถึงจุด **{next_cp}** แล้ว")
                
                # --- จุดสำคัญ: แก้ไขตรงนี้ ---
                # เพิ่ม unique_key โดยรวมชื่อจุด และจำนวนจุดที่เคยสแกน เพื่อให้ Key เปลี่ยนเสมอ
                unique_key = f"scanner_{next_cp}_{len(already_scanned)}"
                
                qr = qrcode_scanner(key=unique_key)
                # -------------------------

                if qr:
                    if qr == next_cp:
                        supabase.table("run_logs").insert({
                            "bib_number": st.session_state.my_bib, 
                            "checkpoint_name": qr
                        }).execute()
                        st.balloons()
                        st.success(f"🎉 บันทึกจุด {qr} เรียบร้อย!")
                        time.sleep(1.5)
                        st.rerun()
                    else:
                        st.error(f"❌ นี่ไม่ใช่ QR ของจุด {next_cp}")
            else:
                st.warning(f"⚠️ จุดถัดไปคือ **{next_cp}** (ห่าง {dist:.0f} ม.)")

    st.button("🏠 กลับหน้าหลัก", on_click=change_page, args=("HOME",), use_container_width=True)

# --- PAGE: LEADERBOARD (5-Lane Fixed) ---
elif st.session_state.page == "LEADERBOARD":
    st.markdown("<h2 style='text-align: center;'>🏎️ RCI RACING LANES</h2>", unsafe_allow_html=True)
    st_autorefresh(interval=5000, key="auto_refresh_race")
    
    lanes = st.columns(len(CHECKPOINT_LIST))
    res = supabase.table("run_logs").select("*, runners(*)").order("scanned_at", desc=True).execute()
    
    latest_positions = pd.DataFrame()
    if res.data:
        df = pd.DataFrame(res.data)
        latest_positions = df.sort_values("scanned_at", ascending=False).groupby("bib_number").first().reset_index()

    for idx, cp in enumerate(CHECKPOINT_LIST):
        with lanes[idx]:
            st.markdown(f"<div class='cp-header'>{cp}</div>", unsafe_allow_html=True)
            st.write("")
            if not latest_positions.empty:
                runners = latest_positions[latest_positions['checkpoint_name'] == cp]
                for _, r in runners.iterrows():
                    pic = r['runners']['profile_url'] if r['runners'] and r['runners']['profile_url'] else ""
                    nick = (r['runners']['name'] if r['runners'] else r['bib_number']).split(" ")[0]
                    st.markdown(f"""
                        <div class='runner-card'>
                            <img src='{pic}' style='width:50px; height:50px; border-radius:50%; border:3px solid gold; object-fit:cover;'>
                            <p style='font-size:10px; margin:0; font-weight:bold;'>{nick}</p>
                        </div>
                    """, unsafe_allow_html=True)
            else:
                st.markdown("<div style='height:100px;'></div>", unsafe_allow_html=True)

    st.button("🏠 กลับหน้าหลัก", on_click=change_page, args=("HOME",), use_container_width=True)

# --- PAGE: REWARD ---
elif st.session_state.page == "REWARD":
    st.subheader("🎁 สรุปผลการวิ่ง")
    res = supabase.table("run_logs").select("*").eq("bib_number", st.session_state.my_bib).execute()
    if res.data:
        logs = pd.DataFrame(res.data)
        checked = logs['checkpoint_name'].tolist()
        st.progress(len(checked)/len(CHECKPOINT_LIST))
        
        cols = st.columns(len(CHECKPOINT_LIST))
        for idx, cp in enumerate(CHECKPOINT_LIST):
            cols[idx].write(f"{'✅' if cp in checked else '⚪'}\n{cp}")
        
        if "Finish" in checked:
            st.success("🎉 ยินดีด้วย! คุณวิ่งครบระยะทางแล้ว")
            st.image(f"https://api.qrserver.com/v1/create-qr-code/?size=200x200&data=REWARD_{st.session_state.my_bib}", caption="แสดง QR นี้เพื่อรับรางวัล")
    else:
        st.warning("ยังไม่พบข้อมูลการวิ่ง")
    
    st.button("🏠 กลับหน้าหลัก", on_click=change_page, args=("HOME",), use_container_width=True)