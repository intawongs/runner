import streamlit as st
import pandas as pd
from supabase import create_client, Client
from streamlit_qrcode_scanner import qrcode_scanner
from streamlit_autorefresh import st_autorefresh
import qrcode
from io import BytesIO
import time
from datetime import datetime
import pytz
import requests
from PIL import Image, ImageDraw, ImageOps
import os

# --- 0. GLOBAL CONFIG ---
# รายชื่อจุดเช็คอินที่ใช้ร่วมกันทั้งระบบ (ต้องสะกดให้ตรงกันเป๊ะ)
CHECKPOINT_LIST = ["Start", "Checkpoint 1", "Checkpoint 2", "Checkpoint 3", "Checkpoint 4", "Checkpoint 5", "Finish"]
tz = pytz.timezone('Asia/Bangkok')

# --- 1. CONFIG & CONNECTION ---
st.set_page_config(page_title="RCI AI Tracker 2026", layout="wide")

def init_connection():
    try:
        return create_client(st.secrets["SUPABASE_URL"], st.secrets["SUPABASE_KEY"])
    except Exception as e:
        st.error(f"❌ Connection Error: {e}")
        st.stop()

supabase = init_connection()

# --- 2. AUDIO FUNCTION ---
def play_beep():
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

def format_thai_time(utc_time_str):
    try:
        # แปลงเวลาจาก Supabase (UTC) เป็น เวลาไทย
        utc_dt = datetime.fromisoformat(utc_time_str.replace('Z', '+00:00'))
        thai_dt = utc_dt.astimezone(tz)
        return thai_dt.strftime("%H:%M")
    except:
        return utc_time_str[11:16]

# --- 4. SIDEBAR MENU ---
st.sidebar.title("🏃 RCI AI Tracker 2026")
menu = st.sidebar.radio("เมนูหลัก", [
    "📝 ลงทะเบียนพนักงาน", 
    "📸 จุดสแกน Checkpoint", 
    "🏆 Leaderboard Map"
])

# --- [ หน้า 1: ลงทะเบียนพนักงาน ] ---
if menu == "📝 ลงทะเบียนพนักงาน":
    st.header("📝 ลงทะเบียนและถ่ายรูปโปรไฟล์")
    if "reg_step" not in st.session_state: st.session_state.reg_step = "FORM"

    if st.session_state.reg_step == "FORM":
        next_bib = get_next_bib()
        with st.form("reg_form"):
            st.info(f"BIB ที่คุณจะได้รับ: **{next_bib}**")
            name = st.text_input("ชื่อ-นามสกุล")
            dept = st.selectbox("แผนก", ["Production", "R&D", "QA", "Logistics", "Office", "Maintenance"])
            if st.form_submit_button("ถัดไป: ถ่ายรูปโปรไฟล์"):
                if name:
                    st.session_state.temp_user = {"bib": next_bib, "name": name, "dept": dept}
                    st.session_state.reg_step = "PHOTO"; st.rerun()
                else: st.warning("กรุณากรอกชื่อ")

    elif st.session_state.reg_step == "PHOTO":
        st.subheader(f"📸 ถ่ายรูป: {st.session_state.temp_user['name']}")
        img = st.camera_input("ส่องหน้าตรงแล้วกดถ่ายรูป")
        if img:
            with st.spinner("กำลังบันทึกข้อมูลและอัปโหลดรูป..."):
                p_url = upload_photo(img.getvalue(), st.session_state.temp_user['bib'])
                if p_url:
                    supabase.table("runners").insert({
                        "bib_number": st.session_state.temp_user['bib'], 
                        "name": st.session_state.temp_user['name'],
                        "department": st.session_state.temp_user['dept'], 
                        "profile_url": p_url
                    }).execute()
                    
                    # สร้าง QR Code
                    qr_img = qrcode.make(st.session_state.temp_user['bib'])
                    buf = BytesIO(); qr_img.save(buf, format="PNG")
                    st.session_state.reg_qr = buf.getvalue()
                    st.session_state.reg_step = "DONE"; st.rerun()

    elif st.session_state.reg_step == "DONE":
        st.success(f"✅ ลงทะเบียนสำเร็จ! BIB: {st.session_state.temp_user['bib']}")
        st.image(st.session_state.reg_qr, width=300, caption="👉 แคปหน้าจอ QR Code นี้ไว้สแกนตามจุดต่างๆ")
        if st.button("ลงทะเบียนพนักงานคนถัดไป"):
            st.session_state.reg_step = "FORM"; st.rerun()

