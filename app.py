import streamlit as st
import google.generativeai as genai
from PIL import Image
import pandas as pd
from io import BytesIO
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer
)
from reportlab.lib.styles import getSampleStyleSheet
import urllib.parse
import tempfile
import json
import re

# -------------------------
# PAGE CONFIG
# -------------------------
st.set_page_config(
    page_title="AI Bill Checker Pro",
    page_icon="🧾",
    layout="wide"
)

# -------------------------
# LOGIN SYSTEM
# -------------------------
USERNAME = st.secrets["APP_USERNAME"]
PASSWORD = st.secrets["APP_PASSWORD"]

if "logged_in" not in st.session_state:
    st.session_state.logged_in = False

if not st.session_state.logged_in:

    st.title("🔐 AI Bill Checker Login")

    username = st.text_input("Username")
    password = st.text_input(
        "Password",
        type="password"
    )

    if st.button("Login"):

        if (
            username == USERNAME
            and password == PASSWORD
        ):
            st.session_state.logged_in = True
            st.rerun()

        else:
            st.error(
                "Invalid Username or Password"
            )

    st.stop()

# -------------------------
# SIDEBAR
# -------------------------
st.sidebar.success("Logged In")

if st.sidebar.button("🚪 Logout"):
    st.session_state.logged_in = False
    st.rerun()

# -------------------------
# TITLE
# -------------------------
st.title("🧾 AI Bill Checker Pro")

# -------------------------
# GEMINI SETUP
# -------------------------
try:
    api_key = st.secrets[
        "GEMINI_API_KEY"
    ]

except Exception:

    st.error(
        "GEMINI_API_KEY not found."
    )
    st.stop()

genai.configure(api_key=api_key)

try:

    model = genai.GenerativeModel(
        "gemini-2.5-flash"
    )

except Exception as e:

    st.error(
        f"Model Error: {e}"
    )

    st.stop()

# -------------------------
# FILE UPLOAD
# -------------------------
uploaded_file = st.file_uploader(
    "Upload Bill Image",
    type=[
        "jpg",
        "jpeg",
        "png"
    ]
)

