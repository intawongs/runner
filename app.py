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
# --- [ หน้า 3: Leaderboard Map - แสดงเฉพาะพิกัดล่าสุดของแต่ละคน ] ---
# --- [ หน้า 3: Leaderboard Map - ฉบับกระจายรูปไม่ให้ทับกัน ] ---
elif menu == "🏆 Leaderboard Map":
    st.header("🏆 RCI Real-time Map (Latest Activity)")
    st_autorefresh(interval=10000, key="map_refresh")
    
    MAP_FILE = "Gemini_Generated_Image_2fhehv2fhehv2fhe.png" 
    
    if os.path.exists(MAP_FILE):
        try:
            bg = Image.open(MAP_FILE).convert("RGBA")
            canvas = bg.copy()
            draw = ImageDraw.Draw(canvas)

            # 1. ดึงข้อมูล Log ทั้งหมด
            res = supabase.table("run_logs").select("*, runners(name, profile_url)").order("scanned_at", desc=True).execute()
            
            if res.data:
                df = pd.DataFrame(res.data)
                
                # 2. หาจุดล่าสุดของพนักงานแต่ละคน (1 คนมี 1 ที่อยู่)
                latest_per_runner = df.sort_values("scanned_at", ascending=False).groupby("bib_number").first().reset_index()

                # 3. พิกัดที่คุณระบุมา (ใช้ค่าที่คุณตั้งไว้)
                POINTS = {
                    "Checkpoint 1": (715, 390),
                    "Checkpoint 2": (715, 190),
                    "Start": (1250, 1750),
                    "Finish": (1250, 1750)
                }

                # 4. วนลูปราย Checkpoint เพื่อวาดรูป "กลุ่มคนล่าสุด"
                for cp_name, base_pos in POINTS.items():
                    # ดึง 3 คนล่าสุดที่อยู่ที่จุดนี้ (และต้องเป็นจุดล่าสุดของเขาจริงๆ)
                    runners_at_cp = latest_per_runner[latest_per_runner['checkpoint_name'] == cp_name].head(3)
                    
                    # ตัวแปรสำหรับขยับตำแหน่ง (Offset)
                    # เริ่มต้นที่ 0 (คนแรกอยู่ที่จุดเป๊ะๆ) คนถัดไปจะเยื้องออกไป
                    step_x = 0
                    step_y = 0

                    for i, r in enumerate(runners_at_cp.iloc[::-1].iterrows()): # วาดคนเก่าก่อน คนใหม่จะได้ทับข้างบน
                        idx, row = r
                        if row['runners']['profile_url']:
                            try:
                                p_res = requests.get(row['runners']['profile_url'])
                                p_img = Image.open(BytesIO(p_res.content)).convert("RGBA")
                                
                                # ขนาดรูป (ปรับให้เหมาะกับพิกัดหลักพัน)
                                size = (120, 120) 
                                p_img = ImageOps.fit(p_img, size, centering=(0.5, 0.5))
                                mask = Image.new('L', size, 0)
                                ImageDraw.Draw(mask).ellipse((0, 0) + size, fill=255)
                                
                                # คำนวณตำแหน่งเยื้อง (กระจายออกไปทางขวา+ล่าง)
                                pos_x = base_pos[0] - (size[0]//2) + step_x
                                pos_y = base_pos[1] - (size[1]//2) + step_y
                                
                                canvas.paste(p_img, (pos_x, pos_y), mask)
                                
                                # วาดเส้นขอบ (ถ้าเป็นคนล่าสุด i == 2 ให้ขอบสีฟ้า Neon)
                                color = "#00FFFF" if i == len(runners_at_cp)-1 else "#FFFFFF"
                                draw.ellipse([pos_x, pos_y, pos_x+size[0], pos_y+size[1]], outline=color, width=6)
                                
                                # เพิ่มค่าเยื้องสำหรับคนถัดไป
                                step_x += 50 
                                step_y += 40 
                            except:
                                continue

            st.image(canvas, use_container_width=True)
            
        except Exception as e:
            st.error(f"Error: {e}")
    else:
        st.error(f"ไม่พบไฟล์รูป {MAP_FILE}")

    # --- ตาราง Leaderboard ด้านล่าง ---
    st.divider()
    # ... (โค้ดตารางด้านล่างคงเดิม) ...

    # --- ส่วนตารางคะแนน (แสดงทุกคนเพื่อความชัดเจน) ---
    st.divider()
    st.subheader("📊 อันดับนักวิ่งทั้งหมด")
    
    # ดึงข้อมูลมาแสดงเป็นตารางปกติไว้ด้านล่างแผนที่
    if res.data:
        df_all = pd.DataFrame([{
            "Profile": r['runners']['profile_url'],
            "BIB": r['bib_number'],
            "ชื่อ": r['runners']['name'],
            "จุดล่าสุด": r['checkpoint_name'],
            "เวลาล่าสุด": r['scanned_at']
        } for r in res.data])
        
        # จัดกลุ่มเพื่อหาคะแนนสะสม (จำนวนจุดที่ผ่าน)
        summary = df_all.sort_values("เวลาล่าสุด", ascending=False).groupby("BIB").first().reset_index()
        counts = df_all.groupby("BIB").size().reset_index(name="คะแนนสะสม")
        final_table = pd.merge(summary, counts, on="BIB").sort_values(["คะแนนสะสม", "เวลาล่าสุด"], ascending=[False, True])
        
        st.dataframe(
            final_table[["Profile", "BIB", "ชื่อ", "คะแนนสะสม", "จุดล่าสุด"]],
            column_config={"Profile": st.column_config.ImageColumn("รูปถ่าย")},
            use_container_width=True
        )