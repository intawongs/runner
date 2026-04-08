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

# --- 0. CONFIG (5 STATIONS - LOOP) ---
CP_COORDINATES = {
    "Start": {"lat": 13.6470, "lon": 100.3206},
    "Checkpoint 1": {"lat": 13.3859, "lon": 100.1904},
    "Checkpoint 2": {"lat": 13.3901, "lon": 100.1913},
    "Checkpoint 3": {"lat": 13.3901, "lon": 100.1917},
    "Finish": {"lat": 13.3849, "lon": 100.1914}
}
CHECKPOINT_LIST = list(CP_COORDINATES.keys())
tz = pytz.timezone('Asia/Bangkok')

st.set_page_config(page_title="RCI AI RACING 2026", layout="wide", initial_sidebar_state="collapsed")

# --- 1. CONNECTION ---
@st.cache_resource
def init_connection():
    try:
        return create_client(st.secrets["SUPABASE_URL"], st.secrets["SUPABASE_KEY"])
    except Exception as e:
        st.error(f"❌ DB Connection Failed: {e}"); st.stop()

supabase = init_connection()

# --- 2. HELPERS ---
def haversine(lat1, lon1, lat2, lon2):
    R = 6371000 
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi, dlambda = math.radians(lat2-lat1), math.radians(lon2-lon1)
    a = math.sin(dphi/2)**2 + math.cos(phi1)*math.cos(phi2)*math.sin(dlambda/2)**2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))

def upload_photo(file_bytes, bib):
    path = f"profile_{bib}.jpg"
    bucket = "runner_photos"
    try:
        supabase.storage.from_(bucket).remove([path])
    except: pass
    supabase.storage.from_(bucket).upload(path, file_bytes, {"content-type": "image/jpeg"})
    return f"{st.secrets['SUPABASE_URL']}/storage/v1/object/public/{bucket}/{path}"

# --- 3. SESSION STATE ---
if "page" not in st.session_state: st.session_state.page = "HOME"
if "my_bib" not in st.session_state: st.session_state.my_bib = ""
if "reg_step" not in st.session_state: st.session_state.reg_step = "FORM"

def change_page(t):
    st.session_state.page = t; st.rerun()

# ---------------------------------------------------------
# --- MAIN UI ---
# ---------------------------------------------------------

if st.session_state.page == "HOME":
    st.markdown("<h1 style='text-align: center;'>🏃‍♂️ RCI AI RACING 2026 🏁</h1>", unsafe_allow_html=True)
    if not st.session_state.my_bib:
        st.button("📝 ลงทะเบียนใหม่ (Register)", on_click=change_page, args=("REGISTER",), use_container_width=True, type="primary")
        with st.expander("ล็อกอินด้วย BIB เดิม"):
            old_bib = st.text_input("กรอกเลข BIB")
            if st.button("ตกลon"):
                st.session_state.my_bib = old_bib.upper(); st.rerun()
    else:
        st.success(f"📟 ล็อกอิน BIB: **{st.session_state.my_bib}**")
        st.button("🏁 สแกนเช็คอิน (Check-in)", on_click=change_page, args=("SCAN",), use_container_width=True, type="primary")
        st.button("🏆 กระดานคะแนน (Leaderboard)", on_click=change_page, args=("LEADERBOARD",), use_container_width=True)
        st.button("🎁 สรุปผลการวิ่ง", on_click=change_page, args=("REWARD",), use_container_width=True)
        if st.button("Logout"): st.session_state.my_bib = ""; st.rerun()

elif st.session_state.page == "REGISTER":
    st.header("📝 ลงทะเบียน")
    if st.session_state.reg_step == "FORM":
        with st.form("reg_form"):
            n = st.text_input("ชื่อ-นามสกุล")
            d = st.selectbox("แผนก", ["Production", "R&D", "QA", "Logistics", "Office", "Maintenance"])
            if st.form_submit_button("ถัดไป: ถ่ายรูป"):
                if n:
                    res = supabase.table("runners").select("bib_number").order("bib_number", desc=True).limit(1).execute()
                    nb = f"RCI-{(int(res.data[0]['bib_number'].split('-')[1])+1):03d}" if res.data else "RCI-001"
                    st.session_state.temp = {"bib": nb, "name": n, "dept": d}
                    st.session_state.reg_step = "PHOTO"; st.rerun()
    
    elif st.session_state.reg_step == "PHOTO":
        st.info(f"📸 ถ่ายรูปสำหรับ BIB: {st.session_state.temp['bib']}")
        img = st.camera_input("กดถ่ายรูปเพื่อบันทึก")
        if img:
            with st.spinner("💾 กำลังบันทึก..."):
                try:
                    p_url = upload_photo(img.getvalue(), st.session_state.temp['bib'])
                    db_res = supabase.table("runners").insert({
                        "bib_number": st.session_state.temp['bib'],
                        "name": st.session_state.temp['name'],
                        "department": st.session_state.temp['dept'],
                        "profile_url": p_url
                    }).execute()
                    # ตรวจสอบการบันทึกสำเร็จ
                    if db_res.data:
                        st.session_state.my_bib = st.session_state.temp['bib']
                        st.session_state.reg_step = "DONE"; st.rerun()
                    else: st.error("❌ บันทึกลงตารางไม่สำเร็จ (Database Reject)")
                except Exception as e: st.error(f"❌ Error: {e}")

    elif st.session_state.reg_step == "DONE":
        st.success("🎉 ลงทะเบียนสำเร็จ!"); st.button("🏠 กลับหน้าหลัก", on_click=change_page, args=("HOME",))
        st.session_state.reg_step = "FORM"

