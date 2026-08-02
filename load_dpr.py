"""
load_dpr.py
-----------
Fetches DPR data from your public Google Sheet and loads it into fact_dpr_progress.

Usage:
    python load_dpr.py --sheet-id YOUR_SHEET_ID_HERE
"""

import argparse
import datetime as dt
import pandas as pd

from db_utils import (
    get_conn,
    get_or_create_site,
    get_or_create_date,
    get_or_create_block,
    get_or_create_activity_from_description,
    get_or_create_contractor,
)

COLUMN_MAP = {
    "Date": "date",
    "Site Name": "site",
    "Block Name": "block",
    "Work Description": "work_description",
    "Contractor Name": "contractor",
    "Skilled Labour Count": "skilled",
    "Helper": "helper",
    "Coolie": "coolie",
    "Remarks": "remarks",
}


def fetch_sheet(sheet_id: str, gid: str = "0") -> pd.DataFrame:
    url = f"https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=csv&gid={gid}"
    return pd.read_csv(url)


def load_dpr(df: pd.DataFrame, source_label: str):
    df.columns = [c.strip() for c in df.columns]
    df = df.rename(columns=COLUMN_MAP)

    missing = set(COLUMN_MAP.values()) - set(df.columns)
    if missing:
        raise ValueError(f"Sheet is missing expected columns: {missing}")

    conn = get_conn()
    inserted, skipped = 0, 0

    for _, row in df.iterrows():
        try:
            if pd.isna(row["site"]) or pd.isna(row["date"]) or pd.isna(row["work_description"]):
                skipped += 1
                continue

            site_id = get_or_create_site(conn, str(row["site"]))
            date_id = get_or_create_date(conn, row["date"])

            block_id = None
            if not pd.isna(row.get("block")) and str(row.get("block")).strip():
                block_id = get_or_create_block(conn, site_id, str(row["block"]))

            activity_id = get_or_create_activity_from_description(conn, str(row["work_description"]))

            contractor_id = None
            if not pd.isna(row.get("contractor")) and str(row.get("contractor")).strip():
                contractor_id = get_or_create_contractor(conn, str(row["contractor"]))

            def to_int(v):
                return None if pd.isna(v) else int(v)

            cur = conn.execute(
                """INSERT OR IGNORE INTO fact_dpr_progress
                   (site_id, date_id, block_id, activity_id, contractor_id,
                    skilled_count, helper_count, coolie_count, remarks, source_file)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    site_id, date_id, block_id, activity_id, contractor_id,
                    to_int(row.get("skilled")),
                    to_int(row.get("helper")),
                    to_int(row.get("coolie")),
                    None if pd.isna(row.get("remarks")) else str(row["remarks"]),
                    source_label,
                ),
            )
            if cur.rowcount:
                inserted += 1
        except Exception as e:
            print(f"  ! Skipped bad row: {e}")
            skipped += 1

    conn.commit()
    conn.close()
    print(f"Load complete: {inserted} inserted, {skipped} skipped.")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--sheet-id", required=True)
    parser.add_argument("--gid", default="0")
    args = parser.parse_args()

    df = fetch_sheet(args.sheet_id, args.gid)
    source_label = f"gsheet:{args.sheet_id}:{dt.date.today()}"
    load_dpr(df, source_label)


if __name__ == "__main__":
    main()