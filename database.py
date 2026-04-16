"""SQLite persistence layer — pure stdlib, no Flask imports."""
import sqlite3, re
from datetime import datetime, date
from pathlib import Path

DB_PATH = Path(__file__).parent / "bizfinder.db"

# ── Schema ─────────────────────────────────────────────────────────────────────

SCHEMA = """
CREATE TABLE IF NOT EXISTS leads (
    place_id            TEXT PRIMARY KEY,
    name                TEXT NOT NULL,
    address             TEXT,
    phone               TEXT,
    city                TEXT,
    state               TEXT,
    google_rating       REAL,
    google_reviews      INTEGER,
    google_maps_url     TEXT,
    category            TEXT,
    category_color      TEXT,
    presence            TEXT DEFAULT 'none',
    social_url          TEXT,
    email               TEXT,
    email_source        TEXT,
    email_mx_valid      INTEGER DEFAULT -1,
    price_level         INTEGER,
    owner_responses     INTEGER DEFAULT 0,
    review_recency      TEXT,
    yelp_rating         REAL,
    yelp_reviews        INTEGER,
    yelp_url            TEXT,
    lead_score          INTEGER DEFAULT 0,
    status              TEXT,
    status_date         TEXT,
    notes               TEXT DEFAULT '',
    do_not_contact      INTEGER DEFAULT 0,
    created_at          TEXT DEFAULT (datetime('now')),
    updated_at          TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS dnc_list (
    place_id    TEXT PRIMARY KEY,
    name        TEXT,
    reason      TEXT,
    added_at    TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS search_history (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    city            TEXT,
    state           TEXT,
    category        TEXT,
    total           INTEGER,
    no_website      INTEGER,
    with_website    INTEGER,
    searched_at     TEXT DEFAULT (datetime('now'))
);
"""


def _conn() -> sqlite3.Connection:
    c = sqlite3.connect(str(DB_PATH))
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA journal_mode=WAL")
    return c


def init_db():
    with _conn() as c:
        c.executescript(SCHEMA)


# ── Leads ──────────────────────────────────────────────────────────────────────

def upsert_lead(lead: dict):
    """INSERT OR REPLACE, preserving existing status / notes / do_not_contact."""
    with _conn() as c:
        existing = c.execute(
            "SELECT status, status_date, notes, do_not_contact FROM leads WHERE place_id=?",
            (lead["place_id"],),
        ).fetchone()
        if existing:
            if not lead.get("status"):
                lead["status"]         = existing["status"]
                lead["status_date"]    = existing["status_date"]
            if lead.get("notes") is None:
                lead["notes"]          = existing["notes"] or ""
            if lead.get("do_not_contact") is None:
                lead["do_not_contact"] = existing["do_not_contact"]
        lead.setdefault("notes",           "")
        lead.setdefault("do_not_contact",  0)
        lead["updated_at"] = datetime.utcnow().isoformat(timespec="seconds")
        cols         = list(lead.keys())
        placeholders = ", ".join(["?"] * len(cols))
        col_names    = ", ".join(cols)
        c.execute(
            f"INSERT OR REPLACE INTO leads ({col_names}) VALUES ({placeholders})",
            [lead[k] for k in cols],
        )


def patch_lead(place_id: str, **kwargs):
    """Update specific fields. Sets status_date automatically when status changes."""
    if not kwargs:
        return
    if "status" in kwargs:
        kwargs["status_date"] = datetime.utcnow().isoformat(timespec="seconds")
    kwargs["updated_at"] = datetime.utcnow().isoformat(timespec="seconds")
    sets = ", ".join(f"{k}=?" for k in kwargs)
    vals = list(kwargs.values()) + [place_id]
    with _conn() as c:
        c.execute(f"UPDATE leads SET {sets} WHERE place_id=?", vals)


def _compute_overdue(row: dict) -> bool:
    if row.get("status") not in ("emailed", "followup", "replied"):
        return False
    sd = row.get("status_date")
    if not sd:
        return False
    try:
        return (date.today() - date.fromisoformat(sd[:10])).days >= 3
    except Exception:
        return False


def get_leads(city: str = None, state: str = None) -> list[dict]:
    """Return leads ordered by score desc, with computed overdue/days_ago."""
    q      = "SELECT * FROM leads WHERE do_not_contact=0"
    params = []
    if city:  q += " AND lower(city)=lower(?)";  params.append(city)
    if state: q += " AND lower(state)=lower(?)"; params.append(state)
    q += " ORDER BY lead_score DESC, google_reviews DESC"
    with _conn() as c:
        rows = c.execute(q, params).fetchall()
    today = date.today()
    out   = []
    for r in rows:
        d = dict(r)
        if d.get("status_date"):
            try:
                sd            = date.fromisoformat(d["status_date"][:10])
                d["days_ago"] = (today - sd).days
                d["overdue"]  = _compute_overdue(d)
            except Exception:
                d["days_ago"] = None
                d["overdue"]  = False
        else:
            d["days_ago"] = None
            d["overdue"]  = False
        out.append(d)
    return out


