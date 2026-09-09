# GWSCafeteria External - Standalone Streamlit app for external users without Snowflake access
# Co-authored with CoCo
import streamlit as st
import pandas as pd
import altair as alt
import snowflake.connector
from datetime import date
from openai import OpenAI

# --- Config ---
FOOD_ITEMS = [
    "Salad", "Rotis", "Dry Veg", "Wet Veg", "Rasam / Sambar",
    "Dal", "Steamed Rice", "Flavoured Rice", "Curd", "Dessert",
    "Refreshment/Juice"
]
CHECK_TIMES = ["12:30", "13:00", "13:30", "14:30"]
FEEDBACK_CRITERIA = ["Portioning", "Taste", "Texture", "Presentation", "Aroma"]
FLOORS = ["8th Floor", "9th Floor"]
DB_SCHEMA = "DEV_ENT_RAW.COMMON"


# --- Snowflake Connection ---
@st.cache_resource
def get_snowflake_connection():
    sf = st.secrets["snowflake"]
    return snowflake.connector.connect(
        account=sf["account"],
        user=sf["user"],
        private_key_file=sf["private_key_path"],
        role=sf["role"],
        warehouse=sf["warehouse"],
        database=sf["database"],
        schema=sf["schema"],
    )


def run_query(sql, params=None):
    conn = get_snowflake_connection()
    cur = conn.cursor()
    try:
        if params:
            cur.execute(sql, params)
        else:
            cur.execute(sql)
        cols = [desc[0] for desc in cur.description] if cur.description else []
        rows = cur.fetchall()
        return pd.DataFrame(rows, columns=cols) if cols else pd.DataFrame()
    finally:
        cur.close()


def run_insert(sql, params=None):
    conn = get_snowflake_connection()
    cur = conn.cursor()
    try:
        if params:
            cur.execute(sql, params)
        else:
            cur.execute(sql)
    finally:
        cur.close()


def ai_complete(prompt):
    try:
        client = OpenAI(api_key=st.secrets["openai"]["api_key"])
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

    col1, col2, col3, col4 = st.columns(4)

    try:
        df = run_query(f"""
            SELECT COUNT(*) as TOTAL,
                   SUM(CASE WHEN is_available THEN 1 ELSE 0 END) as AVAILABLE
            FROM {DB_SCHEMA}.FACILITY_FOOD_AVAILABILITY WHERE check_date = CURRENT_DATE()
        """)
        total = int(df["TOTAL"].iloc[0] or 0)
        available = int(df["AVAILABLE"].iloc[0] or 0)
        avail_pct = round((available / total) * 100, 1) if total > 0 else 0
    except:
        avail_pct = 0

    try:
        df = run_query(f"""
            SELECT SUM(projected_count) as PROJECTED, SUM(actual_consumption) as ACTUAL
            FROM {DB_SCHEMA}.FACILITY_FOOD_PROJECTION WHERE projection_date = CURRENT_DATE()
        """)
        projected = int(df["PROJECTED"].iloc[0] or 0)
        actual = int(df["ACTUAL"].iloc[0] or 0)
    except:
        projected, actual = 0, 0

    try:
        df = run_query(f"""
            SELECT AVG(overall_rating) as AVG_R, COUNT(*) as CNT
            FROM {DB_SCHEMA}.FACILITY_MEAL_FEEDBACK
            WHERE feedback_date >= DATEADD(day, -7, CURRENT_DATE())
        """)
        avg_r = round(float(df["AVG_R"].iloc[0] or 0), 1)
    except:
        avg_r = 0

    with col1:
        st.markdown(f'<div class="metric-card"><div class="metric-value">{avail_pct}%</div><div class="metric-label">Food Availability Today</div></div>', unsafe_allow_html=True)
    with col2:
        st.markdown(f'<div class="metric-card"><div class="metric-value">{projected}</div><div class="metric-label">Meals Projected Today</div></div>', unsafe_allow_html=True)
    with col3:
        st.markdown(f'<div class="metric-card"><div class="metric-value">{actual}</div><div class="metric-label">Actual Consumption</div></div>', unsafe_allow_html=True)
    with col4:
        st.markdown(f'<div class="metric-card"><div class="metric-value">{avg_r}/5</div><div class="metric-label">Avg Rating (7 days)</div></div>', unsafe_allow_html=True)

    st.divider()
    st.subheader("Today's Food Availability")
    try:
        today_df = run_query(f"""
            SELECT CHECK_TIME, FLOOR, ITEM_NAME, IS_AVAILABLE
            FROM {DB_SCHEMA}.FACILITY_FOOD_AVAILABILITY
            WHERE check_date = CURRENT_DATE() ORDER BY CHECK_TIME, FLOOR, ITEM_NAME
        """)
        if not today_df.empty:
            for floor in FLOORS:
                floor_data = today_df[today_df["FLOOR"] == floor]
                if not floor_data.empty:
                    st.markdown(f"**{floor}**")
                    pivot = floor_data.pivot_table(index="ITEM_NAME", columns="CHECK_TIME", values="IS_AVAILABLE", aggfunc="first").fillna("")
                    pivot = pivot.replace({True: "✅", False: "❌", "": "—"})
                    st.dataframe(pivot, use_container_width=True)
        else:
            st.info("No availability data recorded yet today.")
    except:
        st.info("No availability data yet.")

    st.divider()
    st.subheader("Projection vs Consumption (Last 14 Days)")
    try:
        trend_df = run_query(f"""
            SELECT PROJECTION_DATE, FLOOR, SUM(PROJECTED_COUNT) as PROJECTED, SUM(ACTUAL_CONSUMPTION) as ACTUAL
            FROM {DB_SCHEMA}.FACILITY_FOOD_PROJECTION
            WHERE projection_date >= DATEADD(day, -14, CURRENT_DATE())
            GROUP BY PROJECTION_DATE, FLOOR ORDER BY PROJECTION_DATE
        """)
        if not trend_df.empty:
            melted = trend_df.melt(id_vars=["PROJECTION_DATE", "FLOOR"], value_vars=["PROJECTED", "ACTUAL"], var_name="Type", value_name="Meal Count")
            chart = alt.Chart(melted).mark_line(point=True).encode(
                x=alt.X("PROJECTION_DATE:T", title="Date"), y=alt.Y("Meal Count:Q"),
                color="FLOOR:N", strokeDash="Type:N"
            ).properties(height=350)
            st.altair_chart(chart, use_container_width=True)
        else:
            st.info("No projection data available yet.")
    except:
        st.info("No projection data available yet.")