# --- [ หน้า 2: จุดสแกน Checkpoint ] ---
elif menu == "📸 จุดสแกน Checkpoint":
    st.header("📸 จุดสแกนพนักงาน (Checkpoint Station)")
    cp_loc = st.selectbox("📍 เครื่องนี้ประจำอยู่ที่จุดไหน?", CHECKPOINT_LIST)
    
    if "last_bib" not in st.session_state: st.session_state.last_bib = None
    if "last_time" not in st.session_state: st.session_state.last_time = 0

    st.success(f"🟢 กล้องพร้อมทำงาน ณ จุด: **{cp_loc}**")
    
    # Scanner เปิดค้างตลอดเวลา
    val = qrcode_scanner(key=f"scanner_{cp_loc}")

    if val:
        now = time.time()
        # Cooldown 15 วินาทีต่อคน เพื่อกันการสแกนซ้ำแบบไม่ตั้งใจ
        if val != st.session_state.last_bib or (now - st.session_state.last_time) > 15:
            try:
                # เช็คว่าเคยสแกนจุดนี้ไปแล้วหรือยัง
                check = supabase.table("run_logs").select("id").eq("bib_number", val).eq("checkpoint_name", cp_loc).execute()
                
                if len(check.data) > 0:
                    st.warning(f"⚠️ BIB: {val} เคยผ่านจุด {cp_loc} นี้ไปแล้ว")
                else:
                    res = supabase.table("run_logs").insert({"bib_number": val, "checkpoint_name": cp_loc}).execute()
                    if res.data:
                        play_beep()
                        st.session_state.last_bib = val
                        st.session_state.last_time = now
                        st.toast(f"🔊 บันทึก {val} สำเร็จ!", icon="✅")
                        if cp_loc == "Finish": st.balloons()
                        
                        # ดึงชื่อมาโชว์ให้กรรมการดู
                        runner = supabase.table("runners").select("name").eq("bib_number", val).single().execute()
                        r_name = runner.data['name'] if runner.data else "ไม่พบรายชื่อ"
                        st.success(f"บันทึกแล้ว: {val} - {r_name} (ผ่านจุด {cp_loc})")
            except Exception as e:
                st.error(f"Error: {e}")

# --- [ หน้า 3: Leaderboard (Lanes) ] ---
elif menu == "🏆 Leaderboard Map":
    st.header("🏆 RCI Walk Rally Real-time Tracker")
    
    # Auto-Refresh ทุก 5 วินาที
    st_autorefresh(interval=5000, key="refresh_leaderboard")

    # ดึงข้อมูล Log และ Join กับตาราง Runners
    res = supabase.table("run_logs").select("*, runners(name, profile_url)").order("scanned_at", desc=True).execute()
    
    if res.data:
        df = pd.DataFrame(res.data)
        # ดึงสถานะล่าสุดของแต่ละคน (คนละ 1 ตำแหน่งบนบอร์ด)
        latest_status = df.sort_values("scanned_at", ascending=False).groupby("bib_number").first().reset_index()

        # สร้าง Column ตามจำนวนจุดเช็คอิน
        cols = st.columns(len(CHECKPOINT_LIST))
        
        for idx, cp_name in enumerate(CHECKPOINT_LIST):
            with cols[idx]:
                st.markdown(f"#### 📍 {cp_name}")
                st.divider()
                
                # กรองรายชื่อพนักงานที่อยู่จุดนี้
                runners_here = latest_status[latest_status['checkpoint_name'] == cp_name]
                
                for _, runner in runners_here.iterrows():
                    # แสดงรูปโปรไฟล์ (ถ้ามี)
                    if runner['runners'] and runner['runners']['profile_url']:
                        st.image(runner['runners']['profile_url'], width=80)
                    
                    r_name = runner['runners']['name'] if runner['runners'] else "Unknown"
                    st.caption(f"**{r_name}**")
                    
                    # แสดงเวลาไทย GMT+7
                    t_display = format_thai_time(runner['scanned_at'])
                    st.write(f"⏱️ {t_display}")
                    st.divider()
    else:
        st.info("ยังไม่มีข้อมูลการวิ่งในขณะนี้")

# import streamlit as st
# import pandas as pd
# from supabase import create_client, Client
# from streamlit_qrcode_scanner import qrcode_scanner
# from streamlit_autorefresh import st_autorefresh
# import qrcode
# from io import BytesIO
# import time
# from datetime import datetime
# import pytz # เพิ่ม Library สำหรับจัดการ Timezone
# import requests
# from PIL import Image, ImageDraw, ImageOps
# import os

