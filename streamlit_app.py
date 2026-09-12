# GWSCafeteria Dashboard - Auto-reads from Google Sheets synced via Power Automate from Microsoft Forms
# Co-authored with CoCo
import streamlit as st
import pandas as pd
import altair as alt
from datetime import date, timedelta
import google.generativeai as genai
import requests as http_requests

# --- Config ---
FOOD_ITEMS = [
    "Salad", "Rotis", "Dry Veg", "Wet Veg", "Rasam / Sambar",
    "Dal", "Steamed Rice", "Flavoured Rice", "Curd", "Dessert",
    "Refreshment/Juice"
]
FEEDBACK_CRITERIA = ["Portioning", "Taste", "Texture", "Presentation", "Aroma"]
FLOORS = ["8th Floor", "9th Floor"]


# --- Column name finder (fuzzy match) ---
def find_col(df, *candidates):
    """Find a column by trying multiple name variants."""
    for c in candidates:
        for col in df.columns:
            if col.strip().lower() == c.strip().lower():
                return col
    return None


# --- Data Loading ---
@st.cache_data(ttl=300)
def load_food_tracker():
    url = st.secrets.get("google_sheets", {}).get("food_tracker_url", "")
    if not url:
        return pd.DataFrame()
    try:
        df = pd.read_csv(url, on_bad_lines="skip")
        df.columns = df.columns.str.strip()
        date_col = find_col(df, "Date")
        if date_col:
            df[date_col] = pd.to_datetime(df[date_col], errors="coerce").dt.date
            if date_col != "Date":
                df = df.rename(columns={date_col: "Date"})
        floor_col = find_col(df, "Floor")
        if floor_col and floor_col != "Floor":
            df = df.rename(columns={floor_col: "Floor"})
        check_col = find_col(df, "Check Time", "Check_Time", "CheckTime")
        if check_col and check_col != "Check Time":
            df = df.rename(columns={check_col: "Check Time"})
        proj_col = find_col(df, "Food Projected for the Day", "Food Projected for the day", "Projected")
        if proj_col and proj_col != "Food Projected for the Day":
            df = df.rename(columns={proj_col: "Food Projected for the Day"})
        actual_col = find_col(df, "Actual Consumption", "Actual_Consumption", "Consumption")
        if actual_col and actual_col != "Actual Consumption":
            df = df.rename(columns={actual_col: "Actual Consumption"})
        # Parse "Mark item availability:" multi-select into individual columns
        avail_col = find_col(df, "Mark item availability:", "Mark item availability", "Item Availability")
        if avail_col:
            for item in FOOD_ITEMS:
                df[item] = df[avail_col].astype(str).str.contains(item, case=False, na=False).map({True: "Yes", False: "No"})
        # Ensure numeric columns
        for c in ["Food Projected for the Day", "Actual Consumption"]:
            if c in df.columns:
                df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0).astype(int)
        return df
    except Exception as e:
        st.error(f"Error loading Food Tracker: {e}")
        return pd.DataFrame()


@st.cache_data(ttl=300)
def load_meal_feedback():
    url = st.secrets.get("google_sheets", {}).get("meal_feedback_url", "")
    if not url:
        return pd.DataFrame()
    try:
        df = pd.read_csv(url, on_bad_lines="skip")
        df.columns = df.columns.str.strip()

        # Date: use Start time or Completion time if Feedback Date not present
        date_col = find_col(df, "Feedback Date", "Date", "Start time", "Completion time")
        if date_col:
            df["Feedback Date"] = pd.to_datetime(df[date_col], errors="coerce").dt.date

        # Floor
        floor_col = find_col(df, "Floor")
        if floor_col and floor_col != "Floor":
            df = df.rename(columns={floor_col: "Floor"})

        # Employee Name
        name_col = find_col(df, "Employee Name", "Name")
        if name_col and name_col != "Employee Name":
            df["Employee Name"] = df[name_col]

        # Ratings: map long question names to short criteria names
        rating_mappings = {
            "Portioning": ["Portioning", "How would you rate the food portioning", "portioning"],
            "Taste": ["Taste", "How would you rate the taste", "taste"],
            "Texture": ["Texture", "How would you rate the texture", "texture"],
            "Presentation": ["Presentation", "How would you rate the presentation", "presentation"],
            "Aroma": ["Aroma", "How would you rate the aroma", "aroma"],
            "Overall Rating": ["Overall Rating", "Overall_Rating", "Overall"],
        }
        for short_name, candidates in rating_mappings.items():
            matched = None
            for cand in candidates:
                for col in df.columns:
                    if cand.lower() in col.lower():
                        matched = col
                        break
                if matched:
                    break
            if matched:
                df[short_name] = pd.to_numeric(df[matched], errors="coerce")

        # Highlights / Low Lights
        hl_col = find_col(df, "Highlights", "Highlights (what was good)")
        if hl_col and hl_col != "Highlights":
            df["Highlights"] = df[hl_col]
        ll_col = find_col(df, "Low Lights", "Low lights", "Lowlights", "Low Lights (what needs improvement)")
        if ll_col and ll_col != "Low Lights":
            df["Low Lights"] = df[ll_col]
        ca_col = find_col(df, "Corrective Action", "Corrective Action Required")
        if ca_col and ca_col != "Corrective Action":
            df["Corrective Action"] = df[ca_col]

        return df
    except Exception as e:
        st.error(f"Error loading Meal Feedback: {e}")
        return pd.DataFrame()


