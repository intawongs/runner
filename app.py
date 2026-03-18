import streamlit as st
import pandas as pd
from supabase import create_client, Client
from streamlit_qrcode_scanner import qrcode_scanner
from streamlit_autorefresh import st_autorefresh
import qrcode
from io import BytesIO
from datetime import datetime
import time

# --- 1. เชื่อมต่อ Supabase (ดึงจาก Secrets) ---
def init_connection():
    try:
        url = st.secrets["SUPABASE_URL"]
        key = st.secrets["SUPABASE_KEY"]
        return create_client(url, key)
    except Exception as e:
        st.error("❌ ไม่พบข้อมูล Secret: กรุณาตั้งค่าใน Settings > Secrets")
        st.stop()

supabase = init_connection()

st.set_page_config(page_title="RCI AI Tracker", layout="wide")

# --- 2. ฟังก์ชันช่วย (Helpers) ---
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
        # อัปโหลดรูปเข้า Storage (ต้องสร้าง Bucket ชื่อ runner_photos และตั้งเป็น Public)
        supabase.storage.from_(bucket_name).upload(filepath, file_bytes, {"content-type": "image/jpeg"})
        # ดึง Public URL
        res = supabase.storage.from_(bucket_name).get_public_url(filepath)
        return res
    except Exception as e:
        st.error(f"Upload Error: {e}")
        return None

# --- 3. Sidebar Menu ---
st.sidebar.title("🏃 RCI Walk Rally")
menu = st.sidebar.radio("เลือกเมนู", ["ลงทะเบียนพนักงาน", "จุดสแกนประจำจุด", "Leaderboard"])

# --- [ หน้าลงทะเบียน ] ---
if menu == "ลงทะเบียนพนักงาน":
    st.header("📝 ลงทะเบียนพนักงาน")
    
    if "is_reg_done" not in st.session_state:
        st.session_state.is_reg_done = False

    next_bib = get_next_bib()
    
    with st.form("register_form", clear_on_submit=True):
        st.info(f"หมายเลข BIB ที่จะได้รับ: **{next_bib}**")
        name = st.text_input("ชื่อ-นามสกุล")
        dept = st.selectbox("แผนก", ["Production", "R&D", "QA", "Logistics", "Office", "Maintenance"])
        submit_reg = st.form_submit_button("บันทึกและรับ QR")
        
        if submit_reg:
            if name:
                try:
                    supabase.table("runners").insert({"bib_number": next_bib, "name": name, "department": dept}).execute()
                    # สร้างรูป QR
                    qr = qrcode.make(next_bib)
                    buf = BytesIO()
                    qr.save(buf, format="PNG")
                    st.session_state.qr_buffer = buf.getvalue()
                    st.session_state.temp_name = name
                    st.session_state.temp_bib = next_bib
                    st.session_state.is_reg_done = True
                    st.rerun()
                except Exception as e:
                    st.error(f"เกิดข้อผิดพลาด: {e}")
            else:
                st.warning("กรุณากรอกชื่อพนักงาน")

    # แสดง QR นอก Form (เพื่อให้ปุ่ม Refresh ทำงานได้)
    if st.session_state.is_reg_done:
        st.success(f"ลงทะเบียนคุณ {st.session_state.temp_name} สำเร็จ!")
        st.image(st.session_state.qr_buffer, width=300, caption="👉 แคปหน้าจอ (Screenshot) รูปนี้ไว้สแกน")
        if st.button("ตกลง (ลงทะเบียนคนต่อไป)"):
            st.session_state.is_reg_done = False
            st.rerun()

