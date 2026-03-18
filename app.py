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
# --- [ หน้า 3: Leaderboard Map - ฉบับ Grid Anti-Overlap 100% ] ---
elif menu == "🏆 Leaderboard Map":
    st.header("🏆 RCI Real-time Map (Multi-User View)")
    # รีเฟรชหน้าจออัตโนมัติทุก 15 วินาที
    st_autorefresh(interval=15000, key="map_refresh_grid")
    
    MAP_FILE = "map.png" 
    
    if os.path.exists(MAP_FILE):
        try:
            # 1. โหลดรูปแผนที่โรงงาน RCI
            bg = Image.open(MAP_FILE).convert("RGBA")
            canvas = bg.copy()
            draw = ImageDraw.Draw(canvas)

            # 2. ดึงข้อมูล Log ทั้งหมดจาก Supabase
            res = supabase.table("run_logs").select("*, runners(name, profile_url)").order("scanned_at", desc=True).execute()
            
            if res.data:
                df = pd.DataFrame(res.data)
                
                # ---LOGIC สำคัญ 1: หาจุดล่าสุดของพนักงานแต่ละคน ---
                # (1 คนมี 1 ที่อยู่เสมอ เพื่อไม่ให้รูปค้างที่จุดเก่า)
                latest_per_runner = df.sort_values("scanned_at", ascending=False).groupby("bib_number").first().reset_index()

                # --- LOGIC สำคัญ 2: หาคนล่าสุดรายแผนก (Optional) ---
                # เราจะโชว์เฉพาะคนล่าสุดของแต่ละแผนกที่อยู่ที่จุดนี้ เพื่อประหยัดพื้นที่
                # display_on_map = latest_per_runner.sort_values("scanned_at", ascending=False).groupby(["checkpoint_name", "runners.department"]).first().reset_index()
                
                # แต่สำหรับคุณ ผมตั้งให้โชว์ "3 คนล่าสุด" ของจุดนั้นๆ เพื่อไม่ให้รูปเต็มเกินไป
                display_on_map = latest_per_runner.sort_values("scanned_at", ascending=False).groupby("checkpoint_name").head(3)

                # 3. พิกัดหลักที่คุณระบุมา (ต้องตั้งเป็น int)
                BASE_POINTS = {
                    "Checkpoint 1": (715, 390),
                    "Checkpoint 2": (715, 190),
                    "Start": (1250, 1750),
                    "Finish": (1400, 1500) # แยก Finish ออกจาก Start สักนิดเพื่อให้เห็นชัด
                }

                # 4. วนลูปราย Checkpoint เพื่อสร้าง Grid และวางรูป
                for cp_name, base_pos in BASE_POINTS.items():
                    # ดึงกลุ่มคนล่าสุดที่อยู่ที่จุดนี้
                    runners_at_cp = display_on_map[display_on_map['checkpoint_name'] == cp_name]
                    
                    # --- สร้าง Grid 3x3 (ตาราง 9 ช่อง) รอบพิกัดหลัก ---
                    # รูปพนักงานขนาด 120x120 เราจะเผื่อช่องว่าง (Gap) 20 พิกเซล
                    img_size = 120
                    gap = 20
                    total_step = img_size + gap # 140 พิกเซล ต่อช่อง

                    # เริ่มวางรูปจากมุมซ้ายบนของ Grid เพื่อให้พิกัดหลักอยู่กึ่งกลาง
                    start_x = base_pos[0] - (total_step * 1.5) # ขยับซ้ายไป 1.5 ช่อง
                    start_y = base_pos[1] - (total_step * 1.5) # ขยับบนไป 1.5 ช่อง

                    for i, r in enumerate(runners_at_cp.iterrows()):
                        idx, row = r
                        if row['runners']['profile_url']:
                            try:
                                # คำนวณแถว (Row) และคอลัมน์ (Col) ของช่องในตาราง (0-2)
                                row_idx = i // 3
                                col_idx = i % 3
                                
                                # ถ้าเกิน 9 คน (i >= 9) ให้หยุดวาดจุดนี้
                                if row_idx > 2: break 

                                # ดึงและจัดการรูปโปรไฟล์
                                p_res = requests.get(row['runners']['profile_url'])
                                p_img = Image.open(BytesIO(p_res.content)).convert("RGBA")
                                p_img = ImageOps.fit(p_img, (img_size, img_size), centering=(0.5, 0.5))
                                
                                mask = Image.new('L', (img_size, img_size), 0)
                                ImageDraw.Draw(mask).ellipse((0, 0, img_size, img_size), fill=255)
                                
                                # --- คำนวณตำแหน่งพิกัดในช่อง Grid ---
                                pos_x = int(start_x + (col_idx * total_step))
                                pos_y = int(start_y + (row_idx * total_step))
                                
                                # วางรูปลงแผนที่
                                canvas.paste(p_img, (pos_x, pos_y), mask)
                                
                                # วาดเส้นขอบ (คนล่าสุดi==0 ขอบสีฟ้า Neon)
                                color = "#00FFFF" if i == 0 else "#FFFFFF"
                                draw.ellipse([pos_x, pos_y, pos_x+img_size, pos_y+img_size], outline=color, width=6)
                                
                            except:
                                continue

            # 5. แสดงผลรูปแผนที่บน Streamlit
            st.image(canvas, use_container_width=True, caption="📍 แผนที่แสดงตำแหน่งพนักงานล่าสุด (1 จุด มีได้สูงสุด 9 คน)")
            
        except Exception as e:
            st.error(f"❌ เกิดข้อผิดพลาดในการประมวลผลแผนที่: {e}")
    else:
        st.error(f"❌ ไม่พบไฟล์รูป '{MAP_FILE}' ในโฟลเดอร์แอป")
        st.info("กรุณาตรวจสอบว่าได้อัปโหลดรูปแผนที่ขึ้น GitHub เรียบร้อยแล้ว")

    # --- ส่วนตารางคะแนน (แสดงทุกคนเพื่อความชัดเจน) ---
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