def ai_complete(prompt):
    try:
        api_key = st.secrets.get("gemini", {}).get("api_key", "")
        if not api_key:
            return "Gemini API key not configured. Add it to Streamlit secrets under [gemini] api_key."
        # Try v1 endpoint first, then v1beta
        endpoints = [
            f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={api_key}",
            f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={api_key}",
            f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash-latest:generateContent?key={api_key}",
        ]
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"maxOutputTokens": 500, "temperature": 0.7}
        }
        for url in endpoints:
            resp = http_requests.post(url, json=payload, timeout=30)
            if resp.status_code == 200:
                data = resp.json()
                return data["candidates"][0]["content"]["parts"][0]["text"]
        # All endpoints failed — show the last error
        error_detail = resp.json().get("error", {}).get("message", resp.text[:300])
        return f"AI error: {error_detail}"
    except Exception as e:
        return f"AI unavailable: {str(e)}"


# --- CSS ---
def inject_css():
    st.markdown("""
    <style>
        .main-header { font-size: 2rem; font-weight: 700; color: #1E2340; margin-bottom: 0.5rem; }
        .sub-header { font-size: 1rem; color: #6B7280; margin-bottom: 1.5rem; }
        .metric-card {
            background: linear-gradient(135deg, #F0F9FF 0%, #E0F2FE 100%);
            border-radius: 12px; padding: 1.2rem; border-left: 4px solid #0891B2; margin-bottom: 1rem;
        }
        .metric-value { font-size: 2rem; font-weight: 700; color: #0891B2; }
        .metric-label { font-size: 0.85rem; color: #6B7280; text-transform: uppercase; letter-spacing: 0.5px; }
        .ai-response { background: #F0F9FF; border-left: 4px solid #0891B2; border-radius: 8px; padding: 1rem; margin: 0.5rem 0; }
    </style>
    """, unsafe_allow_html=True)


