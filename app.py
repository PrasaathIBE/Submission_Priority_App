#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import streamlit as st
import pandas as pd
from datetime import datetime
import re
import unicodedata
import io

DAY_LIMIT = 25
DATE_THRESHOLD = pd.Timestamp("2024-01-01")

# =========================
# COMMON NORMALIZATION (Same as your logic)
# =========================
def excel_like_ref(ref):
    if pd.isna(ref):
        return ""
    txt = unicodedata.normalize("NFKC", str(ref))
    txt = re.sub(r"[\s\u200b\xa0]+", "", txt)
    txt = txt.lower()

    bracket_match = re.search(r"\[([a-z0-9\-]+kit[a-z0-9\-_]+)\]", txt)
    if bracket_match:
        txt = bracket_match.group(1)
    else:
        txt = re.sub(r"^(zr|za|zxx)\d+", "", txt)
        txt = txt.strip("[]")

    dup_match = re.match(r"^([a-z0-9\-_]+)\[\1\]$", txt)
    if dup_match:
        txt = dup_match.group(1)

    return txt.strip()

# =========================
# PRIORITY 1 FUNCTION (Your original logic)
# =========================
def priority_1_logic(df):

    df.columns = df.columns.str.strip()
    ref_col = [c for c in df.columns if "ref" in c.lower() or "reference" in c.lower()][0]
    status_col = [c for c in df.columns if "status" in c.lower()][0]
    init_date_col = [c for c in df.columns if "initial" in c.lower()][0]
    update_date_col = [c for c in df.columns if "updated" in c.lower() or "last" in c.lower()][0]

    # Step 1: Normalize Reference_No
    df[ref_col] = df[ref_col].apply(excel_like_ref)

    # Step 2: Convert dates
    df[init_date_col] = pd.to_datetime(df[init_date_col], errors="coerce")
    df[update_date_col] = pd.to_datetime(df[update_date_col], errors="coerce")

    today = pd.Timestamp(datetime.now().date())

    # Step 3: Filter ref where ALL statuses = Rejected
    priority1_refs = (
        df.groupby(ref_col)[status_col]
        .apply(lambda x: all(str(s).strip().lower() == "rejected" for s in x))
        .reset_index()
    )
    priority1_refs = priority1_refs[priority1_refs[status_col]][ref_col]

    # Step 4: Get all rows for these Reference_Nos
    priority1_data = df[df[ref_col].isin(priority1_refs)].copy()

    # Step 5: Apply date filters
    priority1_filtered = priority1_data[
        (priority1_data[init_date_col] >= DATE_THRESHOLD)
        & ((today - priority1_data[update_date_col]).dt.days > DAY_LIMIT)
    ]

    # Step 6: FINAL – EXACT Excel behavior (deduplicate on Reference_No)
    final_output = priority1_filtered.drop_duplicates(subset=[ref_col], keep="first")

    return final_output



# =========================
# PRIORITY 2 FUNCTION (Your original logic)
# =========================
def priority_2_logic(df):

    df.columns = df.columns.str.strip()
    ref_col = [c for c in df.columns if "ref" in c.lower() or "reference" in c.lower()][0]
    status_col = [c for c in df.columns if "status" in c.lower()][0]
    init_date_col = [c for c in df.columns if "initial" in c.lower()][0]
    update_date_col = [c for c in df.columns if "updated" in c.lower() or "last" in c.lower()][0]

    df[ref_col] = df[ref_col].apply(excel_like_ref)
    df[init_date_col] = pd.to_datetime(df[init_date_col], errors="coerce")
    df[update_date_col] = pd.to_datetime(df[update_date_col], errors="coerce")

    today = pd.Timestamp(datetime.now().date())

    # Priority Conditions
    conditions = {
        "2a": {"pair": {"rejected", "po paper submitted"}, "date_col": init_date_col},
        "2b": {"pair": {"rejected", "under review (reviewer assigned by eic)"}, "date_col": update_date_col},
        "2c": {"pair": {"rejected", "under review – revised version (reviewer assigned by eic)"}, "date_col": update_date_col},
        "2d": {"pair": {"rejected", "paper send back to author"}, "date_col": update_date_col},
    }

    grouped = df.groupby(ref_col)
    output_dict = {}

    for key, conf in conditions.items():
        pair = conf["pair"]
        date_col = conf["date_col"]
        valid_refs = []

        for ref, group in grouped:
            statuses = set(group[status_col].dropna().astype(str).str.strip().str.lower())

            if statuses == pair:
                active_status = list(pair - {"rejected"})[0]
                sub_df = group[group[status_col].str.strip().str.lower() == active_status]
                sub_df["Days_Diff"] = (today - sub_df[date_col]).dt.days

                if (sub_df["Days_Diff"] > DAY_LIMIT).any():
                    valid_refs.append(ref)

        # All rows for matching refs
        filtered = df[df[ref_col].isin(valid_refs)]

        # FINAL – Excel dedupe: keep only first row per Reference_No
        filtered_unique = filtered.drop_duplicates(subset=[ref_col], keep="first")

        output_dict[key] = filtered_unique

    return output_dict



# =========================
# STREAMLIT UI WITH TABS
# =========================
st.title("📌 Priority 1 & Priority 2 — Excel Logic Tool")

uploaded_file = st.file_uploader("Upload Master Excel File", type=["xlsx"])

if uploaded_file:
    df = pd.read_excel(uploaded_file)

    tab1, tab2 = st.tabs(["Priority 1", "Priority 2"])

    # ---------------------- TAB 1 ----------------------
    with tab1:
        st.header("Priority 1 — All statuses = Rejected (>25 days)")
        if st.button("Run Priority 1"):
            with st.spinner("Running Priority 1 Logic..."):
                result1 = priority_1_logic(df)

            st.success(f"Completed! {len(result1)} records found.")

            output = io.BytesIO()
            result1.to_excel(output, index=False)
            output.seek(0)

            st.download_button(
                label="📥 Download Priority_1_Rejected_Final_ExcelLogic.xlsx",
                data=output,
                file_name="Priority_1_Rejected_Final_ExcelLogic.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )

            st.dataframe(result1, use_container_width=True)

    # ---------------------- TAB 2 ----------------------
    with tab2:
        st.header("Priority 2 — Strict Crosschecked Output (2a – 2d)")

        if st.button("Run Priority 2"):
            with st.spinner("Running Priority 2 Logic..."):
                result2 = priority_2_logic(df)

            for key, table in result2.items():
                st.subheader(f"Priority {key.upper()} — {len(table)} records")

                out = io.BytesIO()
                table.to_excel(out, index=False)
                out.seek(0)

                st.download_button(
                    label=f"📥 Download Priority_{key}_STRICT_CROSSCHECKED_Final_ExcelLogic.xlsx",
                    data=out,
                    file_name=f"Priority_{key}_STRICT_CROSSCHECKED_Final_ExcelLogic.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )

                st.dataframe(table, use_container_width=True)
