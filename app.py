"""
app.py — Project Centralization Dashboard
-------------------------------------------
Run with: streamlit run app.py
Needs project.db in the same folder (built + loaded already).

Requires: pip install streamlit pandas plotly
"""

import sqlite3
import pandas as pd
import plotly.express as px
import streamlit as st

DB_PATH = "project.db"

st.set_page_config(page_title="Project Dashboard", layout="wide")

# ---------------- Theme ----------------
ACCENT = "#2E6F95"       # steel blue — labour
ACCENT_2 = "#D98E04"     # amber — material
NEUTRAL = "#6B7280"

px.defaults.template = "plotly_white"
px.defaults.color_discrete_sequence = [ACCENT, ACCENT_2, "#5B8C5A", "#A34D4D", "#7C6BA6", "#4A9B9B"]

st.markdown(
    """
    <style>
    .block-container {padding-top: 1.5rem; max-width: 1200px;}
    div[data-testid="stMetric"] {
        background: #F8FAFC;
        border: 1px solid #E5E7EB;
        border-radius: 10px;
        padding: 16px 18px 12px 18px;
    }
    div[data-testid="stMetricLabel"] {font-weight: 600; color: #374151; font-size: 0.95rem;}
    div[data-testid="stMetricValue"] {font-size: 1.8rem;}
    h1 {font-weight: 700;}
    h2, h3 {font-weight: 600;}
    .stTabs [data-baseweb="tab"] {font-size: 1rem; font-weight: 600; padding: 10px 18px;}
    </style>
    """,
    unsafe_allow_html=True,
)


# ---------------- Data loading (unchanged logic) ----------------
@st.cache_data(ttl=300)
def load_data():
    conn = sqlite3.connect(DB_PATH)

    dpr = pd.read_sql("""
        SELECT f.dpr_id, s.site_name, b.block_name, a.activity_name,
               c.contractor_name, d.date,
               f.skilled_count, f.helper_count, f.coolie_count
        FROM fact_dpr_progress f
        JOIN dim_site s ON f.site_id = s.site_id
        LEFT JOIN dim_block b ON f.block_id = b.block_id
        JOIN dim_activity a ON f.activity_id = a.activity_id
        LEFT JOIN dim_contractor c ON f.contractor_id = c.contractor_id
        JOIN dim_date d ON f.date_id = d.date_id
    """, conn)

    material = pd.read_sql("""
        SELECT m.material_txn_id, s.site_name, b.block_name,
               c.contractor_name, mat.material_name, mat.unit,
               m.received_quantity, d.date
        FROM fact_material m
        JOIN dim_site s ON m.site_id = s.site_id
        LEFT JOIN dim_block b ON m.block_id = b.block_id
        LEFT JOIN dim_contractor c ON m.contractor_id = c.contractor_id
        JOIN dim_material mat ON m.material_id = mat.material_id
        JOIN dim_date d ON m.date_id = d.date_id
    """, conn)

    conn.close()

    dpr["date"] = pd.to_datetime(dpr["date"])
    material["date"] = pd.to_datetime(material["date"])
    dpr["total_labour"] = dpr[["skilled_count", "helper_count", "coolie_count"]].sum(axis=1, min_count=1)

    return dpr, material