# --- [ หน้าสแกน + ถ่ายรูป ] ---
elif menu == "จุดสแกนประจำจุด":
    st.header("📸 สแกน QR และ ถ่ายรูปยืนยัน")
    
    cp_loc = st.selectbox("จุดที่คุณประจำการ", ["Start", "CP1", "CP2", "CP3", "CP4", "CP5", "Finish"])
    
    # ใช้ Step เพื่อแยกหน้าจอ SCAN กับ PHOTO
    if "app_step" not in st.session_state:
        st.session_state.app_step = "SCAN"
        st.session_state.scanned_bib = None

    # --- STEP 1: สแกน QR ---
    if st.session_state.app_step == "SCAN":
        st.subheader("1️⃣ ขั้นตอนการสแกน QR Code")
        # ตัวสแกนจะทำงานเฉพาะหน้านี้
        val = qrcode_scanner(key="rci_scanner_widget")
        if val:
            st.session_state.scanned_bib = val
            st.session_state.app_step = "PHOTO"
            st.rerun() # บังคับ Refresh เพื่อ "ทำลาย" กล้องสแกนทิ้งก่อนเปิดกล้องถ่ายรูป

    # --- STEP 2: ถ่ายรูป (จะปรากฏหลังจากสแกนติด) ---
    elif st.session_state.app_step == "PHOTO":
        st.subheader(f"2️⃣ ขั้นตอนการถ่ายรูป (BIB: {st.session_state.scanned_bib})")
        
        # ช่องเปิดกล้องถ่ายรูป (st.camera_input)
        cam_photo = st.camera_input("👉 กดปุ่มถ่ายรูปพนักงาน", key="rci_camera_input")
        
        if cam_photo:
            with st.spinner("กำลังอัปโหลดข้อมูลและรูปถ่าย..."):
                ts = datetime.now().strftime("%H%M%S")
                fname = f"{st.session_state.scanned_bib}_{cp_loc}_{ts}"
                p_url = upload_photo(cam_photo.getvalue(), fname)
                
                if p_url:
                    supabase.table("run_logs").insert({
                        "bib_number": st.session_state.scanned_bib,
                        "checkpoint_name": cp_loc,
                        "photo_url": p_url
                    }).execute()
                    
                    st.success("✅ บันทึกข้อมูลสำเร็จ!")
                    time.sleep(1.5)
                    st.session_state.app_step = "SCAN" # กลับไปเริ่มสแกนคนใหม่
                    st.session_state.scanned_bib = None
                    st.rerun()

        if st.button("❌ ยกเลิกและกลับไปสแกนใหม่"):
            st.session_state.app_step = "SCAN"
            st.rerun()

# --- [ หน้า Leaderboard ] ---
elif menu == "Leaderboard":
    st.header("🏆 อันดับนักวิ่ง Real-time")
    st_autorefresh(interval=15000, key="refresh_board")

    # ดึงข้อมูลจาก Supabase (Join กับตาราง runners)
    res = supabase.table("run_logs").select("*, runners(name, department)").execute()
    
    if res.data:
        data_list = []
        for r in res.data:
            data_list.append({
                "รูป": r['photo_url'],
                "BIB": r['bib_number'],
                "ชื่อ": r['runners']['name'],
                "แผนก": r['runners']['department'],
                "จุดที่ผ่าน": r['checkpoint_name'],
                "เวลาสแกน": r['scanned_at']
            })
        df = pd.DataFrame(data_list)

        # จัดลำดับ: นับจำนวนจุด และเอารูปถ่ายล่าสุดของแต่ละคน
        summary = df.sort_values("เวลาสแกน", ascending=False).groupby("BIB").first().reset_index()
        count_data = df.groupby("BIB").size().reset_index(name="จุดสะสม")
        final_df = pd.merge(summary, count_data, on="BIB").sort_values("จุดสะสม", ascending=False)
        
        # แสดงผลตารางพร้อมรูป (ใช้ ImageColumn)
        st.dataframe(
            final_df[["รูป", "BIB", "ชื่อ", "แผนก", "จุดสะสม", "จุดที่ผ่าน"]],
            column_config={"รูป": st.column_config.ImageColumn("รูปล่าสุด")},
            use_container_width=True
        )
    else:
        st.info("ยังไม่มีข้อมูลการวิ่งในระบบ...")