def get_lead(place_id: str) -> dict | None:
    with _conn() as c:
        r = c.execute("SELECT * FROM leads WHERE place_id=?", (place_id,)).fetchone()
    return dict(r) if r else None


# ── DNC ────────────────────────────────────────────────────────────────────────

def is_dnc(place_id: str) -> bool:
    with _conn() as c:
        r = c.execute("SELECT 1 FROM dnc_list WHERE place_id=?", (place_id,)).fetchone()
    return r is not None


def add_dnc(place_id: str, name: str, reason: str = ""):
    now = datetime.utcnow().isoformat(timespec="seconds")
    with _conn() as c:
        c.execute(
            "INSERT OR REPLACE INTO dnc_list (place_id, name, reason) VALUES (?,?,?)",
            (place_id, name, reason),
        )
        c.execute(
            "UPDATE leads SET do_not_contact=1, updated_at=? WHERE place_id=?",
            (now, place_id),
        )


def remove_dnc(place_id: str):
    now = datetime.utcnow().isoformat(timespec="seconds")
    with _conn() as c:
        c.execute("DELETE FROM dnc_list WHERE place_id=?", (place_id,))
        c.execute(
            "UPDATE leads SET do_not_contact=0, updated_at=? WHERE place_id=?",
            (now, place_id),
        )


def get_dnc_list() -> list[dict]:
    with _conn() as c:
        rows = c.execute("SELECT * FROM dnc_list ORDER BY added_at DESC").fetchall()
    return [dict(r) for r in rows]


def get_dnc_ids() -> set:
    with _conn() as c:
        rows = c.execute("SELECT place_id FROM dnc_list").fetchall()
    return {r[0] for r in rows}


def get_known_ids(city: str = None, state: str = None) -> set:
    """All place_ids previously saved (for cross-search Previously Seen badge)."""
    q      = "SELECT place_id FROM leads"
    where, params = [], []
    if city:  where.append("lower(city)=lower(?)");  params.append(city)
    if state: where.append("lower(state)=lower(?)"); params.append(state)
    if where: q += " WHERE " + " AND ".join(where)
    with _conn() as c:
        rows = c.execute(q, params).fetchall()
    return {r[0] for r in rows}


# ── Search history / saturation ────────────────────────────────────────────────

def record_search_history(city, state, category, total, no_website, with_website):
    with _conn() as c:
        c.execute(
            "INSERT INTO search_history "
            "(city,state,category,total,no_website,with_website) VALUES (?,?,?,?,?,?)",
            (city, state, category, total, no_website, with_website),
        )


def get_saturation(city: str = None, state: str = None) -> list[dict]:
    q = """
        SELECT category,
               MAX(searched_at)  AS last_searched,
               SUM(total)        AS total,
               SUM(no_website)   AS no_website,
               SUM(with_website) AS with_website,
               ROUND(100.0 * SUM(no_website) / NULLIF(SUM(total),0), 1) AS gap_pct
        FROM search_history
    """
    where, params = [], []
    if city:  where.append("lower(city)=lower(?)");  params.append(city)
    if state: where.append("lower(state)=lower(?)"); params.append(state)
    if where: q += " WHERE " + " AND ".join(where)
    q += " GROUP BY category ORDER BY gap_pct DESC"
    with _conn() as c:
        rows = c.execute(q, params).fetchall()
    return [dict(r) for r in rows]


# ── Dashboard ──────────────────────────────────────────────────────────────────

def get_dashboard(city: str = None, state: str = None, category: str = None) -> dict:
    q      = "SELECT * FROM leads WHERE do_not_contact=0"
    params = []
    if city:     q += " AND lower(city)=lower(?)";     params.append(city)
    if state:    q += " AND lower(state)=lower(?)";    params.append(state)
    if category: q += " AND lower(category)=lower(?)"; params.append(category)
    with _conn() as c:
        rows = [dict(r) for r in c.execute(q, params).fetchall()]

    total     = len(rows)
    has_email = sum(1 for r in rows if r.get("email"))
    statuses  = {s: sum(1 for r in rows if r.get("status") == s)
                 for s in ("emailed", "followup", "replied", "closed", "skip")}
    overdue   = sum(1 for r in rows if _compute_overdue(r))
    avg_score = (round(sum(r.get("lead_score") or 0 for r in rows) / total, 1)
                 if total else 0)

    top_cats: dict[str, int] = {}
    for r in rows:
        k = r.get("category", "?")
        top_cats[k] = top_cats.get(k, 0) + 1

    return {
        "total":     total,
        "has_email": has_email,
        "statuses":  statuses,
        "overdue":   overdue,
        "avg_score": avg_score,
        "top_cats":  sorted(top_cats.items(), key=lambda x: -x[1])[:5],
    }