# # --- 0. GLOBAL CONFIG ---
# CHECKPOINT_LIST = ["Start", "Checkpoint 1", "Checkpoint 2", "Checkpoint 3", "Checkpoint 4", "Checkpoint 5", "Finish"]
# tz = pytz.timezone('Asia/Bangkok') # กำหนด Timezone ไทย

# # --- 1. CONFIG & CONNECTION ---
# st.set_page_config(page_title="RCI AI Tracker 2026", layout="wide")

# def init_connection():
#     try:
#         return create_client(st.secrets["SUPABASE_URL"], st.secrets["SUPABASE_KEY"])
#     except:
#         st.error("❌ เช็ค Secrets ใน Streamlit Cloud (URL/KEY)")
#         st.stop()

# supabase = init_connection()

# # --- 2. AUDIO FUNCTION (เสียงติ๊ด) ---
# def play_beep():
#     beep_html = """
#         <audio autoplay>
#             <source src="https://www.soundjay.com/button/beep-07.wav" type="audio/wav">
#         </audio>
#     """
#     st.components.v1.html(beep_html, height=0)

# # --- 3. HELPER FUNCTIONS ---
# def get_next_bib():
#     try:
#         res = supabase.table("runners").select("bib_number").order("bib_number", desc=True).limit(1).execute()
#         if not res.data: return "RCI-001"
#         last_num = int(res.data[0]['bib_number'].split("-")[1])
#         return f"RCI-{last_num + 1:03d}"
#     except: return "RCI-001"

# def upload_photo(file_bytes, filename):
#     try:
#         path = f"profile_{filename}.jpg"
#         supabase.storage.from_("runner_photos").upload(path, file_bytes, {"content-type": "image/jpeg"})
#         return supabase.storage.from_("runner_photos").get_public_url(path)
#     except: return None

# # ฟังก์ชันแปลงเวลา UTC เป็น Thai Time
# def format_thai_time(utc_time_str):
#     try:
#         # Supabase ส่งมาเป็น ISO format (e.g., 2026-04-08T01:33:15.123+00:00)
#         utc_dt = datetime.fromisoformat(utc_time_str.replace('Z', '+00:00'))
#         thai_dt = utc_dt.astimezone(tz)
#         return thai_dt.strftime("%H:%M") # คืนค่าเฉพาะ ชั่วโมง:นาที
#     except:
#         return utc_time_str[11:16] # Fallback กรณี Error ให้ตัดสตริงเอา

# # --- 4. SIDEBAR MENU ---
# st.sidebar.title("🏃 RCI AI Tracker")
# menu = st.sidebar.radio("เมนูหลัก", ["📝 ลงทะเบียนพนักงาน", "📸 จุดสแกน Checkpoint", "🏆 Leaderboard Map"])

# # --- [ หน้า 1: ลงทะเบียนพนักงาน ] ---
# if menu == "📝 ลงทะเบียนพนักงาน":
#     st.header("📝 ลงทะเบียนและถ่ายรูปโปรไฟล์")
#     if "reg_step" not in st.session_state: st.session_state.reg_step = "FORM"

#     if st.session_state.reg_step == "FORM":
#         next_bib = get_next_bib()
#         with st.form("reg_form"):
#             st.info(f"BIB: **{next_bib}**")
#             name = st.text_input("ชื่อ-นามสกุล")
#             dept = st.selectbox("แผนก", ["Production", "R&D", "QA", "Logistics", "Office", "Maintenance"])
#             if st.form_submit_button("ถัดไป: ถ่ายรูป"):
#                 if name:
#                     st.session_state.temp_user = {"bib": next_bib, "name": name, "dept": dept}
#                     st.session_state.reg_step = "PHOTO"; st.rerun()
#                 else: st.warning("กรุณากรอกชื่อ")

#     elif st.session_state.reg_step == "PHOTO":
#         st.subheader(f"📸 ถ่ายรูป: {st.session_state.temp_user['name']}")
#         img = st.camera_input("ส่องหน้าตรงแล้วกดถ่ายรูป")
#         if img:
#             with st.spinner("บันทึกข้อมูล..."):
#                 p_url = upload_photo(img.getvalue(), st.session_state.temp_user['bib'])
#                 if p_url:
#                     supabase.table("runners").insert({
#                         "bib_number": st.session_state.temp_user['bib'], "name": st.session_state.temp_user['name'],
#                         "department": st.session_state.temp_user['dept'], "profile_url": p_url
#                     }).execute()
#                     qr_img = qrcode.make(st.session_state.temp_user['bib'])
#                     buf = BytesIO(); qr_img.save(buf, format="PNG")
#                     st.session_state.reg_qr = buf.getvalue()
#                     st.session_state.reg_step = "DONE"; st.rerun()

