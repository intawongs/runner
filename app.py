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

# --- 0. CONFIG & STYLES ---
# กำหนดจุดเช็คพอยท์ที่ต้องการให้สแกนเรียงลำดับ
CHECKPOINT_LIST = ["Start", "Checkpoint 1", "Checkpoint 2", "Checkpoint 3", "Finish"]
tz = pytz.timezone('Asia/Bangkok')

st.set_page_config(page_title="RCI RACING 2026", layout="wide", initial_sidebar_state="collapsed")

# Custom CSS สำหรับ UI
st.markdown("""
    <style>
    .main { background-color: #f5f7f9; }
    .stButton>button { border-radius: 10px; font-weight: bold; height: 3em; }
    .cp-header { background:#2E86C1; color:white; border-radius:10px; text-align:center; padding:10px; font-size:12px; font-weight:bold; min-height:45px; display:flex; align-items:center; justify-content:center; }
    .runner-card { text-align:center; margin-bottom:15px; border: 1px solid #ddd; padding: 5px; border-radius: 10px; background: white; }
    </style>
""", unsafe_allow_html=True)

# --- 1. DATABASE CONNECTION ---
def init_connection():
    try:
        return create_client(st.secrets["SUPABASE_URL"], st.secrets["SUPABASE_KEY"])
    except Exception as e:
        st.error(f"❌ Connection Error: {e}")
        st.stop()

supabase = init_connection()

# --- 2. SESSION STATE & AUTH ---
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

# --- 3. HELPER FUNCTIONS ---
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
        # อัปโหลดรูปพร้อม Upsert (เขียนทับไฟล์เดิม)
        supabase.storage.from_(bucket).upload(
            path=path, 
            file=file_bytes, 
            file_options={"content-type": "image/jpeg", "upsert": "true"}
        )
        return f"{st.secrets['SUPABASE_URL']}/storage/v1/object/public/{bucket}/{path}"
    except:
        # กรณี Error มักเกิดจาก Policy แต่ไฟล์อาจจะขึ้นไปแล้ว หรือลองดึง URL ตรงๆ
        return f"{st.secrets['SUPABASE_URL']}/storage/v1/object/public/{bucket}/{path}"

# --- 4. NAVIGATION CONTROL ---

# --- PAGE: HOME ---
if st.session_state.page == "HOME":
    st.markdown("<h1 style='text-align: center;'>🏃‍♂️ RCI AI RACING 2026</h1>", unsafe_allow_html=True)
    st.write("---")
    
    if not st.session_state.my_bib:
        col1, col2 = st.columns(2)
        with col1:
            if st.button("📝 ลงทะเบียนใหม่", use_container_width=True, type="primary"):
                change_page("REGISTER")
        with col2:
            existing_bib = st.text_input("มี BIB แล้ว? (เช่น RCI-001)").upper()
            if st.button("เข้าสู่ระบบ", use_container_width=True):
                if existing_bib:
                    res = supabase.table("runners").select("bib_number").eq("bib_number", clean_bib(existing_bib)).execute()
                    if res.data: login_user(clean_bib(existing_bib))
                    else: st.error("ไม่พบหมายเลข BIB นี้ในระบบ")
    else:
        st.success(f"ยินดีต้อนรับ! BIB ปัจจุบันของคุณคือ: **{st.session_state.my_bib}**")
        st.button("🏁 สแกนเช็คพอยท์", on_click=change_page, args=("SCAN",), use_container_width=True, type="primary")
        st.button("🏆 กระดานคะแนน (Leaderboard)", on_click=change_page, args=("LEADERBOARD",), use_container_width=True)
        st.button("🎁 รับรางวัล / สรุปผล", on_click=change_page, args=("REWARD",), use_container_width=True)
        st.write("")
        if st.button("🚪 ออกจากระบบ / เปลี่ยนตัววิ่ง", use_container_width=True):
            logout_user()

