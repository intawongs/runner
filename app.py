import streamlit as st
import pandas as pd
from supabase import create_client, Client
from streamlit_qrcode_scanner import qrcode_scanner
from streamlit_autorefresh import st_autorefresh
import qrcode
from io import BytesIO
from datetime import datetime
import time

# --- 1. การตั้งค่าระบบและการเชื่อมต่อ ---
st.set_page_config(page_title="RCI Walk Rally AI Tracker", layout="wide", initial_sidebar_state="expanded")

def init_connection():
    try:
        url = st.secrets["SUPABASE_URL"]
        key = st.secrets["SUPABASE_KEY"]
        return create_client(url, key)
    except Exception as e:
        st.error("❌ กรุณาตั้งค่า Secrets: SUPABASE_URL และ SUPABASE_KEY ใน Streamlit Cloud")
        st.stop()

supabase = init_connection()

# --- 2. ฟังก์ชันช่วย (Helper Functions) ---
def get_next_bib():
    try:
        res = supabase.table("runners").select("bib_number").order("bib_number", desc=True).limit(1).execute()
        if not res.data: return "RCI-001"
        last_bib = res.data[0]['bib_number']
        last_num = int(last_bib.split("-")[1])
        return f"RCI-{last_num + 1:03d}"
    except: return "RCI-001"

def upload_photo(file_bytes, filename):
    try:
        bucket_name = "runner_photos"
        filepath = f"profile_{filename}.jpg"
        # อัปโหลดรูป (ต้องตั้ง Bucket เป็น Public ใน Supabase Storage)
        supabase.storage.from_(bucket_name).upload(filepath, file_bytes, {"content-type": "image/jpeg"})
        res = supabase.storage.from_(bucket_name).get_public_url(filepath)
        return res
    except Exception as e:
        st.error(f"Upload Error: {e}")
        return None

# --- 3. Sidebar เมนูหลัก ---
st.sidebar.title("🏃 RCI Walk Rally 2026")
st.sidebar.subheader("ระบบติดตามนักวิ่ง AI")
menu = st.sidebar.radio("เมนูหลัก", ["📝 ลงทะเบียนพนักงาน", "📸 จุดสแกน Checkpoint", "🏆 Leaderboard"])

# --- [ หน้า 1: ลงทะเบียนพนักงาน ] ---
if menu == "📝 ลงทะเบียนพนักงาน":
    st.header("📝 ลงทะเบียนและถ่ายรูปโปรไฟล์")
    
    # ควบคุม Step การลงทะเบียน
    if "reg_step" not in st.session_state:
        st.session_state.reg_step = "FORM"

    if st.session_state.reg_step == "FORM":
        next_bib = get_next_bib()
        with st.form("reg_form"):
            st.info(f"หมายเลข BIB ถัดไปคือ: **{next_bib}**")
            name = st.text_input("ชื่อ-นามสกุลพนักงาน")
            dept = st.selectbox("แผนก", ["Production", "R&D", "QA", "Logistics", "Office", "Maintenance", "Accounting", "Finance"])
            submit_form = st.form_submit_button("ถัดไป: ถ่ายรูปโปรไฟล์")
            
            if submit_form:
                if name:
                    st.session_state.temp_user = {"bib": next_bib, "name": name, "dept": dept}
                    st.session_state.reg_step = "PHOTO"
                    st.rerun()
                else: st.warning("กรุณากรอกชื่อพนักงาน")

    elif st.session_state.reg_step == "PHOTO":
        st.subheader(f"📸 ถ่ายรูปโปรไฟล์: {st.session_state.temp_user['name']}")
        img_file = st.camera_input("ส่องหน้าให้ตรงแล้วกดถ่ายรูป")
        
        if img_file:
            with st.spinner("กำลังบันทึกข้อมูลและเจน QR..."):
                p_url = upload_photo(img_file.getvalue(), st.session_state.temp_user['bib'])
                if p_url:
                    # บันทึกลงตาราง runners (ต้องมีคอลัมน์ profile_url ใน DB)
                    supabase.table("runners").insert({
                        "bib_number": st.session_state.temp_user['bib'],
                        "name": st.session_state.temp_user['name'],
                        "department": st.session_state.temp_user['dept'],
                        "profile_url": p_url
                    }).execute()
                    
                    # สร้าง QR Code
                    qr = qrcode.make(st.session_state.temp_user['bib'])
                    buf = BytesIO()
                    qr.save(buf, format="PNG")
                    st.session_state.reg_qr = buf.getvalue()
                    st.session_state.reg_step = "DONE"
                    st.rerun()
        
        if st.button("⬅️ กลับไปแก้ไขชื่อ"):
            st.session_state.reg_step = "FORM"
            st.rerun()

    elif st.session_state.reg_step == "DONE":
        st.success(f"✅ ลงทะเบียนสำเร็จ! BIB: {st.session_state.temp_user['bib']}")
        st.image(st.session_state.reg_qr, width=300, caption="👉 แคปหน้าจอรูปนี้ไว้สแกนที่จุด Checkpoint")
        if st.button("ลงทะเบียนคนถัดไป"):
            st.session_state.reg_step = "FORM"
            st.rerun()

