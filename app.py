import streamlit as st
import pandas as pd
from supabase import create_client, Client
from streamlit_qrcode_scanner import qrcode_scanner
from streamlit_autorefresh import st_autorefresh
import qrcode
from io import BytesIO
from datetime import datetime
import time
import requests
from PIL import Image, ImageDraw, ImageOps
import os

# --- 1. การตั้งค่าระบบและการเชื่อมต่อ ---
st.set_page_config(page_title="RCI Walk Rally AI Tracker", layout="wide")

def init_connection():
    try:
        url = st.secrets["SUPABASE_URL"]
        key = st.secrets["SUPABASE_KEY"]
        return create_client(url, key)
    except:
        st.error("❌ กรุณาตั้งค่า Secrets ใน Streamlit Cloud")
        st.stop()

supabase = init_connection()

# --- 2. Helper Functions ---
def get_next_bib():
    try:
        res = supabase.table("runners").select("bib_number").order("bib_number", desc=True).limit(1).execute()
        if not res.data: return "RCI-001"
        last_num = int(res.data[0]['bib_number'].split("-")[1])
        return f"RCI-{last_num + 1:03d}"
    except: return "RCI-001"

def upload_photo(file_bytes, filename):
    try:
        path = f"profile_{filename}.jpg"
        supabase.storage.from_("runner_photos").upload(path, file_bytes, {"content-type": "image/jpeg"})
        return supabase.storage.from_("runner_photos").get_public_url(path)
    except: return None

# --- 3. Sidebar Menu ---
st.sidebar.title("🏃 RCI AI Tracker")
menu = st.sidebar.radio("เมนูหลัก", ["📝 ลงทะเบียนพนักงาน", "📸 จุดสแกน Checkpoint", "🏆 Leaderboard Map"])

# --- [ หน้า 1: ลงทะเบียนพนักงาน + ถ่ายรูป ] ---
if menu == "📝 ลงทะเบียนพนักงาน":
    st.header("📝 ลงทะเบียนและถ่ายรูปโปรไฟล์")
    if "reg_step" not in st.session_state: st.session_state.reg_step = "FORM"

    if st.session_state.reg_step == "FORM":
        next_bib = get_next_bib()
        with st.form("reg_form"):
            st.info(f"BIB ถัดไป: **{next_bib}**")
            name = st.text_input("ชื่อ-นามสกุล")
            dept = st.selectbox("แผนก", ["Production", "R&D", "QA", "Logistics", "Office", "Maintenance"])
            if st.form_submit_button("ถัดไป: ถ่ายรูป"):
                if name:
                    st.session_state.temp_user = {"bib": next_bib, "name": name, "dept": dept}
                    st.session_state.reg_step = "PHOTO"
                    st.rerun()
                else: st.warning("กรุณากรอกชื่อ")

    elif st.session_state.reg_step == "PHOTO":
        st.subheader(f"📸 ถ่ายรูปโปรไฟล์: {st.session_state.temp_user['name']}")
        img_file = st.camera_input("กดถ่ายรูปหน้าตรง")
        if img_file:
            with st.spinner("กำลังบันทึก..."):
                p_url = upload_photo(img_file.getvalue(), st.session_state.temp_user['bib'])
                if p_url:
                    supabase.table("runners").insert({
                        "bib_number": st.session_state.temp_user['bib'], "name": st.session_state.temp_user['name'],
                        "department": st.session_state.temp_user['dept'], "profile_url": p_url
                    }).execute()
                    qr = qrcode.make(st.session_state.temp_user['bib'])
                    buf = BytesIO(); qr.save(buf, format="PNG")
                    st.session_state.reg_qr = buf.getvalue()
                    st.session_state.reg_step = "DONE"
                    st.rerun()

    elif st.session_state.reg_step == "DONE":
        st.success(f"✅ สำเร็จ! BIB: {st.session_state.temp_user['bib']}")
        st.image(st.session_state.reg_qr, width=300, caption="👉 แคปหน้าจอรูปนี้ไว้สแกน")
        if st.button("ลงทะเบียนคนถัดไป"):
            st.session_state.reg_step = "FORM"; st.rerun()

# --- [ หน้า 2: จุดสแกน Checkpoint (Auto & Refresh) ] ---
elif menu == "📸 จุดสแกน Checkpoint":
    st.header("📸 สแกน QR เช็คอิน")
    cp_loc = st.selectbox("📍 คุณอยู่จุดไหน?", ["Start", "Checkpoint 1", "Checkpoint 2", "Finish"])
    
    if "is_saving" not in st.session_state: st.session_state.is_saving = False

    if not st.session_state.is_saving:
        st.info(f"🔍 รอสแกนที่จุด: {cp_loc}")
        val = qrcode_scanner(key=f"scanner_{cp_loc}")
        if val:
            st.session_state.is_saving = True
            st.session_state.curr_bib = val
            st.rerun()
    else:
        with st.status(f"🚀 กำลังบันทึก {st.session_state.curr_bib}...") as s:
            try:
                supabase.table("run_logs").insert({"bib_number": st.session_state.curr_bib, "checkpoint_name": cp_loc}).execute()
                s.update(label="✅ บันทึกสำเร็จ!", state="complete")
                st.balloons(); time.sleep(1.5)
                st.session_state.is_saving = False; st.rerun()
            except:
                st.error("Error!"); st.session_state.is_saving = False; st.button("Reset")