# --- Page: Food Availability Tracker ---
def page_food_tracker():
    st.markdown('<div class="main-header">Food Availability Tracker</div>', unsafe_allow_html=True)
    st.markdown('<div class="sub-header">Record food item availability at each check time</div>', unsafe_allow_html=True)

    col1, col2, col3 = st.columns(3)
    with col1:
        check_date = st.date_input("Date", value=date.today(), max_value=date.today())
    with col2:
        check_time = st.selectbox("Check Time", CHECK_TIMES)
    with col3:
        floor = st.selectbox("Floor", FLOORS)

    st.markdown("---")
    st.markdown("**Mark item availability:**")

    availability = {}
    cols = st.columns(3)
    for i, item in enumerate(FOOD_ITEMS):
        with cols[i % 3]:
            availability[item] = st.checkbox(f"{item}", value=True, key=f"avail_{item}")

    available_count = sum(1 for v in availability.values() if v)
    unavailable_count = len(availability) - available_count
    summ_col1, summ_col2 = st.columns(2)
    with summ_col1:
        st.markdown(f'<div style="background:#ECFDF5; border-left:4px solid #10B981; border-radius:8px; padding:12px; text-align:center;"><span style="font-size:1.5rem; font-weight:700; color:#10B981;">{available_count}</span><br><span style="font-size:0.8rem; color:#6B7280;">Items Available</span></div>', unsafe_allow_html=True)
    with summ_col2:
        bg = "#FEF2F2" if unavailable_count > 0 else "#F0F9FF"
        border = "#EF4444" if unavailable_count > 0 else "#94A3B8"
        color = "#EF4444" if unavailable_count > 0 else "#94A3B8"
        st.markdown(f'<div style="background:{bg}; border-left:4px solid {border}; border-radius:8px; padding:12px; text-align:center;"><span style="font-size:1.5rem; font-weight:700; color:{color};">{unavailable_count}</span><br><span style="font-size:0.8rem; color:#6B7280;">Items Unavailable</span></div>', unsafe_allow_html=True)

    unavailable_items = [item for item, avail in availability.items() if not avail]
    if unavailable_items:
        st.markdown('<div style="background:#FEF2F2; border:1px solid #FECACA; border-radius:8px; padding:10px; margin-top:8px;"><span style="color:#EF4444; font-weight:600;">⚠️ Unavailable items: </span>' + ', '.join(f'<span style="color:#DC2626; font-weight:500;">{item}</span>' for item in unavailable_items) + '</div>', unsafe_allow_html=True)

    remarks = st.text_area("Remarks / Comments", placeholder="e.g., Papad over at 13:50 on 9th floor")

    if st.button("Submit Availability Check", type="primary", use_container_width=True):
        try:
            for item, is_avail in availability.items():
                run_insert(
                    f"INSERT INTO {DB_SCHEMA}.FACILITY_FOOD_AVAILABILITY "
                    f"(check_date, check_time, floor, item_name, is_available, remarks, recorded_by) "
                    f"VALUES (%s, %s, %s, %s, %s, %s, %s)",
                    (str(check_date), check_time, floor, item, is_avail, remarks, "external_user")
                )
            st.success(f"Availability recorded for {floor} at {check_time} on {check_date}")
        except Exception as e:
            st.error(f"Error saving: {str(e)}")

    st.divider()
    st.subheader("Meal Projection & Consumption")
    pcol1, pcol2, pcol3 = st.columns(3)
    with pcol1:
        registration_count = st.number_input("No of Registrations Received", min_value=0, value=0, step=10)
    with pcol2:
        projected_count = st.number_input("Food Projected for the Day", min_value=0, value=250, step=10)
    with pcol3:
        actual_count = st.number_input("Actual Consumption", min_value=0, value=0, step=10)

    if actual_count > 0 and projected_count > 0:
        diff = projected_count - actual_count
        diff_pct = round(abs(diff) / projected_count * 100, 1)
        if diff > 0:
            st.markdown(f'<div style="background:#FFFBEB; border-left:4px solid #F59E0B; border-radius:8px; padding:10px; margin:8px 0;"><span style="color:#D97706; font-weight:600;">📊 Surplus: {diff} meals ({diff_pct}% over)</span> — consider reducing projection</div>', unsafe_allow_html=True)
        elif diff < 0:
            st.markdown(f'<div style="background:#FEF2F2; border-left:4px solid #EF4444; border-radius:8px; padding:10px; margin:8px 0;"><span style="color:#DC2626; font-weight:600;">📊 Shortage: {abs(diff)} meals ({diff_pct}% under)</span> — demand exceeded projection</div>', unsafe_allow_html=True)
        else:
            st.markdown(f'<div style="background:#ECFDF5; border-left:4px solid #10B981; border-radius:8px; padding:10px; margin:8px 0;"><span style="color:#059669; font-weight:600;">✅ Perfect match!</span> — projection matched consumption exactly</div>', unsafe_allow_html=True)

    proj_comments = st.text_input("Projection Comments", placeholder="e.g., Special lunch day")

    if st.button("Save Projection Data", use_container_width=True):
        try:
            run_insert(
                f"MERGE INTO {DB_SCHEMA}.FACILITY_FOOD_PROJECTION tgt "
                f"USING (SELECT %s::DATE as d, %s as f) src "
                f"ON tgt.projection_date = src.d AND tgt.floor = src.f "
                f"WHEN MATCHED THEN UPDATE SET "
                f"registration_count = %s, projected_count = %s, actual_consumption = %s, "
                f"comments = %s, recorded_by = %s, recorded_at = CURRENT_TIMESTAMP() "
                f"WHEN NOT MATCHED THEN INSERT "
                f"(projection_date, floor, registration_count, projected_count, actual_consumption, comments, recorded_by) "
                f"VALUES (src.d, src.f, %s, %s, %s, %s, %s)",
                (str(check_date), floor, registration_count, projected_count, actual_count, proj_comments, "external_user",
                 registration_count, projected_count, actual_count, proj_comments, "external_user")
            )
            st.success(f"Projection data saved for {floor} on {check_date}")
        except Exception as e:
            st.error(f"Error saving projection: {str(e)}")


