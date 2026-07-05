import streamlit as st
import cv2
import easyocr
import numpy as np
import pandas as pd
import re
from PIL import Image
from fpdf import FPDF
import datetime
import database as db

# Database එක initialize කිරීම
db.init_db()

st.set_page_config(page_title="Bulk DC Toll Scanner Pro", page_icon="🚛", layout="wide")

# --- OCR Loader ---
@st.cache_resource
def load_ocr():
    return easyocr.Reader(['en'])

reader = load_ocr()

# --- 🛠️ Image Preprocessing Function ---
def preprocess_for_ocr(pil_image):
    """OpenCV භාවිතයෙන් පින්තූරය Grayscale කර, හෙවනැලි මකා, අකුරු තද කළු කිරීම"""
    # PIL Image එක OpenCV format (numpy array) එකට හැරවීම
    img = np.array(pil_image)
    img = cv2.cvtColor(img, cv2.COLOR_RGB2BGR)
    
    # 1. Grayscale කිරීම
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    
    # 2. Resizing - පින්තූරය 1.5 ගුණයකින් විශාල කිරීම (කුඩා අකුරු පැහැදිලි වීමට)
    gray = cv2.resize(gray, None, fx=1.5, fy=1.5, interpolation=cv2.INTER_CUBIC)
    
    # 3. Adaptive Thresholding - පසුබිම සුදු කර අකුරු තද කළු කිරීම (Shadow removal)
    processed_img = cv2.adaptiveThreshold(
        gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 15, 9
    )
    
    return processed_img

# --- 🔍 Advanced Data Extraction Function ---
def process_image_ocr(image):
    # පින්තූරය clear කරගැනීම
    processed_img = preprocess_for_ocr(image)
    
    # OCR මඟින් අකුරු කියවීම
    results = reader.readtext(processed_img, detail=0)
    full_text = " ".join(results).upper()
    
    # 📝 DEBUG: අවශ්‍ය නම් මෙතනින් AI එකට කියවුණු මුළු text එකම බලාගන්න පුළුවන්
    # print(full_text)

    # 1. වාහන අංකය සෙවීම (Regex)
    vehicle_pattern = r'\b([A-Z]{2,3}\s*[-–\.]?\s*[0-9]{4})\b'
    vehicle_match = re.search(vehicle_pattern, full_text)
    vehicle_no = vehicle_match.group(1).replace(".", "").replace(" ", "-") if vehicle_match else "Unknown"
    
    # 2. දිනය සෙවීම
    date_pattern = r'\b(202[0-9]\s*[-/]?\s*[0-1][0-9]\s*[-/]?\s*[0-3][0-9])\b'
    date_match = re.search(date_pattern, full_text)
    date = date_match.group(1).replace(" ", "-") if date_match else str(datetime.date.today())
    
    # 3. මුදල සෙවීම (RS(LKR) හෝ RS හෝ .00 රටාවන් අනුව)
    amount_float = 0.00
    # ක්‍රමය A: RS(LKR) : 700.00 වගේ ඒවා සෙවීම
    amount_pattern_a = r'(?:RS\(LKR\)|RS|LKR)\s*[:\.-]?\s*([\d,]+\s*\.\s*\d{2})'
    match_a = re.search(amount_pattern_a, full_text)
    
    if match_a:
        amt_str = match_a.group(1).replace(" ", "").replace(",", "")
        try: amount_float = float(amt_str)
        except: pass
    else:
        # ක්‍රමය B: කෙළින්ම .00 න් ඉවර වෙන අගයක් සෙවීම
        amount_pattern_b = r'\b([0-9,]+\s*\.\s*00)\b'
        amount_matches = re.findall(amount_pattern_b, full_text)
        if amount_matches:
            amt_str = amount_matches[-1].replace(" ", "").replace(",", "")
            try: amount_float = float(amt_str)
            except: pass
        
    # 4. මාර්ගය (Interchanges) නිවැරදිව හඳුනාගැනීම
    # ලංකාවේ ප්‍රධාන හයිවේ ස්ථාන ලැයිස්තුව (අකුරු වැරදීම් අවම කිරීමට Keyword Matching)
    stations_list = [
        "WELIPENNA", "KERAWALAPITIYA", "KOTTAWA", "KADAWATHA", "KUNDASALE", 
        "KATUNAYAKE", "GAMPALHA", "GALANIGAMA", "DODANGODA", "GELANIGAMA",
        "KOKMADUWA", "GODAGAMA", "KURUNEGALA", "MIRIGAMA", "ATHURUGIRIYA"
    ]
    
    found_stations = []
    for station in stations_list:
        if station in full_text:
            found_stations.append(station)
            
    if len(found_stations) >= 2:
        location = " / ".join(found_stations[:2])
    elif len(found_stations) == 1:
        # බිල්පතේ එක තැනක් විතරක් අහුවුනොත් (උදා: වැලිපැන්න විතරක් තිබුණොත්)
        location = f"{found_stations[0]} / Unknown"
    else:
        # කිසිවක්ම නැත්නම් පරණ Regex එකෙන් / ලකුණ මැද තියෙන වචන සෙවීම
        location_pattern = r'\b([A-Z\s]+/+[A-Z\s]+[0-9]*)\b'
        location_match = re.search(location_pattern, full_text)
        location = location_match.group(1).strip() if location_match else "Unknown"
    
    status = "Review Needed ⚠️" if (vehicle_no == "Unknown" or amount_float == 0.00 or location == "Unknown") else "Verified ✅"
    return date, vehicle_no, location, "Class 02 (Lorry)", amount_float, status

