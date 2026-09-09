# GWSCafeteria Forms Dashboard - Reads food availability and meal feedback from Microsoft Forms Excel exports
# Co-authored with CoCo
import streamlit as st
import pandas as pd
import altair as alt
from datetime import date, timedelta
from openai import OpenAI

# --- Config ---
# Replace these with your OneDrive/SharePoint direct download links for each form's Excel responses.
# To get the link: Open Form > Responses tab > "Open in Excel" > Share > Copy link > change "edit" to "download"
# Or: OneDrive > right-click the Excel file > Embed > use the download URL

FOOD_TRACKER_EXCEL_URL = st.secrets.get("forms", {}).get(
    "food_tracker_url", ""
)
MEAL_FEEDBACK_EXCEL_URL = st.secrets.get("forms", {}).get(
    "meal_feedback_url", ""
)

FOOD_ITEMS = [
    "Salad", "Rotis", "Dry Veg", "Wet Veg", "Rasam / Sambar",
    "Dal", "Steamed Rice", "Flavoured Rice", "Curd", "Dessert",
    "Refreshment/Juice"
]
CHECK_TIMES = ["12:30", "13:00", "13:30", "14:30"]
FEEDBACK_CRITERIA = ["Portioning", "Taste", "Texture", "Presentation", "Aroma"]
FLOORS = ["8th Floor", "9th Floor"]


# --- Data Loading ---
@st.cache_data(ttl=300)
def load_food_tracker():
    """Load food availability data from Microsoft Forms Excel."""
    if not FOOD_TRACKER_EXCEL_URL:
        return pd.DataFrame()
    try:
        df = pd.read_excel(FOOD_TRACKER_EXCEL_URL)
        df.columns = df.columns.str.strip()
        # Expected columns from the form:
        # Date, Check Time, Floor, Salad, Rotis, Dry Veg, Wet Veg, Rasam / Sambar,
        # Dal, Steamed Rice, Flavoured Rice, Curd, Dessert, Refreshment/Juice,
        # Remarks, No of Registrations Received, Food Projected for the Day, Actual Consumption, Projection Comments
        if "Date" in df.columns:
            df["Date"] = pd.to_datetime(df["Date"], errors="coerce").dt.date
        return df
    except Exception as e:
        st.error(f"Error loading Food Tracker data: {e}")
        return pd.DataFrame()


@st.cache_data(ttl=300)
def load_meal_feedback():
    """Load meal feedback data from Microsoft Forms Excel."""
    if not MEAL_FEEDBACK_EXCEL_URL:
        return pd.DataFrame()
    try:
        df = pd.read_excel(MEAL_FEEDBACK_EXCEL_URL)
        df.columns = df.columns.str.strip()
        # Expected columns from the form:
        # Feedback Date, Floor, Employee Name, Employee ID, Vendor Name,
        # Portioning, Taste, Texture, Presentation, Aroma, Overall Rating,
        # Highlights, Low Lights, Corrective Action
        if "Feedback Date" in df.columns:
            df["Feedback Date"] = pd.to_datetime(df["Feedback Date"], errors="coerce").dt.date
        return df
    except Exception as e:
        st.error(f"Error loading Meal Feedback data: {e}")
        return pd.DataFrame()