# --- [ หน้า 3: Leaderboard Map (Dynamic Map) ] ---
# --- [ หน้า 3: Leaderboard Map (ฉบับเช็คไฟล์ละเอียด) ] ---
elif menu == "🏆 Leaderboard Map":
    st.header("🏆 RCI Real-time Map")
    st_autorefresh(interval=10000, key="map_refresh")
    
    # 1. ระบุชื่อไฟล์ (เช็คให้ตรงกับที่อัปโหลดขึ้น GitHub)
    MAP_FILE = "Gemini_Generated_Image_2fhehv2fhehv2fhe.png" 
    
    # ตรวจสอบว่าไฟล์มีตัวตนอยู่ใน Server ไหม
    if os.path.exists(MAP_FILE):
        try:
            # 2. โหลดรูปพื้นหลัง
            bg = Image.open(MAP_FILE).convert("RGBA")
            canvas = bg.copy()
            draw = ImageDraw.Draw(canvas)

            # 3. ดึงข้อมูลนักวิ่งล่าสุด
            res = supabase.table("run_logs").select("*, runners(name, profile_url)").order("scanned_at", desc=True).execute()
            
            if res.data:
                df = pd.DataFrame(res.data)
                # พิกัด x, y (Checkpoint 1 อยู่ล่าง, 2 อยู่บน)
                POINTS = {
                    "Checkpoint 1": (530, 800), 
                    "Checkpoint 2": (580, 350),
                    "Start": (530, 800),
                    "Finish": (850, 560)
                }

                # ดึงคนล่าสุดของแต่ละจุดมาแปะ
                latest = df.groupby("checkpoint_name").first().reset_index()
                for _, r in latest.iterrows():
                    cp = r['checkpoint_name']
                    if cp in POINTS and r['runners']['profile_url']:
                        try:
                            # โหลดรูปโปรไฟล์พนักงานจาก URL
                            p_res = requests.get(r['runners']['profile_url'])
                            p_img = Image.open(BytesIO(p_res.content)).convert("RGBA")
                            
                            # ทำรูปเป็นวงกลม
                            size = (120, 120)
                            p_img = ImageOps.fit(p_img, size, centering=(0.5, 0.5))
                            mask = Image.new('L', size, 0)
                            draw_mask = ImageDraw.Draw(mask)
                            draw_mask.ellipse((0, 0) + size, fill=255)
                            
                            # วางรูปลงพิกัด
                            pos = POINTS[cp]
                            offset = (pos[0]-size[0]//2, pos[1]-size[1]//2)
                            canvas.paste(p_img, offset, mask)
                            
                            # วาดวงกลมเรืองแสงรอบรูป
                            draw.ellipse([offset, (offset[0]+size[0], offset[1]+size[1])], outline="#00FFFF", width=8)
                        except:
                            continue # ถ้าโหลดรูปคนนี้ไม่ได้ ให้ข้ามไปคนถัดไป

            # 4. แสดงรูปแผนที่
            st.image(canvas, use_container_width=True, caption="📍 แผนที่แสดงตำแหน่งนักวิ่งล่าสุดรายจุด")
            
        except Exception as e:
            st.error(f"❌ โหลดรูปแผนที่ไม่ได้: {e}")
    else:
        # ถ้าหาไฟล์ไม่เจอ จะแสดงข้อความเตือนนี้
        st.error(f"❌ ไม่พบไฟล์รูป '{MAP_FILE}' ในโฟลเดอร์หลัก")
        st.info("💡 วิธีแก้: ตรวจสอบว่าคุณได้อัปโหลดไฟล์รูปนี้ขึ้น GitHub หรือยัง? และชื่อไฟล์สะกดถูกต้องหรือไม่?")
        # ลองลิสต์ไฟล์ที่มีทั้งหมดในโฟลเดอร์ออกมาดู (เพื่อ Debug)
        st.write("ไฟล์ที่พบในเครื่องขณะนี้:", os.listdir("."))
    
    # ตาราง Leaderboard ด้านล่าง
    st.divider()
    res_all = supabase.table("run_logs").select("*, runners(name, department, profile_url)").execute()
    if res_all.data:
        df_all = pd.DataFrame([{ "รูป": r['runners']['profile_url'], "BIB": r['bib_number'], "ชื่อ": r['runners']['name'], "แผนก": r['runners']['department'], "จุด": r['checkpoint_name'], "เวลา": r['scanned_at'] } for r in res_all.data])
        sum_df = df_all.sort_values("เวลา", ascending=False).groupby("BIB").first().reset_index()
        cnt_df = df_all.groupby("BIB").size().reset_index(name="คะแนน")
        final = pd.merge(sum_df, cnt_df, on="BIB").sort_values("คะแนน", ascending=False)
        st.dataframe(final[["รูป", "BIB", "ชื่อ", "คะแนน", "จุด"]], column_config={"รูป": st.column_config.ImageColumn()})