# --- Page: Dashboard ---
def page_dashboard():
    st.markdown('<div class="main-header">GWSCafeteria Dashboard</div>', unsafe_allow_html=True)
    st.markdown('<div class="sub-header">F5 Hyderabad Office | 8th & 9th Floors</div>', unsafe_allow_html=True)

    food_df = load_food_tracker()
    feedback_df = load_meal_feedback()
    today = date.today()

    # --- Filters ---
    filter_col1, filter_col2 = st.columns(2)
    with filter_col1:
        available_dates = sorted(food_df["Date"].dropna().unique().tolist(), reverse=True) if not food_df.empty and "Date" in food_df.columns else [today]
        default_idx = 0 if today in available_dates else 0
        display_date = st.selectbox("Select Date", available_dates, index=default_idx, key="dash_date")
    with filter_col2:
        all_floors = food_df["Floor"].dropna().unique().tolist() if not food_df.empty and "Floor" in food_df.columns else []
        floor_options = ["All Floors"] + sorted(all_floors)
        selected_floor = st.selectbox("Select Floor", floor_options, key="dash_floor")

    st.markdown("---")

    # Apply filters
    filtered_food = food_df.copy() if not food_df.empty else pd.DataFrame()
    if not filtered_food.empty and "Date" in filtered_food.columns:
        filtered_food = filtered_food[filtered_food["Date"] == display_date]
    if not filtered_food.empty and selected_floor != "All Floors" and "Floor" in filtered_food.columns:
        filtered_food = filtered_food[filtered_food["Floor"] == selected_floor]

    col1, col2, col3, col4 = st.columns(4)

    avail_pct = 0
    if not filtered_food.empty:
        total_checks, available_checks = 0, 0
        for _, row in filtered_food.iterrows():
            for item in FOOD_ITEMS:
                if item in row:
                    total_checks += 1
                    if str(row[item]).strip().lower() in ("yes", "true", "1", "available"):
                        available_checks += 1
        avail_pct = round((available_checks / total_checks) * 100, 1) if total_checks > 0 else 0

    projected, actual = 0, 0
    if not filtered_food.empty and "Food Projected for the Day" in filtered_food.columns:
        projected = int(filtered_food["Food Projected for the Day"].sum())
        if "Actual Consumption" in filtered_food.columns:
            actual = int(filtered_food["Actual Consumption"].sum())

    avg_r = 0
    if not feedback_df.empty and "Feedback Date" in feedback_df.columns and "Overall Rating" in feedback_df.columns:
        recent = feedback_df[feedback_df["Feedback Date"] >= today - timedelta(days=7)]
        if not recent.empty:
            avg_r = round(recent["Overall Rating"].mean(), 1)

    with col1:
        st.markdown(f'<div class="metric-card"><div class="metric-value">{avail_pct}%</div><div class="metric-label">Food Availability</div></div>', unsafe_allow_html=True)
    with col2:
        st.markdown(f'<div class="metric-card"><div class="metric-value">{projected}</div><div class="metric-label">Meals Projected</div></div>', unsafe_allow_html=True)
    with col3:
        st.markdown(f'<div class="metric-card"><div class="metric-value">{actual}</div><div class="metric-label">Actual Consumption</div></div>', unsafe_allow_html=True)
    with col4:
        st.markdown(f'<div class="metric-card"><div class="metric-value">{avg_r}/5</div><div class="metric-label">Avg Rating (7 days)</div></div>', unsafe_allow_html=True)

    if display_date != today:
        st.caption(f"Showing data for {display_date}. Select today's date if available.")

    st.divider()
    st.subheader("Food Availability")
    if not filtered_food.empty:
        floors_in_data = filtered_food["Floor"].unique().tolist() if "Floor" in filtered_food.columns else ["All"]
        for floor in floors_in_data:
            floor_data = filtered_food[filtered_food["Floor"] == floor] if "Floor" in filtered_food.columns else filtered_food
            if not floor_data.empty:
                st.markdown(f"**{floor}**")
                display_rows = []
                for _, row in floor_data.iterrows():
                    item_status = {"Check Time": row.get("Check Time", "")}
                    for item in FOOD_ITEMS:
                        val = str(row.get(item, "")).strip().lower()
                        item_status[item] = "✅" if val in ("yes", "true", "1", "available") else "❌" if val else "—"
                    display_rows.append(item_status)
                if display_rows:
                    st.dataframe(pd.DataFrame(display_rows).set_index("Check Time"), use_container_width=True)
    else:
        st.info("No availability data for selected filters.")

    # Show raw data summary for debugging
    if not food_df.empty:
        with st.expander("Raw data preview (for debugging)"):
            st.caption(f"Total rows: {len(food_df)} | Columns: {', '.join(food_df.columns.tolist())}")
            st.caption(f"Date values: {sorted(food_df['Date'].dropna().unique().tolist()) if 'Date' in food_df.columns else 'N/A'}")
            st.caption(f"Floor values: {food_df['Floor'].unique().tolist() if 'Floor' in food_df.columns else 'N/A'}")
            st.dataframe(food_df.tail(5), use_container_width=True)

    st.divider()
    st.subheader("Projection vs Consumption (Last 14 Days)")
    if not food_df.empty and "Date" in food_df.columns and "Food Projected for the Day" in food_df.columns and "Actual Consumption" in food_df.columns:
        cutoff = today - timedelta(days=14)
        trend = food_df[food_df["Date"] >= cutoff].copy()
        if not trend.empty:
            group_cols = ["Date", "Floor"] if "Floor" in trend.columns else ["Date"]
            trend_agg = trend.groupby(group_cols).agg(Projected=("Food Projected for the Day", "sum"), Actual=("Actual Consumption", "sum")).reset_index()
            if not trend_agg.empty:
                melted = trend_agg.melt(id_vars=group_cols, value_vars=["Projected", "Actual"], var_name="Type", value_name="Meal Count")
                if "Floor" in group_cols:
                    chart = alt.Chart(melted).mark_line(point=True).encode(
                        x=alt.X("Date:T"), y="Meal Count:Q", color="Floor:N", strokeDash="Type:N"
                    ).properties(height=350)
                else:
                    chart = alt.Chart(melted).mark_line(point=True).encode(
                        x=alt.X("Date:T"), y="Meal Count:Q", strokeDash="Type:N"
                    ).properties(height=350)
                st.altair_chart(chart, use_container_width=True)
    else:
        st.info("No projection data available yet.")

    # --- Recent Meal Feedback ---
    st.divider()
    st.subheader("Recent Meal Feedback")
    if not feedback_df.empty and "Feedback Date" in feedback_df.columns:
        fb_filter1, fb_filter2 = st.columns(2)
        with fb_filter1:
            fb_dates = sorted(feedback_df["Feedback Date"].dropna().unique().tolist(), reverse=True)
            fb_date_options = ["All Dates"] + [str(d) for d in fb_dates]
            fb_date_sel = st.selectbox("Filter by Date", fb_date_options, key="fb_date_filter")
        with fb_filter2:
            fb_floors = feedback_df["Floor"].dropna().unique().tolist() if "Floor" in feedback_df.columns else []
            fb_floor_options = ["All Floors"] + sorted(fb_floors)
            fb_floor_sel = st.selectbox("Filter by Floor", fb_floor_options, key="fb_floor_filter")

        filtered_fb = feedback_df.copy()
        if fb_date_sel != "All Dates":
            filtered_fb = filtered_fb[filtered_fb["Feedback Date"].astype(str) == fb_date_sel]
        if fb_floor_sel != "All Floors" and "Floor" in filtered_fb.columns:
            filtered_fb = filtered_fb[filtered_fb["Floor"] == fb_floor_sel]

        if not filtered_fb.empty:
            # Summary metrics
            fb_m1, fb_m2, fb_m3 = st.columns(3)
            avg_overall = filtered_fb["Overall Rating"].mean() if "Overall Rating" in filtered_fb.columns else 0
            total_responses = len(filtered_fb)
            low_rated = len(filtered_fb[filtered_fb["Overall Rating"] <= 2]) if "Overall Rating" in filtered_fb.columns else 0

            r_color = "#EF4444" if avg_overall < 2.5 else "#F59E0B" if avg_overall < 3.5 else "#10B981"
            with fb_m1:
                st.markdown(f'<div class="metric-card"><div class="metric-value" style="color:{r_color}">{avg_overall:.1f}/5</div><div class="metric-label">Avg Rating</div></div>', unsafe_allow_html=True)
            with fb_m2:
                st.markdown(f'<div class="metric-card"><div class="metric-value">{total_responses}</div><div class="metric-label">Total Responses</div></div>', unsafe_allow_html=True)
            with fb_m3:
                st.markdown(f'<div class="metric-card"><div class="metric-value" style="color:#EF4444">{low_rated}</div><div class="metric-label">Low Ratings (1-2)</div></div>', unsafe_allow_html=True)

            # Feedback cards
            RATING_COLORS = {5: "#166534", 4: "#4ADE80", 3: "#F97316", 2: "#FACC15", 1: "#EF4444"}
            RATING_LABELS = {5: "Excellent", 4: "Good", 3: "Okay", 2: "Fair", 1: "Very Bad"}

            for _, fb in filtered_fb.iterrows():
                rating_val = int(fb.get("Overall Rating", 3)) if pd.notna(fb.get("Overall Rating")) else 3
                rating_val = max(1, min(5, rating_val))
                color = RATING_COLORS.get(rating_val, "#F97316")
                label = RATING_LABELS.get(rating_val, "")
                floor_txt = fb.get("Floor", "")
                fb_date_txt = fb.get("Feedback Date", "")
                highlights = fb.get("Highlights", "")
                lowlights = fb.get("Low Lights", "")
                emp_name = fb.get("Employee Name", "Anonymous")

                comment_parts = []
                if pd.notna(highlights) and str(highlights).strip():
                    comment_parts.append(f"<b>Highlights:</b> {highlights}")
                if pd.notna(lowlights) and str(lowlights).strip():
                    comment_parts.append(f"<b>Issues:</b> {lowlights}")
                comment_html = "<br>".join(comment_parts) if comment_parts else "<i>No comments</i>"

                st.markdown(f"""
                <div style="border-left:4px solid {color}; background:#FAFAFA; border-radius:8px; padding:12px; margin:6px 0;">
                    <b>{emp_name}</b> &nbsp;
                    <span style="background:{color}; color:#fff; padding:2px 8px; border-radius:12px; font-size:0.8rem;">{rating_val}/5 - {label}</span>
                    <span style="color:#6B7280; font-size:0.8rem;"> &nbsp; {floor_txt} &nbsp; {fb_date_txt}</span><br>
                    <span style="color:#374151; font-size:0.9rem;">{comment_html}</span>
                </div>
                """, unsafe_allow_html=True)
        else:
            st.info("No feedback data for selected filters.")
    else:
        st.info("No meal feedback data available yet.")


