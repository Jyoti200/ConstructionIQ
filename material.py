"""
load_material.py
-----------------
Fetches Material data from your public Google Sheet and loads it into fact_material.

Usage:
    python load_material.py --sheet-id YOUR_SHEET_ID_HERE
"""

import argparse
import datetime as dt
import pandas as pd

from db_utils import (
    get_conn,
    get_or_create_site,
    get_or_create_date,
    get_or_create_material,
    get_or_create_contractor,
    get_or_create_block,
    get_or_create_activity_from_description,
)

COLUMN_MAP = {
    "Site Name": "site",
    "Date": "date",
    "Material Description": "material",
    "Block Name": "block",
    "Contractor Name": "contractor",
    "Work Description": "work_description",   # optional, may be blank
    "Received Quantity": "quantity",
    "Unit": "unit",
    "Remarks": "remarks",
}


def fetch_sheet(sheet_id: str, gid: str = "0") -> pd.DataFrame:
    url = f"https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=csv&gid={gid}"
    return pd.read_csv(url)


def load_material(df: pd.DataFrame, source_label: str):
    df.columns = [c.strip() for c in df.columns]
    df = df.rename(columns=COLUMN_MAP)

    missing = set(COLUMN_MAP.values()) - set(df.columns) - {"work_description"}
    if missing:
        raise ValueError(f"Sheet is missing expected columns: {missing}")
    if "work_description" not in df.columns:
        df["work_description"] = None

    conn = get_conn()
    inserted, skipped = 0, 0

    for _, row in df.iterrows():
        try:
            if pd.isna(row["site"]) or pd.isna(row["date"]) or pd.isna(row["material"]):
                skipped += 1
                continue

            site_id = get_or_create_site(conn, str(row["site"]))
            date_id = get_or_create_date(conn, row["date"])

            unit = str(row["unit"]).strip() if not pd.isna(row.get("unit")) else ""
            material_id = get_or_create_material(conn, str(row["material"]), unit)

            block_id = None
            if not pd.isna(row.get("block")) and str(row.get("block")).strip():
                block_id = get_or_create_block(conn, site_id, str(row["block"]))

            contractor_id = None
            if not pd.isna(row.get("contractor")) and str(row.get("contractor")).strip():
                contractor_id = get_or_create_contractor(conn, str(row["contractor"]))

            # Work description is optional — some site engineers don't know it.
            # Leave activity_id NULL when blank rather than guessing.
            activity_id = None
            if not pd.isna(row.get("work_description")) and str(row.get("work_description")).strip():
                activity_id = get_or_create_activity_from_description(conn, str(row["work_description"]))

            qty = None if pd.isna(row.get("quantity")) else float(row.get("quantity"))

            cur = conn.execute(
                """INSERT OR IGNORE INTO fact_material
                   (site_id, date_id, block_id, contractor_id, activity_id, material_id,
                    received_quantity, remarks, source_file)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    site_id, date_id, block_id, contractor_id, activity_id, material_id,
                    qty,
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
    load_material(df, source_label)


if __name__ == "__main__":
    main()