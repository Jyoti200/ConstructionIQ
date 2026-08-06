import sqlite3
import datetime as dt
import re

from rapidfuzz import fuzz
import jellyfish


DB_PATH = "project.db"

# Tunable thresholds (0-100 scale for rapidfuzz token_sort_ratio)
FUZZY_THRESHOLD = 87          # accept purely on text similarity
FUZZY_PHONETIC_THRESHOLD = 72  # lower bar accepted IF phonetic keys also agree


def slugify(text: str, maxlen: int = 60) -> str:
    """'Foundation Excavation - Block A' -> 'foundation-excavation-block-a'"""
    s = text.strip().lower()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    s = s.strip("-")
    return s[:maxlen] or "unspecified"


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn


# -------------------------------------------------------------------
# generic text normalization + fuzzy matching helpers
# -------------------------------------------------------------------
def normalize_text(text) -> str:
    """Lowercase, strip punctuation-ish noise, collapse whitespace."""
    if text is None:
        return ""
    s = str(text).strip().lower()
    s = re.sub(r"[^\w\s]", " ", s)   # punctuation -> space (not deleted, so
                                      # "R.K.Sharma" -> "r k sharma", not "rksharma")
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _strip_common_suffixes(s: str) -> str:
    """Remove filler words that shouldn't drive a match (contractor-style suffixes)."""
    s = re.sub(
        r"\b(construction|constructions|const|cons|co|company|cont|contractor|"
        r"pvt|private|ltd|ji)\b",
        "",
        s,
    )
    return re.sub(r"\s+", " ", s).strip()


def _phonetic_key(s: str) -> str:
    tokens = [t for t in s.split() if t]
    return " ".join(jellyfish.metaphone(t) for t in tokens)


def _fuzzy_best_match(candidate_norm: str, rows, threshold=FUZZY_THRESHOLD,
                       phonetic_threshold=FUZZY_PHONETIC_THRESHOLD):
    """
    rows: iterable of (id, existing_norm_name) already normalized the
    same way as candidate_norm.
    Returns the id of the best match, or None.
    """
    if not candidate_norm:
        return None

    cand_phon = _phonetic_key(candidate_norm)
    cand_compact = candidate_norm.replace(" ", "")
    COMPACT_THRESHOLD = 90  # comparing whitespace-free strings needs a higher bar

    for row_id, existing_norm in rows:
        if not existing_norm:
            continue

        score = fuzz.token_sort_ratio(candidate_norm, existing_norm)
        if score >= threshold:
            return row_id  # strong text match, done

        # weaker text match but phonetically identical -> still accept
        if score >= phonetic_threshold and _phonetic_key(existing_norm) == cand_phon and cand_phon:
            return row_id

        # handles spacing-only differences: "Govind Garh" vs "govindgarh"
        compact_score = fuzz.ratio(cand_compact, existing_norm.replace(" ", ""))
        if compact_score >= COMPACT_THRESHOLD:
            return row_id

    return None


# -------------------------------------------------------------------
# dim_date  (formal key -> never fuzzy matched)
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
    for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y", "%Y/%m/%d", "%d-%b-%Y",
                "%d %b %Y", "%d/%m/%y", "%m/%d/%y", "%m/%d/%Y"):
        try:
            return dt.datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    raise ValueError(f"Unrecognized date format: {s!r}")


# -------------------------------------------------------------------
# dim_site
# -------------------------------------------------------------------
def get_or_create_site(conn, site_name: str, site_code: str = None) -> int:
    raw = site_name.strip()
    norm = normalize_text(raw)

    row = conn.execute(
        "SELECT site_id FROM dim_site WHERE LOWER(site_name) = ?", (norm,)
    ).fetchone()
    if row:
        return row[0]

    existing = conn.execute("SELECT site_id, site_name FROM dim_site").fetchall()
    existing_norm = [(sid, normalize_text(name)) for sid, name in existing]
    match_id = _fuzzy_best_match(norm, existing_norm)
    if match_id:
        return match_id

    conn.execute(
        "INSERT INTO dim_site (site_name, site_code) VALUES (?, ?)",
        (raw, site_code),
    )
    return conn.execute(
        "SELECT site_id FROM dim_site WHERE site_name = ?", (raw,)
    ).fetchone()[0]