#     elif st.session_state.reg_step == "DONE":
#         st.success(f"✅ บันทึกสำเร็จ! BIB: {st.session_state.temp_user['bib']}")
#         st.image(st.session_state.reg_qr, width=300, caption="👉 แคปหน้าจอเพื่อใช้สแกน")
#         if st.button("ลงทะเบียนคนถัดไป"):
#             st.session_state.reg_step = "FORM"; st.rerun()

# # --- [ หน้า 2: จุดสแกน Checkpoint ] ---
# elif menu == "📸 จุดสแกน Checkpoint":
#     st.header("📸 จุดสแกน Checkpoint")
#     cp_loc = st.selectbox("📍 คุณประจำอยู่จุดไหน?", CHECKPOINT_LIST)
    
#     if "last_bib" not in st.session_state: st.session_state.last_bib = None
#     if "last_time" not in st.session_state: st.session_state.last_time = 0

#     st.info(f"ขณะนี้กำลังบันทึกข้อมูลสำหรับ: **{cp_loc}**")
#     st.success("🟢 เครื่องสแกนพร้อมทำงาน พนักงานโชว์ QR Code ได้เลย")
    
#     val = qrcode_scanner(key=f"fixed_scanner_{cp_loc}")

#     if val:
#         now = time.time()
#         if val != st.session_state.last_bib or (now - st.session_state.last_time) > 15:
#             try:
#                 check_exist = supabase.table("run_logs").select("id").eq("bib_number", val).eq("checkpoint_name", cp_loc).execute()
                
#                 if len(check_exist.data) > 0:
#                     st.warning(f"⚠️ BIB: {val} เคยสแกนที่ {cp_loc} ไปแล้ว")
#                 else:
#                     res = supabase.table("run_logs").insert({"bib_number": val, "checkpoint_name": cp_loc}).execute()
#                     if res.data:
#                         play_beep()
#                         st.session_state.last_bib = val
#                         st.session_state.last_time = now
#                         st.toast(f"✅ บันทึก BIB: {val} เรียบร้อย!", icon="🔊")
#                         if cp_loc == "Finish": st.balloons()
                        
#                         runner_info = supabase.table("runners").select("name").eq("bib_number", val).single().execute()
#                         runner_name = runner_info.data['name'] if runner_info.data else "ไม่ทราบชื่อ"
#                         st.success(f"ล่าสุด: {val} ({runner_name}) ผ่านจุด {cp_loc} แล้ว!")
#             except Exception as e:
#                 st.error(f"เกิดข้อผิดพลาด: {e}")

# # --- [ หน้า 3: Leaderboard Map (Ranking by Lane) ] ---
# elif menu == "🏆 Leaderboard Map":
#     st.header("🏆 Real-time Race Tracker (Thai Time GMT+7)")
#     st_autorefresh(interval=5000, key="leaderboard_refresh")

#     res = supabase.table("run_logs").select("*, runners(name, profile_url)").order("scanned_at", desc=True).execute()
    
#     if res.data:
#         df = pd.DataFrame(res.data)
#         latest_status = df.sort_values("scanned_at", ascending=False).groupby("bib_number").first().reset_index()

#         cols = st.columns(len(CHECKPOINT_LIST))
        
#         for idx, cp_name in enumerate(CHECKPOINT_LIST):
#             with cols[idx]:
#                 st.markdown(f"##### 📍 {cp_name}")
#                 st.divider()
                
#                 runners_here = latest_status[latest_status['checkpoint_name'] == cp_name]
                
#                 for _, runner in runners_here.iterrows():
#                     if runner['runners'] and runner['runners']['profile_url']:
#                         st.image(runner['runners']['profile_url'], width=70)
                    
#                     name_display = runner['runners']['name'] if runner['runners'] else "Unknown"
#                     st.caption(f"**{name_display}**")
                    
#                     # เรียกใช้ฟังก์ชันแปลงเวลาเป็น Thai Time
#                     thai_time = format_thai_time(runner['scanned_at'])
#                     st.write(f"⏱️ {thai_time}")
#                     st.divider()

# # import streamlit as st
# # import pandas as pd
# # from supabase import create_client, Client
# # from streamlit_qrcode_scanner import qrcode_scanner
# # from streamlit_autorefresh import st_autorefresh
# # import qrcode
# # from io import BytesIO
# # import time
# # import requests
# # from PIL import Image, ImageDraw, ImageOps
# # import os

