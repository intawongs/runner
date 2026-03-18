import streamlit as st
import pandas as pd
from supabase import create_client, Client
from streamlit_qrcode_scanner import qrcode_scanner
from streamlit_autorefresh import st_autorefresh
import qrcode
from io import BytesIO
from datetime import datetime
import time

# --- 1. Connection ---
def init_connection():
    try:
        url = st.secrets["SUPABASE_URL"]
        key = st.secrets["SUPABASE_KEY"]
        return create_client(url, key)
    except:
        st.error("❌ เช็ค Secrets: SUPABASE_URL และ SUPABASE_KEY")
        st.stop()

supabase = init_connection()
st.set_page_config(page_title="RCI AI Tracker", layout="wide")

# --- 2. Helper ---
def get_next_bib():
    res = supabase.table("runners").select("bib_number").order("bib_number", desc=True).limit(1).execute()
    if not res.data: return "RCI-001"
    try:
        last_num = int(res.data[0]['bib_number'].split("-")[1])
        return f"RCI-{last_num + 1:03d}"
    except: return "RCI-001"

def upload_photo(file_bytes, filename):
    try:
        path = f"{filename}.jpg"
        supabase.storage.from_("runner_photos").upload(path, file_bytes, {"content-type": "image/jpeg"})
        return supabase.storage.from_("runner_photos").get_public_url(path)
    except: return None

# --- 3. Menu ---
menu = st.sidebar.radio("เมนู", ["ลงทะเบียน", "สแกนและถ่ายรูป", "Leaderboard"])

# --- หน้าลงทะเบียน ---
if menu == "ลงทะเบียน":
    st.header("📝 ลงทะเบียน (ไม่ต้องกดโหลดรูป)")
    next_bib = get_next_bib()
    
    with st.form("reg_form", clear_on_submit=True):
        name = st.text_input("ชื่อ-นามสกุล")
        dept = st.selectbox("แผนก", ["Production", "R&D", "QA", "Office"])
        if st.form_submit_button("บันทึกข้อมูล"):
            if name:
                supabase.table("runners").insert({"bib_number": next_bib, "name": name, "department": dept}).execute()
                qr = qrcode.make(next_bib)
                buf = BytesIO()
                qr.save(buf, format="PNG")
                st.session_state.last_qr = buf.getvalue()
                st.session_state.last_bib = next_bib
                st.session_state.is_reg = True
            else: st.warning("ใส่ชื่อด้วยครับ")

    if st.get_option("registration_status", False) or "is_reg" in st.session_state:
        if st.session_state.get("is_reg"):
            st.success(f"ลงทะเบียนสำเร็จ! BIB: {st.session_state.last_bib}")
            st.image(st.session_state.last_qr, caption="👉 แคปหน้าจอรูปนี้ไว้ใช้วิ่ง", width=300)
            if st.button("ตกลง (ลงทะเบียนคนต่อไป)"):
                st.session_state.is_reg = False
                st.rerun()

# --- หน้าสแกนและถ่ายรูป (หัวใจสำคัญ) ---
elif menu == "สแกนและถ่ายรูป":
    st.header("📸 จุดสแกน QR + ถ่ายรูป")
    cp = st.selectbox("จุดประจำการ", ["Start", "CP1", "CP2", "CP3", "Finish"])
    
    # ใช้สถานะเพื่อสลับหน้าจอระหว่าง "สแกน" กับ "ถ่ายรูป"
    if "step" not in st.session_state:
        st.session_state.step = "scan"
        st.session_state.temp_bib = None

    if st.session_state.step == "scan":
        st.subheader("1️⃣ ขั้นตอนการสแกน QR")
        # เมื่อสแกนติด ค่าจะถูกส่งมาที่ val
        val = qrcode_scanner(key="scanner_active")
        if val:
            st.session_state.temp_bib = val
            st.session_state.step = "photo"
            st.rerun() # บังคับปิดกล้องสแกนทันทีเพื่อเปิดกล้องถ่ายรูป

    elif st.session_state.step == "photo":
        st.subheader(f"2️⃣ ขั้นตอนการถ่ายรูป (BIB: {st.session_state.temp_bib})")
        # ช่องถ่ายรูปของ Streamlit
        img_file = st.camera_input("กดถ่ายรูปพนักงาน")
        
        if img_file:
            with st.spinner("กำลังส่งข้อมูล..."):
                fname = f"{st.session_state.temp_bib}_{int(time.time())}"
                url = upload_photo(img_file.getvalue(), fname)
                if url:
                    supabase.table("run_logs").insert({
                        "bib_number": st.session_state.temp_bib,
                        "checkpoint_name": cp,
                        "photo_url": url
                    }).execute()
                    st.success("บันทึกเรียบร้อย!")
                    time.sleep(1)
                    st.session_state.step = "scan" # กลับไปรอสแกนคนใหม่
                    st.session_state.temp_bib = None
                    st.rerun()
        
        if st.button("ยกเลิก / สแกนใหม่"):
            st.session_state.step = "scan"
            st.rerun()

# --- Leaderboard ---
elif menu == "Leaderboard":
    st.header("🏆 Leaderboard")
    st_autorefresh(15000)
    res = supabase.table("run_logs").select("*, runners(name, department)").execute()
    if res.data:
        df = pd.DataFrame([{
            "รูป": r['photo_url'], "BIB": r['bib_number'], "ชื่อ": r['runners']['name'],
            "แผนก": r['runners']['department'], "จุด": r['checkpoint_name'], "เวลา": r['scanned_at']
        } for r in res.data])
        # แสดงรูปล่าสุด
        summary = df.sort_values("เวลา", ascending=False).groupby("BIB").first().reset_index()
        st.dataframe(summary[["รูป", "BIB", "ชื่อ", "แผนก", "จุด"]], 
                     column_config={"รูป": st.column_config.ImageColumn()})