def ai_complete(prompt):
    """Call OpenAI for AI assistant."""
    try:
        api_key = st.secrets.get("openai", {}).get("api_key", "")
        if not api_key:
            return "OpenAI API key not configured. Add it to .streamlit/secrets.toml under [openai] api_key."
        client = OpenAI(api_key=api_key)
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=500,
            temperature=0.7,
        )
        return response.choices[0].message.content
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

    # Metrics
    col1, col2, col3, col4 = st.columns(4)

    # Food availability today
    if not food_df.empty and "Date" in food_df.columns:
        today_food = food_df[food_df["Date"] == today]
        total_checks = 0
        available_checks = 0
        for _, row in today_food.iterrows():
            for item in FOOD_ITEMS:
                if item in row:
                    total_checks += 1
                    val = str(row[item]).strip().lower()
                    if val in ("yes", "true", "1", "available"):
                        available_checks += 1
        avail_pct = round((available_checks / total_checks) * 100, 1) if total_checks > 0 else 0
    else:
        avail_pct = 0

    # Projection
    projected, actual = 0, 0
    if not food_df.empty and "Date" in food_df.columns and "Food Projected for the Day" in food_df.columns:
        today_proj = food_df[food_df["Date"] == today]
        projected = int(today_proj["Food Projected for the Day"].sum()) if not today_proj.empty else 0
        if "Actual Consumption" in food_df.columns:
            actual = int(today_proj["Actual Consumption"].sum()) if not today_proj.empty else 0

    # Avg rating
    avg_r = 0
    if not feedback_df.empty and "Feedback Date" in feedback_df.columns and "Overall Rating" in feedback_df.columns:
        week_ago = today - timedelta(days=7)
        recent = feedback_df[feedback_df["Feedback Date"] >= week_ago]
        if not recent.empty:
            avg_r = round(recent["Overall Rating"].mean(), 1)

    with col1:
        st.markdown(f'<div class="metric-card"><div class="metric-value">{avail_pct}%</div><div class="metric-label">Food Availability Today</div></div>', unsafe_allow_html=True)
    with col2:
        st.markdown(f'<div class="metric-card"><div class="metric-value">{projected}</div><div class="metric-label">Meals Projected Today</div></div>', unsafe_allow_html=True)
    with col3:
        st.markdown(f'<div class="metric-card"><div class="metric-value">{actual}</div><div class="metric-label">Actual Consumption</div></div>', unsafe_allow_html=True)
    with col4:
        st.markdown(f'<div class="metric-card"><div class="metric-value">{avg_r}/5</div><div class="metric-label">Avg Rating (7 days)</div></div>', unsafe_allow_html=True)

    st.divider()

    # Today's food availability grid
    st.subheader("Today's Food Availability")
    if not food_df.empty and "Date" in food_df.columns:
        today_food = food_df[food_df["Date"] == today]
        if not today_food.empty:
            for floor in FLOORS:
                floor_data = today_food[today_food["Floor"] == floor] if "Floor" in today_food.columns else pd.DataFrame()
                if not floor_data.empty:
                    st.markdown(f"**{floor}**")
                    display_rows = []
                    for _, row in floor_data.iterrows():
                        check_time = row.get("Check Time", "")
                        item_status = {}
                        for item in FOOD_ITEMS:
                            if item in row:
                                val = str(row[item]).strip().lower()
                                item_status[item] = "✅" if val in ("yes", "true", "1", "available") else "❌"
                            else:
                                item_status[item] = "—"
                        item_status["Check Time"] = check_time
                        display_rows.append(item_status)
                    if display_rows:
                        grid_df = pd.DataFrame(display_rows).set_index("Check Time")
                        st.dataframe(grid_df, use_container_width=True)
        else:
            st.info("No availability data recorded yet today.")
    else:
        st.info("No food tracker data available. Check your Excel link in settings.")

    st.divider()

    # Projection vs consumption trend
    st.subheader("Projection vs Consumption (Last 14 Days)")
    if not food_df.empty and "Date" in food_df.columns and "Food Projected for the Day" in food_df.columns:
        cutoff = today - timedelta(days=14)
        trend = food_df[food_df["Date"] >= cutoff].copy()
        if not trend.empty and "Actual Consumption" in trend.columns:
            trend_agg = trend.groupby(["Date", "Floor"]).agg(
                Projected=("Food Projected for the Day", "sum"),
                Actual=("Actual Consumption", "sum")
            ).reset_index()
            if not trend_agg.empty:
                melted = trend_agg.melt(id_vars=["Date", "Floor"], value_vars=["Projected", "Actual"], var_name="Type", value_name="Meal Count")
                chart = alt.Chart(melted).mark_line(point=True).encode(
                    x=alt.X("Date:T", title="Date"), y=alt.Y("Meal Count:Q"),
                    color="Floor:N", strokeDash="Type:N"
                ).properties(height=350)
                st.altair_chart(chart, use_container_width=True)
            else:
                st.info("No projection data available yet.")
        else:
            st.info("No projection data available yet.")
    else:
        st.info("No projection data available yet.")


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
            cutoff = today - timedelta(days=30)
            recent = feedback_df[feedback_df["Feedback Date"] >= cutoff].copy()
            if not recent.empty and "Floor" in recent.columns:
                daily = recent.groupby(["Feedback Date", "Floor"]).agg(
                    Overall=("Overall Rating", "mean"),
                    Portioning=("Portioning", "mean"),
                    Taste=("Taste", "mean"),
                    Texture=("Texture", "mean"),
                    Presentation=("Presentation", "mean"),
                    Aroma=("Aroma", "mean"),
                ).reset_index()

                target_line = alt.Chart(pd.DataFrame({"y": [3]})).mark_rule(strokeDash=[5, 5], color="orange").encode(y="y:Q")
                line_chart = alt.Chart(daily).mark_line(point=True).encode(
                    x=alt.X("Feedback Date:T", title="Date"), y=alt.Y("Overall:Q", title="Overall Rating"), color="Floor:N"
                ).properties(height=350, title="Overall Rating Trend (Last 30 Days)")
                st.altair_chart(line_chart + target_line, use_container_width=True)

                # Criteria bar chart
                avg_vals = recent[FEEDBACK_CRITERIA].mean()
                criteria_df = pd.DataFrame({"Criteria": FEEDBACK_CRITERIA, "Score": avg_vals.values})
                criteria_chart = alt.Chart(criteria_df).mark_bar(color="#0891B2", cornerRadiusTopLeft=4, cornerRadiusTopRight=4).encode(
                    x=alt.X("Criteria:N", sort=FEEDBACK_CRITERIA), y=alt.Y("Score:Q", scale=alt.Scale(domain=[0, 5]))
                ).properties(height=350, title="Average Criteria Scores")
                st.altair_chart(criteria_chart, use_container_width=True)
            else:
                st.info("No feedback data available yet.")
        else:
            st.info("No feedback data available yet.")

    with tab2:
        if not food_df.empty and "Date" in food_df.columns:
            cutoff = today - timedelta(days=14)
            recent_food = food_df[food_df["Date"] >= cutoff]
            if not recent_food.empty:
                item_avail = {}
                for item in FOOD_ITEMS:
                    if item in recent_food.columns:
                        vals = recent_food[item].astype(str).str.strip().str.lower()
                        total = len(vals)
                        avail = vals.isin(["yes", "true", "1", "available"]).sum()
                        item_avail[item] = round((avail / total) * 100, 1) if total > 0 else 0
                if item_avail:
                    avail_summary = pd.DataFrame({"Item": list(item_avail.keys()), "Availability %": list(item_avail.values())})
                    avail_summary = avail_summary.sort_values("Availability %")
                    fig = alt.Chart(avail_summary).mark_bar(cornerRadiusTopRight=4, cornerRadiusBottomRight=4).encode(
                        x=alt.X("Availability %:Q", scale=alt.Scale(domain=[0, 100])),
                        y=alt.Y("Item:N", sort=alt.EncodingSortField(field="Availability %", order="ascending")),
                        color=alt.Color("Availability %:Q", scale=alt.Scale(domain=[0, 50, 100], range=["#EF4444", "#F59E0B", "#10B981"]), legend=None)
                    ).properties(height=400, title="Item Availability Rate (Last 14 Days)")
                    st.altair_chart(fig, use_container_width=True)
                else:
                    st.info("No item availability columns found.")
            else:
                st.info("No availability data in the last 14 days.")
        else:
            st.info("No availability data yet.")

    with tab3:
        if not food_df.empty and "Date" in food_df.columns and "Food Projected for the Day" in food_df.columns and "Actual Consumption" in food_df.columns:
            cutoff = today - timedelta(days=14)
            recent_proj = food_df[food_df["Date"] >= cutoff].copy()
            if not recent_proj.empty:
                recent_proj["Waste"] = recent_proj["Food Projected for the Day"] - recent_proj["Actual Consumption"]
                recent_proj["Waste %"] = (recent_proj["Waste"] / recent_proj["Food Projected for the Day"].replace(0, pd.NA) * 100).round(1)

                if "Floor" in recent_proj.columns:
                    zero_line = alt.Chart(pd.DataFrame({"y": [0]})).mark_rule(color="black").encode(y="y:Q")
                    waste_chart = alt.Chart(recent_proj).mark_bar().encode(
                        x=alt.X("Date:T", title="Date"), y=alt.Y("Waste:Q", title="Surplus Meals"),
                        color="Floor:N", xOffset="Floor:N"
                    ).properties(height=350, title="Food Waste (Projected - Actual) Last 14 Days")
                    st.altair_chart(waste_chart + zero_line, use_container_width=True)

                avg_waste = recent_proj["Waste %"].mean()
                st.markdown(f'<div class="metric-card"><div class="metric-value">{avg_waste:.1f}%</div><div class="metric-label">Average Surplus Rate (14 days)</div></div>', unsafe_allow_html=True)
            else:
                st.info("No projection data in the last 14 days.")
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
        week_ago = today - timedelta(days=7)
        recent = feedback_df[feedback_df["Feedback Date"] >= week_ago]
        if not recent.empty:
            context_parts.append(
                f"Recent feedback (last 7 days, {len(recent)} entries): "
                f"Avg rating: {recent['Overall Rating'].mean():.1f}/5. "
            )
            if "Highlights" in recent.columns:
                highlights = recent["Highlights"].dropna().head(5).tolist()
                if highlights:
                    context_parts.append(f"Highlights: {'; '.join(highlights)}.")
            if "Low Lights" in recent.columns:
                lowlights = recent["Low Lights"].dropna().head(5).tolist()
                if lowlights:
                    context_parts.append(f"Issues: {'; '.join(lowlights)}.")

    if not food_df.empty and "Food Projected for the Day" in food_df.columns and "Feedback Date" not in food_df.columns:
        week_ago = today - timedelta(days=7)
        if "Date" in food_df.columns:
            recent_proj = food_df[food_df["Date"] >= week_ago]
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
                "The system tracks: food availability at 4 check times daily (12:30, 13:00, 13:30, 14:30), "
                "meal projections vs actual consumption, and employee feedback ratings on "
                "Portioning, Taste, Texture, Presentation, and Aroma (1-5 scale). "
                f"Current data context: {context} "
                "Answer the user's question clearly and provide actionable recommendations. "
                "Keep your response under 200 words. "
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
    - Peak time availability issues

    *Powered by OpenAI GPT-4o-mini*
    """)


# --- Page: Settings ---
def page_settings():
    st.markdown('<div class="main-header">Settings & Data Sources</div>', unsafe_allow_html=True)
    st.markdown('<div class="sub-header">Configure Microsoft Forms data connections</div>', unsafe_allow_html=True)

    st.markdown("**Current data source URLs:**")
    st.code(f"Food Tracker: {FOOD_TRACKER_EXCEL_URL or '(not configured)'}", language=None)
    st.code(f"Meal Feedback: {MEAL_FEEDBACK_EXCEL_URL or '(not configured)'}", language=None)

    st.divider()
    st.markdown("""
    **How to get the Excel download link from Microsoft Forms:**

    1. Open your Microsoft Form
    2. Go to the **Responses** tab
    3. Click **"Open in Excel"** — this creates/opens an Excel file on OneDrive
    4. In OneDrive, right-click the Excel file → **Share** → **Copy link**
    5. Change the URL to a direct download link:
       - Replace `edit` with `download` at the end
       - Or use: `https://your-org.sharepoint.com/.../:x:/r/...?download=1`
    6. Add the URL to `.streamlit/secrets.toml`:
       ```toml
       [forms]
       food_tracker_url = "https://..."
       meal_feedback_url = "https://..."
       ```

    **Data refreshes every 5 minutes** (cached with `@st.cache_data(ttl=300)`).
    """)

    st.divider()
    st.markdown("**Test data loading:**")
    if st.button("Reload Food Tracker Data"):
        st.cache_data.clear()
        df = load_food_tracker()
        st.success(f"Loaded {len(df)} rows") if not df.empty else st.warning("No data loaded")
        if not df.empty:
            st.dataframe(df.head(10), use_container_width=True)

    if st.button("Reload Meal Feedback Data"):
        st.cache_data.clear()
        df = load_meal_feedback()
        st.success(f"Loaded {len(df)} rows") if not df.empty else st.warning("No data loaded")
        if not df.empty:
            st.dataframe(df.head(10), use_container_width=True)


# --- Main ---
def main():
    st.set_page_config(page_title="GWSCafeteria", page_icon="🍽️", layout="wide", initial_sidebar_state="expanded")
    inject_css()

    st.sidebar.markdown("## 🍽️ GWSCafeteria")
    st.sidebar.markdown("F5 Hyderabad | Floors 8 & 9")
    st.sidebar.divider()

    page = st.sidebar.radio(
        "Navigation",
        ["Dashboard", "Analytics", "AI Assistant", "Settings"],
        label_visibility="collapsed"
    )

    if page == "Dashboard":
        page_dashboard()
    elif page == "Analytics":
        page_analytics()
    elif page == "AI Assistant":
        page_ai_assistant()
    elif page == "Settings":
        page_settings()

    st.sidebar.divider()

    # Direct links to Microsoft Forms for data entry
    st.sidebar.markdown("**Submit Data:**")
    st.sidebar.markdown("[📋 Food Availability Tracker](https://forms.cloud.microsoft/Pages/DesignPageV2.aspx?origin=NeoPortalPage&subpage=design&collectionid=soiwjuemwwsot5ngpv98cq&id=L_093Ttq0UCb4L-DJ9gcUP0u1_vQu9ROniTDubCBSUJUNERQMVdTNlMyUklWQTFIVzA0SEpIQ1kyNC4u)")
    st.sidebar.markdown("[⭐ Meal Feedback Form](https://forms.cloud.microsoft/Pages/DesignPageV2.aspx?origin=NeoPortalPage&subpage=design&collectionid=soiwjuemwwsot5ngpv98cq&id=L_093Ttq0UCb4L-DJ9gcUP0u1_vQu9ROniTDubCBSUJUQjFXRUlaUkVDU1NMMzlVQVlQRVhRNUlIVS4u)")

    st.sidebar.divider()
    st.sidebar.caption("GWSCafeteria v0.1 (Forms Edition)")


if __name__ == "__main__":
    main()
