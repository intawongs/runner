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
        st.error("❌ เช็ค Secrets ใน Streamlit Cloud")
        st.stop()

supabase = init_connection()
st.set_page_config(page_title="RCI AI Tracker", layout="wide")

# --- 2. Helpers ---
def get_next_bib():
    res = supabase.table("runners").select("bib_number").order("bib_number", desc=True).limit(1).execute()
    if not res.data: return "RCI-001"
    try:
        last_num = int(res.data[0]['bib_number'].split("-")[1])
        return f"RCI-{last_num + 1:03d}"
    except: return "RCI-001"

def upload_photo(file_bytes, filename):
    try:
        path = f"profile_{filename}.jpg"
        supabase.storage.from_("runner_photos").upload(path, file_bytes, {"content-type": "image/jpeg"})
        return supabase.storage.from_("runner_photos").get_public_url(path)
    except: return None

# --- 3. Menu ---
menu = st.sidebar.radio("เมนูหลัก", ["📝 ลงทะเบียนพนักงาน", "📷 จุดสแกน Checkpoint", "🏆 Leaderboard"])

# --- [ หน้าลงทะเบียน + ถ่ายรูป ] ---
if menu == "📝 ลงทะเบียนพนักงาน":
    st.header("📝 ลงทะเบียนและถ่ายรูปโปรไฟล์")
    
    if "reg_step" not in st.session_state:
        st.session_state.reg_step = "FORM"

    if st.session_state.reg_step == "FORM":
        next_bib = get_next_bib()
        with st.form("reg_form"):
            st.info(f"BIB ถัดไป: **{next_bib}**")
            name = st.text_input("ชื่อ-นามสกุล")
            dept = st.selectbox("แผนก", ["Production", "R&D", "QA", "Office", "Maintenance", "Logistics"])
            if st.form_submit_button("ถัดไป: ถ่ายรูป"):
                if name:
                    st.session_state.temp_data = {"bib": next_bib, "name": name, "dept": dept}
                    st.session_state.reg_step = "PHOTO"
                    st.rerun()
                else: st.warning("กรุณากรอกชื่อ")

    elif st.session_state.reg_step == "PHOTO":
        st.subheader(f"📸 ถ่ายรูปโปรไฟล์ (BIB: {st.session_state.temp_data['bib']})")
        profile_img = st.camera_input("กดถ่ายรูปหน้าตรง")
        
        if profile_img:
            with st.spinner("กำลังบันทึกข้อมูล..."):
                # 1. อัปโหลดรูปโปรไฟล์
                p_url = upload_photo(profile_img.getvalue(), st.session_state.temp_data['bib'])
                if p_url:
                    # 2. บันทึกลงตาราง runners (เพิ่มคอลัมน์ profile_url ใน SQL ด้วยนะคร้บ)
                    supabase.table("runners").insert({
                        "bib_number": st.session_state.temp_data['bib'],
                        "name": st.session_state.temp_data['name'],
                        "department": st.session_state.temp_data['dept'],
                        "profile_url": p_url # เก็บรูปไว้ที่นี่เลย
                    }).execute()
                    
                    # 3. เจน QR
                    qr = qrcode.make(st.session_state.temp_data['bib'])
                    buf = BytesIO()
                    qr.save(buf, format="PNG")
                    st.session_state.final_qr = buf.getvalue()
                    st.session_state.reg_step = "DONE"
                    st.rerun()
        
        if st.button("⬅️ กลับไปแก้ไขข้อมูล"):
            st.session_state.reg_step = "FORM"
            st.rerun()

    elif st.session_state.reg_step == "DONE":
        st.success(f"✅ ลงทะเบียนสำเร็จ! BIB: {st.session_state.temp_data['bib']}")
        st.image(st.session_state.final_qr, width=300, caption="👉 แคปหน้าจอรูปนี้ไว้ใช้สแกน")
        if st.button("ลงทะเบียนคนต่อไป"):
            st.session_state.reg_step = "FORM"
            del st.session_state.temp_data
            st.rerun()