# --- PDF Report Generator ---
def generate_pdf(dataframe):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", size=14)
    pdf.cell(200, 10, txt="Bulk DC - Highway Bill Summary Report", ln=1, align='C')
    pdf.ln(10)
    
    pdf.set_font("Arial", 'B', size=10)
    headers = ["ID", "Date", "Vehicle No", "Route", "Amount"]
    for h in headers:
        pdf.cell(35, 10, h, 1)
    pdf.ln()
    
    pdf.set_font("Arial", size=9)
    for _, row in dataframe.iterrows():
        pdf.cell(35, 10, str(row['id']), 1)
        pdf.cell(35, 10, str(row['date']), 1)
        pdf.cell(35, 10, str(row['vehicle_no']), 1)
        pdf.cell(35, 10, str(row['route']), 1)
        pdf.cell(35, 10, str(row['amount']), 1)
        pdf.ln()
    return pdf.output(dest='S').encode('latin1')

# --- Navigation Tabs ---
tab1, tab2, tab3 = st.tabs(["📸 Scanner & Live Edit", "📊 Dashboard Charts", "🗂️ Database Records"])

# --- TAB 1: SCANNER ---
with tab1:
    st.subheader("📸 Mobile Cam Live Scanner")
    cam_image = st.camera_input("📸 බිල්පතක් ස්කෑන් කරන්න")
    
    if cam_image:
        image = Image.open(cam_image)
        with st.spinner("AI සහ OpenCV මඟින් පින්තූරය පැහැදිලි කර කියවමින් පවති..."):
            dt, v_no, loc, v_tp, amt, stat = process_image_ocr(image)
        
        st.warning("🔍 දත්ත නිවැරදිදැයි තහවුරු කරගන්න (වැරදි ඇත්නම් සකසන්න):")
        col1, col2 = st.columns(2)
        with col1:
            edit_date = st.text_input("දිනය", value=dt)
            edit_v_no = st.text_input("වාහන අංකය", value=v_no)
            edit_loc = st.text_input("මාර්ගය / ස්ථානය", value=loc)
        with col2:
            edit_amt = st.number_input("මුදල (LKR)", value=amt, step=50.0)
            new_stat = "Verified ✅" if (edit_v_no != "Unknown" and edit_amt > 0) else stat
            st.write(f"තත්ත්වය: **{new_stat}**")
            
        if st.button("💾 Save to Database"):
            db.add_record(edit_date, edit_v_no, edit_loc, v_tp, edit_amt, new_stat)
            st.success("🎉 සාර්ථකව Database එකට සේව් කරන ලදී!")

# --- TAB 2: DASHBOARD ---
with tab2:
    st.subheader("📊 Transport Analytics Dashboard")
    df = db.get_all_records()
    if not df.empty:
        c1, c2 = st.columns(2)
        c1.metric("Total Bills Scanned", len(df))
        c2.metric("Total Cost (LKR)", f"LKR {df['amount'].sum():,.2f}")
        
        st.markdown("---")
        st.write("🚚 **ලොරි රථ අනුව මාසික වියදම**")
        st.bar_chart(df.groupby("vehicle_no")["amount"].sum())
    else:
        st.info("දත්ත පෙන්වීමට ප්‍රමාණවත් රෙකෝඩ්ස් නොමැත.")

# --- TAB 3: RECORDS DATABASE ---
with tab3:
    st.subheader("🗂️ Stored Database Records")
    df_records = db.get_all_records()
    
    if not df_records.empty:
        st.write("💡 ඔබට අවශ්‍ය නම් පහත වගුවේ ඕනෑම තැනක් ක්ලික් කර අගයන් වෙනස් කල හැක:")
        edited_df = st.data_editor(df_records, use_container_width=True, num_rows="dynamic")
        
        if st.button("🔄 Update Database Changes"):
            db.update_db_from_dataframe(edited_df)
            st.success("Database එක සාර්ථකව Update කරන ලදී!")
            
        st.markdown("---")
        # Download buttons
        csv = edited_df.to_csv(index=False).encode('utf-8')
        st.download_button("📥 Download Excel (CSV)", data=csv, file_name="Highway_Toll_Report.csv", mime="text/csv")
        
        pdf_data = generate_pdf(edited_df)
        st.download_button("📥 Download PDF Report", data=pdf_data, file_name="Highway_Toll_Report.pdf", mime="application/pdf")
    else:
        st.info("Database එකේ දැනට දත්ත කිසිවක් සේව් කර නොමැත.")