import streamlit as st
import pandas as pd
from supabase import create_client, Client
from streamlit_qrcode_scanner import qrcode_scanner
from streamlit_autorefresh import st_autorefresh
import qrcode
from io import BytesIO
from datetime import datetime
import time

# --- 1. Connection using Secrets ---
# Streamlit จะอ่านค่าจาก .streamlit/secrets.toml (Local) 
# หรือจากหน้า Advanced Settings (Cloud) ให้อัตโนมัติ
try:
    url = st.secrets["SUPABASE_URL"]
    key = st.secrets["SUPABASE_KEY"]
    supabase: Client = create_client(url, key)
except Exception as e:
    st.error("❌ ไม่พบข้อมูลการเชื่อมต่อ Supabase ใน Secrets")
    st.stop()

st.set_page_config(page_title="RCI Tracking System", layout="wide")

# --- 2. Helper Functions ---
def get_next_bib():
    res = supabase.table("runners").select("bib_number").order("bib_number", desc=True).limit(1).execute()
    if not res.data:
        return "RCI-001"
    last_bib = res.data[0]['bib_number']
    try:
        last_num = int(last_bib.split("-")[1])
        return f"RCI-{last_num + 1:03d}"
    except:
        return "RCI-ERR"

def upload_photo(file_bytes, filename):
    try:
        bucket_name = "runner_photos"
        filepath = f"{filename}.jpg"
        supabase.storage.from_(bucket_name).upload(filepath, file_bytes, {"content-type": "image/jpeg"})
        res = supabase.storage.from_(bucket_name).get_public_url(filepath)
        return res
    except Exception as e:
        st.error(f"Error uploading photo: {e}")
        return None

# --- 3. Sidebar Navigation ---
menu = st.sidebar.radio("เมนูใช้งาน", ["📝 ลงทะเบียนนักวิ่ง", "📸 จุดสแกน+ถ่ายรูป", "🏆 Leaderboard"])

# --- PAGE 1: REGISTER (Fixed Version) ---
if menu == "📝 ลงทะเบียนนักวิ่ง (Admin)":
    st.header("📝 ลงทะเบียนพนักงาน (Auto BIB)")
    next_bib = get_next_bib()
    
    # สร้างตัวแปรใน session_state เพื่อเก็บข้อมูล QR หลังกด Submit
    if "reg_success" not in st.session_state:
        st.session_state.reg_success = False
        st.session_state.last_bib = ""
        st.session_state.qr_buffer = None

    with st.form("reg_form", clear_on_submit=True):
        st.info(f"หมายเลข BIB ถัดไปคือ: **{next_bib}**")
        bib = st.text_input("หมายเลข BIB", value=next_bib, disabled=True)
        name = st.text_input("ชื่อ-นามสกุลพนักงาน")
        dept = st.selectbox("แผนก", ["Production", "R&D", "QA", "Logistics", "Maintenance", "Office"])
        
        submitted = st.form_submit_button("บันทึกและเจน QR")
        
        if submitted:
            if name:
                try:
                    # 1. บันทึกลง Supabase
                    supabase.table("runners").insert({"bib_number": bib, "name": name, "department": dept}).execute()
                    
                    # 2. เจน QR Code และเก็บลง Buffer
                    qr_img = qrcode.make(bib)
                    buf = BytesIO()
                    qr_img.save(buf, format="PNG")
                    
                    # 3. เก็บสถานะลง Session State (เพื่อเอาไปแสดงผลนอก Form)
                    st.session_state.reg_success = True
                    st.session_state.last_bib = bib
                    st.session_state.qr_buffer = buf.getvalue()
                    
                except Exception as e:
                    st.error(f"เกิดข้อผิดพลาด: {e}")
            else:
                st.warning("กรุณากรอกชื่อพนักงาน")

    # --- ส่วนที่แสดงผลนอก Form (หลังกด Submit สำเร็จ) ---
    if st.session_state.reg_success:
        st.success(f"ลงทะเบียน BIB: {st.session_state.last_bib} เรียบร้อย!")
        st.image(st.session_state.qr_buffer, caption=f"QR Code: {st.session_state.last_bib}")
        
        # ย้ายปุ่มดาวน์โหลดมาไว้นอก Form ตรงนี้ครับ ✅
        st.download_button(
            label="💾 ดาวน์โหลดรูป QR",
            data=st.session_state.qr_buffer,
            file_name=f"{st.session_state.last_bib}.png",
            mime="image/png"
        )
        
        if st.button("ลงทะเบียนคนถัดไป"):
            st.session_state.reg_success = False
            st.rerun()

# --- PAGE 2: CHECKPOINT ---
elif menu == "📸 จุดสแกน+ถ่ายรูป":
    st.header("📸 จุดสแกน QR + ถ่ายรูป")
    cp_location = st.selectbox("จุดประจำการ", ["Start", "CP1", "CP2", "CP3", "Finish"])
    
    if "current_bib" not in st.session_state:
        st.session_state.current_bib = None

    if st.session_state.current_bib is None:
        st.subheader("สแกน QR Code")
        qr_data = qrcode_scanner(key="scanner")
        if qr_data:
            st.session_state.current_bib = qr_data
            st.rerun()
    else:
        bib = st.session_state.current_bib
        st.subheader(f"ถ่ายรูปยืนยัน (BIB: {bib})")
        photo = st.camera_input("กดถ่ายรูป")
        
        if photo:
            with st.spinner("บันทึกข้อมูล..."):
                ts = datetime.now().strftime("%Y%m%d_%H%M%S")
                filename = f"{bib}_{cp_location}_{ts}"
                url = upload_photo(photo.getvalue(), filename)
                if url:
                    supabase.table("run_logs").insert({
                        "bib_number": bib, "checkpoint_name": cp_location, "photo_url": url
                    }).execute()
                    st.success(f"บันทึกสำเร็จ!")
                    del st.session_state.current_bib
                    time.sleep(2)
                    st.rerun()

# --- PAGE 3: LEADERBOARD ---
elif menu == "🏆 Leaderboard":
    st.header("🏆 อันดับนักวิ่ง Real-time")
    st_autorefresh(interval=15000, key="refresh")
    
    res = supabase.table("run_logs").select("*, runners(name, department)").execute()
    if res.data:
        df = pd.DataFrame([{
            "รูป": r['photo_url'], "BIB": r['bib_number'], "ชื่อ": r['runners']['name'],
            "แผนก": r['runners']['department'], "จุด": r['checkpoint_name'], "เวลา": r['scanned_at']
        } for r in res.data])
        
        summary = df.sort_values("เวลา", ascending=False).groupby("BIB").first().reset_index()
        count_df = df.groupby("BIB").size().reset_index(name="จำนวนจุด")
        summary = pd.merge(summary, count_df, on="BIB").sort_values("จำนวนจุด", ascending=False)
        
        st.dataframe(
            summary[["รูป", "BIB", "ชื่อ", "แผนก", "จำนวนจุด", "จุด"]],
            column_config={"รูป": st.column_config.ImageColumn("รูปถ่าย")},
            use_container_width=True
        )