# --- Page: Analytics ---
def page_analytics():
    st.markdown('<div class="main-header">Analytics & Insights</div>', unsafe_allow_html=True)
    st.markdown('<div class="sub-header">Food service performance across 8th & 9th floors</div>', unsafe_allow_html=True)

    food_df = load_food_tracker()
    feedback_df = load_meal_feedback()
    today = date.today()

    tab1, tab2, tab3 = st.tabs(["Rating Trends", "Availability Analysis", "Waste Analysis"])

    with tab1:
        if not feedback_df.empty and "Feedback Date" in feedback_df.columns and "Overall Rating" in feedback_df.columns:
            recent = feedback_df[feedback_df["Feedback Date"] >= today - timedelta(days=30)].copy()
            if not recent.empty:
                group_cols = ["Feedback Date", "Floor"] if "Floor" in recent.columns else ["Feedback Date"]
                daily = recent.groupby(group_cols).agg(Overall=("Overall Rating", "mean")).reset_index()
                target_line = alt.Chart(pd.DataFrame({"y": [3]})).mark_rule(strokeDash=[5, 5], color="orange").encode(y="y:Q")
                if "Floor" in group_cols:
                    line_chart = alt.Chart(daily).mark_line(point=True).encode(
                        x=alt.X("Feedback Date:T"), y=alt.Y("Overall:Q", title="Overall Rating"), color="Floor:N"
                    ).properties(height=350, title="Overall Rating Trend (Last 30 Days)")
                else:
                    line_chart = alt.Chart(daily).mark_line(point=True, color="#0891B2").encode(
                        x=alt.X("Feedback Date:T"), y=alt.Y("Overall:Q", title="Overall Rating")
                    ).properties(height=350, title="Overall Rating Trend (Last 30 Days)")
                st.altair_chart(line_chart + target_line, use_container_width=True)

                available_criteria = [c for c in FEEDBACK_CRITERIA if c in recent.columns]
                if available_criteria:
                    avg_vals = recent[available_criteria].mean()
                    criteria_df = pd.DataFrame({"Criteria": available_criteria, "Score": avg_vals.values})
                    criteria_chart = alt.Chart(criteria_df).mark_bar(color="#0891B2", cornerRadiusTopLeft=4, cornerRadiusTopRight=4).encode(
                        x=alt.X("Criteria:N", sort=available_criteria), y=alt.Y("Score:Q", scale=alt.Scale(domain=[0, 5]))
                    ).properties(height=350, title="Average Criteria Scores")
                    st.altair_chart(criteria_chart, use_container_width=True)
            else:
                st.info("No feedback data available yet.")
        else:
            st.info("No feedback data available yet.")

    with tab2:
        if not food_df.empty and "Date" in food_df.columns:
            recent_food = food_df[food_df["Date"] >= today - timedelta(days=14)]
            if not recent_food.empty:
                item_avail = {}
                for item in FOOD_ITEMS:
                    if item in recent_food.columns:
                        vals = recent_food[item].astype(str).str.strip().str.lower()
                        total = len(vals)
                        avail = vals.isin(["yes", "true", "1", "available"]).sum()
                        item_avail[item] = round((avail / total) * 100, 1) if total > 0 else 0
                if item_avail:
                    avail_summary = pd.DataFrame({"Item": list(item_avail.keys()), "Availability %": list(item_avail.values())}).sort_values("Availability %")
                    fig = alt.Chart(avail_summary).mark_bar(cornerRadiusTopRight=4, cornerRadiusBottomRight=4).encode(
                        x=alt.X("Availability %:Q", scale=alt.Scale(domain=[0, 100])),
                        y=alt.Y("Item:N", sort=alt.EncodingSortField(field="Availability %", order="ascending")),
                        color=alt.Color("Availability %:Q", scale=alt.Scale(domain=[0, 50, 100], range=["#EF4444", "#F59E0B", "#10B981"]), legend=None)
                    ).properties(height=400, title="Item Availability Rate (Last 14 Days)")
                    st.altair_chart(fig, use_container_width=True)
                else:
                    st.info("No food item columns found in data.")
        else:
            st.info("No availability data yet.")

    with tab3:
        if not food_df.empty and "Date" in food_df.columns and "Food Projected for the Day" in food_df.columns and "Actual Consumption" in food_df.columns:
            recent_proj = food_df[food_df["Date"] >= today - timedelta(days=14)].copy()
            if not recent_proj.empty:
                recent_proj["Waste"] = recent_proj["Food Projected for the Day"] - recent_proj["Actual Consumption"]
                recent_proj["Waste %"] = (recent_proj["Waste"] / recent_proj["Food Projected for the Day"].replace(0, pd.NA) * 100).fillna(0).round(1)
                if "Floor" in recent_proj.columns:
                    zero_line = alt.Chart(pd.DataFrame({"y": [0]})).mark_rule(color="black").encode(y="y:Q")
                    waste_chart = alt.Chart(recent_proj).mark_bar().encode(
                        x=alt.X("Date:T"), y=alt.Y("Waste:Q", title="Surplus Meals"), color="Floor:N", xOffset="Floor:N"
                    ).properties(height=350, title="Food Waste (Projected - Actual) Last 14 Days")
                    st.altair_chart(waste_chart + zero_line, use_container_width=True)
                avg_waste = recent_proj["Waste %"].mean()
                st.markdown(f'<div class="metric-card"><div class="metric-value">{avg_waste:.1f}%</div><div class="metric-label">Average Surplus Rate (14 days)</div></div>', unsafe_allow_html=True)
        else:
            st.info("No projection data available yet.")


