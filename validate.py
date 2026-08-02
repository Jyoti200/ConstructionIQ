"""
validate.py
-----------
Run this after loading DPR/Material to catch data quality issues
before they hit Streamlit. Prints a report, doesn't fix anything
automatically (fixing silently would hide real problems from you).

Usage:
    python validate.py
"""

import sqlite3

DB_PATH = "project.db"


def run_checks():
    conn = sqlite3.connect(DB_PATH)
    issues_found = 0

    print("=" * 50)
    print("DATA QUALITY REPORT")
    print("=" * 50)

    # 1. Row counts — sanity check nothing is empty
    print("\n[1] Row counts:")
    for table in ["dim_site", "dim_block", "dim_contractor", "dim_material",
                  "fact_dpr_progress", "fact_material"]:
        n = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        print(f"  {table}: {n}")
        if n == 0:
            print(f"  ⚠ {table} is empty — did the loader actually run?")
            issues_found += 1

    # 2. Possible duplicate contractors that normalization missed
    #    (same name, different casing/spacing that slipped through)
    print("\n[2] Possible duplicate contractors:")
    contractors = conn.execute("SELECT contractor_name FROM dim_contractor").fetchall()
    names = [c[0] for c in contractors]
    seen = {}
    for name in names:
        key = name.lower().strip()
        seen.setdefault(key, []).append(name)
    dupes = {k: v for k, v in seen.items() if len(v) > 1}
    if dupes:
        for k, v in dupes.items():
            print(f"  ⚠ Possible duplicates: {v}")
            issues_found += 1
    else:
        print("  none found")

    # 3. Negative or zero material quantities (likely data entry errors)
    print("\n[3] Suspicious material quantities:")
    bad_qty = conn.execute(
        "SELECT material_txn_id, received_quantity FROM fact_material WHERE received_quantity <= 0"
    ).fetchall()
    if bad_qty:
        for row in bad_qty:
            print(f"  ⚠ material_txn_id={row[0]} has quantity={row[1]}")
            issues_found += 1
    else:
        print("  none found")

    # 4. DPR rows with all labour counts zero (likely blank/junk rows)
    print("\n[4] DPR rows with zero labour across the board:")
    zero_labour = conn.execute(
        """SELECT dpr_id FROM fact_dpr_progress
           WHERE COALESCE(skilled_count,0) = 0
             AND COALESCE(helper_count,0) = 0
             AND COALESCE(coolie_count,0) = 0"""
    ).fetchall()
    if zero_labour:
        print(f"  ⚠ {len(zero_labour)} rows with zero labour everywhere: {[r[0] for r in zero_labour]}")
        issues_found += 1
    else:
        print("  none found")

    # 5. Blocks not linked to any site (shouldn't happen due to FK, but confirm)
    print("\n[5] Orphan blocks (no valid site):")
    orphan_blocks = conn.execute(
        """SELECT b.block_id, b.block_name FROM dim_block b
           LEFT JOIN dim_site s ON b.site_id = s.site_id
           WHERE s.site_id IS NULL"""
    ).fetchall()
    if orphan_blocks:
        for row in orphan_blocks:
            print(f"  ⚠ block_id={row[0]} ({row[1]}) has no matching site")
            issues_found += 1
    else:
        print("  none found")

    # 6. Dates far outside a sane range (typo years like 2016 or 2099)
    print("\n[6] Suspicious dates:")
    bad_dates = conn.execute(
        "SELECT date FROM dim_date WHERE year < 2024 OR year > 2027"
    ).fetchall()
    if bad_dates:
        for row in bad_dates:
            print(f"  ⚠ suspicious date: {row[0]}")
            issues_found += 1
    else:
        print("  none found")

    conn.close()

    print("\n" + "=" * 50)
    if issues_found == 0:
        print("All checks passed. Data looks clean.")
    else:
        print(f"{issues_found} issue(s) flagged above — review before building the dashboard.")
    print("=" * 50)


if __name__ == "__main__":
    run_checks()