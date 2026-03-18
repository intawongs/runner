import streamlit as st
import pandas as pd
from supabase import create_client, Client
from streamlit_qrcode_scanner import qrcode_scanner
from streamlit_autorefresh import st_autorefresh
import qrcode
from io import BytesIO
from datetime import datetime
import time

# --- 1. การเชื่อมต่อ Supabase (ดึงจาก Secrets) ---
def init_connection():
    try:
        url = st.secrets["SUPABASE_URL"]
        key = st.secrets["SUPABASE_KEY"]
        return create_client(url, key)
    except Exception as e:
        st.error("❌ ไม่พบข้อมูล Secret หรือการเชื่อมต่อล้มเหลว")
        st.info("กรุณาเช็ค Settings > Secrets ใน Streamlit Cloud")
        st.stop()

supabase = init_connection()

st.set_page_config(page_title="RCI Tracking AI", layout="wide")

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
        supabase.storage.from_(bucket_name).upload(filepath, file_bytes, {"content-type": "image/jpeg"})
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
    
    # ใช้ Session State เก็บสถานะหลังบันทึก เพื่อเลี่ยง Error ใน Form
    if "reg_done" not in st.session_state:
        st.session_state.reg_done = False

    next_bib = get_next_bib()
    
    with st.form("register_form", clear_on_submit=True):
        st.info(f"BIB ที่จะได้รับ: **{next_bib}**")
        name = st.text_input("ชื่อ-นามสกุล")
        dept = st.selectbox("แผนก", ["Production", "R&D", "QA", "Logistics", "Office", "Maintenance"])
        submit_reg = st.form_submit_button("บันทึกข้อมูล")
        
        if submit_reg:
            if name:
                supabase.table("runners").insert({"bib_number": next_bib, "name": name, "department": dept}).execute()
                # เจน QR
                qr = qrcode.make(next_bib)
                buf = BytesIO()
                qr.save(buf, format="PNG")
                st.session_state.qr_buf = buf.getvalue()
                st.session_state.last_name = name
                st.session_state.last_bib = next_bib
                st.session_state.reg_done = True
            else:
                st.warning("กรุณาใส่ชื่อ")

    # แสดงผลนอก Form หลังบันทึกสำเร็จ
    if st.session_state.reg_done:
        st.success(f"ลงทะเบียนคุณ {st.session_state.last_name} (BIB: {st.session_state.last_bib}) สำเร็จ!")
        st.image(st.session_state.qr_buf, width=200)
        st.download_button("💾 ดาวน์โหลด QR Code", st.session_state.qr_buf, f"{st.session_state.last_bib}.png", "image/png")
        if st.button("ลงทะเบียนคนต่อไป"):
            st.session_state.reg_done = False
            st.rerun()

# --- PAGE 2: จุดสแกน (Checkpoint) ---
elif menu == "จุดสแกนประจำจุด":
    st.header("📸 สแกน QR + ถ่ายรูป")
    
    cp_loc = st.selectbox("เลือกจุดประจำการของคุณ", ["Start", "CP1", "CP2", "CP3", "CP4", "CP5", "Finish"])
    
    if "scanning_bib" not in st.session_state:
        st.session_state.scanning_bib = None

    # ขั้นตอนที่ 1: สแกน QR
    if st.session_state.scanning_bib is None:
        st.subheader("1. สแกน QR Code")
        scanned_val = qrcode_scanner(key="scanner_widget")
        if scanned_val:
            st.session_state.scanning_bib = scanned_val
            st.rerun()
            
    # ขั้นตอนที่ 2: ถ่ายรูป
    else:
        st.subheader(f"2. ถ่ายรูปยืนยัน (BIB: {st.session_state.scanning_bib})")
        cam_photo = st.camera_input("ถ่ายรูปพนักงาน")
        
        if cam_photo:
            with st.spinner("กำลังบันทึก..."):
                ts = datetime.now().strftime("%H%M%S")
                fname = f"{st.session_state.scanning_bib}_{cp_loc}_{ts}"
                p_url = upload_photo(cam_photo.getvalue(), fname)
                
                if p_url:
                    supabase.table("run_logs").insert({
                        "bib_number": st.session_state.scanning_bib,
                        "checkpoint_name": cp_loc,
                        "photo_url": p_url
                    }).execute()
                    st.success("บันทึกสำเร็จ!")
                    st.session_state.scanning_bib = None # Reset
                    time.sleep(1)
                    st.rerun()

# --- PAGE 3: LEADERBOARD ---
elif menu == "Leaderboard":
    st.header("🏆 อันดับนักวิ่ง Real-time")
    st_autorefresh(interval=15000, key="auto_refresh_board")

    # ดึงข้อมูลมาแสดงผล
    res = supabase.table("run_logs").select("*, runners(name, department)").execute()
    
    if res.data:
        raw_df = pd.DataFrame([{
            "รูป": r['photo_url'], "BIB": r['bib_number'], "ชื่อ": r['runners']['name'],
            "แผนก": r['runners']['department'], "จุด": r['checkpoint_name'], "เวลา": r['scanned_at']
        } for r in res.data])
        
        # จัดลำดับ: นับจำนวนจุด และเอารูปล่าสุด
        summary = raw_df.sort_values("เวลา", ascending=False).groupby("BIB").first().reset_index()
        count_data = raw_df.groupby("BIB").size().reset_index(name="จุดสะสม")
        final_df = pd.merge(summary, count_data, on="BIB").sort_values("จุดสะสม", ascending=False)
        
        # แสดง Top 3 Podium
        top_cols = st.columns(3)
        for i in range(min(3, len(final_df))):
            with top_cols[i]:
                st.image(final_df.iloc[i]['รูป'], width=150)
                st.metric(f"อันดับ {i+1}", final_df.iloc[i]['ชื่อ'], f"{final_df.iloc[i]['จุดสะสม']} จุด")

        st.divider()
        # ตารางข้อมูล
        st.dataframe(
            final_df[["รูป", "BIB", "ชื่อ", "แผนก", "จุดสะสม", "จุด"]],
            column_config={"รูป": st.column_config.ImageColumn("รูปถ่าย")},
            use_container_width=True
        )
    else:
        st.info("รอข้อมูลการวิ่ง...")