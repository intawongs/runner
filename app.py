import streamlit as st
import pandas as pd
from supabase import create_client, Client
from streamlit_qrcode_scanner import qrcode_scanner
from streamlit_autorefresh import st_autorefresh
import pytz
from datetime import datetime
import time
import streamlit.components.v1 as components
import os
import base64

# --- 0. CONFIG & STYLES ---
CHECKPOINT_LIST = ["Start", "Checkpoint 1", "Checkpoint 2", "Checkpoint 3", "Finish"]
tz = pytz.timezone('Asia/Bangkok')

st.set_page_config(page_title="RCI RACING 2026", layout="wide", initial_sidebar_state="collapsed")

# Custom CSS
st.markdown("""
    <style>
    .main { background-color: #f5f7f9; }
    .stButton>button { border-radius: 10px; font-weight: bold; height: 3em; }
    .cp-header { background:#2E86C1; color:white; border-radius:10px; text-align:center; padding:10px; font-size:12px; font-weight:bold; min-height:45px; display:flex; align-items:center; justify-content:center; }
    .runner-card { text-align:center; margin-bottom:15px; border: 1px solid #ddd; padding: 5px; border-radius: 10px; background: white; }
    </style>
""", unsafe_allow_html=True)

# --- 1. CONNECTION ---
def init_connection():
    try:
        return create_client(st.secrets["SUPABASE_URL"], st.secrets["SUPABASE_KEY"])
    except Exception as e:
        st.error(f"❌ Connection Error: {e}"); st.stop()

supabase = init_connection()

# --- 2. AUTH & STATE ---
if "my_bib" not in st.session_state:
    st.session_state.my_bib = st.query_params.get("bib", "")

if "page" not in st.session_state:
    st.session_state.page = "HOME"

def login_user(bib):
    st.session_state.my_bib = bib
    st.query_params["bib"] = bib
    st.session_state.page = "HOME"
    st.rerun()

def logout_user():
    st.session_state.my_bib = ""
    st.query_params.clear()
    st.session_state.page = "HOME"
    st.rerun()

def change_page(t):
    st.session_state.page = t
    st.rerun()

# --- 3. HELPERS ---
def clean_bib(text):
    c = text.replace("-", "").replace(" ", "").upper()
    if c.startswith("RCI") and len(c) > 3: return f"RCI-{c[3:]}"
    return c

def get_base64_bin(bin_file):
    with open(bin_file, 'rb') as f:
        return base64.b64encode(f.read()).decode()

def upload_photo(file_bytes, bib):
    path = f"profile_{bib}.jpg"
    bucket = "runner_photos"
    try:
        supabase.storage.from_(bucket).upload(
            path=path, 
            file=file_bytes, 
            file_options={"content-type": "image/jpeg", "upsert": "true"}
        )
        return f"{st.secrets['SUPABASE_URL']}/storage/v1/object/public/{bucket}/{path}"
    except:
        return f"{st.secrets['SUPABASE_URL']}/storage/v1/object/public/{bucket}/{path}"

# --- 4. NAVIGATION CONTROL ---

# --- HOME ---
if st.session_state.page == "HOME":
    st.markdown("<h1 style='text-align: center;'>🏃‍♂️ RCI AI RACING 2026</h1>", unsafe_allow_html=True)
    st.write("---")
    
    if not st.session_state.my_bib:
        col1, col2 = st.columns(2)
        with col1:
            if st.button("📝 ลงทะเบียนใหม่", use_container_width=True, type="primary", key="home_reg_btn"):
                change_page("REGISTER")
        with col2:
            existing_bib = st.text_input("มี BIB แล้ว?", key="home_bib_input").upper()
            if st.button("เข้าสู่ระบบ", use_container_width=True, key="home_login_btn"):
                if existing_bib:
                    res = supabase.table("runners").select("bib_number").eq("bib_number", clean_bib(existing_bib)).execute()
                    if res.data: login_user(clean_bib(existing_bib))
                    else: st.error("ไม่พบหมายเลข BIB")
    else:
        st.success(f"BIB ปัจจุบัน: **{st.session_state.my_bib}**")
        st.button("🏁 สแกนเช็คพอยท์", on_click=change_page, args=("SCAN",), use_container_width=True, type="primary", key="home_scan_btn")
        st.button("🏆 กระดานคะแนน", on_click=change_page, args=("LEADERBOARD",), use_container_width=True, key="home_leader_btn")
        st.button("🎁 รับรางวัล / สรุปผล", on_click=change_page, args=("REWARD",), use_container_width=True, key="home_reward_btn")
        st.write("")
        if st.button("🚪 ออกจากระบบ", use_container_width=True, key="home_logout_btn"):
            logout_user()

