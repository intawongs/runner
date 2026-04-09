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
ADMIN_CODE = "3571138" # รหัสลับแอดมิน
tz = pytz.timezone('Asia/Bangkok')

st.set_page_config(page_title="RCI RACING 2026", layout="wide", initial_sidebar_state="collapsed")

# Custom CSS: ปรับเลนให้เป็น Grid (Flexbox) เพื่อรองรับคนเยอะ
st.markdown("""
    <style>
    .main { background-image: linear-gradient(120deg, #fdfbfb 0%, #ebedee 100%); }
    .stButton>button { border-radius: 10px; font-weight: bold; height: 3.5em; width: 100%; }
    
    /* เลนวิ่งแบบโปร่งแสงและยืดหยุ่น */
    .lane-container {
        background: rgba(255, 255, 255, 0.4);
        border-radius: 15px;
        border: 1px solid rgba(255, 255, 255, 0.6);
        backdrop-filter: blur(10px);
        padding: 10px;
        min-height: 600px;
        box-shadow: 0 4px 6px rgba(0,0,0,0.05);
        display: flex;
        flex-wrap: wrap; /* ถ้านักวิ่งเยอะ ให้ขึ้นแถวใหม่ในเลนเดิม */
        justify-content: center;
        align-content: flex-start;
    }
    
    .cp-header { 
        background: rgba(46, 134, 193, 0.9); 
        color: white; border-radius: 10px; text-align: center; 
        padding: 10px; font-size: 13px; font-weight: bold; 
        margin-bottom: 10px; width: 100%;
    }
    
    .runner-card { 
        text-align: center; margin: 5px; padding: 5px; 
        border-radius: 50%; width: 55px; background: white;
        box-shadow: 0 4px 8px rgba(0,0,0,0.1);
    }
    
    .runner-name {
        font-size: 9px; font-weight: bold; color: #2E86C1;
        margin-top: 3px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
    }
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
        supabase.storage.from_(bucket).upload(path=path, file=file_bytes, file_options={"content-type": "image/jpeg", "upsert": "true"})
        return f"{st.secrets['SUPABASE_URL']}/storage/v1/object/public/{bucket}/{path}"
    except:
        return f"{st.secrets['SUPABASE_URL']}/storage/v1/object/public/{bucket}/{path}"

# --- 4. PAGES ---

# --- HOME ---
if st.session_state.page == "HOME":
    st.markdown("<h1 style='text-align: center;'>🏃‍♂️ RCI AI RACING 2026</h1>", unsafe_allow_html=True)
    st.write("---")
    if not st.session_state.my_bib:
        col1, col2 = st.columns(2)
        with col1:
            if st.button("📝 ลงทะเบียนใหม่", key="h_reg", type="primary"): change_page("REGISTER")
        with col2:
            input_val = st.text_input("ระบุเลข BIB หรือ รหัสแอดมิน", key="h_input").strip()
            if st.button("เข้าสู่ระบบ", key="h_login"):
                if input_val == ADMIN_CODE: change_page("ADMIN_PANEL")
                elif input_val:
                    res = supabase.table("runners").select("bib_number").eq("bib_number", clean_bib(input_val)).execute()
                    if res.data: login_user(clean_bib(input_val))
                    else: st.error("ไม่พบหมายเลข BIB")
    else:
        st.success(f"ล็อกอินเป็น BIB: **{st.session_state.my_bib}**")
        st.button("🏁 สแกนเช็คพอยท์", on_click=change_page, args=("SCAN",), type="primary", key="h_scan")
        st.button("🏆 กระดานคะแนน", on_click=change_page, args=("LEADERBOARD",), key="h_leader")
        st.button("🎁 รับรางวัล / สรุปผล", on_click=change_page, args=("REWARD",), key="h_reward")
        if st.button("🚪 ออกจากระบบ", key="h_logout"): logout_user()

# --- ADMIN PANEL ---
elif st.session_state.page == "ADMIN_PANEL":
    st.markdown("<h2 style='color:#ef4444;'>🛠 Admin Control</h2>", unsafe_allow_html=True)
    t1, t2 = st.tabs(["จัดการนักวิ่ง", "ลบประวัติ"])
    with t1:
        adm_bib = st.text_input("BIB นักวิ่ง", key="adm_bib").upper()
        adm_cp = st.selectbox("จุดเช็คอิน", CHECKPOINT_LIST, key="adm_cp")
        if st.button("เช็คอินแทนนักวิ่ง", type="primary", key="adm_btn"):
            if adm_bib:
                supabase.table("run_logs").insert({"bib_number": clean_bib(adm_bib), "checkpoint_name": adm_cp}).execute()
                st.success("บันทึกสำเร็จ!"); time.sleep(1); st.rerun()
    with t2:
        res_l = supabase.table("run_logs").select("*, runners(name)").order("scanned_at", desc=True).execute()
        if res_l.data:
            for l in res_l.data:
                c1, c2, c3 = st.columns([3,2,1])
                c1.write(f"{l['bib_number']} - {l['runners']['name'] if l['runners'] else 'N/A'}")
                c2.write(l['checkpoint_name'])
                if c3.button("ลบ", key=f"del_{l['id']}"):
                    supabase.table("run_logs").delete().eq("id", l['id']).execute(); st.rerun()
    st.button("🏠 กลับหน้าหลัก", on_click=change_page, args=("HOME",), key="adm_home")

# --- REGISTER ---
elif st.session_state.page == "REGISTER":
    st.subheader("📝 ลงทะเบียน")
    if "reg_step" not in st.session_state: st.session_state.reg_step = "FORM"
    if st.session_state.reg_step == "FORM":
        with st.form("f_reg"):
            name = st.text_input("ชื่อ-นามสกุล")
            dept = st.selectbox("แผนก", ["Production", "R&D", "QA", "Logistics", "Office", "Maintenance", "Others"])
            if st.form_submit_button("ถัดไป: ถ่ายรูป"):
                if name:
                    res = supabase.table("runners").select("bib_number").order("bib_number", desc=True).limit(1).execute()
                    last_num = int(res.data[0]['bib_number'].split("-")[1]) if res.data else 0
                    st.session_state.temp_user = {"bib": f"RCI-{last_num+1:03d}", "name": name, "dept": dept}
                    st.session_state.reg_step = "PHOTO"; st.rerun()
        if st.button("🏠 กลับหน้าหลัก", key="reg_home"): change_page("HOME")
    elif st.session_state.reg_step == "PHOTO":
        img = st.camera_input("ถ่ายรูป")
        if img:
            with st.spinner("บันทึก..."):
                url = upload_photo(img.getvalue(), st.session_state.temp_user['bib'])
                supabase.table("runners").insert({"bib_number": st.session_state.temp_user['bib'], "name": st.session_state.temp_user['name'], "department": st.session_state.temp_user['dept'], "profile_url": url}).execute()
                st.session_state.my_bib = st.session_state.temp_user['bib']
                st.query_params["bib"] = st.session_state.my_bib
                st.session_state.reg_step = "FORM"; st.success("สำเร็จ!"); time.sleep(1.5); st.session_state.page = "HOME"; st.rerun()

# --- SCAN ---
elif st.session_state.page == "SCAN":
    st.subheader(f"🏁 สแกน (BIB: {st.session_state.my_bib})")
    res_l = supabase.table("run_logs").select("checkpoint_name").eq("bib_number", st.session_state.my_bib).execute()
    already = [l['checkpoint_name'] for l in res_l.data] if res_l.data else []
    next_cp = next((cp for cp in CHECKPOINT_LIST if cp not in already), None)
    if not next_cp:
        st.success("🎉 ครบแล้ว!"); st.button("🏠 กลับหน้าหลัก", key="sc_done", on_click=change_page, args=("HOME",))
    else:
        st.info(f"🚩 จุดถัดไป: **{next_cp}**")
        qr = qrcode_scanner(key=f"qr_{next_cp}_{len(already)}")
        if qr == next_cp:
            supabase.table("run_logs").insert({"bib_number": st.session_state.my_bib, "checkpoint_name": qr}).execute()
            st.balloons(); st.success("บันทึกสำเร็จ!"); time.sleep(1.2); st.rerun()
    st.button("🏠 กลับหน้าหลัก", on_click=change_page, args=("HOME",), key="sc_home")

# --- LEADERBOARD ---
# --- PAGE: LEADERBOARD (Optimized Grid) ---
elif st.session_state.page == "LEADERBOARD":
    st.markdown("<h2 style='text-align: center; color: #2E86C1;'>🏎️ RCI RACING REAL-TIME</h2>", unsafe_allow_html=True)
    st_autorefresh(interval=5000, key="auto_lb_final")
    
    # 1. ดึงข้อมูลล่าสุด
    res = supabase.table("run_logs").select("*, runners(*)").order("scanned_at", desc=True).execute()
    latest_df = pd.DataFrame()
    if res.data:
        df = pd.DataFrame(res.data)
        # เก็บเฉพาะจุดล่าสุดของแต่ละ BIB
        latest_df = df.sort_values("scanned_at", ascending=False).groupby("bib_number").first().reset_index()

    # 2. สร้าง Column สำหรับ 5 เลน
    lanes = st.columns(len(CHECKPOINT_LIST))

    for idx, cp in enumerate(CHECKPOINT_LIST):
        with lanes[idx]:
            # ส่วนหัวของเลน
            st.markdown(f"<div class='cp-header'>{cp}</div>", unsafe_allow_html=True)
            
            # พื้นที่เลนวิ่งแบบ Grid
            # ใช้ CSS แบบ inline เพื่อบังคับให้รูปอยู่ด้านบนเสมอ
            lane_html = """
            <div style="
                background: rgba(255, 255, 255, 0.4);
                border-radius: 15px;
                border: 1px solid rgba(255, 255, 255, 0.6);
                backdrop-filter: blur(10px);
                padding: 15px 5px;
                min-height: 550px;
                display: flex;
                flex-wrap: wrap;
                justify-content: center;
                align-content: flex-start; /* บังคับให้เริ่มเรียงจากด้านบน */
                gap: 10px;
            ">
            """
            
            if not latest_df.empty:
                runners_in_cp = latest_df[latest_df['checkpoint_name'] == cp]
                for _, r in runners_in_cp.iterrows():
                    pic = r['runners']['profile_url'] if r['runners'] and r['runners']['profile_url'] else ""
                    # ตัดชื่อให้สั้นลงเพื่อความสวยงาม
                    nick = (r['runners']['name'] if r['runners'] else r['bib_number']).split(" ")[0]
                    
                    lane_html += f"""
                    <div style="text-align: center; width: 60px;">
                        <div style="
                            width: 55px; height: 55px; border-radius: 50%; 
                            border: 3px solid gold; overflow: hidden; background: white;
                            box-shadow: 0 4px 8px rgba(0,0,0,0.1); margin: 0 auto;
                        ">
                            <img src='{pic}' style='width: 100%; height: 100%; object-fit: cover;'>
                        </div>
                        <div style='font-size: 10px; font-weight: bold; color: #2E86C1; margin-top: 5px; 
                             white-space: nowrap; overflow: hidden; text-overflow: ellipsis;'>
                            {nick}
                        </div>
                    </div>
                    """
            
            lane_html += "</div>"
            st.markdown(lane_html, unsafe_allow_html=True)

    st.write("---")
    st.button("🏠 กลับหน้าหลัก", on_click=change_page, args=("HOME",), use_container_width=True, key="lb_home_btn_final")

# --- REWARD ---
elif st.session_state.page == "REWARD":
    st.markdown("<h2 style='text-align: center;'>🎊 FINISHER 🎊</h2>", unsafe_allow_html=True)
    try:
        res_r = supabase.table("runners").select("*").eq("bib_number", st.session_state.my_bib).single().execute()
        res_l = supabase.table("run_logs").select("*").eq("bib_number", st.session_state.my_bib).execute()
        if res_r.data and "Finish" in [l['checkpoint_name'] for l in res_l.data]:
            st.balloons()
            start_t = pd.to_datetime(next(l for l in res_l.data if l['checkpoint_name']=="Start")['scanned_at'])
            end_t = pd.to_datetime(next(l for l in res_l.data if l['checkpoint_name']=="Finish")['scanned_at'])
            dur = int((end_t - start_t).total_seconds() / 60)
            f_time = end_t.astimezone(tz).strftime('%H:%M:%S')
            m_uri = f"data:image/jpeg;base64,{get_base64_bin('badge.jpg')}" if os.path.exists('badge.jpg') else ""
            h_card = f"""
            <div style="font-family: sans-serif; display: flex; justify-content: center;">
                <div style="background: white; padding: 25px; border-radius: 20px; border: 6px solid #D4AF37; text-align: center; width: 320px;">
                    <h3 style="color: #D4AF37; margin: 0;">CONGRATULATIONS!</h3>
                    <div style="position: relative; display: inline-block; margin: 20px 0;">
                        <img src="{res_r.data['profile_url']}" style="width: 160px; height: 160px; border-radius: 50%; border: 6px solid #D4AF37; object-fit: cover;">
                        <img src="{m_uri}" style="position: absolute; top: -15px; right: -15px; width: 85px; height: 85px; border-radius: 50%; border: 3px solid #D4AF37; background: white;">
                    </div>
                    <h2 style="margin: 5px 0; color: #2C3E50;">{res_r.data['name']}</h2>
                    <p style="color: #D4AF37; font-weight: bold;">BIB: {res_r.data['bib_number']}</p>
                    <div style="display: flex; justify-content: space-around; border-top: 1px dashed #eee; margin-top: 15px; padding-top: 10px;">
                        <div><p style="font-size: 10px; color: #999;">TIME</p><p style="font-size: 18px; font-weight: bold;">{dur} Min</p></div>
                        <div><p style="font-size: 10px; color: #999;">FINISHED</p><p style="font-size: 18px; font-weight: bold;">{f_time}</p></div>
                    </div>
                </div>
            </div>
            """
            components.html(h_card, height=560)
        else: st.warning("ยังสแกนไม่ครบจุดครับ")
    except Exception as e: st.error(f"Error: {e}")
    st.button("🏠 กลับหน้าหลัก", on_click=change_page, args=("HOME",), key="rw_home")