# # # --- 1. CONFIG & CONNECTION ---
# # st.set_page_config(page_title="RCI AI Tracker 2026", layout="wide")

# # def init_connection():
# #     try:
# #         return create_client(st.secrets["SUPABASE_URL"], st.secrets["SUPABASE_KEY"])
# #     except:
# #         st.error("❌ เช็ค Secrets ใน Streamlit Cloud (URL/KEY)")
# #         st.stop()

# # supabase = init_connection()

# # # --- 2. AUDIO FUNCTION (เสียงติ๊ด) ---
# # def play_beep():
# #     # ใช้เสียง Beep จาก URL มาตรฐาน
# #     beep_html = """
# #         <audio autoplay>
# #             <source src="https://www.soundjay.com/button/beep-07.wav" type="audio/wav">
# #         </audio>
# #     """
# #     st.components.v1.html(beep_html, height=0)

# # # --- 3. HELPER FUNCTIONS ---
# # def get_next_bib():
# #     try:
# #         res = supabase.table("runners").select("bib_number").order("bib_number", desc=True).limit(1).execute()
# #         if not res.data: return "RCI-001"
# #         last_num = int(res.data[0]['bib_number'].split("-")[1])
# #         return f"RCI-{last_num + 1:03d}"
# #     except: return "RCI-001"

# # def upload_photo(file_bytes, filename):
# #     try:
# #         path = f"profile_{filename}.jpg"
# #         supabase.storage.from_("runner_photos").upload(path, file_bytes, {"content-type": "image/jpeg"})
# #         return supabase.storage.from_("runner_photos").get_public_url(path)
# #     except: return None

# # # --- 4. SIDEBAR MENU ---
# # st.sidebar.title("🏃 RCI AI Tracker")
# # menu = st.sidebar.radio("เมนูหลัก", ["📝 ลงทะเบียนพนักงาน", "📸 จุดสแกน Checkpoint", "🏆 Leaderboard Map"])

# # # --- [ หน้า 1: ลงทะเบียนพนักงาน ] ---
# # if menu == "📝 ลงทะเบียนพนักงาน":
# #     st.header("📝 ลงทะเบียนและถ่ายรูปโปรไฟล์")
# #     if "reg_step" not in st.session_state: st.session_state.reg_step = "FORM"

# #     if st.session_state.reg_step == "FORM":
# #         next_bib = get_next_bib()
# #         with st.form("reg_form"):
# #             st.info(f"BIB: **{next_bib}**")
# #             name = st.text_input("ชื่อ-นามสกุล")
# #             dept = st.selectbox("แผนก", ["Production", "R&D", "QA", "Logistics", "Office", "Maintenance"])
# #             if st.form_submit_button("ถัดไป: ถ่ายรูป"):
# #                 if name:
# #                     st.session_state.temp_user = {"bib": next_bib, "name": name, "dept": dept}
# #                     st.session_state.reg_step = "PHOTO"; st.rerun()
# #                 else: st.warning("กรุณากรอกชื่อ")

# #     elif st.session_state.reg_step == "PHOTO":
# #         st.subheader(f"📸 ถ่ายรูป: {st.session_state.temp_user['name']}")
# #         img = st.camera_input("ส่องหน้าตรงแล้วกดถ่ายรูป")
# #         if img:
# #             with st.spinner("บันทึกข้อมูล..."):
# #                 p_url = upload_photo(img.getvalue(), st.session_state.temp_user['bib'])
# #                 if p_url:
# #                     supabase.table("runners").insert({
# #                         "bib_number": st.session_state.temp_user['bib'], "name": st.session_state.temp_user['name'],
# #                         "department": st.session_state.temp_user['dept'], "profile_url": p_url
# #                     }).execute()
# #                     qr_img = qrcode.make(st.session_state.temp_user['bib'])
# #                     buf = BytesIO(); qr_img.save(buf, format="PNG")
# #                     st.session_state.reg_qr = buf.getvalue()
# #                     st.session_state.reg_step = "DONE"; st.rerun()

# #     elif st.session_state.reg_step == "DONE":
# #         st.success(f"✅ บันทึกสำเร็จ! BIB: {st.session_state.temp_user['bib']}")
# #         st.image(st.session_state.reg_qr, width=300, caption="👉 แคปหน้าจอเพื่อใช้สแกน")
# #         if st.button("ลงทะเบียนคนถัดไป"):
# #             st.session_state.reg_step = "FORM"; st.rerun()