# --- [ หน้า 2: จุดสแกน Checkpoint ] ---
elif menu == "📸 จุดสแกน Checkpoint":
    st.header("📸 สแกน QR เช็คอินอัตโนมัติ")
    
    # ล็อคป้องกันการสแกนรัว (Double Scan)
    if "is_saving" not in st.session_state:
        st.session_state.is_saving = False

    cp_loc = st.selectbox("📍 คุณประจำการอยู่ที่จุดไหน?", ["Start", "CP1", "CP2", "CP3", "CP4", "CP5", "Finish"])
    
    st.divider()

    if not st.session_state.is_saving:
        st.info(f"🔍 กำลังรอสแกนที่จุด: **{cp_loc}**")
        # เครื่องสแกน QR
        scanned_val = qrcode_scanner(key=f"scanner_{cp_loc}")
        
        if scanned_val:
            st.session_state.is_saving = True
            st.session_state.current_bib = scanned_val
            st.rerun()
    else:
        # ขั้นตอนบันทึกลง DB
        bib_to_save = st.session_state.current_bib
        st.warning(f"🚀 กำลังบันทึก BIB: {bib_to_save} ...")
        
        try:
            res = supabase.table("run_logs").insert({
                "bib_number": bib_to_save,
                "checkpoint_name": cp_loc
            }).execute()
            
            if res.data:
                st.success(f"✅ บันทึกสำเร็จ! BIB: {bib_to_save} ผ่านจุด {cp_loc}")
                st.balloons()
                time.sleep(1.5) # หน่วงเวลาให้เห็นผล
                
                # ล้างค่าและ Refresh จอเพื่อรอคนใหม่
                st.session_state.is_saving = False
                st.session_state.current_bib = None
                st.rerun()
        except Exception as e:
            st.error(f"Error: {e}")
            if st.button("🔄 รีเซ็ตเพื่อลองใหม่"):
                st.session_state.is_saving = False
                st.rerun()

# --- [ หน้า 3: Leaderboard ] ---
elif menu == "🏆 Leaderboard":
    st.header("🏆 อันดับนักวิ่ง Real-time")
    st_autorefresh(interval=15000, key="auto_refresh_board")

    # ดึงข้อมูล Log และ Join กับตาราง Runners เพื่อเอาชื่อและรูปโปรไฟล์
    res = supabase.table("run_logs").select("*, runners(name, department, profile_url)").execute()
    
    if res.data:
        # แปลงเป็น DataFrame
        df = pd.DataFrame([{
            "Profile": r['runners']['profile_url'],
            "BIB": r['bib_number'],
            "ชื่อ-นามสกุล": r['runners']['name'],
            "แผนก": r['runners']['department'],
            "จุดล่าสุด": r['checkpoint_name'],
            "เวลาล่าสุด": r['scanned_at']
        } for r in res.data])

        # คำนวณอันดับ: เอารูปล่าสุด และนับจำนวนจุดที่ผ่าน
        summary = df.sort_values("เวลาล่าสุด", ascending=False).groupby("BIB").first().reset_index()
        counts = df.groupby("BIB").size().reset_index(name="คะแนนสะสม")
        
        final_df = pd.merge(summary, counts, on="BIB").sort_values(["คะแนนสะสม", "เวลาล่าสุด"], ascending=[False, True])
        
        # แสดงตารางสวยงาม
        st.dataframe(
            final_df[["Profile", "BIB", "ชื่อ-นามสกุล", "แผนก", "คะแนนสะสม", "จุดล่าสุด"]],
            column_config={"Profile": st.column_config.ImageColumn("รูปถ่าย")},
            use_container_width=True
        )
    else:
        st.info("ยังไม่มีข้อมูลการวิ่งในขณะนี้...")