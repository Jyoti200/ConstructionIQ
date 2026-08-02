import pandas as pd
import sqlite3
DB_PATH='project.db'
conn = sqlite3.connect(DB_PATH)

query = """
SELECT
    m.contractor_id,
    m.site_id AS material_site,
    d.site_id AS dpr_site,
    d.skilled_count,
    d.contractor_id
FROM fact_material m
LEFT JOIN fact_dpr_progress d
ON m.contractor_id = d.contractor_id
AND m.site_id = d.site_id
LIMIT 20;
"""

df = pd.read_sql_query(query, conn)
conn.close()

print(df.to_string())