# --- Page: Meal Feedback ---
def page_feedback():
    st.markdown('<div class="main-header">Meal Feedback Form</div>', unsafe_allow_html=True)
    st.markdown('<div class="sub-header">Rate today\'s meal quality across key criteria</div>', unsafe_allow_html=True)

    col1, col2, col3 = st.columns(3)
    with col1:
        feedback_date = st.date_input("Feedback Date", value=date.today(), max_value=date.today(), key="fb_date")
        vendor_name = st.text_input("Vendor Name")
    with col2:
        employee_name = st.text_input("Employee Name")
        floor = st.selectbox("Floor", FLOORS, key="fb_floor")
    with col3:
        employee_id = st.text_input("Employee ID")

    st.markdown("---")
    st.markdown("**Rate each criterion (1-5):**")
    st.markdown("""
    <div style="display:flex; gap:12px; margin-bottom:1rem; flex-wrap:wrap;">
        <span style="background:#166534; color:#fff; padding:4px 10px; border-radius:6px; font-size:0.8rem;">5 - Excellent</span>
        <span style="background:#4ADE80; color:#1a1a1a; padding:4px 10px; border-radius:6px; font-size:0.8rem;">4 - Good</span>
        <span style="background:#F97316; color:#fff; padding:4px 10px; border-radius:6px; font-size:0.8rem;">3 - Okay</span>
        <span style="background:#FACC15; color:#1a1a1a; padding:4px 10px; border-radius:6px; font-size:0.8rem;">2 - Fair</span>
        <span style="background:#EF4444; color:#fff; padding:4px 10px; border-radius:6px; font-size:0.8rem;">1 - Very Bad</span>
    </div>
    """, unsafe_allow_html=True)

    RATING_COLORS = {5: "#166534", 4: "#4ADE80", 3: "#F97316", 2: "#FACC15", 1: "#EF4444"}
    RATING_TEXT_COLORS = {5: "#fff", 4: "#1a1a1a", 3: "#fff", 2: "#1a1a1a", 1: "#fff"}
    RATING_LABELS = {5: "Excellent", 4: "Good", 3: "Okay", 2: "Fair", 1: "Very Bad"}

    ratings = {}
    rating_cols = st.columns(5)
    for i, criterion in enumerate(FEEDBACK_CRITERIA):
        with rating_cols[i]:
            ratings[criterion] = st.select_slider(criterion, options=[1, 2, 3, 4, 5], value=3, key=f"rate_{criterion}")
            val = ratings[criterion]
            st.markdown(f'<div style="background:{RATING_COLORS[val]}; color:{RATING_TEXT_COLORS[val]}; text-align:center; padding:6px; border-radius:8px; font-weight:600; font-size:0.85rem;">{val} - {RATING_LABELS[val]}</div>', unsafe_allow_html=True)

    overall = st.select_slider("Overall Rating", options=[1, 2, 3, 4, 5], value=3, key="overall")
    st.markdown(f'<div style="background:{RATING_COLORS[overall]}; color:{RATING_TEXT_COLORS[overall]}; text-align:center; padding:8px; border-radius:8px; font-weight:700; font-size:1rem; margin-top:4px;">Overall: {overall} - {RATING_LABELS[overall]}</div>', unsafe_allow_html=True)

    st.markdown("---")
    hcol1, hcol2 = st.columns(2)
    with hcol1:
        highlights = st.text_area("Highlights (what was good)", placeholder="e.g., Fresh salad, good variety")
    with hcol2:
        lowlights = st.text_area("Low Lights (what needs improvement)", placeholder="e.g., Rice too dry, dessert finished early")

    corrective = st.text_area("Corrective Action Required", placeholder="e.g., Increase rice quantity by 20%")

    if st.button("Submit Feedback", type="primary", use_container_width=True):
        if not employee_name:
            st.warning("Please enter your name.")
            return
        if not employee_name.replace(" ", "").isalpha():
            st.warning("Employee Name must contain only letters and spaces — no numbers or special characters.")
            return
        try:
            run_insert(
                f"INSERT INTO {DB_SCHEMA}.FACILITY_MEAL_FEEDBACK "
                f"(feedback_date, floor, employee_name, employee_id, vendor_name, "
                f"portioning_rating, taste_rating, texture_rating, presentation_rating, aroma_rating, "
                f"overall_rating, highlights, lowlights, corrective_action) "
                f"VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                (str(feedback_date), floor, employee_name, employee_id, vendor_name,
                 ratings['Portioning'], ratings['Taste'], ratings['Texture'],
                 ratings['Presentation'], ratings['Aroma'], overall,
                 highlights, lowlights, corrective)
            )
            st.success("Feedback submitted successfully! Thank you.")
            st.balloons()
        except Exception as e:
            st.error(f"Error submitting feedback: {str(e)}")