# --- Page: AI Assistant ---
def page_ai_assistant():
    st.markdown('<div class="main-header">GWSCafeteria AI</div>', unsafe_allow_html=True)
    st.markdown('<div class="sub-header">Ask questions about food service quality and trends</div>', unsafe_allow_html=True)

    feedback_df = load_meal_feedback()
    food_df = load_food_tracker()
    today = date.today()

    context_parts = []
    if not feedback_df.empty and "Feedback Date" in feedback_df.columns:
        recent = feedback_df[feedback_df["Feedback Date"] >= today - timedelta(days=7)]
        if not recent.empty and "Overall Rating" in recent.columns:
            context_parts.append(f"Recent feedback (last 7 days, {len(recent)} entries): Avg rating: {recent['Overall Rating'].mean():.1f}/5.")
            if "Highlights" in recent.columns:
                hl = recent["Highlights"].dropna().head(5).tolist()
                if hl:
                    context_parts.append(f"Highlights: {'; '.join(str(h) for h in hl)}.")
            if "Low Lights" in recent.columns:
                ll = recent["Low Lights"].dropna().head(5).tolist()
                if ll:
                    context_parts.append(f"Issues: {'; '.join(str(l) for l in ll)}.")

    if not food_df.empty and "Date" in food_df.columns and "Food Projected for the Day" in food_df.columns:
        recent_proj = food_df[food_df["Date"] >= today - timedelta(days=7)]
        if not recent_proj.empty:
            avg_p = recent_proj["Food Projected for the Day"].mean()
            avg_a = recent_proj.get("Actual Consumption", pd.Series([0])).mean()
            context_parts.append(f"Meal projections (7-day avg): Projected={avg_p:.0f}, Actual={avg_a:.0f}.")

    context = " ".join(context_parts) if context_parts else "No historical data available yet."

    question = st.text_input("Ask GWSCafeteria AI a question:", placeholder="e.g., What are the most common food complaints this week?")

    if st.button("Ask AI", type="primary") and question:
        with st.spinner("Analyzing..."):
            prompt = (
                "You are GWSCafeteria AI, an intelligent assistant for food service quality management "
                "at the F5 Networks Hyderabad office (8th and 9th floors). "
                f"Current data context: {context} "
                "Answer clearly with actionable recommendations. Keep under 200 words. "
                f"Question: {question}"
            )
            response = ai_complete(prompt)
            st.markdown(f'<div class="ai-response"><b>🤖 GWSCafeteria AI says:</b><br><br>{response}</div>', unsafe_allow_html=True)

    st.divider()
    st.markdown("""
    **What can you ask?**
    - Food quality trends and common complaints
    - Waste reduction recommendations
    - Floor-level comparison of satisfaction
    - Vendor performance insights

    *Powered by Google Gemini*
    """)