# --- [ หน้าสแกน Checkpoint (สแกนอย่างเดียว) ] ---
# --- [ หน้าสแกน Checkpoint - ฉบับบันทึกแล้วรีเฟรช ] ---
elif menu == "จุดสแกนประจำจุด":
    st.header("📸 สแกน QR อัตโนมัติ")
    cp_loc = st.selectbox("เลือกจุดประจำการ", ["Start", "CP1", "CP2", "CP3", "Finish"])
    
    # 1. Cooldown เพื่อกันรันรัวๆ ในเสี้ยววินาที (0.5 วินาทีก็พอถ้าจะ rerun)
    if "last_scan_time" not in st.session_state:
        st.session_state.last_scan_time = 0

    st.info(f"💡 จ่อ QR เพื่อบันทึก (ระบบจะรีเซ็ตอัตโนมัติหลังสแกน)")

    # 2. เครื่องสแกน QR
    scanned_bib = qrcode_scanner(key=f"scanner_{cp_loc}")

    if scanned_bib:
        now = time.time()
        # เช็คว่าผ่านไปอย่างน้อย 2 วินาทีหรือยัง (ป้องกันการ rerun วนลูป)
        if (now - st.session_state.last_scan_time) > 2:
            st.session_state.last_scan_time = now # ล็อคเวลาทันที
            
            try:
                with st.spinner(f"กำลังบันทึก BIB: {scanned_bib}..."):
                    res = supabase.table("run_logs").insert({
                        "bib_number": scanned_bib,
                        "checkpoint_name": cp_loc
                    }).execute()
                    
                    if res.data:
                        st.success(f"✅ บันทึกสำเร็จ: {scanned_bib}")
                        st.toast(f"บันทึก {scanned_bib} เรียบร้อย", icon="✅")
                        
                        # 3. **หน่วงเวลา 1.5 วินาที** ให้เจ้าหน้าที่เห็นชื่อคนวิ่ง
                        time.sleep(1.5)
                        
                        # 4. **สั่ง Refresh จอ 1 ครั้ง** เพื่อรอคนใหม่
                        st.rerun() 
                        
            except Exception as e:
                st.error(f"เกิดข้อผิดพลาด: {e}")
                if st.button("รีเซ็ตหน้าจอ"):
                    st.rerun()

# --- [ Leaderboard (ดึงรูปจากตารางพนักงาน) ] ---
elif menu == "🏆 Leaderboard":
    st.header("🏆 อันดับนักวิ่ง Real-time")
    st_autorefresh(15000)
    
    # ดึงข้อมูลจาก log และเอารูปโปรไฟล์จากตาราง runners
    # ตัวอย่าง Logic ใน Leaderboard
    res = supabase.table("run_logs").select("*, runners(name, department, profile_url)").execute()
    if res.data:
        df = pd.DataFrame([{
            "รูป": r['runners']['profile_url'],
            "BIB": r['bib_number'],
            "ชื่อ": r['runners']['name'],
            "จุดล่าสุด": r['checkpoint_name'],
            "เวลา": r['scanned_at']
        } for r in res.data])
        
        # ดึงเฉพาะ Log ล่าสุดของแต่ละคน
        summary = df.sort_values("เวลา", ascending=False).groupby("BIB").first().reset_index()
        # นับจำนวนจุดสะสม
        count_df = df.groupby("BIB").size().reset_index(name="คะแนน")
        
        final = pd.merge(summary, count_df, on="BIB").sort_values("คะแนน", ascending=False)
        st.dataframe(final[["รูป", "BIB", "ชื่อ", "คะแนน", "จุดล่าสุด"]], 
                    column_config={"รูป": st.column_config.ImageColumn()})
    else:
        st.info("ยังไม่มีข้อมูลการเช็คอิน")