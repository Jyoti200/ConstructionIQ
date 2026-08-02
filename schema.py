import sqlite3
import os

DB_PATH = "project.db"   # must match DB_PATH in db_utils.py

SCHEMA = """
CREATE TABLE dim_date (
    date_id INTEGER PRIMARY KEY AUTOINCREMENT,
    date TEXT NOT NULL UNIQUE,
    year INTEGER,
    quarter INTEGER,
    month INTEGER,
    month_name TEXT,
    day INTEGER,
    day_name TEXT,
    week_of_year INTEGER
);

CREATE TABLE dim_site (
    site_id INTEGER PRIMARY KEY AUTOINCREMENT,
    site_name TEXT NOT NULL UNIQUE,
    site_code TEXT
);

CREATE TABLE dim_block (
    block_id INTEGER PRIMARY KEY AUTOINCREMENT,
    site_id INTEGER NOT NULL,
    block_name TEXT NOT NULL,
    FOREIGN KEY (site_id) REFERENCES dim_site(site_id),
    UNIQUE (site_id, block_name)
);

CREATE TABLE dim_contractor (
    contractor_id INTEGER PRIMARY KEY AUTOINCREMENT,
    contractor_name TEXT NOT NULL UNIQUE
);

CREATE TABLE contractor_alias (
    alias_name TEXT PRIMARY KEY,
    contractor_id INTEGER NOT NULL,
    FOREIGN KEY (contractor_id) REFERENCES dim_contractor(contractor_id)
);

CREATE TABLE dim_activity (
    activity_id INTEGER PRIMARY KEY AUTOINCREMENT,
    wbs_code TEXT NOT NULL UNIQUE,
    activity_name TEXT NOT NULL
);

CREATE TABLE dim_material (
    material_id INTEGER PRIMARY KEY AUTOINCREMENT,
    material_name TEXT NOT NULL UNIQUE,
    unit TEXT
);

CREATE TABLE fact_dpr_progress (
    dpr_id INTEGER PRIMARY KEY AUTOINCREMENT,
    site_id INTEGER NOT NULL,
    date_id INTEGER NOT NULL,
    block_id INTEGER,
    activity_id INTEGER NOT NULL,
    contractor_id INTEGER,
    skilled_count INTEGER,
    helper_count INTEGER,
    coolie_count INTEGER,
    remarks TEXT,
    source_file TEXT,
    FOREIGN KEY (site_id) REFERENCES dim_site(site_id),
    FOREIGN KEY (date_id) REFERENCES dim_date(date_id),
    FOREIGN KEY (block_id) REFERENCES dim_block(block_id),
    FOREIGN KEY (activity_id) REFERENCES dim_activity(activity_id),
    FOREIGN KEY (contractor_id) REFERENCES dim_contractor(contractor_id),
    UNIQUE (site_id, date_id, block_id, activity_id, contractor_id)
);

CREATE TABLE fact_material (
    material_txn_id INTEGER PRIMARY KEY AUTOINCREMENT,
    site_id INTEGER NOT NULL,
    date_id INTEGER NOT NULL,
    block_id INTEGER,
    contractor_id INTEGER,
    activity_id INTEGER,
    material_id INTEGER NOT NULL,
    received_quantity REAL,
    remarks TEXT,
    source_file TEXT,
    FOREIGN KEY (site_id) REFERENCES dim_site(site_id),
    FOREIGN KEY (date_id) REFERENCES dim_date(date_id),
    FOREIGN KEY (block_id) REFERENCES dim_block(block_id),
    FOREIGN KEY (contractor_id) REFERENCES dim_contractor(contractor_id),
    FOREIGN KEY (activity_id) REFERENCES dim_activity(activity_id),
    FOREIGN KEY (material_id) REFERENCES dim_material(material_id)
);

CREATE INDEX idx_fact_dpr_site_date ON fact_dpr_progress(site_id, date_id);
CREATE INDEX idx_fact_material_site_date ON fact_material(site_id, date_id);
"""


def build_schema():
    if os.path.exists(DB_PATH):
        print(f"{DB_PATH} already exists — delete it first if you want a fresh rebuild.")
        return

    conn = sqlite3.connect(DB_PATH)
    conn.executescript(SCHEMA)
    conn.commit()

    cur = conn.cursor()
    cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = [row[0] for row in cur.fetchall()]
    conn.close()

    print(f"Created {DB_PATH} with tables: {tables}")


if __name__ == "__main__":
    build_schema()