# --- Page: Data Status ---
def page_data_status():
    st.markdown('<div class="main-header">Data Status</div>', unsafe_allow_html=True)
    st.markdown('<div class="sub-header">Live connection to Google Sheets (auto-synced from Microsoft Forms)</div>', unsafe_allow_html=True)

    food_url = st.secrets.get("google_sheets", {}).get("food_tracker_url", "")
    feedback_url = st.secrets.get("google_sheets", {}).get("meal_feedback_url", "")

    st.markdown(f"**Food Tracker Sheet:** {'✅ Connected' if food_url else '❌ Not configured'}")
    st.markdown(f"**Meal Feedback Sheet:** {'✅ Connected' if feedback_url else '❌ Not configured'}")
    st.caption("Data refreshes every 5 minutes automatically.")

    st.divider()

    if st.button("Refresh Food Tracker Now"):
        st.cache_data.clear()
        df = load_food_tracker()
        if not df.empty:
            st.success(f"Loaded {len(df)} rows | Columns: {', '.join(df.columns.tolist())}")
            st.dataframe(df.head(10), use_container_width=True)
        else:
            st.warning("No data loaded")

    if st.button("Refresh Meal Feedback Now"):
        st.cache_data.clear()
        df = load_meal_feedback()
        if not df.empty:
            st.success(f"Loaded {len(df)} rows | Columns: {', '.join(df.columns.tolist())}")
            st.dataframe(df.head(10), use_container_width=True)
        else:
            st.warning("No data loaded")


