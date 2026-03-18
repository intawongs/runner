import streamlit as st
import pandas as pd
from supabase import create_client, Client
from streamlit_qrcode_scanner import qrcode_scanner
from streamlit_autorefresh import st_autorefresh
import qrcode
from io import BytesIO
import time
import requests
from PIL import Image, ImageDraw, ImageOps
import os

# --- 1. CONFIG & CONNECTION ---
st.set_page_config(page_title="RCI AI Tracker 2026", layout="wide")

def init_connection():
    try:
        return create_client(st.secrets["SUPABASE_URL"], st.secrets["SUPABASE_KEY"])
    except:
        st.error("❌ เช็ค Secrets ใน Streamlit Cloud (URL/KEY)")
        st.stop()

supabase = init_connection()

# --- 2. AUDIO FUNCTION (เสียงติ๊ด) ---
def play_beep():
    # ใช้เสียง Beep จาก URL มาตรฐาน
    beep_html = """
        <audio autoplay>
            <source src="https://www.soundjay.com/button/beep-07.wav" type="audio/wav">
        </audio>
    """
    st.components.v1.html(beep_html, height=0)

# --- 3. HELPER FUNCTIONS ---
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

# --- 4. SIDEBAR MENU ---
st.sidebar.title("🏃 RCI AI Tracker")
menu = st.sidebar.radio("เมนูหลัก", ["📝 ลงทะเบียนพนักงาน", "📸 จุดสแกน Checkpoint", "🏆 Leaderboard Map"])

# --- [ หน้า 1: ลงทะเบียนพนักงาน ] ---
if menu == "📝 ลงทะเบียนพนักงาน":
    st.header("📝 ลงทะเบียนและถ่ายรูปโปรไฟล์")
    if "reg_step" not in st.session_state: st.session_state.reg_step = "FORM"

    if st.session_state.reg_step == "FORM":
        next_bib = get_next_bib()
        with st.form("reg_form"):
            st.info(f"BIB: **{next_bib}**")
            name = st.text_input("ชื่อ-นามสกุล")
            dept = st.selectbox("แผนก", ["Production", "R&D", "QA", "Logistics", "Office", "Maintenance"])
            if st.form_submit_button("ถัดไป: ถ่ายรูป"):
                if name:
                    st.session_state.temp_user = {"bib": next_bib, "name": name, "dept": dept}
                    st.session_state.reg_step = "PHOTO"; st.rerun()
                else: st.warning("กรุณากรอกชื่อ")

    elif st.session_state.reg_step == "PHOTO":
        st.subheader(f"📸 ถ่ายรูป: {st.session_state.temp_user['name']}")
        img = st.camera_input("ส่องหน้าตรงแล้วกดถ่ายรูป")
        if img:
            with st.spinner("บันทึกข้อมูล..."):
                p_url = upload_photo(img.getvalue(), st.session_state.temp_user['bib'])
                if p_url:
                    supabase.table("runners").insert({
                        "bib_number": st.session_state.temp_user['bib'], "name": st.session_state.temp_user['name'],
                        "department": st.session_state.temp_user['dept'], "profile_url": p_url
                    }).execute()
                    qr_img = qrcode.make(st.session_state.temp_user['bib'])
                    buf = BytesIO(); qr_img.save(buf, format="PNG")
                    st.session_state.reg_qr = buf.getvalue()
                    st.session_state.reg_step = "DONE"; st.rerun()

    elif st.session_state.reg_step == "DONE":
        st.success(f"✅ บันทึกสำเร็จ! BIB: {st.session_state.temp_user['bib']}")
        st.image(st.session_state.reg_qr, width=300, caption="👉 แคปหน้าจอเพื่อใช้สแกน")
        if st.button("ลงทะเบียนคนถัดไป"):
            st.session_state.reg_step = "FORM"; st.rerun()