# # # --- [ หน้า 2: จุดสแกน Checkpoint (Always-On + Sound) ] ---
# # # --- [ หน้า 2: จุดสแกน Checkpoint (Always-On + Sound) ] ---
# # elif menu == "📸 จุดสแกน Checkpoint":
# #     st.header("📸 จุดสแกน Checkpoint")
    
# #     # 1. เพิ่มจุดให้ครบตามที่ต้องการ
# #     checkpoints = ["Start", "Checkpoint 1", "Checkpoint 2", "Checkpoint 3", "Checkpoint 4", "Checkpoint 5", "Finish"]
# #     cp_loc = st.selectbox("📍 คุณประจำอยู่จุดไหน?", checkpoints)
    
# #     if "last_bib" not in st.session_state: st.session_state.last_bib = None
# #     if "last_time" not in st.session_state: st.session_state.last_time = 0

# #     st.info(f"ขณะนี้กำลังบันทึกข้อมูลสำหรับ: **{cp_loc}**")
# #     st.success("🟢 เครื่องสแกนพร้อมทำงาน พนักงานโชว์ QR Code ได้เลย")
    
# #     # กล้องเปิดค้าง (Always-On)
# #     val = qrcode_scanner(key=f"fixed_scanner_{cp_loc}")

# #     if val:
# #         now = time.time()
# #         # Logic: จะบันทึกก็ต่อเมื่อ (เป็นคนใหม่) หรือ (คนเดิมแต่ผ่านไปแล้ว 15 วินาที)
# #         if val != st.session_state.last_bib or (now - st.session_state.last_time) > 15:
            
# #             try:
# #                 # [เสริม] เช็คก่อนว่าคนนี้เคยสแกน "จุดนี้" ไปหรือยัง เพื่อป้องกัน Data ขยะ
# #                 check_exist = supabase.table("run_logs") \
# #                     .select("id") \
# #                     .eq("bib_number", val) \
# #                     .eq("checkpoint_name", cp_loc) \
# #                     .execute()
                
# #                 if len(check_exist.data) > 0:
# #                     st.warning(f"⚠️ BIB: {val} เคยสแกนที่ {cp_loc} ไปแล้ว")
# #                 else:
# #                     # บันทึกข้อมูล
# #                     res = supabase.table("run_logs").insert({
# #                         "bib_number": val, 
# #                         "checkpoint_name": cp_loc
# #                     }).execute()
                    
# #                     if res.data:
# #                         play_beep() # ส่งเสียงติ๊ด
# #                         st.session_state.last_bib = val
# #                         st.session_state.last_time = now
# #                         st.toast(f"✅ บันทึก BIB: {val} เรียบร้อย!", icon="🔊")
# #                         st.balloons() if cp_loc == "Finish" else None # แสดงความยินดีถ้าถึงเส้นชัย
                        
# #                         # แสดง Profile ผู้สแกนล่าสุด (ดึงชื่อจากตาราง runners)
# #                         runner_info = supabase.table("runners").select("name").eq("bib_number", val).single().execute()
# #                         runner_name = runner_info.data['name'] if runner_info.data else "ไม่ทราบชื่อ"
# #                         st.success(f"ล่าสุด: {val} ({runner_name}) ผ่านจุด {cp_loc} แล้ว!")
            
# #             except Exception as e:
# #                 st.error(f"เกิดข้อผิดพลาด: {e}")
# #         else:
# #             # กรณีสแกนซ้ำภายใน 15 วินาที ไม่ต้องทำอะไร หรือโชว์ Warning เบาๆ
# #             pass

# # # --- [ หน้า 3: Leaderboard แบบแบ่งโซน Checkpoint ] ---
# # # --- [ หน้า 3: Leaderboard แบบแบ่งโซน Checkpoint ] ---
# # elif menu == "🏆 Leaderboard Map":
# #     st.header("🏆 Real-time Race Tracker")
    
# #     # เพิ่มบรรทัดนี้เพื่อให้หน้าจอ Auto-Refresh ทุกๆ 5 วินาที
# #     from streamlit_autorefresh import st_autorefresh
# #     st_autorefresh(interval=5000, key="leaderboard_refresh")

# #     # 1. ดึงข้อมูลล่าสุด
# #     res = supabase.table("run_logs").select("*, runners(name, profile_url)").order("scanned_at", desc=True).execute()
    
# #     if res.data:
# #         df = pd.DataFrame(res.data)
# #         # กรองเอาเฉพาะจุดล่าสุดของแต่ละ BIB
# #         latest_status = df.sort_values("scanned_at", ascending=False).groupby("bib_number").first().reset_index()