# --- REGISTER ---
elif st.session_state.page == "REGISTER":
    st.subheader("📝 ลงทะเบียนนักวิ่ง")
    if "reg_step" not in st.session_state: st.session_state.reg_step = "FORM"

    if st.session_state.reg_step == "FORM":
        with st.form("reg_form_v2"):
            name = st.text_input("ชื่อ-นามสกุล")
            dept = st.selectbox("แผนก", ["Production", "R&D", "QA", "Logistics", "Office", "Maintenance", "Others"])
            if st.form_submit_button("ถัดไป: ถ่ายรูป"):
                if name:
                    res = supabase.table("runners").select("bib_number").order("bib_number", desc=True).limit(1).execute()
                    last_num = int(res.data[0]['bib_number'].split("-")[1]) if res.data else 0
                    st.session_state.temp_user = {"bib": f"RCI-{last_num+1:03d}", "name": name, "dept": dept}
                    st.session_state.reg_step = "PHOTO"; st.rerun()
        if st.button("🏠 กลับหน้าหลัก", use_container_width=True, key="reg_back_btn"): change_page("HOME")

    elif st.session_state.reg_step == "PHOTO":
        img = st.camera_input("ถ่ายรูปโปรไฟล์")
        if img:
            with st.spinner("กำลังบันทึก..."):
                url = upload_photo(img.getvalue(), st.session_state.temp_user['bib'])
                supabase.table("runners").insert({
                    "bib_number": st.session_state.temp_user['bib'],
                    "name": st.session_state.temp_user['name'],
                    "department": st.session_state.temp_user['dept'],
                    "profile_url": url
                }).execute()
                st.session_state.my_bib = st.session_state.temp_user['bib']
                st.query_params["bib"] = st.session_state.my_bib
                st.session_state.reg_step = "FORM" 
                st.success("✅ ลงทะเบียนสำเร็จ!")
                time.sleep(1.5)
                st.session_state.page = "HOME"; st.rerun()
        if st.button("⬅️ กลับ", use_container_width=True, key="reg_photo_back"):
            st.session_state.reg_step = "FORM"; st.rerun()

# --- SCAN ---
elif st.session_state.page == "SCAN":
    st.subheader(f"🏁 สแกนจุด (BIB: {st.session_state.my_bib})")
    res_logs = supabase.table("run_logs").select("checkpoint_name").eq("bib_number", st.session_state.my_bib).execute()
    already = [log['checkpoint_name'] for log in res_logs.data] if res_logs.data else []
    next_cp = next((cp for cp in CHECKPOINT_LIST if cp not in already), None)
            
    if not next_cp:
        st.success("🎉 ครบทุกจุดแล้ว!"); st.button("🏠 กลับหน้าหลัก", key="scan_done_home", on_click=change_page, args=("HOME",))
    else:
        st.info(f"🚩 จุดถัดไป: **{next_cp}**")
        qr = qrcode_scanner(key=f"scanner_{next_cp}_{len(already)}")
        if qr == next_cp:
            supabase.table("run_logs").insert({"bib_number": st.session_state.my_bib, "checkpoint_name": qr}).execute()
            st.balloons(); st.success("บันทึกสำเร็จ!"); time.sleep(1.5); st.rerun()
    st.button("🏠 กลับหน้าหลัก", on_click=change_page, args=("HOME",), use_container_width=True, key="scan_home_btn")