@st.cache_data(ttl=300)
def load_combined():
    """Pre-joined labour-vs-material view (kept for the raw-data tab)."""
    conn = sqlite3.connect(DB_PATH)
    query = """
    WITH dpr_daily AS (
        SELECT
            contractor_id, site_id, block_id, date_id,
            SUM(COALESCE(skilled_count,0)) AS skilled_count,
            SUM(COALESCE(helper_count,0)) AS helper_count,
            SUM(COALESCE(coolie_count,0)) AS coolie_count
        FROM fact_dpr_progress
        GROUP BY contractor_id, site_id, block_id, date_id
    )
    SELECT
        c.contractor_name, s.site_name, b.block_name, dt.date,
        mat.material_name, m.received_quantity, mat.unit AS material_unit,
        dp.skilled_count, dp.helper_count, dp.coolie_count,
        (COALESCE(dp.skilled_count,0) + COALESCE(dp.helper_count,0) + COALESCE(dp.coolie_count,0)) AS total_labour
    FROM fact_material m
    JOIN dim_contractor c ON m.contractor_id = c.contractor_id
    JOIN dim_site s ON m.site_id = s.site_id
    LEFT JOIN dim_block b ON m.block_id = b.block_id
    JOIN dim_date dt ON m.date_id = dt.date_id
    JOIN dim_material mat ON m.material_id = mat.material_id
    LEFT JOIN dpr_daily dp
        ON dp.contractor_id = m.contractor_id
        AND dp.site_id = m.site_id
        AND dp.date_id = m.date_id
        AND IFNULL(dp.block_id,-1) = IFNULL(m.block_id,-1)
    ORDER BY c.contractor_name, b.block_name, dt.date;
    """
    combined = pd.read_sql_query(query, conn)
    conn.close()
    combined["date"] = pd.to_datetime(combined["date"])
    return combined


dpr, material = load_data()
combined = load_combined()

st.title("🏗️ Project Dashboard")
st.caption("A simple view of who's working where, and what materials have come in.")

# ---------------- Sidebar filters (plain language) ----------------
st.sidebar.header("Filter")

sites = sorted(set(dpr["site_name"]) | set(material["site_name"]))
selected_sites = st.sidebar.multiselect("Site", sites, default=sites)

contractors = sorted(
    set(dpr["contractor_name"].dropna()) |
    set(material["contractor_name"].dropna())
)
selected_contractors = st.sidebar.multiselect("Contractor", contractors, default=contractors)

min_date = min(dpr["date"].min(), material["date"].min()).date()
max_date = max(dpr["date"].max(), material["date"].max()).date()

st.sidebar.markdown("**Time period**")
mode = st.sidebar.radio("Time period", ["One day", "Date range"], label_visibility="collapsed")

if mode == "One day":
    selected_date = st.sidebar.date_input("Pick a date", value=max_date)
    start = end = pd.to_datetime(selected_date)
else:
    start_date, end_date = st.sidebar.date_input("Pick a range", value=(min_date, max_date))
    start = pd.to_datetime(start_date)
    end = pd.to_datetime(end_date)

dpr_f = dpr[
    dpr["site_name"].isin(selected_sites)
    & dpr["contractor_name"].isin(selected_contractors)
    & (dpr["date"] >= start) & (dpr["date"] <= end)
]

mat_f = material[
    material["site_name"].isin(selected_sites)
    & material["contractor_name"].isin(selected_contractors)
    & (material["date"] >= start) & (material["date"] <= end)
]

combined_f = combined[
    combined["site_name"].isin(selected_sites)
    & combined["contractor_name"].isin(selected_contractors)
    & (combined["date"] >= start) & (combined["date"] <= end)
]

# ---------------- KPI row (always visible, above the tabs) ----------------
is_company=dpr_f['contractor_name']=="company"
total_mason_cost = (dpr_f[is_company,"skilled_count"].sum()) * 1000
total_helper_cost = (dpr_f[is_company,"helper_count"].sum()) * 650
total_coolie_cost = (dpr_f[is_company,"coolie_count"].sum()) * 450
total_labour_cost = total_mason_cost + total_helper_cost + total_coolie_cost
total_labour = dpr_f["total_labour"].sum()
active_contractors = dpr_f["contractor_name"].nunique()
material_entries = len(mat_f)
avg_daily_labour = dpr_f.groupby("date")["total_labour"].sum().mean() if not dpr_f.empty else 0

