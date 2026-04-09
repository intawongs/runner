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
ADMIN_CODE = "3571138" # รหัสลับแอดมินที่คุณกำหนด
tz = pytz.timezone('Asia/Bangkok')

st.set_page_config(page_title="RCI RACING 2026", layout="wide", initial_sidebar_state="collapsed")

# Custom CSS เพื่อความสวยงามและรองรับมือถือ
st.markdown("""
    <style>
    .main { background-color: #f5f7f9; }
    .stButton>button { border-radius: 10px; font-weight: bold; height: 3.5em; width: 100%; }
    .cp-header { background:#2E86C1; color:white; border-radius:10px; text-align:center; padding:10px; font-size:12px; font-weight:bold; min-height:45px; display:flex; align-items:center; justify-content:center; }
    .runner-card { text-align:center; margin-bottom:15px; border: 1px solid #ddd; padding: 5px; border-radius: 10px; background: white; }
    .admin-tab { background: #fff1f2; padding: 15px; border-radius: 10px; border: 1px solid #fda4af; }
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

# --- PAGE: HOME ---
if st.session_state.page == "HOME":
    st.markdown("<h1 style='text-align: center;'>🏃‍♂️ RCI AI RACING 2026</h1>", unsafe_allow_html=True)
    st.write("---")
    
    if not st.session_state.my_bib:
        col1, col2 = st.columns(2)
        with col1:
            if st.button("📝 ลงทะเบียนใหม่", key="h_btn_reg", type="primary"):
                change_page("REGISTER")
        with col2:
            input_val = st.text_input("ระบุเลข BIB หรือ รหัสแอดมิน", key="h_input_auth").strip()
            if st.button("เข้าสู่ระบบ", key="h_btn_login"):
                if input_val == ADMIN_CODE:
                    change_page("ADMIN_PANEL")
                elif input_val:
                    res = supabase.table("runners").select("bib_number").eq("bib_number", clean_bib(input_val)).execute()
                    if res.data: login_user(clean_bib(input_val))
                    else: st.error("ไม่พบหมายเลข BIB")
    else:
        st.success(f"ล็อกอินเป็น BIB: **{st.session_state.my_bib}**")
        st.button("🏁 สแกนเช็คพอยท์", on_click=change_page, args=("SCAN",), type="primary", key="h_btn_scan")
        st.button("🏆 กระดานคะแนน", on_click=change_page, args=("LEADERBOARD",), key="h_btn_leader")
        st.button("🎁 รับรางวัล / สรุปผล", on_click=change_page, args=("REWARD",), key="h_btn_reward")
        st.write("")
        if st.button("🚪 ออกจากระบบ", key="h_btn_logout"):
            logout_user()

# --- PAGE: ADMIN PANEL ---
elif st.session_state.page == "ADMIN_PANEL":
    st.markdown("<h2 style='color:#ef4444;'>🛠 Admin Management System</h2>", unsafe_allow_html=True)
    tab1, tab2 = st.tabs(["👥 จัดการนักวิ่ง", "📜 ประวัติการสแกน"])
    
    with tab1:
        st.write("### Manual Check-in")
        with st.container(border=True):
            adm_bib = st.text_input("ระบุ BIB (เช่น RCI-001)", key="adm_m_bib").upper()
            adm_cp = st.selectbox("เลือกจุดที่จะเช็คอินให้", CHECKPOINT_LIST, key="adm_m_cp")
            if st.button("บันทึกข้อมูลแทนนักวิ่ง", type="primary", key="adm_btn_manual"):
                if adm_bib:
                    supabase.table("run_logs").insert({"bib_number": clean_bib(adm_bib), "checkpoint_name": adm_cp}).execute()
                    st.success(f"เช็คอิน {adm_cp} ให้ {adm_bib} แล้ว!"); time.sleep(1); st.rerun()
        
        st.write("### รายชื่อนักวิ่งที่ลงทะเบียน")
        res_r = supabase.table("runners").select("*").execute()
        if res_r.data: st.dataframe(pd.DataFrame(res_r.data)[['bib_number', 'name', 'department']], use_container_width=True)

    with tab2:
        st.write("### ประวัติการสแกนทั้งหมด (ลบเพื่อเริ่มใหม่ได้)")
        res_l = supabase.table("run_logs").select("*, runners(name)").order("scanned_at", desc=True).execute()
        if res_l.data:
            for log in res_l.data:
                c1, c2, c3 = st.columns([3, 2, 1])
                c1.write(f"**{log['bib_number']}** - {log['runners']['name'] if log['runners'] else 'N/A'}")
                c2.write(f"{log['checkpoint_name']} ({pd.to_datetime(log['scanned_at']).astimezone(tz).strftime('%H:%M:%S')})")
                if c3.button("ลบ", key=f"del_log_{log['id']}"):
                    supabase.table("run_logs").delete().eq("id", log['id']).execute(); st.rerun()

    st.button("🏠 กลับหน้าหลัก", on_click=change_page, args=("HOME",), key="adm_btn_home")

# --- PAGE: REGISTER ---
elif st.session_state.page == "REGISTER":
    st.subheader("📝 ลงทะเบียนนักวิ่ง")
    if "reg_step" not in st.session_state: st.session_state.reg_step = "FORM"

    if st.session_state.reg_step == "FORM":
        with st.form("f_reg_v4"):
            name = st.text_input("ชื่อ-นามสกุล")
            dept = st.selectbox("แผนก", ["Production", "R&D", "QA", "Logistics", "Office", "Maintenance", "Others"])
            if st.form_submit_button("ถัดไป: ถ่ายรูปโปรไฟล์"):
                if name:
                    res = supabase.table("runners").select("bib_number").order("bib_number", desc=True).limit(1).execute()
                    last_num = int(res.data[0]['bib_number'].split("-")[1]) if res.data else 0
                    st.session_state.temp_user = {"bib": f"RCI-{last_num+1:03d}", "name": name, "dept": dept}
                    st.session_state.reg_step = "PHOTO"; st.rerun()
        if st.button("🏠 กลับหน้าหลัก", key="reg_btn_home"): change_page("HOME")

    elif st.session_state.reg_step == "PHOTO":
        st.warning(f"คุณ {st.session_state.temp_user['name']} จะได้รับหมายเลข BIB: {st.session_state.temp_user['bib']}")
        img = st.camera_input("ถ่ายรูปโปรไฟล์เพื่อใช้ในการ์ด Finisher")
        if img:
            with st.spinner("กำลังบันทึกข้อมูล..."):
                url = upload_photo(img.getvalue(), st.session_state.temp_user['bib'])
                supabase.table("runners").insert({"bib_number": st.session_state.temp_user['bib'], "name": st.session_state.temp_user['name'], "department": st.session_state.temp_user['dept'], "profile_url": url}).execute()
                st.session_state.my_bib = st.session_state.temp_user['bib']
                st.query_params["bib"] = st.session_state.my_bib
                st.session_state.reg_step = "FORM" 
                st.success("✅ ลงทะเบียนสำเร็จ!"); time.sleep(1.5); st.session_state.page = "HOME"; st.rerun()
        if st.button("⬅️ กลับไปแก้ไขข้อมูล", key="reg_btn_back"): st.session_state.reg_step = "FORM"; st.rerun()

# --- PAGE: SCAN ---
elif st.session_state.page == "SCAN":
    st.subheader(f"🏁 สแกนจุด (BIB: {st.session_state.my_bib})")
    res_l = supabase.table("run_logs").select("checkpoint_name").eq("bib_number", st.session_state.my_bib).execute()
    already = [l['checkpoint_name'] for l in res_l.data] if res_l.data else []
    next_cp = next((cp for cp in CHECKPOINT_LIST if cp not in already), None)
            
    if not next_cp:
        st.success("🎉 คุณวิ่งครบทุกจุดแล้ว!"); st.button("🏠 กลับหน้าหลัก", key="scan_btn_done", on_click=change_page, args=("HOME",))
    else:
        st.info(f"🚩 จุดที่ต้องสแกนถัดไปคือ: **{next_cp}**")
        qr = qrcode_scanner(key=f"qr_{next_cp}_{len(already)}")
        if qr == next_cp:
            supabase.table("run_logs").insert({"bib_number": st.session_state.my_bib, "checkpoint_name": qr}).execute()
            st.balloons(); st.success("บันทึกจุดสำเร็จ!"); time.sleep(1.2); st.rerun()
    st.button("🏠 กลับหน้าหลัก", on_click=change_page, args=("HOME",), key="scan_btn_home")

# --- PAGE: LEADERBOARD ---
elif st.session_state.page == "LEADERBOARD":
    st.markdown("<h2 style='text-align: center;'>🏆 RACING LEADERBOARD</h2>", unsafe_allow_html=True)
    st_autorefresh(interval=5000, key="auto_lb")
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
                    st.markdown(f"<div class='runner-card'><img src='{pic}' style='width:45px;height:45px;border-radius:50%;border:2px solid gold;object-fit:cover;'><br><span style='font-size:9px;font-weight:bold;'>{r['runners']['name'].split(' ')[0]}</span></div>", unsafe_allow_html=True)
    st.button("🏠 กลับหน้าหลัก", on_click=change_page, args=("HOME",), key="leader_btn_home")

# --- PAGE: REWARD ---
# --- PAGE: REWARD (ปรับปรุงใหม่เพื่อแสดงเวลา) ---
elif st.session_state.page == "REWARD":
    st.markdown("<h2 style='text-align: center;'>🎊 FINISHER 🎊</h2>", unsafe_allow_html=True)
    try:
        res_r = supabase.table("runners").select("*").eq("bib_number", st.session_state.my_bib).single().execute()
        res_l = supabase.table("run_logs").select("*").eq("bib_number", st.session_state.my_bib).execute()
        
        if res_r.data and res_l.data:
            logs = res_l.data
            checkpoints = [l['checkpoint_name'] for l in logs]
            
            if "Finish" in checkpoints and "Start" in checkpoints:
                st.balloons()
                
                # --- คำนวณเวลา ---
                start_time = pd.to_datetime(next(l for l in logs if l['checkpoint_name']=="Start")['scanned_at'])
                finish_time = pd.to_datetime(next(l for l in logs if l['checkpoint_name']=="Finish")['scanned_at'])
                
                # คำนวณส่วนต่างเวลาเป็นนาที
                duration = finish_time - start_time
                total_minutes = int(duration.total_seconds() / 60)
                
                f_time_str = finish_time.astimezone(tz).strftime('%H:%M:%S')
                m_uri = f"data:image/jpeg;base64,{get_base64_bin('badge.jpg')}" if os.path.exists('badge.jpg') else ""
                
                h_card = """
                <div style="font-family: sans-serif; display: flex; justify-content: center;">
                    <div style="background: white; padding: 25px; border-radius: 20px; border: 6px solid #D4AF37; text-align: center; box-shadow: 0px 10px 30px rgba(0,0,0,0.1); width: 320px;">
                        <h3 style="color: #D4AF37; margin: 0; font-size: 18px; letter-spacing: 1px;">CONGRATULATIONS!</h3>
                        <div style="position: relative; display: inline-block; margin: 25px 0;">
                            <img src="R_IMG" style="width: 160px; height: 160px; border-radius: 50%; border: 6px solid #D4AF37; object-fit: cover;">
                            <img src="M_IMG" style="position: absolute; top: -15px; right: -15px; width: 85px; height: 85px; border-radius: 50%; border: 4px solid #D4AF37; background: white; box-shadow: 0px 4px 10px rgba(0,0,0,0.3);">
                        </div>
                        <h2 style="margin: 5px 0; color: #2C3E50; font-size: 24px;">U_NAME</h2>
                        <p style="font-size: 18px; color: #D4AF37; font-weight: bold; margin: 0;">BIB: U_BIB</p>
                        
                        <div style="display: flex; justify-content: space-around; border-top: 2px dashed #eee; margin: 20px 0; padding-top: 15px;">
                            <div>
                                <p style="font-size: 10px; color: #999; margin:0;">TOTAL TIME</p>
                                <p style="font-size: 20px; font-weight: bold; color: #2C3E50;">DUR_MIN Min</p>
                            </div>
                            <div>
                                <p style="font-size: 10px; color: #999; margin:0;">FINISHED AT</p>
                                <p style="font-size: 20px; font-weight: bold; color: #2C3E50;">T_STAMP</p>
                            </div>
                        </div>
                        
                        <div style="background: #FFF9E6; padding: 10px; border-radius: 10px; font-size: 13px; color: #856404; font-weight: bold;">🏅 รับเหรียญได้ที่จุดอำนวยการ</div>
                    </div>
                </div>
                """
                # แทนที่ค่าต่างๆ ใน HTML
                final = h_card.replace("R_IMG", res_r.data['profile_url']) \
                              .replace("M_IMG", m_uri) \
                              .replace("U_NAME", res_r.data['name']) \
                              .replace("U_BIB", res_r.data['bib_number']) \
                              .replace("DUR_MIN", str(total_minutes)) \
                              .replace("T_STAMP", f_time_str)
                
                components.html(final, height=580)
            elif "Start" not in checkpoints:
                st.error("❌ ไม่พบข้อมูลการสแกนที่จุด Start กรุณาติดต่อเจ้าหน้าที่")
            else:
                st.warning("⚠️ คุณยังวิ่งไม่ถึงจุด Finish! สแกนให้ครบก่อนรับรางวัลนะ")
        else:
            st.error("ไม่พบข้อมูลนักวิ่ง")
    except Exception as e:
        st.error(f"Error: {e}")
    
    st.button("🏠 กลับหน้าหลัก", on_click=change_page, args=("HOME",), key="reward_btn_home")