# --- PAGE: REGISTER ---
elif st.session_state.page == "REGISTER":
    st.subheader("📝 ลงทะเบียนนักวิ่ง")
    if "reg_step" not in st.session_state: st.session_state.reg_step = "FORM"

    if st.session_state.reg_step == "FORM":
        with st.form("reg_form"):
            name = st.text_input("ชื่อ-นามสกุล (สำหรับพิมพ์บนการ์ด)")
            dept = st.selectbox("แผนก/หน่วยงาน", ["Production", "R&D", "QA", "Logistics", "Office", "Maintenance", "Others"])
            if st.form_submit_button("ถัดไป: ถ่ายรูปโปรไฟล์"):
                if name:
                    res = supabase.table("runners").select("bib_number").order("bib_number", desc=True).limit(1).execute()
                    last_num = int(res.data[0]['bib_number'].split("-")[1]) if res.data else 0
                    st.session_state.temp_user = {"bib": f"RCI-{last_num+1:03d}", "name": name, "dept": dept}
                    st.session_state.reg_step = "PHOTO"; st.rerun()
                else: st.warning("กรุณากรอกชื่อ-นามสกุล")
        if st.button("🏠 กลับหน้าแรก", use_container_width=True): change_page("HOME")

    elif st.session_state.reg_step == "PHOTO":
        st.info(f"ยินดีที่รู้จักคุณ {st.session_state.temp_user['name']}! ระบบกำหนด BIB ให้คุณคือ: {st.session_state.temp_user['bib']}")
        img = st.camera_input("ถ่ายรูปหน้าตรงเพื่อใช้ในระบบ")
        if img:
            with st.spinner("กำลังบันทึกข้อมูล..."):
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
                st.success("✅ ลงทะเบียนสำเร็จ! กำลังพากลับหน้าหลัก...")
                time.sleep(2)
                st.session_state.page = "HOME"; st.rerun()
        if st.button("⬅️ กลับไปแก้ไขข้อมูล", use_container_width=True):
            st.session_state.reg_step = "FORM"; st.rerun()

# --- PAGE: SCAN (Sequence Validation) ---
elif st.session_state.page == "SCAN":
    st.subheader(f"🏁 บันทึกจุดสแกน (BIB: {st.session_state.my_bib})")
    
    res_logs = supabase.table("run_logs").select("checkpoint_name").eq("bib_number", st.session_state.my_bib).execute()
    already = [log['checkpoint_name'] for log in res_logs.data] if res_logs.data else []
    
    next_cp = next((cp for cp in CHECKPOINT_LIST if cp not in already), None)
            
    if not next_cp:
        st.success("🎉 คุณวิ่งครบทุกจุดเรียบร้อยแล้ว!")
        if st.button("🏠 กลับหน้าหลัก", use_container_width=True): change_page("HOME")
    else:
        st.info(f"🚩 จุดที่คุณต้องสแกนลำดับถัดไปคือ: **{next_cp}**")
        qr = qrcode_scanner(key=f"scanner_{next_cp}_{len(already)}")
        
        if qr:
            if qr == next_cp:
                with st.spinner("บันทึกข้อมูล..."):
                    supabase.table("run_logs").insert({"bib_number": st.session_state.my_bib, "checkpoint_name": qr}).execute()
                    st.balloons(); st.success(f"✅ บันทึกจุด {qr} สำเร็จ!"); time.sleep(1.5); st.rerun()
            else:
                st.error(f"❌ ผิดจุด! ท่านสแกนเจอจุด '{qr}' แต่ลำดับที่ต้องสแกนจริงคือ '{next_cp}'")
    
    st.write("---")
    st.button("🏠 กลับหน้าหลัก", on_click=change_page, args=("HOME",), use_container_width=True)

# --- PAGE: LEADERBOARD ---
elif st.session_state.page == "LEADERBOARD":
    st.markdown("<h2 style='text-align: center;'>🏆 RCI RACING REAL-TIME</h2>", unsafe_allow_html=True)
    st_autorefresh(interval=5000, key="leaderboard_refresh")
    
    lanes = st.columns(len(CHECKPOINT_LIST))
    res = supabase.table("run_logs").select("*, runners(*)").order("scanned_at", desc=True).execute()
    
    if res.data:
        df = pd.DataFrame(res.data)
        latest = df.sort_values("scanned_at", ascending=False).groupby("bib_number").first().reset_index()
        
        for idx, cp in enumerate(CHECKPOINT_LIST):
            with lanes[idx]:
                st.markdown(f"<div class='cp-header'>{cp}</div>", unsafe_allow_html=True)
                runners_in_cp = latest[latest['checkpoint_name'] == cp]
                for _, r in runners_in_cp.iterrows():
                    pic = r['runners']['profile_url'] if r['runners'] and r['runners']['profile_url'] else ""
                    name_tag = (r['runners']['name'] if r['runners'] else r['bib_number']).split(" ")[0]
                    st.markdown(f"""
                        <div class='runner-card'>
                            <img src='{pic}' style='width:50px; height:50px; border-radius:50%; border:2px solid #D4AF37; object-fit:cover;'>
                            <p style='font-size:10px; margin:0; font-weight:bold;'>{name_tag}</p>
                        </div>
                    """, unsafe_allow_html=True)
    
    st.write("---")
    st.button("🏠 กลับหน้าหลัก", on_click=change_page, args=("HOME",), use_container_width=True)