# #         # 2. ใช้ตัวแปร Global เดียวกัน (สำคัญมาก!)
# #         all_checkpoints = CHECKPOINT_LIST 
        
# #         cols = st.columns(len(all_checkpoints))
        
# #         for idx, cp_name in enumerate(all_checkpoints):
# #             with cols[idx]:
# #                 st.markdown(f"##### 📍 {cp_name}") # ใช้หัวข้อเล็กลงหน่อยให้พอดี column
# #                 st.divider()
                
# #                 # Filter ข้อมูลพนักงานที่อยู่จุดนี้
# #                 runners_here = latest_status[latest_status['checkpoint_name'] == cp_name]
                
# #                 for _, runner in runners_here.iterrows():
# #                     # แสดงรูปและชื่อ
# #                     if runner['runners'] and runner['runners']['profile_url']:
# #                         st.image(runner['runners']['profile_url'], width=70)
                    
# #                     name_display = runner['runners']['name'] if runner['runners'] else "Unknown"
# #                     st.caption(f"**{name_display}**")
                    
# #                     # ตัดเวลามาโชว์ (รองรับทั้ง format ที่มี T หรือช่องว่าง)
# #                     raw_time = runner['scanned_at']
# #                     time_display = raw_time[11:16] if len(raw_time) > 16 else raw_time
# #                     st.write(f"⏱️ {time_display}")
# #                     st.divider()


# # elif menu == "📸 จุดสแกน Checkpoint":
# #     st.header("📸 จุดสแกน Checkpoint")
# #     cp_loc = st.selectbox("📍 คุณอยู่จุดไหน?", ["Start", "Checkpoint 1", "Checkpoint 2", "Finish"])
    
# #     if "last_bib" not in st.session_state: st.session_state.last_bib = None
# #     if "last_time" not in st.session_state: st.session_state.last_time = 0

# #     st.success("🟢 กล้องพร้อมทำงาน พนักงานเดินมาสแกนได้เลย")
    
# #     # กล้องเปิดค้าง (Always-On)
# #     val = qrcode_scanner(key=f"fixed_scanner_{cp_loc}")

# #     if val:
# #         now = time.time()
# #         # เช็ค Cooldown กันสแกนเบิ้ล (10 วินาทีสำหรับคนเดิม)
# #         if val != st.session_state.last_bib or (now - st.session_state.last_time) > 10:
# #             try:
# #                 res = supabase.table("run_logs").insert({"bib_number": val, "checkpoint_name": cp_loc}).execute()
# #                 if res.data:
# #                     play_beep() # เสียงติ๊ด
# #                     st.session_state.last_bib = val
# #                     st.session_state.last_time = now
# #                     st.toast(f"✅ บันทึก BIB: {val} เรียบร้อย!", icon="🔊")
# #                     st.success(f"ล่าสุด: {val} ผ่านจุด {cp_loc}")
# #             except: st.error("บันทึกไม่สำเร็จ เช็คเลข BIB ในระบบ")
# #         else:
# #             st.warning(f"⏳ {val} สแกนไปแล้ว รอสักครู่...")

# # --- [ หน้า 3: Leaderboard Map (Grid View + Anti-Overlap) ] ---
# # --- [ หน้า 3: Leaderboard Map - FIFO 3 Latest per Point ] ---

# # elif menu == "🏆 Leaderboard Map":
# #     st.header("🏆 RCI Real-time Map (FIFO 3 Latest)")
# #     st_autorefresh(interval=10000, key="map_refresh_fifo_v2")
    
# #     MAP_FILE = "map.png" 
    
# #     # พิกัดใหม่ที่คุณระบุ (Start/Finish อยู่โซนล่าง)
# #     BASE_POINTS = {
# #         "Checkpoint 1": (715, 390), 
# #         "Checkpoint 2": (715, 190),
# #         "Start": (750, 650), 
# #         "Finish": (950, 630)
# #     }

# #     if os.path.exists(MAP_FILE):
# #         try:
# #             bg = Image.open(MAP_FILE).convert("RGBA")
# #             canvas = bg.copy()
# #             draw = ImageDraw.Draw(canvas)

# #             # 1. ดึง Log ทั้งหมดจาก Supabase
# #             res = supabase.table("run_logs").select("*, runners(name, profile_url)").order("scanned_at", desc=True).execute()
            
# #             if res.data:
# #                 df = pd.DataFrame(res.data)
                
# #                 # 2. หาจุดล่าสุดของแต่ละคน (คนละ 1 ตำแหน่งบนแผนที่)
# #                 latest_per_runner = df.sort_values("scanned_at", ascending=False).groupby("bib_number").first().reset_index()

