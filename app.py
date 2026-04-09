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
import streamlit.components.v1 as components 
import os 
import base64 

# --- 0. CONFIG ---
CP_COORDINATES = {
    "Start": {"lat": 13.3849, "lon": 100.1914},
    "Checkpoint 1": {"lat": 13.3859, "lon": 100.1904},
    "Checkpoint 2": {"lat": 13.3901, "lon": 100.1913},
    "Checkpoint 3": {"lat": 13.3901, "lon": 100.1917},
    "Finish": {"lat": 13.3849, "lon": 100.1914}
}
CHECKPOINT_LIST = list(CP_COORDINATES.keys())
tz = pytz.timezone('Asia/Bangkok')

st.set_page_config(page_title="RCI RACING 2026", layout="wide", initial_sidebar_state="collapsed")

# --- 1. CONNECTION ---
def init_connection():
    try:
        return create_client(st.secrets["SUPABASE_URL"], st.secrets["SUPABASE_KEY"])
    except Exception as e:
        st.error(f"❌ เชื่อมต่อ Database ล้มเหลว: {e}"); st.stop()

supabase = init_connection()

# --- 2. AUTH & STATE ---
if "my_bib" not in st.session_state:
    st.session_state.my_bib = st.query_params.get("bib", "")

if "page" not in st.session_state:
    st.session_state.page = "HOME"

def login_user(bib):
    st.session_state.my_bib = bib
    st.query_params["bib"] = bib
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

def upload_photo(file_bytes, bib):
    path = f"profile_{bib}.jpg"
    bucket = "runner_photos"
    try:
        # ใช้ upsert: true เพื่อเขียนทับไฟล์เดิมได้
        supabase.storage.from_(bucket).upload(
            path=path, 
            file=file_bytes, 
            file_options={"content-type": "image/jpeg", "upsert": "true"}
        )
        return f"{st.secrets['SUPABASE_URL']}/storage/v1/object/public/{bucket}/{path}"
    except Exception as e:
        # หากอัปโหลดล้มเหลว ให้ลองดึง URL เดิม (กรณีทำ Policy ผิดพลาด)
        return f"{st.secrets['SUPABASE_URL']}/storage/v1/object/public/{bucket}/{path}"

# --- 4. NAVIGATION ---

# --- HOME ---
if st.session_state.page == "HOME":
    st.markdown("<h1 style='text-align: center;'>🏃‍♂️ RCI AI RACING 2026</h1>", unsafe_allow_html=True)
    if not st.session_state.my_bib:
        col1, col2 = st.columns(2)
        with col1:
            if st.button("📝 ลงทะเบียนใหม่", use_container_width=True, type="primary"): change_page("REGISTER")
        with col2:
            existing_bib = st.text_input("มี BIB แล้ว?").upper()
            if st.button("เข้าสู่ระบบ", use_container_width=True):
                if existing_bib:
                    res = supabase.table("runners").select("bib_number").eq("bib_number", clean_bib(existing_bib)).execute()
                    if res.data: login_user(clean_bib(existing_bib))
                    else: st.error("ไม่พบหมายเลข BIB")
    else:
        st.success(f"BIB: **{st.session_state.my_bib}**")
        st.button("🏁 สแกนเช็คพอยท์", on_click=change_page, args=("SCAN",), use_container_width=True, type="primary")
        st.button("🏆 กระดานคะแนน", on_click=change_page, args=("LEADERBOARD",), use_container_width=True)
        st.button("🎁 รับรางวัล / สรุปผล", on_click=change_page, args=("REWARD",), use_container_width=True)
        if st.button("🚪 ออกจากระบบ"): logout_user()

# --- REGISTER ---
elif st.session_state.page == "REGISTER":
    if "reg_step" not in st.session_state: st.session_state.reg_step = "FORM"
    
    if st.session_state.reg_step == "FORM":
        with st.form("reg"):
            name = st.text_input("ชื่อ-นามสกุล")
            dept = st.selectbox("แผนก", ["Production", "R&D", "QA", "Logistics", "Office", "Maintenance"])
            if st.form_submit_button("ถัดไป: ถ่ายรูป"):
                if name:
                    res = supabase.table("runners").select("bib_number").order("bib_number", desc=True).limit(1).execute()
                    last_num = int(res.data[0]['bib_number'].split("-")[1]) if res.data else 0
                    st.session_state.temp_user = {"bib": f"RCI-{last_num+1:03d}", "name": name, "dept": dept}
                    st.session_state.reg_step = "PHOTO"; st.rerun()
                    
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
                st.session_state.reg_step = "FORM" # Reset step
                login_user(st.session_state.temp_user['bib'])

# --- SCAN ---
elif st.session_state.page == "SCAN":
    st.subheader(f"🏁 เช็คพอยท์ (BIB: {st.session_state.my_bib})")
    res_logs = supabase.table("run_logs").select("checkpoint_name").eq("bib_number", st.session_state.my_bib).execute()
    already = [log['checkpoint_name'] for log in res_logs.data] if res_logs.data else []
    
    next_cp = next((cp for cp in CHECKPOINT_LIST if cp not in already), None)

    if not next_cp:
        st.success("🎉 ครบทุกจุดแล้ว!"); st.button("🏠 กลับหน้าหลัก", on_click=change_page, args=("HOME",))
    else:
        st.info(f"🚩 จุดถัดไป: **{next_cp}**")
        qr = qrcode_scanner(key=f"sc_{next_cp}_{len(already)}")
        if qr == next_cp:
            supabase.table("run_logs").insert({"bib_number": st.session_state.my_bib, "checkpoint_name": qr}).execute()
            st.balloons(); st.success("บันทึกสำเร็จ!"); time.sleep(1.5); st.rerun()

