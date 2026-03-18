import streamlit as st
import pandas as pd
from supabase import create_client, Client
from streamlit_qrcode_scanner import qrcode_scanner
from streamlit_autorefresh import st_autorefresh
import qrcode
from io import BytesIO
from datetime import datetime
import time

# --- 1. Connection (ดึงจาก Secrets) ---
def init_connection():
    try:
        url = st.secrets["SUPABASE_URL"]
        key = st.secrets["SUPABASE_KEY"]
        return create_client(url, key)
    except Exception as e:
        st.error("❌ ตรวจสอบการตั้งค่า Secrets (SUPABASE_URL, SUPABASE_KEY)")
        st.stop()

supabase = init_connection()

st.set_page_config(page_title="RCI AI Tracker", layout="wide")

# --- 2. Helper Functions ---
def get_next_bib():
    try:
        res = supabase.table("runners").select("bib_number").order("bib_number", desc=True).limit(1).execute()
        if not res.data:
            return "RCI-001"
        last_bib = res.data[0]['bib_number']
        last_num = int(last_bib.split("-")[1])
        return f"RCI-{last_num + 1:03d}"
    except:
        return "RCI-001"

def upload_photo(file_bytes, filename):
    try:
        bucket_name = "runner_photos"
        filepath = f"{filename}.jpg"
        # อัปโหลดรูปเข้า Storage
        supabase.storage.from_(bucket_name).upload(filepath, file_bytes, {"content-type": "image/jpeg"})
        # ดึง Public URL
        res = supabase.storage.from_(bucket_name).get_public_url(filepath)
        return res
    except Exception as e:
        st.error(f"Upload Error: {e}")
        return None

# --- 3. Sidebar Menu ---
st.sidebar.title("🏃 RCI Walk Rally")
menu = st.sidebar.radio("เมนูหลัก", ["ลงทะเบียนพนักงาน", "จุดสแกนประจำจุด", "Leaderboard"])

# --- PAGE 1: ลงทะเบียน (Register) ---
if menu == "ลงทะเบียนพนักงาน":
    st.header("📝 ลงทะเบียนพนักงาน (Auto BIB)")
    
    # ใช้ Session State ควบคุมการแสดงผล QR
    if "is_reg" not in st.session_state:
        st.session_state.is_reg = False

    next_bib = get_next_bib()
    
    with st.form("register_form", clear_on_submit=True):
        st.info(f"BIB ที่จะได้รับ: **{next_bib}**")
        name = st.text_input("ชื่อ-นามสกุล")
        dept = st.selectbox("แผนก", ["Production", "R&D", "QA", "Office", "Maintenance", "Logistics"])
        submit_reg = st.form_submit_button("บันทึกข้อมูล")
        
        if submit_reg:
            if name:
                try:
                    supabase.table("runners").insert({"bib_number": next_bib, "name": name, "department": dept}).execute()
                    # เจน QR
                    qr = qrcode.make(next_bib)
                    buf = BytesIO()
                    qr.save(buf, format="PNG")
                    st.session_state.last_qr = buf.getvalue()
                    st.session_state.last_bib = next_bib
                    st.session_state.is_reg = True
                    st.rerun()
                except Exception as e:
                    st.error(f"Error: {e}")
            else:
                st.warning("กรุณาใส่ชื่อพนักงาน")

    # แสดงผลนอก Form เมื่อลงทะเบียนสำเร็จ
    if st.session_state.get("is_reg"):
        st.success(f"ลงทะเบียนสำเร็จ! BIB: {st.session_state.last_bib}")
        st.image(st.session_state.last_qr, width=300, caption="👉 แคปหน้าจอรูปนี้ไว้สแกน")
        if st.button("ตกลง (ลงทะเบียนคนต่อไป)"):
            st.session_state.is_reg = False
            st.rerun()

# --- PAGE 2: จุดสแกน (Checkpoint) ---
elif menu == "จุดสแกนประจำจุด":
    st.header("📸 สแกน QR + ถ่ายรูป")
    cp_loc = st.selectbox("จุดประจำการ", ["Start", "CP1", "CP2", "CP3", "CP4", "CP5", "Finish"])
    
    # ควบคุม Step: scan -> photo
    if "step" not in st.session_state:
        st.session_state.step = "scan"
        st.session_state.temp_bib = None

    if st.session_state.step == "scan":
        st.subheader("1️⃣ ขั้นตอนที่ 1: สแกน QR Code")
        scanned_val = qrcode_scanner(key="scanner_widget")
        if scanned_val:
            st.session_state.temp_bib = scanned_val
            st.session_state.step = "photo"
            st.rerun()
            
    elif st.session_state.step == "photo":
        st.subheader(f"2️⃣ ขั้นตอนที่ 2: ถ่ายรูปยืนยัน (BIB: {st.session_state.temp_bib})")
        cam_photo = st.camera_input("กดปุ่มถ่ายรูปพนักงาน")
        
        if cam_photo:
            with st.spinner("กำลังบันทึกข้อมูลและรูปถ่าย..."):
                ts = datetime.now().strftime("%Y%m%d_%H%M%S")
                fname = f"{st.session_state.temp_bib}_{cp_loc}_{ts}"
                p_url = upload_photo(cam_photo.getvalue(), fname)
                
                if p_url:
                    supabase.table("run_logs").insert({
                        "bib_number": st.session_state.temp_bib,
                        "checkpoint_name": cp_loc,
                        "photo_url": p_url
                    }).execute()
                    st.success("✅ บันทึกสำเร็จ!")
                    time.sleep(1.5)
                    st.session_state.step = "scan"
                    st.session_state.temp_bib = None
                    st.rerun()
        
        if st.button("ยกเลิก / กลับไปสแกนใหม่"):
            st.session_state.step = "scan"
            st.rerun()

# --- PAGE 3: LEADERBOARD ---
elif menu == "Leaderboard":
    st.header("🏆 อันดับนักวิ่ง Real-time")
    st_autorefresh(interval=15000, key="auto_refresh_board")

    # ดึงข้อมูลมาแสดงผล (Join กับตาราง runners เพื่อเอาชื่อ)
    res = supabase.table("run_logs").select("*, runners(name, department)").execute()
    
    if res.data:
        raw_df = pd.DataFrame([{
            "รูป": r['photo_url'], 
            "BIB": r['bib_number'], 
            "ชื่อ": r['runners']['name'],
            "แผนก": r['runners']['department'], 
            "จุด": r['checkpoint_name'], 
            "เวลา": r['scanned_at']
        } for r in res.data])
        
        # จัดลำดับ: นับจำนวนจุด และหารูปล่าสุด
        summary = raw_df.sort_values("เวลา", ascending=False).groupby("BIB").first().reset_index()
        count_data = raw_df.groupby("BIB").size().reset_index(name="จุดสะสม")
        final_df = pd.merge(summary, count_data, on="BIB").sort_values("จุดสะสม", ascending=False)
        
        # แสดงผลตารางพร้อมรูป
        st.dataframe(
            final_df[["รูป", "BIB", "ชื่อ", "แผนก", "จุดสะสม", "จุด"]],
            column_config={"รูป": st.column_config.ImageColumn("รูปถ่ายล่าสุด")},
            use_container_width=True
        )
    else:
        st.info("ยังไม่มีข้อมูลการวิ่งในระบบ")