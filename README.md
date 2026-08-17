# ConstructionIQ — Turning Messy Site Paperwork into a Live Project Dashboard

A data pipeline + Streamlit dashboard that pulls daily labour and material records from multiple construction sites into a single SQLite warehouse, so project managers can see who's working where — and what materials have arrived — without digging through spreadsheets.

**Key highlights:**
- **Star-schema warehouse** consolidating labour (DPR) and material data from multiple sites, blocks, and contractors into one queryable source of truth
- **Fuzzy contractor-name matching** (`rapidfuzz` + `jellyfish`) to resolve inconsistent naming across source files into a single canonical contractor list
- **Interactive Streamlit dashboard** with live KPIs, trend charts, and drill-down tabs for labour, material, and raw data deployed on streamlit cloud

---

## The Challenge

Construction sites generate daily progress reports (DPR) and material-delivery logs as loose files — often filled out by different contractors, in different formats, with inconsistent naming (`"ABC Const."` vs `"ABC Construction"` vs `"abc const"`). This makes it hard to answer simple questions like:

- How many people were actually on site today, across all contractors?
- Which contractor is deploying the most labour, and on which activities?
- What materials have come in, by site and by block?

**Objectives:**
- Centralize labour and material data from multiple sites into one structured database
- Automatically reconcile inconsistent contractor names instead of relying on manual cleanup
- Give non-technical stakeholders (site managers, PMs) a self-serve dashboard instead of raw spreadsheets

---

##  Technology Stack

| Layer | Tools |
|---|---|
| **Data storage** | SQLite (star schema: fact + dimension tables) |
| **Data pipeline** | Python, pandas |
| **Data quality** | `rapidfuzz`, `jellyfish` (fuzzy contractor-name matching), custom validation scripts |
| **Dashboard** | Streamlit, Plotly Express |

---

##  Solution & Architecture

### Data model
The warehouse follows a classic star schema:

- **Fact tables:** `fact_dpr_progress` (daily labour counts by site/block/activity/contractor) and `fact_material` (material deliveries by site/block/contractor)
- **Dimension tables:** `dim_site`, `dim_block`, `dim_contractor`, `dim_activity`, `dim_material`, `dim_date`
- **`contractor_alias`** — maps messy source-file spellings to a canonical `contractor_id`, so "ABC Const." and "ABC Construction" roll up into one contractor in every report

### Pipeline
1. `schema.py` builds the SQLite schema (fact + dimension tables, indexes, dedupe constraints)
2. `load_dpr.py` and `material.py` load and transform raw daily-progress and material source files into the warehouse
3. `check.py`, `check_labour.py`, and `validate.py` run data-quality checks against the loaded data
4. `db_utils.py` holds shared database helper functions used across the pipeline scripts

### Dashboard (`app.py`)
A Streamlit app reads directly from `project.db` and presents:
- **KPI row:** people deployed, average daily labour, active contractors, material deliveries — filtered live by site, contractor, and date range
- **Overview tab:** labour trend over time (daily/weekly) and labour by site
- **Labour tab:** top contractors by people deployed, worker-type mix (skilled/helper/coolie), and top activities by labour
- **Material tab:** material received by type and by contractor
- **Full data tab:** raw underlying records for anyone who wants to verify the numbers

### Key technical hurdle
Contractor names arriving from different site files rarely matched exactly. Rather than requiring manual cleanup before every load, the pipeline uses fuzzy string matching (`rapidfuzz`, `jellyfish`) against the `contractor_alias` table to resolve name variants to a single canonical contractor — keeping the dashboard's "top contractors" views accurate without hand-editing source files.

---

##  Impact

By consolidating scattered site records into one warehouse with a live dashboard, ConstructionIQ replaces manual spreadsheet reconciliation with:
- Reduced manual time from 2 hours to 10 minutes
- A centralized view of labor deployment across every site, every block and contractor
- Material-delivery visibility broken out correctly by unit (so bags, kg, and other units are never mixed together)
  
---

##  Key Takeaways & Future Scope

**What this project involved:**
- Designing a star-schema data model for messy, multi-source operational data
- Applying fuzzy matching to solve real-world data-quality problems (inconsistent naming) rather than relying on manual fixes
- Building a filterable, multi-tab BI-style dashboard on top of a lightweight SQLite backend

**Possible next steps:**
 -Move from SQLite to a cloud based database backend for concurrent access at scale

---

## Getting Started

**Prerequisites:** Python 3.9+

```bash
# 1. Clone the repo
git clone https://github.com/Jyoti200/ConstructionIQ.git
cd ConstructionIQ

# 2. Install dependencies
pip install -r requirements.txt

# 3. Build the database schema (skip if project.db already exists)
python schema.py

# 4. Load your DPR and material source files
python load_dpr.py
python material.py

# 5. (Optional) Run data-quality checks
python validate.py
python check.py
python check_labour.py

# 6. Launch the dashboard
streamlit run app.py
```

The dashboard will open in your browser, reading live from `project.db`.

---

##  Repository Structure

```
ConstructionIQ/
├── app.py              # Streamlit dashboard
├── schema.py            # Builds the SQLite star schema
├── db_utils.py           # Shared database helper functions
├── load_dpr.py           # Loads daily progress report (labour) data
├── material.py           # Loads material delivery data
├── validate.py            # Data validation checks
├── check.py               # Data quality checks
├── check_labour.py         # Labour-specific data checks
├── requirements.txt         # Python dependencies
├── Github Actions Workflow  # yml file that runs every 6 hours to keep updating the                                         project.db file
└── project.db                # SQLite warehouse (fact + dimension tables)
```