# #                 # 3. วนลูปราย Checkpoint เพื่อวาด 3 คนล่าสุด
# #                 for cp_name, base_pos in BASE_POINTS.items():
# #                     # ดึง 3 คนล่าสุดของจุดนี้ (เรียงใหม่ -> เก่า)
# #                     runners_at_cp = latest_per_runner[latest_per_runner['checkpoint_name'] == cp_name].head(3)
                    
# #                     gap = 15 # ระยะห่างระหว่างรูป

# #                     for i, (_, row) in enumerate(runners_at_cp.iterrows()):
# #                         if row['runners']['profile_url']:
# #                             try:
# #                                 # โหลดรูปโปรไฟล์
# #                                 p_res = requests.get(row['runners']['profile_url'])
# #                                 p_img = Image.open(BytesIO(p_res.content)).convert("RGBA")
                                
# #                                 # --- Logic การแสดงผลแบบ FIFO ---
# #                                 # คนใหม่ล่าสุด (i=0) ขนาด 140px, คนเก่าถัดไป (i=1,2) ขนาด 100px
# #                                 current_size = 90 if i == 0 else 70
# #                                 p_img = ImageOps.fit(p_img, (current_size, current_size), centering=(0.5, 0.5))
                                
# #                                 # ทำรูปวงกลม
# #                                 mask = Image.new('L', (current_size, current_size), 0)
# #                                 ImageDraw.Draw(mask).ellipse((0, 0, current_size, current_size), fill=255)
                                
# #                                 # คำนวณพิกัด: เรียงจากซ้ายไปขวา (คนใหม่สุดอยู่ซ้าย)
# #                                 # ขยับ x ไปทางขวาเรื่อยๆ ตามลำดับ i
# #                                 pos_x = int(base_pos[0] - 70 + (i * (110 + gap))) 
# #                                 pos_y = int(base_pos[1] - (current_size // 2))
                                
# #                                 # แปะรูป
# #                                 canvas.paste(p_img, (pos_x, pos_y), mask)
                                
# #                                 # วาดเส้นขอบ: คนใหม่สุดสีฟ้า Neon (#00FFFF), คนเก่าสีขาว (#FFFFFF)
# #                                 b_color = "#00FFFF" if i == 0 else "#FFFFFF"
# #                                 b_width = 10 if i == 0 else 5
# #                                 draw.ellipse([pos_x, pos_y, pos_x+current_size, pos_y+current_size], outline=b_color, width=b_width)
                                
# #                                 # ใส่ชื่อเล่น/BIB สั้นๆ ใต้รูป (Optional)
# #                                 # draw.text((pos_x + 10, pos_y + current_size + 5), row['runners']['name'][:10], fill="white")
                                
# #                             except: continue

# #             # แสดงผลแผนที่
# #             st.image(canvas, use_container_width=True, caption="📍 แผนที่ RCI Walk Rally (คนใหม่ล่าสุดจะอยู่ซ้ายสุดของกลุ่ม)")
            
# #         except Exception as e:
# #             st.error(f"Error drawing map: {e}")
# #     else:
# #         st.error(f"❌ ไม่พบไฟล์รูป {MAP_FILE} ในโฟลเดอร์")

# #     # --- ตาราง Leaderboard ปกติ (ด้านล่าง) ---
# #     st.divider()
# #     # ... (ส่วนตารางคะแนนใช้โค้ดเดิมได้เลยครับ)
    
# #     # ตารางคะแนนรวมด้านล่าง
# #     st.divider(); st.subheader("📊 อันดับนักวิ่ง")
# #     res_all = supabase.table("run_logs").select("*, runners(name, department, profile_url)").execute()
# #     if res_all.data:
# #         df_all = pd.DataFrame([{ "รูป": r['runners']['profile_url'], "BIB": r['bib_number'], "ชื่อ": r['runners']['name'], "จุดล่าสุด": r['checkpoint_name'], "เวลา": r['scanned_at'] } for r in res_all.data])
# #         final = df_all.sort_values("เวลา", ascending=False).groupby("BIB").first().reset_index()
# #         cnts = df_all.groupby("BIB").size().reset_index(name="คะแนน")
# #         board = pd.merge(final, cnts, on="BIB").sort_values(["คะแนน", "เวลา"], ascending=[False, True])
# #         st.dataframe(board[["รูป", "BIB", "ชื่อ", "คะแนน", "จุดล่าสุด"]], column_config={"รูป": st.column_config.ImageColumn()})