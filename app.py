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
# --- PAGE: LEADERBOARD (Fixed Code Leak Version) ---
elif st.session_state.page == "LEADERBOARD":
    st.markdown("<h2 style='text-align: center; color: #2E86C1;'>🏎️ RCI RACING REAL-TIME</h2>", unsafe_allow_html=True)
    st_autorefresh(interval=5000, key="auto_lb_fixed_v3")
    
    res = supabase.table("run_logs").select("*, runners(*)").order("scanned_at", desc=True).execute()
    latest_df = pd.DataFrame()
    if res.data:
        df = pd.DataFrame(res.data)
        latest_df = df.sort_values("scanned_at", ascending=False).groupby("bib_number").first().reset_index()

    lanes = st.columns(len(CHECKPOINT_LIST))

    for idx, cp in enumerate(CHECKPOINT_LIST):
        with lanes[idx]:
            st.markdown(f"<div class='cp-header'>{cp}</div>", unsafe_allow_html=True)
            
            # สร้างก้อน HTML สำหรับเลนนี้
            inner_html = ""
            if not latest_df.empty:
                runners_in_cp = latest_df[latest_df['checkpoint_name'] == cp]
                for _, r in runners_in_cp.iterrows():
                    pic = r['runners']['profile_url'] if r['runners'] and r['runners']['profile_url'] else ""
                    nick = (r['runners']['name'] if r['runners'] else r['bib_number']).split(" ")[0]
                    
                    inner_html += f"""
                    <div style="text-align: center; width: 60px; margin: 5px;">
                        <div style="width: 55px; height: 55px; border-radius: 50%; border: 3px solid gold; overflow: hidden; background: white; box-shadow: 0 4px 8px rgba(0,0,0,0.1);">
                            <img src='{pic}' style='width: 100%; height: 100%; object-fit: cover;'>
                        </div>
                        <div style='font-size: 10px; font-weight: bold; color: #2E86C1; margin-top: 5px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;'>
                            {nick}
                        </div>
                    </div>
                    """
            
            # ใช้ Components HTML เพื่อตัดปัญหา Markdown ไม่ยอม Render
            full_lane_html = f"""
            <div style="
                background: rgba(255, 255, 255, 0.5);
                border-radius: 15px;
                border: 1px solid rgba(255, 255, 255, 0.6);
                padding: 10px 5px;
                min-height: 500px;
                display: flex;
                flex-wrap: wrap;
                justify-content: center;
                align-content: flex-start;
                font-family: sans-serif;
            ">
                {inner_html}
            </div>
            """
            components.html(full_lane_html, height=520, scrolling=False)

    st.write("---")
    st.button("🏠 กลับหน้าหลัก", on_click=change_page, args=("HOME",), use_container_width=True, key="lb_home_v3")

