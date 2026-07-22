"""
contractor_material_labour_report.py
-------------------------------------
For each contractor, on each date: what material they were issued,
and how much labour they had on site that day.

Usage:
    python contractor_material_labour_report.py
"""

import sqlite3
import pandas as pd

DB_PATH = "project.db"


def run_report():
    conn = sqlite3.connect(DB_PATH)

    query = """
    WITH dpr_daily AS (
        SELECT
            contractor_id,
            site_id,
            date_id,
            SUM(COALESCE(skilled_count,0)) AS skilled_count,
            SUM(COALESCE(helper_count,0)) AS helper_count,
            SUM(COALESCE(coolie_count,0)) AS coolie_count
        FROM fact_dpr_progress
        GROUP BY contractor_id, site_id, date_id
    )
    SELECT
        c.contractor_name,
        s.site_name,
        b.block_name,
        d.date,
        mat.material_name,
        m.received_quantity,
        mat.unit AS material_unit,
        dp.skilled_count,
        dp.helper_count,
        dp.coolie_count,
        (COALESCE(dp.skilled_count,0) + COALESCE(dp.helper_count,0) + COALESCE(dp.coolie_count,0)) AS total_labour
    FROM fact_material m
    JOIN dim_contractor c ON m.contractor_id = c.contractor_id
    JOIN dim_site s ON m.site_id = s.site_id
    LEFT JOIN dim_block b ON m.block_id = b.block_id
    JOIN dim_date d ON m.date_id = d.date_id
    JOIN dim_material mat ON m.material_id = mat.material_id
    LEFT JOIN dpr_daily dp
        ON dp.contractor_id = m.contractor_id
        AND dp.site_id = m.site_id
        AND dp.date_id = m.date_id
    ORDER BY c.contractor_name, d.date
    """
    df = pd.read_sql(query, conn)
    conn.close()
    return df


if __name__ == "__main__":
    df = run_report()
    print(df)
    df.to_csv("material_labour_report.csv", index=False)
    print("\nSaved to contractor_material_labour_report.csv")