k1, k2, k3, k4,k5 = st.columns(5)
k1.metric("👷 People deployed", f"{int(total_labour):,}" if pd.notna(total_labour) else "—")
k2.metric("📅 Avg. per day", f"{avg_daily_labour:,.0f}" if pd.notna(avg_daily_labour) else "—")
k3.metric("🏢 Contractors active", f"{active_contractors:,}")
k4.metric("📦 Material deliveries", f"{material_entries:,}")
k5.metric("Total Company Labour Cost",f"{total_labour_cost:,.0f}")

st.write("")

# ---------------- Tabs ----------------
tab_overview, tab_labour, tab_material, tab_data = st.tabs(
    ["📊 Overview", "👷 Labour", "📦 Material", "📋 Full data"]
)

# ===== TAB 1: OVERVIEW =====
with tab_overview:
    st.subheader("People working, over time")
    trend_view = st.radio("View", ["Daily", "Weekly"], horizontal=True, label_visibility="collapsed")

    labour_by_date = dpr_f.groupby("date", as_index=False)["total_labour"].sum().sort_values("date")

    if not labour_by_date.empty:
        if trend_view == "Weekly":
            plot_df = (
                labour_by_date.set_index("date")["total_labour"]
                .resample("W-MON", label="left", closed="left")
                .sum()
                .reset_index()
            )
            x_label = "Week starting"
        else:
            plot_df = labour_by_date
            x_label = ""

        fig = px.area(
            plot_df, x="date", y="total_labour",
            labels={"date": x_label, "total_labour": "People on site"},
        )
        fig.update_traces(line_color=ACCENT, fillcolor="rgba(46,111,149,0.25)")
        fig.update_layout(height=340, margin=dict(t=10, b=10))
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("No labour entries for the current filters.")

    st.write("")
    st.subheader("Where the work is happening")
    site_labour = dpr_f.groupby("site_name", as_index=False)["total_labour"].sum()
    if not site_labour.empty:
        fig = px.bar(
            site_labour.sort_values("total_labour", ascending=False),
            x="site_name", y="total_labour",
            labels={"site_name": "", "total_labour": "People deployed"},
        )
        fig.update_traces(marker_color=ACCENT)
        fig.update_layout(height=340, margin=dict(t=10, b=10))
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("No labour entries for the current filters.")

# ===== TAB 2: LABOUR =====
with tab_labour:
    c1, c2 = st.columns([1.3, 1])

    with c1:
        st.subheader("Who's doing the work")
        st.caption("Top 10 contractors by people deployed.")
        labour_summary = (
            dpr_f.groupby("contractor_name", as_index=False)["total_labour"]
            .sum().sort_values("total_labour", ascending=False).head(10)
            .sort_values("total_labour", ascending=True)
        )
        if not labour_summary.empty:
            fig = px.bar(
                labour_summary, x="total_labour", y="contractor_name", orientation="h",
                labels={"total_labour": "People deployed", "contractor_name": ""},
                text="total_labour",
            )
            fig.update_traces(marker_color=ACCENT, texttemplate="%{text:,.0f}", textposition="outside")
            fig.update_layout(height=max(320, 34 * len(labour_summary)), margin=dict(t=10, b=10))
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("No labour entries for the current filters.")

    with c2:
        st.subheader("Type of worker")
        mix = dpr_f[["skilled_count", "helper_count", "coolie_count"]].sum()
        mix.index = mix.index.str.replace("_count", "").str.title()
        if mix.sum() > 0:
            fig = px.pie(values=mix.values, names=mix.index, hole=0.55)
            fig.update_traces(textinfo="percent+label")
            fig.update_layout(showlegend=False, height=340, margin=dict(t=10, b=10))
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("No data.")

    st.write("")
    st.subheader("What people are working on")
    st.caption("Top 5 activities by people deployed.")
    activity_labour = (
        dpr_f.groupby("activity_name", as_index=False)["total_labour"]
        .sum().sort_values("total_labour", ascending=False).head(5)
        .sort_values("total_labour", ascending=True)
    )
    if not activity_labour.empty:
        fig = px.bar(
            activity_labour, x="total_labour", y="activity_name", orientation="h",
            labels={"total_labour": "People deployed", "activity_name": ""},
            text="total_labour",
        )
        fig.update_traces(marker_color=ACCENT, texttemplate="%{text:,.0f}", textposition="outside")
        fig.update_layout(height=max(320, 32 * len(activity_labour)), margin=dict(t=10, b=10))
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("No activity entries for the current filters.")