# --- PAGE: REWARD ---
elif st.session_state.page == "REWARD":
    st.markdown("<h2 style='text-align: center;'>🎊 FINISHER CELEBRATION 🎊</h2>", unsafe_allow_html=True)
    
    try:
        res_runner = supabase.table("runners").select("*").eq("bib_number", st.session_state.my_bib).single().execute()
        res_logs = supabase.table("run_logs").select("*").eq("bib_number", st.session_state.my_bib).execute()
        
        if res_runner.data and res_logs.data:
            runner = res_runner.data
            logs = pd.DataFrame(res_logs.data)
            checked = logs['checkpoint_name'].tolist()
            
            if "Finish" in checked:
                st.balloons()
                f_row = logs[logs['checkpoint_name'] == "Finish"].iloc[0]
                f_time = pd.to_datetime(f_row['scanned_at']).astimezone(tz).strftime('%H:%M:%S')
                
                # ดึงรูปเหรียญ (Local)
                medal_uri = ""
                if os.path.exists('badge.jpg'):
                    medal_uri = f"data:image/jpeg;base64,{get_base64_bin('badge.jpg')}"

                # Render การ์ดผ่าน HTML Component เพื่อเลี่ยงปัญหา Code Leak
                html_template = """
                <div style="font-family: sans-serif; display: flex; justify-content: center; padding: 10px;">
                    <div style="background: white; padding: 30px; border-radius: 20px; border: 6px solid #D4AF37; text-align: center; box-shadow: 0px 10px 30px rgba(0,0,0,0.1); width: 330px;">
                        <h3 style="color: #D4AF37; margin: 0; letter-spacing: 1px;">CONGRATULATIONS!</h3>
                        <p style="color: #666; font-size: 11px; margin: 5px 0 25px 0;">OFFICIAL FINISHER OF RCI RACING 2026</p>
                        
                        <div style="position: relative; display: inline-block; margin-bottom: 25px;">
                            <img src="RUNNER_IMG" style="width: 170px; height: 170px; border-radius: 50%; border: 6px solid #D4AF37; object-fit: cover;">
                            <img src="MEDAL_IMG" style="position: absolute; top: -15px; right: -15px; width: 90px; height: 90px; border-radius: 50%; border: 4px solid #D4AF37; background: white; box-shadow: 0px 4px 10px rgba(0,0,0,0.3);">
                        </div>
                        
                        <h2 style="margin: 5px 0; color: #2C3E50; font-size: 26px;">USER_NAME</h2>
                        <p style="font-size: 18px; color: #D4AF37; font-weight: bold; margin: 0;">BIB: USER_BIB</p>
                        
                        <div style="border-top: 2px dashed #eee; margin: 25px 0; padding-top: 15px;">
                            <p style="font-size: 10px; color: #999; margin-bottom: 3px;">COMPLETED AT</p>
                            <p style="font-size: 22px; font-weight: bold; color: #2C3E50;">TIME_STAMP น.</p>
                        </div>
                        
                        <div style="background: #FFF9E6; padding: 12px; border-radius: 12px; border: 1px solid #FFE799;">
                            <p style="font-size: 12px; color: #856404; margin: 0; font-weight: bold;">🏅 แสดงหน้าจอนี้ต่อเจ้าหน้าที่เพื่อรับรางวัล</p>
                        </div>
                    </div>
                </div>
                """
                final_html = html_template.replace("RUNNER_IMG", runner['profile_url'] if runner['profile_url'] else "") \
                                          .replace("MEDAL_IMG", medal_uri) \
                                          .replace("USER_NAME", runner['name']) \
                                          .replace("USER_BIB", runner['bib_number']) \
                                          .replace("TIME_STAMP", f_time)

                components.html(final_html, height=550, scrolling=False)
            else:
                st.warning("⚠️ คุณยังสแกนไม่ครบทุกจุด! กรุณาวิ่งและสแกนให้ครบถึงจุด Finish")
                st.info(f"สะสมได้: {len(checked)} / {len(CHECKPOINT_LIST)} จุด")
                st.progress(len(checked) / len(CHECKPOINT_LIST))
        else:
            st.error("ไม่พบข้อมูลนักวิ่งในฐานข้อมูล")
    except Exception as e:
        st.error(f"เกิดข้อผิดพลาด: {e}")

    st.button("🏠 กลับหน้าหลัก", on_click=change_page, args=("HOME",), use_container_width=True)