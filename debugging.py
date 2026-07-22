import pandas as pd
import sqlite3
DB_PATH='project.db'
conn = sqlite3.connect(DB_PATH)

query = """
SELECT
    dim_site.site_id,
    fact_dpr_progress.date_id,
    fact_dpr_progress.block_id,
    fact_dpr_progress.activity_id,
    fact_dpr_progress.contractor_id,
    DIM_CONTRACTOR.CONTRACTOR_NAME,
    dim_site.site_name,
    COUNT(*) AS cnt
FROM fact_dpr_progress
JOIN DIM_SITE ON fact_dpr_progress.site_id=dim_site.site_id
JOIN DIM_CONTRACTOR ON FACT_DPR_PROGRESS.CONTRACTOR_ID=DIM_CONTRACTOR.CONTRACTOR_ID
GROUP BY
    fact_dpr_progress.site_id,
    fact_dpr_progress.date_id,
    fact_dpr_progress.block_id,
    fact_dpr_progress.activity_id,
    fact_dpr_progress.contractor_id
HAVING COUNT(*) > 1;
"""


df = pd.read_sql_query(query, conn)
conn.close()

print(df.to_string())