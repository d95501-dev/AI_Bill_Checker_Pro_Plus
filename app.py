import streamlit as st
import easyocr
from PIL import Image
import pandas as pd
import re
import numpy as np

st.set_page_config(
    page_title="Bill Checker",
    page_icon="🧾"
)

st.title("🧾 Unlimited Bill Checker")

uploaded_file = st.file_uploader(
    "Upload Bill",
    type=["jpg", "jpeg", "png"]
)

if uploaded_file:

    image = Image.open(uploaded_file)

    st.image(
        image,
        use_container_width=True
    )

    if st.button("Analyze Bill"):

        with st.spinner("Reading Bill..."):

            img = np.array(image)

            reader = easyocr.Reader(
                ['en'],
                gpu=False
            )

            results = reader.readtext(
                img,
                detail=0
            )

            text = "\n".join(results)

            st.subheader("Detected Text")
            st.text(text)

            # Extract Numbers
            amounts = re.findall(
                r"\d+\.\d+|\d+",
                text
            )

            numbers = []

            for n in amounts:
                try:
                    numbers.append(float(n))
                except:
                    pass

            st.subheader(
                "Detected Numbers"
            )

            st.write(numbers)

            if len(numbers) > 1:

                bill_total = max(numbers)

                calculated_total = (
                    sum(numbers[:-1])
                )

                st.subheader(
                    "Bill Result"
                )

                st.metric(
                    "Calculated Sum",
                    f"₹{calculated_total:.2f}"
                )

                st.metric(
                    "Bill Total",
                    f"₹{bill_total:.2f}"
                )

                diff = abs(
                    calculated_total -
                    bill_total
                )

                if diff < 1:

                    st.success(
                        "✅ Bill Matched"
                    )

                else:

                    st.error(
                        f"❌ Bill Mismatch (₹{diff:.2f})"
                    )

            df = pd.DataFrame({
                "Detected Text": results
            })

            st.download_button(
                "Download CSV",
                df.to_csv(
                    index=False
                ),
                "bill.csv",
                "text/csv"
            )