# --- Page: Analytics ---
def page_analytics():
    st.markdown('<div class="main-header">Analytics & Insights</div>', unsafe_allow_html=True)
    st.markdown('<div class="sub-header">Food service performance across 8th & 9th floors</div>', unsafe_allow_html=True)

    tab1, tab2, tab3 = st.tabs(["Rating Trends", "Availability Analysis", "Waste Analysis"])

    with tab1:
        try:
            ratings_df = run_query(f"""
                SELECT FEEDBACK_DATE, FLOOR,
                       AVG(PORTIONING_RATING) as PORTIONING, AVG(TASTE_RATING) as TASTE,
                       AVG(TEXTURE_RATING) as TEXTURE, AVG(PRESENTATION_RATING) as PRESENTATION,
                       AVG(AROMA_RATING) as AROMA, AVG(OVERALL_RATING) as OVERALL, COUNT(*) as RESPONSES
                FROM {DB_SCHEMA}.FACILITY_MEAL_FEEDBACK
                WHERE feedback_date >= DATEADD(day, -30, CURRENT_DATE())
                GROUP BY FEEDBACK_DATE, FLOOR ORDER BY FEEDBACK_DATE
            """)
            if not ratings_df.empty:
                target_line = alt.Chart(pd.DataFrame({"y": [3]})).mark_rule(strokeDash=[5, 5], color="orange").encode(y="y:Q")
                line_chart = alt.Chart(ratings_df).mark_line(point=True).encode(
                    x=alt.X("FEEDBACK_DATE:T", title="Date"), y=alt.Y("OVERALL:Q", title="Overall Rating"), color="FLOOR:N"
                ).properties(height=350, title="Overall Rating Trend (Last 30 Days)")
                st.altair_chart(line_chart + target_line, use_container_width=True)

                avg_criteria = ratings_df[["PORTIONING", "TASTE", "TEXTURE", "PRESENTATION", "AROMA"]].mean()
                criteria_df = pd.DataFrame({"Criteria": FEEDBACK_CRITERIA, "Score": avg_criteria.values})
                criteria_chart = alt.Chart(criteria_df).mark_bar(color="#0891B2", cornerRadiusTopLeft=4, cornerRadiusTopRight=4).encode(
                    x=alt.X("Criteria:N", sort=FEEDBACK_CRITERIA), y=alt.Y("Score:Q", scale=alt.Scale(domain=[0, 5]), title="Avg Score")
                ).properties(height=350, title="Average Criteria Scores")
                st.altair_chart(criteria_chart, use_container_width=True)
            else:
                st.info("No feedback data available yet.")
        except:
            st.info("No feedback data available yet.")

    with tab2:
        try:
            avail_df = run_query(f"""
                SELECT CHECK_DATE, FLOOR, ITEM_NAME,
                       SUM(CASE WHEN IS_AVAILABLE THEN 1 ELSE 0 END) as AVAILABLE_CHECKS, COUNT(*) as TOTAL_CHECKS
                FROM {DB_SCHEMA}.FACILITY_FOOD_AVAILABILITY
                WHERE check_date >= DATEADD(day, -14, CURRENT_DATE())
                GROUP BY CHECK_DATE, FLOOR, ITEM_NAME ORDER BY CHECK_DATE
            """)
            if not avail_df.empty:
                avail_df["AVAIL_PCT"] = (avail_df["AVAILABLE_CHECKS"] / avail_df["TOTAL_CHECKS"] * 100).round(1)
                item_summary = avail_df.groupby("ITEM_NAME")["AVAIL_PCT"].mean().reset_index().sort_values("AVAIL_PCT")
                fig = alt.Chart(item_summary).mark_bar(cornerRadiusTopRight=4, cornerRadiusBottomRight=4).encode(
                    x=alt.X("AVAIL_PCT:Q", title="Availability %", scale=alt.Scale(domain=[0, 100])),
                    y=alt.Y("ITEM_NAME:N", sort=alt.EncodingSortField(field="AVAIL_PCT", order="ascending")),
                    color=alt.Color("AVAIL_PCT:Q", scale=alt.Scale(domain=[0, 50, 100], range=["#EF4444", "#F59E0B", "#10B981"]), legend=None)
                ).properties(height=400, title="Item Availability Rate (Last 14 Days)")
                st.altair_chart(fig, use_container_width=True)
            else:
                st.info("No availability data yet.")
        except:
            st.info("No availability data yet.")

    with tab3:
        try:
            waste_df = run_query(f"""
                SELECT PROJECTION_DATE, FLOOR, PROJECTED_COUNT, ACTUAL_CONSUMPTION,
                       PROJECTED_COUNT - ACTUAL_CONSUMPTION as WASTE,
                       ROUND((PROJECTED_COUNT - ACTUAL_CONSUMPTION)::FLOAT / NULLIF(PROJECTED_COUNT, 0) * 100, 1) as WASTE_PCT
                FROM {DB_SCHEMA}.FACILITY_FOOD_PROJECTION
                WHERE projection_date >= DATEADD(day, -14, CURRENT_DATE()) ORDER BY PROJECTION_DATE
            """)
            if not waste_df.empty:
                zero_line = alt.Chart(pd.DataFrame({"y": [0]})).mark_rule(color="black").encode(y="y:Q")
                waste_chart = alt.Chart(waste_df).mark_bar().encode(
                    x=alt.X("PROJECTION_DATE:T", title="Date"), y=alt.Y("WASTE:Q", title="Surplus Meals"),
                    color="FLOOR:N", xOffset="FLOOR:N"
                ).properties(height=350, title="Food Waste (Projected - Actual) Last 14 Days")
                st.altair_chart(waste_chart + zero_line, use_container_width=True)

                avg_waste = waste_df["WASTE_PCT"].mean()
                st.markdown(f'<div class="metric-card"><div class="metric-value">{avg_waste:.1f}%</div><div class="metric-label">Average Surplus Rate (14 days)</div></div>', unsafe_allow_html=True)
            else:
                st.info("No projection data available yet.")
        except:
            st.info("No projection data available yet.")


