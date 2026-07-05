import streamlit as st
import os
import json
import re
from google.cloud import vision
from google.oauth2 import service_account

# database.py එකෙන් insert_bill function එක import කරගැනීම
try:
    from database import insert_bill
except ImportError:
    st.warning("database.py වෙතින් insert_bill සොයාගත නොහැකි විය. කරුණාකර database ශ්‍රිතයන් පරීක්ෂා කරන්න.")

# --- 1. Google Cloud Credentials සක්‍රීය කරගැනීම (Local + Cloud එකටම ගැළපෙන ලෙස) ---
# Streamlit Cloud එකේ Secrets තිබේ නම් එයින් කියවයි, නැතහොත් Local json ගොනුව කියවයි.
if st.secrets.get("gcp_service_account"):
    # Streamlit Cloud (Production) සඳහා
    credentials_info = dict(st.secrets["gcp_service_account"])
    credentials = service_account.Credentials.from_service_account_info(credentials_info)
else:
    # Local PC (Development) සඳහා
    KEY_PATH = "google_key.json"
    if os.path.exists(KEY_PATH):
        credentials = service_account.Credentials.from_service_account_file(KEY_PATH)
    else:
        st.error("Google Cloud Credentials සොයාගත නොහැක. කරුණාකර local json ෆයිල් එක හෝ Streamlit Cloud Secrets පරීක්ෂා කරන්න.")
        st.stop()

# Cloud Vision Client එක සාදා ගැනීම
client = vision.ImageAnnotatorClient(credentials=credentials)


# --- 2. OCR මඟින් ලැබෙන Text එකෙන් දත්ත වෙන් කරගැනීමට Regex භාවිතය ---
def extract_bill_details(text):
    details = {
        "entrance": "Not Found",
        "exit": "Not Found",
        "amount": 0.0,
        "date": "Not Found"
    }
    
    # පේළි වශයෙන් text එක වෙන් කරගැනීම
    lines = text.split("\n")
    
    for line in lines:
        line_lower = line.lower()
        
        # 🧾 ඇතුළු වූ ස්ථානය (Entrance) සෙවීම
        if "entrance" in line_lower or "from" in line_lower:
            match = re.search(r'(?:entrance|from)\s*[:-]?\s*([A-Za-z\s]+)', line, re.IGNORECASE)
            if match:
                details["entrance"] = match.group(1).strip()
                
        # 🚪 පිට වූ ස්ථානය (Exit) සෙවීම
        elif "exit" in line_lower or "to" in line_lower:
            match = re.search(r'(?:exit|to)\s*[:-]?\s*([A-Za-z\s]+)', line, re.IGNORECASE)
            if match:
                details["exit"] = match.group(1).strip()
                
        # 📅 දිනය (Date) සෙවීම (YYYY-MM-DD හෝ DD/MM/YYYY ආකාරයට)
        match_date = re.search(r'(\d{4}[-/]\d{2}[-/]\d{2})|(\d{2}[-/]\d{2}[-/]\d{4})', line)
        if match_date and details["date"] == "Not Found":
            details["date"] = match_date.group(0)

        # 💵 මුදල (Amount / Total) සෙවීම
        if "amount" in line_lower or "total" in line_lower or "rs" in line_lower:
            match_amt = re.search(r'(?:rs\.?|total|amount)\s*[:.-]?\s*([\d,]+\.?\d*)', line, re.IGNORECASE)
            if match_amt:
                try:
                    amt_str = match_amt.group(1).replace(",", "")
                    details["amount"] = float(amt_str)
                except ValueError:
                    pass
                    
    return details


# --- 3. Streamlit UI නිර්මාණය ---
st.set_page_config(page_title="Highway Bill Scanner OCR", page_icon="🛣️", layout="centered")

st.title("🛣️ Highway Bill Scanner & OCR System")
st.write("ගූගල් ක්ලවුඩ් විෂන් API තාක්ෂණයෙන් අධිවේගී මාර්ග බිල්පත් ස්කෑන් කර දත්ත ගබඩා කිරීම.")
st.markdown("---")

# ෆොටෝ එකක් අප්ලෝඩ් කිරීමට හෝ කැමරාවෙන් ගැනීමට ඉඩ දීම
uploaded_file = st.file_uploader("බිල්පතෙහි පැහැදිලි ඡායාරූපයක් තෝරන්න (JPG, PNG)", type=["jpg", "jpeg", "png"])

if uploaded_file is not None:
    # අප්ලෝඩ් කරපු රූපය UI එකේ පෙන්වීම
    st.image(uploaded_file, caption="Uploaded Bill Image", use_container_width=True)
    
    # Scan බටන් එක
    if st.button("🔍 Scan Bill & Extract Data", type="primary"):
        with st.spinner("Google Cloud Vision මඟින් බිල්පත කියවමින් පවතී..."):
            try:
                # --- 4. Google Cloud Vision OCR ක්‍රියාවලිය ---
                content = uploaded_file.read()
                image = vision.Image(content=content)
                
                # Text Detection එක සිදු කිරීම
                response = client.text_detection(image=image)
                texts = response.text_annotations
                
                if not texts:
                    st.error("බිල්පතේ කිසිදු අකුරක් හඳුනා ගැනීමට නොහැකි විය. කරුණාකර වෙනත් පැහැදිලි ඡායාරූපයක් උත්සාහ කරන්න.")
                else:
                    # සම්පූර්ණ කියවා ගත් Text එක
                    full_extracted_text = texts[0].description
                    
                    st.success("📝 බිල්පත සාර්ථකව කියවා ගන්නා ලදී!")
                    
                    # දත්ත වෙන් කරගැනීම (Parsing)
                    bill_data = extract_bill_details(full_extracted_text)
                    
                    # ප්‍රතිඵල UI එකේ පෙන්වීම
                    st.subheader("📊 හඳුනාගත් විස්තර (Extracted Details)")
                    
                    col1, col2 = st.columns(2)
                    with col1:
                        st.markdown(f"**📍 Entrance (ඇතුළු වූ ස්ථානය):** {bill_data['entrance']}")
                        st.markdown(f"**🚪 Exit (පිට වූ ස්ථානය):** {bill_data['exit']}")
                    with col2:
                        st.markdown(f"**📅 Date (දිනය):** {bill_data['date']}")
                        st.markdown(f"**💵 Amount (මුදල):** Rs. {bill_data['amount']:.2f}")
                    
                    # --- 5. Database එකට දත්ත ඇතුළත් කිරීම ---
                    st.markdown("---")
                    with st.spinner("දත්ත සමුදාය (Database) වෙත ඇතුළත් කරමින්..."):
                        try:
                            # database.py හි ඇති ශ්‍රිතය ක්‍රියාත්මක කිරීම
                            insert_bill(
                                entrance=bill_data['entrance'],
                                exit_location=bill_data['exit'],
                                amount=bill_data['amount'],
                                bill_date=bill_data['date']
                            )
                            st.success("💾 දත්ත සාර්ථකව Database එකට සේව් කරන ලදී!")
                        except Exception as db_err:
                            st.error(f"Database Error: දත්ත සුරැකීමට නොහැකි විය. ({db_err})")
                            
                    # අවශ්‍ය නම් මුළු Text එකම බලාගැනීමට Expander එකක්
                    with st.expander("🔍 View Raw Extracted Text"):
                        st.text(full_extracted_text)
                        
            except Exception as api_err:
                st.error(f"API Error: Google Cloud Vision සමඟ සම්බන්ධ වීමේ ගැටලුවක්. ({api_err})")