# --- LEADERBOARD ---
elif st.session_state.page == "LEADERBOARD":
    st.markdown("<h2 style='text-align: center;'>🏎️ RACING LANES</h2>", unsafe_allow_html=True)
    st_autorefresh(interval=5000, key="auto_refresh")
    lanes = st.columns(len(CHECKPOINT_LIST))
    res = supabase.table("run_logs").select("*, runners(*)").execute()
    if res.data:
        df = pd.DataFrame(res.data)
        latest = df.sort_values("scanned_at", ascending=False).groupby("bib_number").first().reset_index()
        for idx, cp in enumerate(CHECKPOINT_LIST):
            with lanes[idx]:
                st.markdown(f"<div style='background:#2E86C1;color:white;text-align:center;padding:5px;border-radius:5px;'>{cp}</div>", unsafe_allow_html=True)
                runners = latest[latest['checkpoint_name'] == cp]
                for _, r in runners.iterrows():
                    pic = r['runners']['profile_url'] if r['runners'] and r['runners']['profile_url'] else ""
                    nick = (r['runners']['name'] if r['runners'] else r['bib_number']).split(" ")[0]
                    st.markdown(f"<div style='text-align:center;margin-top:10px;'><img src='{pic}' style='width:40px;height:40px;border-radius:50%;border:2px solid gold;'><p style='font-size:10px;'>{nick}</p></div>", unsafe_allow_html=True)
    st.button("🏠 กลับหน้าหลัก", on_click=change_page, args=("HOME",))

# --- REWARD ---
elif st.session_state.page == "REWARD":
    try:
        res_runner = supabase.table("runners").select("*").eq("bib_number", st.session_state.my_bib).single().execute()
        res_logs = supabase.table("run_logs").select("*").eq("bib_number", st.session_state.my_bib).execute()
        
        if res_runner.data and res_logs.data:
            runner = res_runner.data
            checked = [log['checkpoint_name'] for log in res_logs.data]
            
            if "Finish" in checked:
                st.balloons()
                f_row = next(l for l in res_logs.data if l['checkpoint_name'] == "Finish")
                f_time = pd.to_datetime(f_row['scanned_at']).astimezone(tz).strftime('%H:%M:%S')
                
                medal_uri = ""
                if os.path.exists('badge.jpg'):
                    with open('badge.jpg', 'rb') as f:
                        medal_uri = f"data:image/jpeg;base64,{base64.b64encode(f.read()).decode()}"

                html_card = """
                <div style="font-family: sans-serif; display: flex; justify-content: center; padding: 10px;">
                    <div style="background: white; padding: 25px; border-radius: 15px; border: 4px solid #D4AF37; text-align: center; box-shadow: 0px 8px 20px rgba(0,0,0,0.1); width: 300px;">
                        <h3 style="color: #D4AF37; margin: 0; font-size: 16px;">CONGRATULATIONS!</h3>
                        <p style="color: #666; font-size: 10px; margin: 5px 0 15px 0;">OFFICIAL FINISHER RCI 2026</p>
                        <div style="position: relative; display: inline-block; margin-bottom: 15px;">
                            <img src="RUNNER_IMG" style="width: 140px; height: 140px; border-radius: 50%; border: 4px solid #D4AF37; object-fit: cover;">
                            <img src="MEDAL_IMG" style="position: absolute; top: -10px; right: -10px; width: 60px; height: 60px; border-radius: 50%; border: 2px solid #D4AF37; background: white;">
                        </div>
                        <h2 style="margin: 5px 0; color: #2C3E50; font-size: 20px;">USER_NAME</h2>
                        <p style="font-size: 16px; color: #D4AF37; font-weight: bold; margin: 0;">BIB: USER_BIB</p>
                        <div style="border-top: 1px dashed #eee; margin: 15px 0; padding-top: 10px;">
                            <p style="font-size: 18px; font-weight: bold; color: #2C3E50;">TIME_HOLDER น.</p>
                        </div>
                    </div>
                </div>
                """
                final_html = html_card.replace("RUNNER_IMG", runner['profile_url'] if runner['profile_url'] else "") \
                                      .replace("MEDAL_IMG", medal_uri) \
                                      .replace("USER_NAME", runner['name']) \
                                      .replace("USER_BIB", runner['bib_number']) \
                                      .replace("TIME_HOLDER", f_time)

                components.html(final_html, height=480)
            else:
                st.warning("⚠️ ยังสแกนไม่ครบ!")
                st.progress(len(checked) / len(CHECKPOINT_LIST))
    except Exception as e:
        st.error(f"Error: {e}")
    st.button("🏠 กลับหน้าหลัก", on_click=change_page, args=("HOME",))