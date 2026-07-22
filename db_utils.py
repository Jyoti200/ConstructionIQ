"""
db_utils.py
-----------
Shared helper functions for the loader scripts. Every loader does the
same "look up or insert a dimension row, get back its ID" dance —
that logic lives here once instead of being copy-pasted four times.

Not meant to be run directly.
"""

import sqlite3
import datetime as dt
import re


def slugify(text: str, maxlen: int = 60) -> str:
    """'Foundation Excavation - Block A' -> 'foundation-excavation-block-a'"""
    s = text.strip().lower()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    s = s.strip("-")
    return s[:maxlen] or "unspecified"

DB_PATH = "project.db"


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn


# -------------------------------------------------------------------
# dim_date
# -------------------------------------------------------------------
def get_or_create_date(conn, date_value) -> int:
    """
    date_value can be a datetime.date/datetime, a pandas Timestamp,
    or a 'YYYY-MM-DD' / 'DD-MM-YYYY' string.
    Returns date_id.
    """
    if isinstance(date_value, str):
        date_value = _parse_date_string(date_value)
    if hasattr(date_value, "date") and not isinstance(date_value, dt.date):
        date_value = date_value.date()  # pandas Timestamp -> date

    date_str = date_value.strftime("%Y-%m-%d")

    row = conn.execute(
        "SELECT date_id FROM dim_date WHERE date = ?", (date_str,)
    ).fetchone()
    if row:
        return row[0]

    conn.execute(
        """INSERT INTO dim_date
           (date, year, quarter, month, month_name, day, day_name, week_of_year)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            date_str,
            date_value.year,
            (date_value.month - 1) // 3 + 1,
            date_value.month,
            date_value.strftime("%B"),
            date_value.day,
            date_value.strftime("%A"),
            date_value.isocalendar()[1],
        ),
    )
    return conn.execute(
        "SELECT date_id FROM dim_date WHERE date = ?", (date_str,)
    ).fetchone()[0]


def _parse_date_string(s: str) -> dt.date:
    s = s.strip()
    for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y", "%Y/%m/%d", "%d-%b-%Y", "%d %b %Y", "%d/%m/%y", "%m/%d/%y"):
        try:
            return dt.datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    raise ValueError(f"Unrecognized date format: {s!r}")


# -------------------------------------------------------------------
# dim_site
# -------------------------------------------------------------------
def get_or_create_site(conn, site_name: str, site_code: str = None) -> int:
    site_name = site_name.strip()
    row = conn.execute(
        "SELECT site_id FROM dim_site WHERE site_name = ?", (site_name,)
    ).fetchone()
    if row:
        return row[0]

    conn.execute(
        "INSERT INTO dim_site (site_name, site_code) VALUES (?, ?)",
        (site_name, site_code),
    )
    return conn.execute(
        "SELECT site_id FROM dim_site WHERE site_name = ?", (site_name,)
    ).fetchone()[0]


# -------------------------------------------------------------------
# dim_contractor + contractor_alias
# -------------------------------------------------------------------
import re

def _normalize_alias(raw_name: str) -> str:
    """Normalize contractor names for matching only."""

    if raw_name is None:
        return ""

    s = str(raw_name).strip().lower()

    # Remove punctuation
    s = re.sub(r"[^\w\s]", "", s)

    # Remove common company suffixes
    s = re.sub(
        r"\b(pvt|private|ltd|limited|construction|constructions|const|co)\b",
        "",
        s,
    )

    # Collapse multiple spaces
    s = re.sub(r"\s+", " ", s).strip()

    return s


def get_or_create_contractor(conn, raw_name: str) -> int:
    """
    Resolves a raw contractor string (as it appears in a source file)
    to a canonical contractor_id via the alias bridge.

    - If this exact raw string was seen before -> reuse its mapping.
    - Else, try to fuzzy-match it to an existing canonical contractor
      (normalized comparison). If found -> add as a new alias of that
      contractor.
    - Else -> create a brand-new canonical contractor + alias pointing
      to itself.
    """
    raw_name = _normalize_alias(raw_name)

    row = conn.execute(
        "SELECT contractor_id FROM contractor_alias WHERE alias_name = ?",
        (raw_name,),
    ).fetchone()
    if row:
        return row[0]

    norm_target = _normalize_alias(raw_name)
    existing = conn.execute("SELECT contractor_id, contractor_name FROM dim_contractor").fetchall()
    for contractor_id, canonical_name in existing:
        if _normalize_alias(canonical_name) == norm_target:
            conn.execute(
                "INSERT OR IGNORE INTO contractor_alias (alias_name, contractor_id) VALUES (?, ?)",
                (raw_name, contractor_id),
            )
            return contractor_id

    # No match at all -> new canonical contractor
    conn.execute(
        "INSERT INTO dim_contractor (contractor_name) VALUES (?)", (raw_name,)
    )
    contractor_id = conn.execute(
        "SELECT contractor_id FROM dim_contractor WHERE contractor_name = ?", (raw_name,)
    ).fetchone()[0]
    conn.execute(
        "INSERT OR IGNORE INTO contractor_alias (alias_name, contractor_id) VALUES (?, ?)",
        (raw_name, contractor_id),
    )
    return contractor_id


# -------------------------------------------------------------------
# dim_activity
# -------------------------------------------------------------------
def get_or_create_activity(conn, wbs_code: str, activity_name: str) -> int:
    wbs_code = str(wbs_code).strip()
    row = conn.execute(
        "SELECT activity_id FROM dim_activity WHERE wbs_code = ?", (wbs_code,)
    ).fetchone()
    if row:
        return row[0]

    conn.execute(
        "INSERT INTO dim_activity (wbs_code, activity_name) VALUES (?, ?)",
        (wbs_code, activity_name.strip()),
    )
    return conn.execute(
        "SELECT activity_id FROM dim_activity WHERE wbs_code = ?", (wbs_code,)
    ).fetchone()[0]


def get_or_create_activity_from_description(conn, description: str) -> int:
    """
    For sources with no formal WBS code (e.g. DPR sheets, which only
    have a free-text 'Work Description'). Builds a synthetic wbs_code
    from the description text so identical descriptions reuse the same
    activity_id, and it can't collide with a real MS Project WBS code
    (all synthetic codes are prefixed 'DPR-').
    """
    description = description.strip()
    wbs_code = f"DPR-{slugify(description)}"
    return get_or_create_activity(conn, wbs_code, description)


# -------------------------------------------------------------------
# dim_block  (site sub-location, e.g. "Block A", "Unit 2")
# -------------------------------------------------------------------
def normalize_text(text):
    if text is None:
        return ""

    text = str(text).lower().strip()
    text = re.sub(r"\s+", " ", text)
    return text


def get_or_create_block(conn, site_id: int, block_name: str) -> int:
    block_name = normalize_text(block_name)
    row = conn.execute(
        "SELECT block_id FROM dim_block WHERE site_id = ? AND block_name = ?",
        (site_id, block_name),
    ).fetchone()
    if row:
        return row[0]

    conn.execute(
        "INSERT INTO dim_block (site_id, block_name) VALUES (?, ?)",
        (site_id, block_name),
    )
    return conn.execute(
        "SELECT block_id FROM dim_block WHERE site_id = ? AND block_name = ?",
        (site_id, block_name),
    ).fetchone()[0]


# -------------------------------------------------------------------
# dim_material
# -------------------------------------------------------------------
def get_or_create_material(conn, material_name: str, unit: str) -> int:
    material_name = material_name.strip()
    row = conn.execute(
        "SELECT material_id FROM dim_material WHERE material_name = ?",
        (material_name,),
    ).fetchone()
    if row:
        return row[0]

    conn.execute(
        "INSERT INTO dim_material (material_name, unit) VALUES (?, ?)",
        (material_name, unit.strip()),
    )
    return conn.execute(
        "SELECT material_id FROM dim_material WHERE material_name = ?",
        (material_name,),
    ).fetchone()[0]