# ===== TAB 3: MATERIAL =====
with tab_material:
    st.subheader("Material received, by type")
    st.caption("Each material is shown in its own unit (bags, kg, etc.) so nothing gets mixed together.")
    mat_by_type = (
        mat_f.groupby(["material_name", "unit"], as_index=False)["received_quantity"]
        .sum().sort_values("received_quantity", ascending=False).head(12)
    )
    if not mat_by_type.empty:
        mat_by_type["label"] = mat_by_type["material_name"] + " (" + mat_by_type["unit"] + ")"
        fig = px.bar(
            mat_by_type, x="label", y="received_quantity", color="unit",
            labels={"label": "", "received_quantity": "Quantity received", "unit": "Unit"},
            text="received_quantity",
        )
        fig.update_traces(texttemplate="%{text:,.0f}", textposition="outside")
        fig.update_layout(height=380, margin=dict(t=10, b=10), legend_title_text="Unit")
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("No material entries for the current filters.")

    st.write("")
    st.subheader("Material received, by contractor")
    st.caption("Counted as number of deliveries, since materials come in different units.")
    mat_count = (
        mat_f.groupby("contractor_name", as_index=False)["material_txn_id"].count()
        .rename(columns={"material_txn_id": "deliveries"})
        .sort_values("deliveries", ascending=True)
    )
    if not mat_count.empty:
        fig = px.bar(
            mat_count, x="deliveries", y="contractor_name", orientation="h",
            labels={"deliveries": "Number of deliveries", "contractor_name": ""},
            text="deliveries",
        )
        fig.update_traces(marker_color=ACCENT_2, texttemplate="%{text:,.0f}", textposition="outside")
        fig.update_layout(height=max(320, 32 * len(mat_count)), margin=dict(t=10, b=10))
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("No material entries for the current filters.")

# ===== TAB 4: FULL DATA =====
with tab_data:
    st.caption("The raw records behind the charts above, for anyone who wants to check the details.")
    t1, t2, t3 = st.tabs(["Daily work entries", "Material deliveries", "Work + material combined"])

    def fmt(df, cols):
        df = df.copy()
        for c in cols:
            df[c] = df[c].fillna("—")
        return df

    with t1:
        dpr_display = fmt(dpr_f, ["block_name", "contractor_name"])
        dpr_display["date"] = dpr_display["date"].dt.strftime("%Y-%m-%d")
        st.dataframe(
            dpr_display[["date", "site_name", "block_name", "activity_name",
                         "contractor_name", "skilled_count", "helper_count", "coolie_count", "total_labour"]]
            .sort_values("date", ascending=False),
            use_container_width=True,
        )

    with t2:
        mat_display = fmt(mat_f, ["block_name", "contractor_name"])
        mat_display["date"] = mat_display["date"].dt.strftime("%Y-%m-%d")
        st.dataframe(
            mat_display[["date", "site_name", "block_name", "contractor_name",
                         "material_name", "received_quantity", "unit"]]
            .sort_values("date", ascending=False),
            use_container_width=True,
        )

    with t3:
        combined_display = fmt(
            combined_f, ["block_name", "skilled_count", "helper_count", "coolie_count", "total_labour"]
        )
        combined_display["date"] = combined_display["date"].dt.strftime("%Y-%m-%d")
        st.dataframe(combined_display, use_container_width=True)