# --- LEADERBOARD ---
elif st.session_state.page == "LEADERBOARD":
    st.markdown("<h2 style='text-align: center;'>🏆 RACING LANES</h2>", unsafe_allow_html=True)
    st_autorefresh(interval=5000, key="lb_refresh")
    lanes = st.columns(len(CHECKPOINT_LIST))
    res = supabase.table("run_logs").select("*, runners(*)").order("scanned_at", desc=True).execute()
    if res.data:
        df = pd.DataFrame(res.data)
        latest = df.sort_values("scanned_at", ascending=False).groupby("bib_number").first().reset_index()
        for idx, cp in enumerate(CHECKPOINT_LIST):
            with lanes[idx]:
                st.markdown(f"<div class='cp-header'>{cp}</div>", unsafe_allow_html=True)
                for _, r in latest[latest['checkpoint_name'] == cp].iterrows():
                    pic = r['runners']['profile_url'] if r['runners'] and r['runners']['profile_url'] else ""
                    st.markdown(f"<div class='runner-card'><img src='{pic}' style='width:45px;height:45px;border-radius:50%;border:2px solid gold;object-fit:cover;'><br><span style='font-size:9px;'>{r['runners']['name'].split(' ')[0]}</span></div>", unsafe_allow_html=True)
    st.button("🏠 กลับหน้าหลัก", on_click=change_page, args=("HOME",), use_container_width=True, key="leader_home_btn")

# --- REWARD ---
elif st.session_state.page == "REWARD":
    st.markdown("<h2 style='text-align: center;'>🎊 FINISHER 🎊</h2>", unsafe_allow_html=True)
    try:
        res_r = supabase.table("runners").select("*").eq("bib_number", st.session_state.my_bib).single().execute()
        res_l = supabase.table("run_logs").select("*").eq("bib_number", st.session_state.my_bib).execute()
        if res_r.data and "Finish" in [l['checkpoint_name'] for l in res_l.data]:
            st.balloons()
            f_time = pd.to_datetime(next(l for l in res_l.data if l['checkpoint_name']=="Finish")['scanned_at']).astimezone(tz).strftime('%H:%M:%S')
            m_uri = f"data:image/jpeg;base64,{get_base64_bin('badge.jpg')}" if os.path.exists('badge.jpg') else ""
            
            h_card = """
            <div style="font-family: sans-serif; display: flex; justify-content: center;">
                <div style="background: white; padding: 25px; border-radius: 20px; border: 5px solid #D4AF37; text-align: center; box-shadow: 0px 10px 30px rgba(0,0,0,0.1); width: 310px;">
                    <h3 style="color: #D4AF37; margin: 0; font-size: 18px;">CONGRATULATIONS!</h3>
                    <div style="position: relative; display: inline-block; margin: 20px 0;">
                        <img src="R_IMG" style="width: 160px; height: 160px; border-radius: 50%; border: 5px solid #D4AF37; object-fit: cover;">
                        <img src="M_IMG" style="position: absolute; top: -15px; right: -15px; width: 85px; height: 85px; border-radius: 50%; border: 3px solid #D4AF37; background: white;">
                    </div>
                    <h2 style="margin: 5px 0; color: #2C3E50; font-size: 24px;">U_NAME</h2>
                    <p style="font-size: 18px; color: #D4AF37; font-weight: bold; margin: 0;">BIB: U_BIB</p>
                    <div style="border-top: 2px dashed #eee; margin: 15px 0; padding-top: 10px;">
                        <p style="font-size: 20px; font-weight: bold; color: #2C3E50;">T_STAMP น.</p>
                    </div>
                    <div style="background: #FFF9E6; padding: 8px; border-radius: 10px; font-size: 12px; color: #856404;">🏅 รับรางวัลได้ที่จุดอำนวยการ</div>
                </div>
            </div>
            """
            final = h_card.replace("R_IMG", res_r.data['profile_url']).replace("M_IMG", m_uri).replace("U_NAME", res_r.data['name']).replace("U_BIB", res_r.data['bib_number']).replace("T_STAMP", f_time)
            components.html(final, height=540)
        else: st.warning("ยังสแกนไม่ครบจุดครับ")
    except Exception as e: st.error(f"Error: {e}")
    st.button("🏠 กลับหน้าหลัก", on_click=change_page, args=("HOME",), use_container_width=True, key="reward_home_btn")