# -------------------------------------------------------------------
# dim_contractor + contractor_alias
# -------------------------------------------------------------------
def get_or_create_contractor(conn, raw_name: str) -> int:
    """
    Resolves a raw contractor string (as it appears in a source file)
    to a canonical contractor_id via the alias bridge.

    - If this exact normalized string was seen before as an alias ->
      reuse its mapping (fast path).
    - Else, fuzzy-match it against existing canonical contractor
      names. If found -> add as a new alias of that contractor.
    - Else -> create a brand-new canonical contractor (keeping the
      ORIGINAL raw name, not the normalized one, so display text
      doesn't get mangled) + alias pointing to itself.
    """
    original = str(raw_name).strip()
    norm = _strip_common_suffixes(normalize_text(original))

    row = conn.execute(
        "SELECT contractor_id FROM contractor_alias WHERE alias_name = ?",
        (norm,),
    ).fetchone()
    if row:
        return row[0]

    existing = conn.execute(
        "SELECT contractor_id, contractor_name FROM dim_contractor"
    ).fetchall()
    existing_norm = [
        (cid, _strip_common_suffixes(normalize_text(name))) for cid, name in existing
    ]
    match_id = _fuzzy_best_match(norm, existing_norm)
    if match_id:
        conn.execute(
            "INSERT OR IGNORE INTO contractor_alias (alias_name, contractor_id) VALUES (?, ?)",
            (norm, match_id),
        )
        return match_id

    # No match at all -> new canonical contractor, keep the ORIGINAL name for display
    conn.execute(
        "INSERT INTO dim_contractor (contractor_name) VALUES (?)", (original,)
    )
    contractor_id = conn.execute(
        "SELECT contractor_id FROM dim_contractor WHERE contractor_name = ?", (original,)
    ).fetchone()[0]
    conn.execute(
        "INSERT OR IGNORE INTO contractor_alias (alias_name, contractor_id) VALUES (?, ?)",
        (norm, contractor_id),
    )
    return contractor_id


# -------------------------------------------------------------------
# dim_activity
# -------------------------------------------------------------------
def get_or_create_activity(conn, wbs_code: str, activity_name: str) -> int:
    """
    Formal MS Project WBS codes are exact identifiers by design —
    NOT fuzzy matched. A code either matches or it doesn't.
    """
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
    have a free-text 'Work Description'). Free text -> fuzzy matched
    against OTHER synthetic (DPR-*) activities before creating a new
    one, so "Excavation - Foundation Block A" and "Excavation
    Foundation Block-A" collapse into a single activity instead of
    forking the fact table's grain.
    """
    description = description.strip()
    norm = normalize_text(description)

    existing = conn.execute(
        "SELECT activity_id, activity_name FROM dim_activity WHERE wbs_code LIKE 'DPR-%'"
    ).fetchall()
    existing_norm = [(aid, normalize_text(name)) for aid, name in existing]
    match_id = _fuzzy_best_match(norm, existing_norm)
    if match_id:
        return match_id

    wbs_code = f"DPR-{slugify(description)}"
    return get_or_create_activity(conn, wbs_code, description)


# -------------------------------------------------------------------
# dim_block
# -------------------------------------------------------------------
def get_or_create_block(conn, site_id: int, block_name: str) -> int:
    norm = normalize_text(block_name)

    row = conn.execute(
        "SELECT block_id FROM dim_block WHERE site_id = ? AND block_name = ?",
        (site_id, norm),
    ).fetchone()
    if row:
        return row[0]

    # fuzzy match, scoped to this site only (a block name can legitimately
    # repeat across different sites)
    existing = conn.execute(
        "SELECT block_id, block_name FROM dim_block WHERE site_id = ?", (site_id,)
    ).fetchall()
    match_id = _fuzzy_best_match(norm, existing)
    if match_id:
        return match_id

    conn.execute(
        "INSERT INTO dim_block (site_id, block_name) VALUES (?, ?)",
        (site_id, norm),
    )
    return conn.execute(
        "SELECT block_id FROM dim_block WHERE site_id = ? AND block_name = ?",
        (site_id, norm),
    ).fetchone()[0]


# -------------------------------------------------------------------
# dim_material
# -------------------------------------------------------------------
def get_or_create_material(conn, material_name: str, unit: str) -> int:
    original = material_name.strip()
    norm = normalize_text(original)

    row = conn.execute(
        "SELECT material_id FROM dim_material WHERE LOWER(material_name) = ?", (norm,)
    ).fetchone()
    if row:
        return row[0]

    existing = conn.execute(
        "SELECT material_id, material_name FROM dim_material"
    ).fetchall()
    existing_norm = [(mid, normalize_text(name)) for mid, name in existing]
    match_id = _fuzzy_best_match(norm, existing_norm)
    if match_id:
        return match_id

    conn.execute(
        "INSERT INTO dim_material (material_name, unit) VALUES (?, ?)",
        (original, unit.strip()),
    )
    return conn.execute(
        "SELECT material_id FROM dim_material WHERE material_name = ?",
        (original,),
    ).fetchone()[0]