# --- Main ---
def main():
    st.set_page_config(page_title="GWSCafeteria", page_icon="🍽️", layout="wide", initial_sidebar_state="expanded")
    inject_css()

    st.sidebar.markdown("## 🍽️ GWSCafeteria")
    st.sidebar.markdown("F5 Hyderabad | Floors 8 & 9")
    st.sidebar.divider()

    page = st.sidebar.radio("Navigation", ["Dashboard", "Analytics", "AI Assistant", "Data Status"], label_visibility="collapsed")

    if page == "Dashboard":
        page_dashboard()
    elif page == "Analytics":
        page_analytics()
    elif page == "AI Assistant":
        page_ai_assistant()
    elif page == "Data Status":
        page_data_status()

    st.sidebar.divider()
    st.sidebar.markdown("**Submit Data:**")
    st.sidebar.markdown("[📋 Food Availability Tracker](https://forms.cloud.microsoft/Pages/DesignPageV2.aspx?origin=NeoPortalPage&subpage=design&collectionid=soiwjuemwwsot5ngpv98cq&id=L_093Ttq0UCb4L-DJ9gcUP0u1_vQu9ROniTDubCBSUJUNERQMVdTNlMyUklWQTFIVzA0SEpIQ1kyNC4u)")
    st.sidebar.markdown("[⭐ Meal Feedback Form](https://forms.cloud.microsoft/Pages/DesignPageV2.aspx?origin=NeoPortalPage&subpage=design&collectionid=soiwjuemwwsot5ngpv98cq&id=L_093Ttq0UCb4L-DJ9gcUP0u1_vQu9ROniTDubCBSUJUQjFXRUlaUkVDU1NMMzlVQVlQRVhRNUlIVS4u)")
    st.sidebar.divider()
    st.sidebar.caption("GWSCafeteria v0.3")


if __name__ == "__main__":
    main()