# --- [ หน้า 2: จุดสแกน Checkpoint (Always-On + Sound) ] ---
elif menu == "📸 จุดสแกน Checkpoint":
    st.header("📸 จุดสแกน Checkpoint")
    cp_loc = st.selectbox("📍 คุณอยู่จุดไหน?", ["Start", "Checkpoint 1", "Checkpoint 2", "Finish"])
    
    if "last_bib" not in st.session_state: st.session_state.last_bib = None
    if "last_time" not in st.session_state: st.session_state.last_time = 0

    st.success("🟢 กล้องพร้อมทำงาน พนักงานเดินมาสแกนได้เลย")
    
    # กล้องเปิดค้าง (Always-On)
    val = qrcode_scanner(key=f"fixed_scanner_{cp_loc}")

    if val:
        now = time.time()
        # เช็ค Cooldown กันสแกนเบิ้ล (10 วินาทีสำหรับคนเดิม)
        if val != st.session_state.last_bib or (now - st.session_state.last_time) > 10:
            try:
                res = supabase.table("run_logs").insert({"bib_number": val, "checkpoint_name": cp_loc}).execute()
                if res.data:
                    play_beep() # เสียงติ๊ด
                    st.session_state.last_bib = val
                    st.session_state.last_time = now
                    st.toast(f"✅ บันทึก BIB: {val} เรียบร้อย!", icon="🔊")
                    st.success(f"ล่าสุด: {val} ผ่านจุด {cp_loc}")
            except: st.error("บันทึกไม่สำเร็จ เช็คเลข BIB ในระบบ")
        else:
            st.warning(f"⏳ {val} สแกนไปแล้ว รอสักครู่...")

# --- [ หน้า 3: Leaderboard Map (Grid View + Anti-Overlap) ] ---
elif menu == "🏆 Leaderboard Map":
    st.header("🏆 RCI Real-time Map")
    st_autorefresh(15000, key="map_refresh")
    
    MAP_FILE = "map.png"
    # พิกัด x, y ตามที่คุณระบุ
    BASE_POINTS = {
        "Checkpoint 1": (715, 390), "Checkpoint 2": (715, 190),
        "Start": (815, 500), "Finish": (850, 550)
    }

    if os.path.exists(MAP_FILE):
        bg = Image.open(MAP_FILE).convert("RGBA")
        canvas = bg.copy(); draw = ImageDraw.Draw(canvas)
        res = supabase.table("run_logs").select("*, runners(name, profile_url)").order("scanned_at", desc=True).execute()
        
        if res.data:
            df = pd.DataFrame(res.data)
            # เอาเฉพาะจุดล่าสุดของแต่ละคน
            latest_per_run = df.sort_values("scanned_at", ascending=False).groupby("bib_number").first().reset_index()
            # แสดงสูงสุด 9 คนต่อจุด (ตาราง 3x3)
            display_on_map = latest_per_run.sort_values("scanned_at", ascending=False).groupby("checkpoint_name").head(9)

            for cp_name, base_pos in BASE_POINTS.items():
                runners = display_on_map[display_on_map['checkpoint_name'] == cp_name]
                img_size = 60; gap = 10; total_step = img_size + gap
                start_x = base_pos[0] - (total_step * 1.5)
                start_y = base_pos[1] - (total_step * 1.5)

                for i, (_, row) in enumerate(runners.iterrows()):
                    try:
                        r_idx, c_idx = i // 3, i % 3
                        p_img = Image.open(BytesIO(requests.get(row['runners']['profile_url']).content)).convert("RGBA")
                        p_img = ImageOps.fit(p_img, (img_size, img_size), centering=(0.5, 0.5))
                        mask = Image.new('L', (img_size, img_size), 0); ImageDraw.Draw(mask).ellipse((0, 0, img_size, img_size), fill=255)
                        
                        pos_x = int(start_x + (c_idx * total_step))
                        pos_y = int(start_y + (r_idx * total_step))
                        canvas.paste(p_img, (pos_x, pos_y), mask)
                        
                        color = "#00FFFF" if i == 0 else "#FFFFFF" # คนล่าสุดขอบสีฟ้า
                        draw.ellipse([pos_x, pos_y, pos_x+img_size, pos_y+img_size], outline=color, width=6)
                    except: continue

        st.image(canvas, use_container_width=True)
    
    # ตารางคะแนนรวมด้านล่าง
    st.divider(); st.subheader("📊 อันดับนักวิ่ง")
    res_all = supabase.table("run_logs").select("*, runners(name, department, profile_url)").execute()
    if res_all.data:
        df_all = pd.DataFrame([{ "รูป": r['runners']['profile_url'], "BIB": r['bib_number'], "ชื่อ": r['runners']['name'], "จุดล่าสุด": r['checkpoint_name'], "เวลา": r['scanned_at'] } for r in res_all.data])
        final = df_all.sort_values("เวลา", ascending=False).groupby("BIB").first().reset_index()
        cnts = df_all.groupby("BIB").size().reset_index(name="คะแนน")
        board = pd.merge(final, cnts, on="BIB").sort_values(["คะแนน", "เวลา"], ascending=[False, True])
        st.dataframe(board[["รูป", "BIB", "ชื่อ", "คะแนน", "จุดล่าสุด"]], column_config={"รูป": st.column_config.ImageColumn()})