# --- Page: AI Assistant ---
def page_ai_assistant():
    st.markdown('<div class="main-header">GWSCafeteria AI</div>', unsafe_allow_html=True)
    st.markdown('<div class="sub-header">Ask questions about food service quality and trends</div>', unsafe_allow_html=True)

    context_parts = []
    try:
        recent_feedback = run_query(f"""
            SELECT FEEDBACK_DATE, FLOOR, OVERALL_RATING, HIGHLIGHTS, LOWLIGHTS
            FROM {DB_SCHEMA}.FACILITY_MEAL_FEEDBACK
            WHERE feedback_date >= DATEADD(day, -7, CURRENT_DATE()) ORDER BY FEEDBACK_DATE DESC LIMIT 20
        """)
        if not recent_feedback.empty:
            context_parts.append(
                f"Recent feedback (last 7 days, {len(recent_feedback)} entries): "
                f"Avg rating: {recent_feedback['OVERALL_RATING'].mean():.1f}/5. "
                f"Common highlights: {'; '.join(recent_feedback['HIGHLIGHTS'].dropna().head(5).tolist())}. "
                f"Common issues: {'; '.join(recent_feedback['LOWLIGHTS'].dropna().head(5).tolist())}."
            )
    except:
        pass

    try:
        proj = run_query(f"""
            SELECT AVG(PROJECTED_COUNT) as AVG_PROJ, AVG(ACTUAL_CONSUMPTION) as AVG_ACTUAL,
                   AVG(PROJECTED_COUNT - ACTUAL_CONSUMPTION) as AVG_WASTE
            FROM {DB_SCHEMA}.FACILITY_FOOD_PROJECTION
            WHERE projection_date >= DATEADD(day, -7, CURRENT_DATE())
        """)
        if not proj.empty:
            context_parts.append(f"Meal projections (7-day avg): Projected={float(proj['AVG_PROJ'].iloc[0] or 0):.0f}, Actual={float(proj['AVG_ACTUAL'].iloc[0] or 0):.0f}, Surplus={float(proj['AVG_WASTE'].iloc[0] or 0):.0f}.")
    except:
        pass

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


# --- Main ---
def main():
    st.set_page_config(page_title="GWSCafeteria", page_icon="🍽️", layout="wide", initial_sidebar_state="expanded")
    inject_css()

    st.sidebar.markdown("## 🍽️ GWSCafeteria")
    st.sidebar.markdown("F5 Hyderabad | Floors 8 & 9")
    st.sidebar.divider()

    page = st.sidebar.radio("Navigation", ["Dashboard", "Food Availability Tracker", "Meal Feedback", "Analytics", "AI Assistant"], label_visibility="collapsed")

    if page == "Dashboard":
        page_dashboard()
    elif page == "Food Availability Tracker":
        page_food_tracker()
    elif page == "Meal Feedback":
        page_feedback()
    elif page == "Analytics":
        page_analytics()
    elif page == "AI Assistant":
        page_ai_assistant()

    st.sidebar.divider()
    st.sidebar.caption("GWSCafeteria v0.1 (External)")


if __name__ == "__main__":
    main()
