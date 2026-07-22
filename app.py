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
import plotly.graph_objects as go
import streamlit as st

DB_PATH = "project.db"

st.set_page_config(page_title="Project Dashboard", layout="wide", page_icon="🏗️")

# ---------------- Theme ----------------
ACCENT = "#2E6F95"       # steel blue — labour
ACCENT_2 = "#D98E04"     # amber — material
NEUTRAL = "#6B7280"
BG_CARD = "#F8FAFC"

px.defaults.template = "plotly_white"
px.defaults.color_discrete_sequence = [ACCENT, ACCENT_2, "#5B8C5A", "#A34D4D", "#7C6BA6", "#4A9B9B"]

st.markdown(
    """
    <style>
    .block-container {padding-top: 1.5rem;}
    div[data-testid="stMetric"] {
        background: #F8FAFC;
        border: 1px solid #E5E7EB;
        border-radius: 10px;
        padding: 14px 16px 8px 16px;
    }
    div[data-testid="stMetricLabel"] {font-weight: 600; color: #374151;}
    h1 {font-weight: 700;}
    h2, h3 {font-weight: 600;}
    </style>
    """,
    unsafe_allow_html=True,
)


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
    """Pre-joined labour-vs-material view, used for the correlation section."""
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

st.title("🏗️ Project Centralization Dashboard")
st.caption("Consolidated labour deployment and material receipts across sites, blocks and contractors.")

# ---------------- Sidebar filters ----------------
st.sidebar.header("Filters")

sites = sorted(set(dpr["site_name"]) | set(material["site_name"]))
selected_sites = st.sidebar.multiselect("Site", sites, default=sites)

contractors = sorted(
    set(dpr["contractor_name"].dropna()) |
    set(material["contractor_name"].dropna())
)
selected_contractors = st.sidebar.multiselect("Contractor", contractors, default=contractors)

min_date = min(dpr["date"].min(), material["date"].min()).date()
max_date = max(dpr["date"].max(), material["date"].max()).date()

mode = st.sidebar.radio("Date Filter", ["Single Date", "Date Range"])

if mode == "Single Date":
    selected_date = st.sidebar.date_input("Select Date", value=max_date)
    start = end = pd.to_datetime(selected_date)
else:
    start_date, end_date = st.sidebar.date_input("Select Date Range", value=(min_date, max_date))
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

# ---------------- KPI row ----------------
total_labour = dpr_f["total_labour"].sum()
active_contractors = dpr_f["contractor_name"].nunique()
material_entries = len(mat_f)
avg_daily_labour = dpr_f.groupby("date")["total_labour"].sum().mean() if not dpr_f.empty else 0

col1, col2, col4, col5 = st.columns(4)
col1.metric("Total labour deployed", f"{int(total_labour):,}" if pd.notna(total_labour) else "—")
col2.metric("Avg. daily labour", f"{avg_daily_labour:,.0f}" if pd.notna(avg_daily_labour) else "—")
col4.metric("Active contractors", f"{active_contractors:,}")
col5.metric("Material transactions", f"{material_entries:,}")

st.divider()

# ---------------- Row 1: Labour trend + Labour mix ----------------
c1, c2 = st.columns([2, 1])

with c1:
    st.subheader("Labour deployed over time")
    labour_by_date = dpr_f.groupby("date", as_index=False)[
        ["skilled_count", "helper_count", "coolie_count"]
    ].sum()
    if not labour_by_date.empty:
        melted = labour_by_date.melt(
            id_vars="date",
            value_vars=["skilled_count", "helper_count", "coolie_count"],
            var_name="category", value_name="count",
        )
        melted["category"] = melted["category"].str.replace("_count", "").str.title()
        fig = px.area(
            melted, x="date", y="count", color="category",
            labels={"date": "", "count": "Labour count", "category": "Category"},
        )
        fig.update_layout(legend_title_text="", height=380, margin=dict(t=10, b=10))
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("No labour data for the selected filters.")

with c2:
    st.subheader("Labour mix")
    mix = dpr_f[["skilled_count", "helper_count", "coolie_count"]].sum()
    mix.index = mix.index.str.replace("_count", "").str.title()
    if mix.sum() > 0:
        fig = px.pie(values=mix.values, names=mix.index, hole=0.55)
        fig.update_traces(textinfo="percent+label")
        fig.update_layout(showlegend=False, height=380, margin=dict(t=10, b=10))
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("No data.")

# ---------------- Row 2: Contractor comparison ----------------
st.subheader("Contractor performance")
c3, c4 = st.columns(2)

with c3:
    labour_summary = (
        dpr_f.groupby("contractor_name", as_index=False)["total_labour"]
        .sum().sort_values("total_labour", ascending=True)
    )
    if not labour_summary.empty:
        fig = px.bar(
            labour_summary, x="total_labour", y="contractor_name", orientation="h",
            labels={"total_labour": "Total labour", "contractor_name": ""},
            text="total_labour",
        )
        fig.update_traces(marker_color=ACCENT, texttemplate="%{text:,.0f}", textposition="outside")
        fig.update_layout(height=max(300, 32 * len(labour_summary)), margin=dict(t=30, b=10))
        fig.update_layout(title="Labour by contractor")
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("No labour data.")

