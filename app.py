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

st.set_page_config(page_title="Bulk DC Toll Scanner", page_icon="🚛", layout="wide")

# OCR Loader
@st.cache_resource
def load_ocr():
    return easyocr.Reader(['en'])

reader = load_ocr()

def process_image_ocr(image):
    img_np = np.array(image)
    results = reader.readtext(img_np, detail=0)
    full_text = " ".join(results).upper()
    
    # Regex Patterns
    vehicle_pattern = r'\b([A-Z]{2,3}\s*[-–\.] ashes?\s*[0-9]{4})\b'
    vehicle_match = re.search(vehicle_pattern, full_text)
    vehicle_no = vehicle_match.group(1).replace(".", "").replace(" ", "-") if vehicle_match else "Unknown"
    
    date_pattern = r'\b(202[0-9]\s*[-/]?\s*[0-1][0-9]\s*[-/]?\s*[0-3][0-9])\b'
    date_match = re.search(date_pattern, full_text)
    date = date_match.group(1).replace(" ", "-") if date_match else str(datetime.date.today())
    
    amount_pattern = r'\b([0-9,]+\s*\.\s*00)\b'
    amount_matches = re.findall(amount_pattern, full_text)
    amount = amount_matches[-1].replace(" ", "") if amount_matches else "0.00"
    try:
        amount_float = float(amount.replace(",", ""))
    except:
        amount_float = 0.00
        
    location_pattern = r'\b([A-Z\s]+/+[A-Z\s]+[0-9]*)\b'
    location_match = re.search(location_pattern, full_text)
    location = location_match.group(1).strip() if location_match else "Unknown"
    
    status = "Review Needed ⚠️" if (vehicle_no == "Unknown" or amount_float == 0.00) else "Verified ✅"
    return date, vehicle_no, location, "Class 02 (Lorry)", amount_float, status

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

# Navigation Tabs
tab1, tab2, tab3 = st.tabs(["📸 Scanner & Live Edit", "📊 Dashboard Charts", "🗂️ Database Records"])

# --- TAB 1: SCANNER ---
with tab1:
    st.subheader("📸 Mobile Cam Live Scanner")
    cam_image = st.camera_input("📸 බිල්පතක් ස්කෑන් කරන්න")
    
    if cam_image:
        image = Image.open(cam_image)
        with st.spinner("AI මඟින් පරීක්ෂා කරමින් පවතී..."):
            dt, v_no, loc, v_tp, amt, stat = process_image_ocr(image)
        
        st.warning("🔍 දත්ත නිවැරදිදැයි තහවුරු කරගන්න:")
        col1, col2 = st.columns(2)
        with col1:
            edit_date = st.text_input("දිනය", value=dt)
            edit_v_no = st.text_input("වාහන අංකය", value=v_no)
            edit_loc = st.text_input("මාර්ගය", value=loc)
        with col2:
            edit_amt = st.number_input("මුදල (LKR)", value=amt)
            new_stat = "Verified ✅" if (edit_v_no != "Unknown" and edit_amt > 0) else stat
            st.write(f"තත්ත්වය: **{new_stat}**")
            
        if st.button("💾 Save to Database"):
            db.add_record(edit_date, edit_v_no, edit_loc, v_tp, edit_amt, new_stat)
            st.success("🎉 සාර්ථකව සේව් කරන ලදී!")

# --- TAB 2: DASHBOARD ---
with tab2:
    st.subheader("📊 Transport Analytics")
    df = db.get_all_records()
    if not df.empty:
        c1, c2 = st.columns(2)
        c1.metric("Total Bills", len(df))
        c2.metric("Total Cost", f"LKR {df['amount'].sum():,.2f}")
        
        st.bar_chart(df.groupby("vehicle_no")["amount"].sum())
    else:
        st.info("දත්ත නොමැත.")

# --- TAB 3: RECORDS DATABASE ---
with tab3:
    st.subheader("🗂️ Stored Database Records")
    df_records = db.get_all_records()
    
    if not df_records.empty:
        # Inline editing table
        edited_df = st.data_editor(df_records, use_container_width=True, num_rows="dynamic")
        
        if st.button("🔄 Update Database Changes"):
            db.update_db_from_dataframe(edited_df)
            st.success("Database එක Update කරන ලදී!")
            
        # Download buttons
        csv = edited_df.to_csv(index=False).encode('utf-8')
        st.download_button("📥 Download Excel (CSV)", data=csv, file_name="Toll_Report.csv", mime="text/csv")
        
        pdf_data = generate_pdf(edited_df)
        st.download_button("📥 Download PDF", data=pdf_data, file_name="Toll_Report.pdf", mime="application/pdf")