# --- REWARD ---
# --- PAGE: REWARD (ฉบับคำนวณลำดับที่เข้าเส้นชัย) ---
elif st.session_state.page == "REWARD":
    st.markdown("<h2 style='text-align: center;'>🎊 FINISHER 🎊</h2>", unsafe_allow_html=True)
    
    try:
        # 1. ดึงข้อมูลนักวิ่งปัจจุบัน
        res_runner = supabase.table("runners").select("*").eq("bib_number", st.session_state.my_bib).single().execute()
        # 2. ดึง Log ทั้งหมดเพื่อมาเรียงลำดับหา Rank
        res_all_finish = supabase.table("run_logs").select("bib_number, scanned_at").eq("checkpoint_name", "Finish").order("scanned_at", desc=False).execute()
        # 3. ดึง Log ของคนปัจจุบันเพื่อดูเวลา Start/Finish
        res_my_logs = supabase.table("run_logs").select("*").eq("bib_number", st.session_state.my_bib).execute()
        
        if res_runner.data and res_my_logs.data:
            runner = res_runner.data
            my_logs = pd.DataFrame(res_my_logs.data)
            my_checkpoints = my_logs['checkpoint_name'].tolist()
            
            if "Finish" in my_checkpoints and "Start" in my_checkpoints:
                # --- คำนวณลำดับที่ (Rank) ---
                all_finish_df = pd.DataFrame(res_all_finish.data)
                # ลำดับคือตำแหน่งใน List ที่เรียงตามเวลาเข้าเส้นชัย (Index + 1)
                rank = all_finish_df[all_finish_df['bib_number'] == st.session_state.my_bib].index[0] + 1
                
                # --- เช็คสิทธิ์รับเหรียญ ---
                has_medal = rank <= 100
                medal_status = "ได้รับเหรียญรางวัล! 🏅" if has_medal else "เสียใจด้วย คุณไม่ติด 100 คนแรก"
                status_color = "#856404" if has_medal else "#721c24"
                status_bg = "#FFF9E6" if has_medal else "#f8d7da"
                
                # --- คำนวณเวลาวิ่ง ---
                start_t = pd.to_datetime(my_logs[my_logs['checkpoint_name']=="Start"].iloc[0]['scanned_at'])
                finish_t = pd.to_datetime(my_logs[my_logs['checkpoint_name']=="Finish"].iloc[0]['scanned_at'])
                duration = finish_t - start_t
                total_min = int(duration.total_seconds() / 60)
                f_time_str = finish_t.astimezone(tz).strftime('%H:%M:%S')

                # รูปเหรียญรางวัล
                medal_uri = ""
                if os.path.exists('badge.jpg'):
                    medal_uri = f"data:image/jpeg;base64,{get_base64_bin('badge.jpg')}"

                # --- Render HTML Card ---
                html_card = f"""
                <div style="font-family: sans-serif; display: flex; justify-content: center; padding: 10px;">
                    <div style="background: white; padding: 25px; border-radius: 20px; border: 6px solid #D4AF37; text-align: center; box-shadow: 0px 10px 30px rgba(0,0,0,0.1); width: 330px;">
                        <div style="font-size: 14px; font-weight: bold; color: #D4AF37; margin-bottom: 10px;">
                            RANK #{rank}
                        </div>
                        
                        <div style="position: relative; display: inline-block; margin-bottom: 20px;">
                            <img src="{runner['profile_url']}" style="width: 150px; height: 150px; border-radius: 50%; border: 5px solid #D4AF37; object-fit: cover;">
                            {"<img src='"+medal_uri+"' style='position: absolute; top: -10px; right: -10px; width: 80px; height: 80px; border-radius: 50%; border: 3px solid #D4AF37; background: white;'>" if has_medal else ""}
                        </div>
                        
                        <h2 style="margin: 0; color: #2C3E50; font-size: 24px;">{runner['name']}</h2>
                        <p style="font-size: 16px; color: #D4AF37; font-weight: bold; margin: 5px 0;">BIB: {runner['bib_number']}</p>
                        
                        <div style="display: flex; justify-content: space-around; border-top: 2px dashed #eee; margin: 20px 0; padding-top: 15px;">
                            <div>
                                <p style="font-size: 10px; color: #999; margin: 0;">TIME</p>
                                <p style="font-size: 18px; font-weight: bold; color: #2C3E50;">{total_min} Min</p>
                            </div>
                            <div>
                                <p style="font-size: 10px; color: #999; margin: 0;">FINISH</p>
                                <p style="font-size: 18px; font-weight: bold; color: #2C3E50;">{f_time_str}</p>
                            </div>
                        </div>
                        
                        <div style="background: {status_bg}; padding: 12px; border-radius: 12px; border: 1px solid rgba(0,0,0,0.1);">
                            <p style="font-size: 13px; color: {status_color}; margin: 0; font-weight: bold;">{medal_status}</p>
                        </div>
                    </div>
                </div>
                """
                components.html(html_card, height=580)
                
                if has_medal:
                    st.balloons()
            else:
                st.warning("⚠️ คุณยังสแกนไม่ครบจุด (ต้องสแกน Start และ Finish เป็นอย่างน้อย)")
        else:
            st.error("ไม่พบข้อมูลนักวิ่งในระบบ")
            
    except Exception as e:
        st.error(f"Error: {e}")

    st.button("🏠 กลับหน้าหลัก", on_click=change_page, args=("HOME",), use_container_width=True, key="rw_home_final")