elif st.session_state.page == "SCAN":
    st.header(f"🏁 เช็คอิน ({st.session_state.my_bib})")
    loc = get_geolocation()
    if loc and 'coords' in loc:
        lat, lon = loc['coords']['latitude'], loc['coords']['longitude']
        st.write(f"📍 พิกัด: `{lat:.6f}, {lon:.6f}`")
        near = None; min_d = 9999
        for cp, pos in CP_COORDINATES.items():
            d = haversine(lat, lon, pos['lat'], pos['lon'])
            if d < min_d: min_d = d; near = cp
        
        hist = supabase.table("run_logs").select("checkpoint_name").eq("bib_number", st.session_state.my_bib).execute()
        done_cps = [r['checkpoint_name'] for r in hist.data]
        if near in ["Start", "Finish"]:
            near = "Start" if ("Start" not in done_cps or not all(x in done_cps for x in ["Checkpoint 1", "Checkpoint 2", "Checkpoint 3"])) else "Finish"

        if min_d <= 150:
            st.success(f"🎯 อยู่ใกล้จุด: **{near}**")
            qr = qrcode_scanner(key=f"sc_{near}_{time.time()}")
            if qr == near:
                if qr not in done_cps:
                    with st.spinner("💾 บันทึกเวลา..."):
                        save = supabase.table("run_logs").insert({"bib_number": st.session_state.my_bib, "checkpoint_name": qr}).execute()
                        if save.data: st.success("✅ สำเร็จ!"); st.balloons(); time.sleep(2); change_page("HOME")
                else: st.warning("เช็คอินไปแล้ว")
        else: st.error(f"❌ อยู่ห่างจุด {near} ({min_d:.1f} ม.)")
    else: st.warning("📡 รอพิกัด GPS..."); st.button("🔄 ดึงใหม่", on_click=st.rerun)
    st.button("🏠 กลับ", on_click=change_page, args=("HOME",))

elif st.session_state.page == "LEADERBOARD":
    st_autorefresh(interval=10000, key="lb_refresh") # รีเฟรช 10 วิ
    st.markdown("<h2 style='text-align: center;'>🏎️ RCI RACING LANES</h2>", unsafe_allow_html=True)
    c1, c2 = st.columns([5, 1])
    with c1: st.button("🏠 กลับหน้าหลัก", on_click=change_page, args=("HOME",), use_container_width=True)
    with c2: 
        if st.button("🔄"): st.rerun()
    
    res = supabase.table("run_logs").select("*, runners(*)").order("scanned_at", desc=True).execute()
    if res.data:
        df = pd.DataFrame(res.data)
        latest = df.sort_values("scanned_at", ascending=False).groupby("bib_number").first().reset_index()
        lanes = st.columns(5)
        for idx, cp in enumerate(CHECKPOINT_LIST):
            with lanes[idx]:
                st.markdown(f"<div style='background:#2E86C1; color:white; border-radius:10px; text-align:center; padding:8px; font-weight:bold; min-height:45px;'>{cp}</div>", unsafe_allow_html=True)
                runners = latest[latest['checkpoint_name'] == cp]
                if not runners.empty:
                    for _, r in runners.iterrows():
                        img = r['runners']['profile_url'] if r['runners'] and r['runners']['profile_url'] else ""
                        name = (r['runners']['name'] if r['runners'] else r['bib_number']).split(" ")[0]
                        st.markdown(f"<div style='text-align:center; margin-top:15px; animation: bounce 0.8s infinite alternate;'><img src='{img}' style='width:45px; height:45px; border-radius:50%; border:2px solid gold; object-fit:cover;'><p style='font-size:10px; font-weight:bold; margin:0;'>{name}</p></div><style>@keyframes bounce {{ from {{transform:translateY(0);}} to {{transform:translateY(-8px);}} }}</style>", unsafe_allow_html=True)
                else: st.markdown("<div style='height:200px;'></div>", unsafe_allow_html=True)

elif st.session_state.page == "REWARD":
    st.header("🎁 สรุปผล")
    res = supabase.table("run_logs").select("*").eq("bib_number", st.session_state.my_bib).execute()
    if res.data:
        done = [r['checkpoint_name'] for r in res.data]
        for cp in CHECKPOINT_LIST: st.write(f"{'✅' if cp in done else '⚪'} {cp}")
    st.button("🏠 กลับหน้าหลัก", on_click=change_page, args=("HOME",))