if uploaded_file:

    image = Image.open(
        uploaded_file
    )

    st.image(
        image,
        caption="Uploaded Bill",
        use_container_width=True
    )

    if st.button(
        "🔍 Analyze Bill"
    ):

        with st.spinner(
            "Analyzing Bill..."
        ):

            prompt = """
Analyze this bill image carefully.

Extract:

- shop_name
- bill_date
- gst_number
- cgst
- sgst
- igst
- items
- total

Return ONLY valid JSON.

{
  "shop_name":"",
  "bill_date":"",
  "gst_number":"",
  "cgst":"",
  "sgst":"",
  "igst":"",
  "items":[
    {
      "name":"",
      "qty":"",
      "rate":"",
      "amount":""
    }
  ],
  "total":""
}
"""

            try:

                response = (
                    model.generate_content(
                        [
                            prompt,
                            image
                        ]
                    )
                )

                text = (
                    response.text.strip()
                )

                text = text.replace(
                    "```json",
                    ""
                )

                text = text.replace(
                    "```",
                    ""
                )

                match = re.search(
                    r"\{.*\}",
                    text,
                    re.DOTALL
                )

                if match:
                    text = match.group(0)

                data = json.loads(text)

                st.success(
                    "✅ Analysis Complete"
                )

                shop_name = data.get(
                    "shop_name",
                    "N/A"
                )

                bill_date = data.get(
                    "bill_date",
                    "N/A"
                )

                gst_number = data.get(
                    "gst_number",
                    "N/A"
                )

                st.subheader(
                    "🏪 Bill Information"
                )

                c1, c2, c3 = (
                    st.columns(3)
                )

                with c1:
                    st.metric(
                        "Shop",
                        shop_name
                    )

                with c2:
                    st.metric(
                        "Date",
                        bill_date
                    )

                with c3:
                    st.metric(
                        "GST",
                        gst_number
                    )

                items = data.get(
                    "items",
                    []
                )

                if not items:

                    st.warning(
                        "No bill items found."
                    )

                    st.stop()

                df = pd.DataFrame(
                    items
                ) 
                # -------------------------
                # BILL ITEMS TABLE
                # -------------------------
                st.subheader(
                    "📋 Bill Items"
                )

                st.dataframe(
                    df,
                    use_container_width=True,
                    hide_index=True
                )

                # -------------------------
                # ADVANCED VALIDATION
                # -------------------------

                df["qty"] = pd.to_numeric(
                    df.get("qty", 0),
                    errors="coerce"
                ).fillna(0)

                df["rate"] = pd.to_numeric(
                    df.get("rate", 0),
                    errors="coerce"
                ).fillna(0)

                df["amount"] = pd.to_numeric(
                    df.get("amount", 0),
                    errors="coerce"
                ).fillna(0)

                # Qty × Rate Validation

                df["expected_amount"] = (
                    df["qty"] *
                    df["rate"]
                )

                df["difference"] = (
                    df["amount"] -
                    df["expected_amount"]
                )

                # -------------------------
                # ITEM VALIDATION
                # -------------------------

                mismatch_rows = df[
                    df["difference"].abs() > 0.01
                ]

                st.subheader(
                    "🔎 Item Validation"
                )

                if mismatch_rows.empty:

                    st.success(
                        "✅ All item rows are correct"
                    )

                else:

                    st.error(
                        f"❌ {len(mismatch_rows)} mismatch row(s) found"
                    )

                    st.dataframe(
                        mismatch_rows,
                        use_container_width=True
                    )

                # -------------------------
                # GST DETECTION
                # -------------------------

                try:
                    cgst = float(
                        data.get(
                            "cgst",
                            0
                        ) or 0
                    )
                except:
                    cgst = 0

                try:
                    sgst = float(
                        data.get(
                            "sgst",
                            0
                        ) or 0
                    )
                except:
                    sgst = 0

                try:
                    igst = float(
                        data.get(
                            "igst",
                            0
                        ) or 0
                    )
                except:
                    igst = 0

                gst_total = (
                    cgst +
                    sgst +
                    igst
                )

                item_total = float(
                    df["amount"].sum()
                )

                if gst_total > 0:

                    bill_type = (
                        "GST Bill"
                    )

                    calculated_total = (
                        item_total +
                        gst_total
                    )

                else:

                    bill_type = (
                        "Non-GST Bill"
                    )

                    calculated_total = (
                        item_total
                    )

                try:

                    bill_total = float(
                        data.get(
                            "total",
                            0
                        )
                    )

                except:

                    bill_total = 0

                # -------------------------
                # BILL SUMMARY
                # -------------------------

                st.subheader(
                    "💰 Bill Summary"
                )

                x1, x2, x3, x4 = (
                    st.columns(4)
                )

                with x1:

                    st.metric(
                        "Items Total",
                        f"₹{item_total:,.2f}"
                    )

                with x2:

                    st.metric(
                        "GST Total",
                        f"₹{gst_total:,.2f}"
                    )

                with x3:

                    st.metric(
                        "Bill Total",
                        f"₹{bill_total:,.2f}"
                    )

                with x4:

                    st.metric(
                        "Bill Type",
                        bill_type
                    )

                diff = abs(
                    calculated_total -
                    bill_total
                )

                if diff < 1:

                    st.success(
                        "✅ Grand Total Matched"
                    )

                else:

                    st.error(
                        f"❌ Bill Mismatch (₹{diff:,.2f})"
                    )

                # -------------------------
                # ERROR ANALYSIS
                # -------------------------

                if not mismatch_rows.empty:

                    st.subheader(
                        "🤖 Error Analysis"
                    )

                    for idx, row in (
                        mismatch_rows
                        .iterrows()
                    ):

                        st.warning(
                            f'''
Row: {idx + 1}

Item:
{row.get("name","N/A")}

Qty:
{row["qty"]}

Rate:
₹{row["rate"]}

Expected Amount:
₹{row["expected_amount"]:.2f}

Bill Amount:
₹{row["amount"]:.2f}

Difference:
₹{row["difference"]:.2f}
'''
                        )
                                        # -------------------------
                # EXCEL DOWNLOAD
                # -------------------------

                excel_buffer = BytesIO()

                export_df = df.copy()

                with pd.ExcelWriter(
                    excel_buffer,
                    engine="openpyxl"
                ) as writer:

                    export_df.to_excel(
                        writer,
                        index=False,
                        sheet_name="Bill Items"
                    )

                st.download_button(
                    "📥 Download Excel",
                    data=excel_buffer.getvalue(),
                    file_name="bill_report.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )

                # -------------------------
                # PDF REPORT
                # -------------------------

                pdf_temp = tempfile.NamedTemporaryFile(
                    delete=False,
                    suffix=".pdf"
                )

                doc = SimpleDocTemplate(
                    pdf_temp.name
                )

                styles = (
                    getSampleStyleSheet()
                )

                elements = [

                    Paragraph(
                        "AI Bill Checker Report",
                        styles["Title"]
                    ),

                    Spacer(1, 12),

                    Paragraph(
                        f"Shop: {shop_name}",
                        styles["BodyText"]
                    ),

                    Paragraph(
                        f"Date: {bill_date}",
                        styles["BodyText"]
                    ),

                    Paragraph(
                        f"GST Number: {gst_number}",
                        styles["BodyText"]
                    ),

                    Paragraph(
                        f"Bill Type: {bill_type}",
                        styles["BodyText"]
                    ),

                    Paragraph(
                        f"Items Total: ₹{item_total:.2f}",
                        styles["BodyText"]
                    ),

                    Paragraph(
                        f"GST Total: ₹{gst_total:.2f}",
                        styles["BodyText"]
                    ),

                    Paragraph(
                        f"Calculated Total: ₹{calculated_total:.2f}",
                        styles["BodyText"]
                    ),

                    Paragraph(
                        f"Bill Total: ₹{bill_total:.2f}",
                        styles["BodyText"]
                    ),

                    Paragraph(
                        f"Difference: ₹{diff:.2f}",
                        styles["BodyText"]
                    ),

                    Spacer(1, 12)
                ]

                if not mismatch_rows.empty:

                    elements.append(
                        Paragraph(
                            "Mismatch Details",
                            styles["Heading2"]
                        )
                    )

                    for idx, row in (
                        mismatch_rows.iterrows()
                    ):

                        elements.append(
                            Paragraph(
                                f"""
Row {idx + 1}
<br/>
Item:
{row.get('name','N/A')}
<br/>
Qty:
{row['qty']}
<br/>
Rate:
₹{row['rate']}
<br/>
Expected:
₹{row['expected_amount']:.2f}
<br/>
Actual:
₹{row['amount']:.2f}
<br/>
Difference:
₹{row['difference']:.2f}
""",
                                styles[
                                    "BodyText"
                                ]
                            )
                        )

                doc.build(elements)

                with open(
                    pdf_temp.name,
                    "rb"
                ) as f:

                    st.download_button(
                        "📄 Download PDF",
                        data=f.read(),
                        file_name="bill_report.pdf",
                        mime="application/pdf"
                    )

                # -------------------------
                # WHATSAPP SHARE
                # -------------------------

                message = f"""
🏪 Shop: {shop_name}

📅 Date: {bill_date}

🧾 GST: {gst_number}

📄 Bill Type: {bill_type}

💰 Items Total: ₹{item_total:.2f}

🧮 GST Total: ₹{gst_total:.2f}

💵 Bill Total: ₹{bill_total:.2f}

📊 Difference: ₹{diff:.2f}
"""

                wa_url = (
                    "https://wa.me/?text="
                    +
                    urllib.parse.quote(
                        message
                    )
                )

                st.link_button(
                    "📱 Share on WhatsApp",
                    wa_url
                )

            except Exception as e:

                st.error(
                    f"Analysis Error: {str(e)}"
                )