with c4:
    mat_summary = (
        mat_f.groupby("contractor_name", as_index=False)["received_quantity"]
        .sum().sort_values("received_quantity", ascending=True)
    )
    if not mat_summary.empty:
        fig = px.bar(
            mat_summary, x="received_quantity", y="contractor_name", orientation="h",
            labels={"received_quantity": "Material received (mixed units)", "contractor_name": ""},
            text="received_quantity",
        )
        fig.update_traces(marker_color=ACCENT_2, texttemplate="%{text:,.0f}", textposition="outside")
        fig.update_layout(height=max(300, 32 * len(mat_summary)), margin=dict(t=30, b=10))
        fig.update_layout(title="Material received by contractor")
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("No material data.")

st.caption(
    "Material totals combine quantities across different units per contractor; "
    "use the material-by-type view below for like-for-like comparisons."
)

# ---------------- Row 3: Material by type + Site breakdown ----------------
c5, c6 = st.columns(2)

with c5:
    st.subheader("Material received by type")
    # Group by material AND unit so quantities in different units (e.g. cement
    # in bags vs. kg) are never silently summed together.
    mat_by_type = (
        mat_f.groupby(["material_name", "unit"], as_index=False)["received_quantity"]
        .sum().sort_values("received_quantity", ascending=False).head(12)
    )
    if not mat_by_type.empty:
        mat_by_type["label"] = mat_by_type["material_name"] + " (" + mat_by_type["unit"] + ")"
        fig = px.bar(
            mat_by_type, x="label", y="received_quantity", color="unit",
            labels={"label": "", "received_quantity": "Quantity", "unit": "Unit"},
            text="received_quantity",
        )
        fig.update_traces(texttemplate="%{text:,.0f}", textposition="outside")
        fig.update_layout(height=380, margin=dict(t=10, b=10), legend_title_text="Unit")
        st.plotly_chart(fig, use_container_width=True)
        dupes = mat_by_type.groupby("material_name")["unit"].nunique()
        if dupes.gt(1).any():
            mixed = ", ".join(dupes[dupes > 1].index)
            st.caption(f"Reported in more than one unit for the selected filters: {mixed}. Bars are kept separate by unit, not combined.")
    else:
        st.info("No material data.")

with c6:
    st.subheader("Labour deployed by site")
    site_labour = dpr_f.groupby("site_name", as_index=False)["total_labour"].sum()
    if not site_labour.empty:
        fig = px.bar(
            site_labour.sort_values("total_labour", ascending=False),
            x="site_name", y="total_labour",
            labels={"site_name": "", "total_labour": "Total labour"},
        )
        fig.update_traces(marker_color=ACCENT)
        fig.update_layout(height=380, margin=dict(t=10, b=10))
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("No labour data.")

# ---------------- Row 3.5: Activity breakdown ----------------
st.subheader("Activity")
c7, c8 = st.columns([1, 1.3])

with c7:
    activity_labour = (
        dpr_f.groupby("activity_name", as_index=False)["total_labour"]
        .sum().sort_values("total_labour", ascending=True)
    )
    if not activity_labour.empty:
        fig = px.bar(
            activity_labour, x="total_labour", y="activity_name", orientation="h",
            labels={"total_labour": "Total labour", "activity_name": ""},
            text="total_labour",
        )
        fig.update_traces(marker_color=ACCENT, texttemplate="%{text:,.0f}", textposition="outside")
        fig.update_layout(height=max(320, 30 * len(activity_labour)), margin=dict(t=30, b=10),
                           title="Labour by activity")
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("No activity data.")

with c8:
    # Simple, familiar stacked bar: one bar per site, segments = activities.
    # Rolled up to site level (block detail stays in the raw-data expander)
    # so it reads at a glance for non-technical stakeholders.
    site_activity = (
        dpr_f.groupby(["site_name", "activity_name"], as_index=False)["total_labour"]
        .sum()
    )
    site_activity = site_activity[site_activity["total_labour"] > 0]
    if not site_activity.empty:
        fig = px.bar(
            site_activity, x="total_labour", y="site_name", color="activity_name",
            orientation="h",
            labels={"total_labour": "Total labour", "site_name": "", "activity_name": "Activity"},
        )
        fig.update_layout(
            height=max(320, 40 * site_activity["site_name"].nunique()),
            margin=dict(t=30, b=10),
            title="Labour by site, split by activity",
            legend_title_text="Activity",
            barmode="stack",
        )
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("No activity data.")


# ---------------- Detail tables (kept minimal, tucked away) ----------------
with st.expander("View underlying records (DPR, material, combined)"):
    t1, t2, t3 = st.tabs(["DPR entries", "Material issued", "Labour vs Material (raw)"])

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