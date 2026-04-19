import os, re, json, time, socket, math, sys
import requests
import dns.resolver
from html import unescape
from urllib.parse import quote_plus, urlparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from flask import Flask, render_template, request, Response, stream_with_context, jsonify
from dotenv import load_dotenv
import scoring
import database as db

# ── Frozen-exe path resolution (PyInstaller) ──────────────────────────────────
_FROZEN   = getattr(sys, 'frozen', False)
_BASE_DIR = sys._MEIPASS if _FROZEN else os.path.dirname(os.path.abspath(__file__))
_EXE_DIR  = os.path.dirname(sys.executable) if _FROZEN else _BASE_DIR

load_dotenv(dotenv_path=os.path.join(_EXE_DIR, '.env'))
app = Flask(__name__, template_folder=os.path.join(_BASE_DIR, 'templates'))
db.init_db()

GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY", "")
YELP_API_KEY   = os.getenv("YELP_API_KEY", "")

# (id, search_query, label, color)
CATEGORIES = [
    ("restaurant",   "restaurant",            "Restaurants",       "#FF9F0A"),
    ("bar",          "bar pub",               "Bars & Pubs",       "#0A84FF"),
    ("night_club",   "night club lounge",     "Night Clubs",       "#BF5AF2"),
    ("barber_shop",  "barber shop",           "Barber Shops",      "#FF6B35"),
    ("beauty_salon", "beauty salon",          "Beauty Salons",     "#FF375F"),
    ("hair_care",    "hair salon",            "Hair Salons",       "#30D158"),
    ("spa",          "day spa",               "Spas",              "#5AC8FA"),
    ("nail_salon",   "nail salon",            "Nail Salons",       "#FF2D55"),
    ("massage",      "massage therapy",       "Massage",           "#64D2FF"),
    ("tattoo",       "tattoo shop",           "Tattoo Shops",      "#AC8E68"),
    ("gym",          "gym fitness center",    "Gyms & Fitness",    "#34C759"),
    ("florist",      "florist flower shop",   "Florists",          "#FFD60A"),
    ("pet_groomer",  "pet groomer",           "Pet Groomers",      "#30D158"),
    ("photographer", "photographer studio",   "Photographers",     "#5E5CE6"),
    ("cleaning",     "cleaning service",      "Cleaning Services", "#32ADE6"),
    ("landscaping",  "landscaping lawn care", "Landscaping",       "#4CD964"),
    ("auto_repair",  "auto repair shop",      "Auto Repair",       "#FF9500"),
    ("alterations",  "alterations tailor",    "Alterations",       "#C969E0"),
    ("tutoring",     "tutoring center",       "Tutoring",          "#5AC8FA"),
    ("catering",     "catering company",      "Catering",          "#FF6B35"),
    ("event_planner","event planner venue",   "Event Planners",    "#FF6B6B"),
    ("daycare",      "daycare childcare",     "Daycare",           "#4ECDC4"),
    ("accountant",   "accountant bookkeeper", "Accountants",       "#45B7D1"),
    ("insurance",    "insurance agent",       "Insurance Agents",  "#96CEB4"),
]

CAT_MAP = {t: (q, l, c) for t, q, l, c in CATEGORIES}

SOCIAL_DOMAINS = {
    "facebook.com", "fb.com", "instagram.com", "twitter.com", "x.com",
    "tiktok.com", "linktr.ee", "linktree.com", "youtube.com", "snapchat.com",
    "threads.net",
}

# ─── Utilities ────────────────────────────────────────────────────────────────

def _extract_lat_lng(url: str):
    """Return (lat, lng) floats from a Google Maps URL, or (None, None)."""
    if not url:
        return None, None
    m = re.search(r'/@(-?\d+\.\d+),(-?\d+\.\d+)', url)
    if m:
        return float(m.group(1)), float(m.group(2))
    return None, None


# ─── Web presence ─────────────────────────────────────────────────────────────

def web_presence(url: str) -> str:
    """'none' | 'social' | 'website'"""
    if not url:
        return "none"
    try:
        domain = urlparse(url).netloc.lower().removeprefix("www.")
        for sd in SOCIAL_DOMAINS:
            if domain == sd or domain.endswith("." + sd):
                return "social"
        return "website"
    except Exception:
        return "none"


# ─── Email discovery ──────────────────────────────────────────────────────────

EMAIL_RE = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")

_SKIP_DOMAINS = {
    "yelp.com", "google.com", "facebook.com", "instagram.com", "twitter.com",
    "x.com", "youtube.com", "tiktok.com", "pinterest.com", "linkedin.com",
    "duckduckgo.com", "bing.com", "w3.org", "schema.org", "example.com",
    "sentry.io", "cloudflare.com", "wixsite.com", "squarespace.com",
    "wordpress.com", "shopify.com", "godaddy.com",
    # gmail/yahoo/hotmail/outlook intentionally NOT here —
    # small businesses commonly use free email for professional contact.
}

_SKIP_PREFIXES = {
    "noreply", "no-reply", "donotreply", "do-not-reply", "privacy",
    "legal", "postmaster", "webmaster", "bounce", "mailer-daemon", "abuse",
}

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}


def _extract_emails(raw: str) -> list[str]:
    text = unescape(raw)
    text = re.sub(r"\s*\[at\]\s*",  "@", text, flags=re.I)
    text = re.sub(r"\s*\(at\)\s*",  "@", text, flags=re.I)
    text = re.sub(r"\s*\[dot\]\s*", ".", text, flags=re.I)
    text = re.sub(r"\s*\(dot\)\s*", ".", text, flags=re.I)
    seen, out = set(), []
    for em in EMAIL_RE.findall(text):
        em = em.lower().rstrip(".")
        if em in seen:
            continue
        seen.add(em)
        domain = em.split("@")[1]
        prefix = em.split("@")[0]
        if domain in _SKIP_DOMAINS:
            continue
        if any(prefix.startswith(p) for p in _SKIP_PREFIXES):
            continue
        out.append(em)
    return out


def _fetch(url: str) -> str:
    try:
        return requests.get(url, headers=_HEADERS, timeout=8).text
    except Exception:
        return ""


_THIRD_PARTY_DOMAINS = {
    # Booking / POS / scheduling platforms
    "squareup.com", "toasttab.com", "opentable.com", "resy.com",
    "mindbodyonline.com", "vagaro.com", "booksy.com", "acuityscheduling.com",
    "appointy.com", "fresha.com", "styleseat.com",
    # Marketing / hosting
    "constantcontact.com", "mailchimp.com", "wix.com", "squarespace.com",
    "godaddy.com", "shopify.com", "weebly.com",
    # Misc platforms often scraped from business pages
    "doordash.com", "grubhub.com", "ubereats.com", "seamless.com",
}


def _score_email(email: str, name: str) -> int:
    """Score how likely this email belongs to the business (higher = better)."""
    domain = email.split("@")[1].lower()
    if domain in _THIRD_PARTY_DOMAINS:
        return -999          # discard platform emails entirely
    name_tokens = set(re.sub(r"[^a-z0-9]", " ", name.lower()).split()) - {"the", "a", "of", "and"}
    domain_clean = re.sub(r"\.(com|net|org|biz|co|us|info)$", "", domain)
    domain_tokens = set(re.sub(r"[^a-z0-9]", " ", domain_clean).split())
    overlap = len(name_tokens & domain_tokens)
    score   = overlap * 20          # 20 pts per matching word
    if domain.endswith((".com", ".net", ".org", ".biz")):
        score += 5                  # professional TLD
    return score


def _src_bing(name, city, state):
    html = _fetch(f"https://www.bing.com/search?q={quote_plus(chr(34)+name+chr(34)+' '+city+' '+state+' email contact')}")
    return [("Bing", em) for em in _extract_emails(html)]


def _src_yellowpages(name, city, state):
    html = _fetch(
        f"https://www.yellowpages.com/search"
        f"?search_terms={quote_plus(name)}&geo_location_terms={quote_plus(city+', '+state)}"
    )
    return [("YellowPages", em) for em in _extract_emails(html)]


def _src_manta(name, city, state):
    html = _fetch(f"https://www.manta.com/search?search_source=nav&search[text]={quote_plus(name+' '+city+' '+state)}")
    return [("Manta", em) for em in _extract_emails(html)]


def find_email(name: str, city: str, state: str) -> tuple:
    """
    Queries all three sources in parallel, scores every candidate by domain
    relevance to the business name, and returns the best (email, source) or
    (None, None).
    """
    candidates: list[tuple[int, str, str]] = []  # (score, email, source)

    with ThreadPoolExecutor(max_workers=3) as ex:
        futs = {
            ex.submit(_src_bing,        name, city, state): None,
            ex.submit(_src_yellowpages, name, city, state): None,
            ex.submit(_src_manta,       name, city, state): None,
        }
        for fut in as_completed(futs):
            try:
                for src, em in (fut.result() or []):
                    score = _score_email(em, name)
                    if score > -999:
                        candidates.append((score, em, src))
            except Exception:
                pass

    if not candidates:
        return None, None

    candidates.sort(reverse=True)       # highest score first
    _, best_email, best_src = candidates[0]
    return best_email, best_src


# ─── MX / domain validation ───────────────────────────────────────────────────

def _mx_check(email: str) -> bool:
    """True if the email domain has at least one MX record."""
    try:
        domain = email.split("@")[1]
        dns.resolver.resolve(domain, "MX")
        return True
    except Exception:
        return False


# ─── Review parsing ───────────────────────────────────────────────────────────

def _parse_review_recency(reviews: list) -> str | None:
    """Classify recency of most recent review: 'active' | 'moderate' | 'quiet'."""
    if not reviews:
        return None
    desc = (reviews[0].get("relative_time_description") or "").lower()
    if not desc:
        return None
    if "hour" in desc or "day" in desc or "week" in desc:
        return "active"
    if "month" in desc:
        m = re.search(r"(\d+)\s+month", desc)
        n = int(m.group(1)) if m else 1  # "a month ago" → 1
        if n <= 2:  return "active"
        if n <= 6:  return "moderate"
        return "quiet"
    if "year" in desc:
        return "quiet"
    return "moderate"


def _parse_owner_responses(reviews: list) -> int:
    """Count how many reviews have an owner reply."""
    return sum(1 for r in reviews if r.get("owner_reply"))


def _extract_review_snippets(reviews: list) -> list:
    """Return up to 5 best review texts (4-5 stars, >= 40 chars), longest first."""
    if not reviews:
        return []
    good = [r for r in reviews
            if r.get("rating", 0) >= 4 and len(r.get("text", "")) >= 40]
    good.sort(key=lambda r: (r.get("rating", 0), len(r.get("text", ""))), reverse=True)
    return [r["text"][:600] for r in good[:5]]


def _format_hours(details: dict) -> str:
    """Return weekday hours as a newline-joined string, or empty string."""
    oh = details.get("opening_hours", {})
    if not oh:
        return ""
    texts = oh.get("weekday_text", [])
    return "\n".join(texts) if texts else ""


# ─── Google Places ────────────────────────────────────────────────────────────

def google_text_search(query: str, location: str, page_token: str = None) -> dict:
    params = {"query": f"{query} in {location}", "key": GOOGLE_API_KEY}
    if page_token:
        params["pagetoken"] = page_token
    try:
        return requests.get(
            "https://maps.googleapis.com/maps/api/place/textsearch/json",
            params=params, timeout=12
        ).json()
    except Exception as e:
        return {"results": [], "error": str(e)}


def google_place_details(place_id: str) -> dict:
    try:
        return requests.get(
            "https://maps.googleapis.com/maps/api/place/details/json",
            params={
                "place_id": place_id,
                "fields": (
                    "name,rating,user_ratings_total,website,"
                    "formatted_address,formatted_phone_number,business_status,url,"
                    "price_level,reviews,opening_hours"
                ),
                "key": GOOGLE_API_KEY,
            },
            timeout=12
        ).json().get("result", {})
    except Exception:
        return {}


# ─── Grid Search ──────────────────────────────────────────────────────────────

def geocode_city(city: str, state: str) -> dict | None:
    """Returns {lat, lng, ne:{lat,lng}, sw:{lat,lng}} or None on failure."""
    try:
        data = requests.get(
            "https://maps.googleapis.com/maps/api/geocode/json",
            params={"address": f"{city}, {state}", "key": GOOGLE_API_KEY},
            timeout=8,
        ).json()
        res = data.get("results", [])
        if not res:
            return None
        loc      = res[0]["geometry"]["location"]
        viewport = res[0]["geometry"]["viewport"]
        return {
            "lat": loc["lat"],
            "lng": loc["lng"],
            "ne":  viewport["northeast"],
            "sw":  viewport["southwest"],
        }
    except Exception:
        return None


def make_grid(geo: dict, divisions: int = 3) -> list[tuple[float, float]]:
    """Return divisions×divisions centre points covering the city bounding box."""
    ne, sw   = geo["ne"], geo["sw"]
    lat_step = (ne["lat"] - sw["lat"]) / divisions
    lng_step = (ne["lng"] - sw["lng"]) / divisions
    return [
        (sw["lat"] + lat_step * (i + 0.5),
         sw["lng"] + lng_step * (j + 0.5))
        for i in range(divisions)
        for j in range(divisions)
    ]


def _grid_radius_m(geo: dict, divisions: int) -> int:
    """Radius in metres that just covers one grid cell (with 10 % overlap)."""
    ne, sw   = geo["ne"], geo["sw"]
    clat     = (ne["lat"] + sw["lat"]) / 2
    km_lat   = (ne["lat"] - sw["lat"]) / divisions * 111.0
    km_lng   = (ne["lng"] - sw["lng"]) / divisions * 111.0 * math.cos(math.radians(clat))
    radius   = math.sqrt((km_lat / 2) ** 2 + (km_lng / 2) ** 2) * 1.1
    return min(50_000, max(3_000, int(radius * 1_000)))


def google_nearby_search(lat: float, lng: float, keyword: str,
                          radius: int = 8_000, page_token: str = None) -> dict:
    params = {
        "location": f"{lat},{lng}",
        "radius":   radius,
        "keyword":  keyword,
        "key":      GOOGLE_API_KEY,
    }
    if page_token:
        params["pagetoken"] = page_token
    try:
        return requests.get(
            "https://maps.googleapis.com/maps/api/place/nearbysearch/json",
            params=params, timeout=12,
        ).json()
    except Exception as e:
        return {"results": [], "error": str(e)}


# ─── Yelp ─────────────────────────────────────────────────────────────────────

def yelp_match(name: str, address1: str, city: str, state: str) -> dict | None:
    if not YELP_API_KEY:
        return None
    try:
        r = requests.get(
            "https://api.yelp.com/v3/businesses/matches",
            headers={"Authorization": f"Bearer {YELP_API_KEY}"},
            params={
                "name": name, "address1": address1,
                "city": city, "state": state, "country": "US",
                "limit": 1, "match_threshold": "normal",
            },
            timeout=6,
        )
        b_list = r.json().get("businesses", [])
        if b_list:
            b = b_list[0]
            return {"rating": b.get("rating"), "review_count": b.get("review_count"), "url": b.get("url", "")}
    except Exception:
        pass
    return None


def street_from_address(addr: str) -> str:
    return addr.split(",")[0].strip() if addr else ""


# ─── Search stream ────────────────────────────────────────────────────────────

def search_stream(city, state, selected, min_rating, min_reviews, require_email, use_grid=False):
    location      = f"{city}, {state}"
    seen          = set()
    total_checked = 0
    pending       = []          # businesses awaiting email lookup
    dnc_ids       = db.get_dnc_ids()
    known_ids     = db.get_known_ids(city, state)

    # Per-category saturation tracking
    cat_stats: dict[str, dict] = {}

    # ── Grid search setup ─────────────────────────────────────
    grid_points  = [None]   # None sentinel → text search
    radius       = 8_000
    center_lat   = None
    center_lng   = None
    if use_grid:
        geo = geocode_city(city, state)
        if geo:
            grid_points = make_grid(geo, 3)
            radius      = _grid_radius_m(geo, 3)
            center_lat  = geo["lat"]
            center_lng  = geo["lng"]
            yield {"type": "status",
                   "message": f"Grid search: 3×3 ({len(grid_points)} zones) over {city}…"}
        else:
            yield {"type": "status", "message": "Geocoding failed — using standard search…"}

    # ── Phase 1: Google discovery ─────────────────────────────
    for cat_type in selected:
        query, label, color = CAT_MAP.get(cat_type, (cat_type, cat_type, "#888"))
        yield {"type": "status", "message": f"Scanning {label}…"}

        cat_stats[label] = {"total": 0, "no_website": 0, "with_website": 0}

        for origin in grid_points:
            page_token, page = None, 0
            while page < 3:
                if page_token:
                    time.sleep(2)

                if origin:
                    lat, lng = origin
                    data = google_nearby_search(lat, lng, query, radius, page_token)
                else:
                    data = google_text_search(query, location, page_token)

                if "error_message" in data:
                    yield {"type": "error", "message": f"Google API: {data['error_message']}"}
                    return

                for place in data.get("results", []):
                    pid = place.get("place_id")
                    if not pid or pid in seen:
                        continue
                    seen.add(pid)
                    total_checked += 1

                    if place.get("rating", 0) < min_rating:
                        continue
                    if place.get("user_ratings_total", 0) < min_reviews:
                        continue

                    details  = google_place_details(pid)
                    presence = web_presence(details.get("website", ""))

                    # Saturation tracking (before website filter)
                    if presence == "website":
                        cat_stats[label]["with_website"] += 1
                    else:
                        cat_stats[label]["no_website"] += 1
                    cat_stats[label]["total"] += 1

                    if presence == "website":
                        continue
                    if details.get("business_status") == "CLOSED_PERMANENTLY":
                        continue
                    if pid in dnc_ids:
                        continue

                    g_rating  = details.get("rating",             place.get("rating", 0))
                    g_reviews = details.get("user_ratings_total", place.get("user_ratings_total", 0))
                    address   = details.get("formatted_address",  place.get("formatted_address", ""))
                    name      = details.get("name",               place.get("name", ""))

                    if g_rating < min_rating or g_reviews < min_reviews:
                        continue

                    # Parse reviews data
                    reviews          = details.get("reviews") or []
                    owner_responses  = _parse_owner_responses(reviews)
                    review_recency   = _parse_review_recency(reviews)
                    review_snippets  = _extract_review_snippets(reviews)
                    opening_hours    = _format_hours(details)
                    price_level     = details.get("price_level")  # int 1-4 or None

                    yelp_data = yelp_match(name, street_from_address(address), city, state)

                    # Preliminary score (no email yet)
                    pre_score = scoring.compute_lead_score(
                        google_rating   = g_rating,
                        google_reviews  = g_reviews,
                        presence        = presence,
                        email           = None,
                        price_level     = price_level,
                        owner_responses = owner_responses,
                        review_recency  = review_recency,
                    )

                    maps_url      = details.get("url", "")
                    _lat, _lng    = _extract_lat_lng(maps_url)

                    biz = {
                        "place_id":        pid,
                        "name":            name,
                        "address":         address,
                        "phone":           details.get("formatted_phone_number", ""),
                        "google_rating":   g_rating,
                        "google_reviews":  g_reviews,
                        "google_maps_url": maps_url,
                        "lat":             _lat,
                        "lng":             _lng,
                        "category":        label,
                        "category_color":  color,
                        "yelp":            yelp_data,
                        "yelp_url":        yelp_data.get("url") if yelp_data else None,
                        "presence":        presence,
                        "social_url":      details.get("website", "") if presence == "social" else "",
                        "price_level":     price_level,
                        "owner_responses":  owner_responses,
                        "review_recency":   review_recency,
                        "review_snippets":  review_snippets,
                        "opening_hours":    opening_hours,
                        "lead_score":       pre_score,
                    }
                    pending.append(biz)

                    # Stream card immediately — email pending
                    payload = {k: v for k, v in biz.items() if k != "yelp_url"}
                    yield {"type": "result", "email_status": "searching",
                           "is_seen": pid in known_ids, **payload}
                    yield {"type": "progress", "phase": 1,
                           "checked": total_checked, "found": len(pending)}

                page_token = data.get("next_page_token")
                if not page_token:
                    break
                page += 1

        # Record saturation for this category
        s = cat_stats[label]
        if s["total"] > 0:
            db.record_search_history(city, state, label,
                                     s["total"], s["no_website"], s["with_website"])
            sat_pct = round(100 * s["no_website"] / s["total"], 1)
            yield {
                "type":       "saturation",
                "category":   label,
                "total":      s["total"],
                "no_website": s["no_website"],
                "pct":        sat_pct,
            }

    if not pending:
        yield {"type": "done", "center_lat": center_lat, "center_lng": center_lng}
        return

    # ── Phase 2: Parallel email lookup ────────────────────────
    yield {
        "type":    "status",
        "message": f"Finding emails for {len(pending)} businesses in parallel…",
    }

    with ThreadPoolExecutor(max_workers=6) as ex:
        fut_map = {
            ex.submit(find_email, b["name"], city, state): b
            for b in pending
        }
        done_count = 0
        for fut in as_completed(fut_map):
            biz = fut_map[fut]
            done_count += 1
            try:
                email, source = fut.result()
            except Exception:
                email, source = None, None

            # MX validation
            mx_valid = -1
            if email:
                mx_valid = 1 if _mx_check(email) else 0
                if mx_valid == 0:
                    email  = None   # discard unresolvable domain
                    source = None

            # Final lead score with email
            final_score = scoring.compute_lead_score(
                google_rating   = biz["google_rating"],
                google_reviews  = biz["google_reviews"],
                presence        = biz["presence"],
                email           = email,
                price_level     = biz.get("price_level"),
                owner_responses = biz.get("owner_responses", 0),
                review_recency  = biz.get("review_recency"),
            )

            # Persist to SQLite
            db.upsert_lead({
                "place_id":        biz["place_id"],
                "name":            biz["name"],
                "address":         biz["address"],
                "phone":           biz.get("phone", ""),
                "city":            city,
                "state":           state,
                "google_rating":   biz["google_rating"],
                "google_reviews":  biz["google_reviews"],
                "google_maps_url": biz.get("google_maps_url", ""),
                "lat":             biz.get("lat"),
                "lng":             biz.get("lng"),
                "category":        biz["category"],
                "category_color":  biz["category_color"],
                "presence":        biz["presence"],
                "social_url":      biz.get("social_url", ""),
                "email":           email,
                "email_source":    source,
                "email_mx_valid":  mx_valid,
                "price_level":     biz.get("price_level"),
                "owner_responses":  biz.get("owner_responses", 0),
                "review_recency":   biz.get("review_recency"),
                "review_snippets":  json.dumps(biz.get("review_snippets") or []),
                "opening_hours":    biz.get("opening_hours", ""),
                "yelp_rating":      biz["yelp"].get("rating")       if biz.get("yelp") else None,
                "yelp_reviews":    biz["yelp"].get("review_count")  if biz.get("yelp") else None,
                "yelp_url":        biz.get("yelp_url"),
                "lead_score":      final_score,
            })

            if require_email and not email:
                yield {"type": "remove_result", "place_id": biz["place_id"]}
            else:
                yield {
                    "type":            "email_update",
                    "place_id":        biz["place_id"],
                    "email":           email,
                    "email_source":    source,
                    "email_mx_valid":  mx_valid,
                    "lead_score":      final_score,
                }

            yield {"type": "progress", "phase": 2,
                   "done": done_count, "total": len(pending)}

    yield {"type": "done", "center_lat": center_lat, "center_lng": center_lng}


# ─── Routes ───────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    cats = [{"type": t, "label": l, "color": c} for t, q, l, c in CATEGORIES]
    return render_template("index.html", categories=cats,
                           google_configured=bool(GOOGLE_API_KEY))


@app.route("/api/maps-js")
def maps_js_proxy():
    """
    Indirection for loading the Google Maps JS bootstrap.

    NOTE: This is a 302 redirect, so the browser still sees the API key in
    the final Location URL — it is NOT a secrecy layer. The key must be
    secured the proper way: via HTTP-referrer / application restrictions in
    the Google Cloud Console. Keeping this route means the key isn't
    hard-coded into index.html and can be rotated server-side.
    """
    cb = request.args.get("callback", "onMapReady")
    if not re.match(r'^[A-Za-z_][A-Za-z0-9_.]*$', cb):
        return "Invalid callback", 400
    if not GOOGLE_API_KEY:
        return "Google API key not configured", 503
    from flask import redirect as _redirect
    return _redirect(
        f"https://maps.googleapis.com/maps/api/js"
        f"?key={GOOGLE_API_KEY}&callback={cb}"
    )


@app.route("/api/status")
def api_status():
    return jsonify({"google": bool(GOOGLE_API_KEY), "yelp": bool(YELP_API_KEY)})


@app.route("/api/search")
def search():
    city          = request.args.get("city",          "").strip()
    state         = request.args.get("state",         "").strip()
    cats_raw      = request.args.get("categories",    "")
    min_rating    = float(request.args.get("min_rating",    4.5))
    min_reviews   = int(request.args.get("min_reviews",     5))
    require_email = request.args.get("require_email", "false").lower() == "true"
    use_grid      = request.args.get("use_grid",      "false").lower() == "true"

    def fail(msg):
        return Response(
            f'data: {json.dumps({"type": "error", "message": msg})}\n\n',
            content_type="text/event-stream",
        )

    if not city or not state:
        return fail("City and state are required.")
    if not GOOGLE_API_KEY:
        return fail("GOOGLE_API_KEY is not configured. Add it to your .env file.")

    selected = [c for c in cats_raw.split(",") if c in CAT_MAP]
    if not selected:
        return fail("No valid categories selected.")

    def generate():
        for event in search_stream(city, state, selected, min_rating, min_reviews, require_email, use_grid):
            yield f"data: {json.dumps(event)}\n\n"

    return Response(
        stream_with_context(generate()),
        content_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ─── Leads API ────────────────────────────────────────────────────────────────

@app.route("/api/leads")
def api_leads():
    city  = request.args.get("city",  "").strip() or None
    state = request.args.get("state", "").strip() or None
    return jsonify(db.get_leads(city, state))


@app.route("/api/leads/<place_id>", methods=["PATCH"])
def api_patch_lead(place_id):
    data    = request.get_json(silent=True) or {}
    allowed = {"status", "notes", "email", "snooze_until"}
    kwargs  = {k: v for k, v in data.items() if k in allowed}
    if not kwargs:
        return jsonify({"error": "No patchable fields provided"}), 400
    db.patch_lead(place_id, **kwargs)
    return jsonify({"ok": True})


# ─── Geocode API ─────────────────────────────────────────────────────────────

@app.route("/api/geocode")
def api_geocode():
    """Return {lat, lng} for a city/state pair (uses Google Geocoding API)."""
    city  = request.args.get("city",  "").strip()
    state = request.args.get("state", "").strip()
    if not city or not state:
        return jsonify({"error": "city and state required"}), 400
    if not GOOGLE_API_KEY:
        return jsonify({"error": "Google API key not configured"}), 503
    geo = geocode_city(city, state)
    if not geo:
        return jsonify({"error": "Could not geocode location"}), 404
    return jsonify({"lat": geo["lat"], "lng": geo["lng"]})


# ─── DNC API ─────────────────────────────────────────────────────────────────

@app.route("/api/dnc", methods=["GET"])
def api_dnc_list():
    return jsonify(db.get_dnc_list())


@app.route("/api/dnc", methods=["POST"])
def api_dnc_add():
    data = request.get_json(silent=True) or {}
    pid  = data.get("place_id", "").strip()
    name = data.get("name", "")
    reason = data.get("reason", "")
    if not pid:
        return jsonify({"error": "place_id required"}), 400
    db.add_dnc(pid, name, reason)
    return jsonify({"ok": True})


@app.route("/api/dnc/<place_id>", methods=["DELETE"])
def api_dnc_remove(place_id):
    db.remove_dnc(place_id)
    return jsonify({"ok": True})


# ─── Dashboard / saturation ───────────────────────────────────────────────────

@app.route("/api/dashboard")
def api_dashboard():
    city     = request.args.get("city",     "").strip() or None
    state    = request.args.get("state",    "").strip() or None
    category = request.args.get("category", "").strip() or None
    return jsonify(db.get_dashboard(city, state, category))


@app.route("/api/saturation")
def api_saturation():
    city  = request.args.get("city",  "").strip() or None
    state = request.args.get("state", "").strip() or None
    return jsonify(db.get_saturation(city, state))


@app.route("/api/reverify/<place_id>")
def api_reverify(place_id):
    """Re-run email discovery for a single lead and update the DB."""
    lead = db.get_lead(place_id)
    if not lead:
        return jsonify({"error": "Lead not found"}), 404

    email, source = find_email(
        lead["name"], lead.get("city", ""), lead.get("state", "")
    )
    mx_valid = -1
    if email:
        mx_valid = 1 if _mx_check(email) else 0
        if mx_valid == 0:
            email = source = None

    new_score = scoring.compute_lead_score(
        google_rating   = lead.get("google_rating",   0),
        google_reviews  = lead.get("google_reviews",  0),
        presence        = lead.get("presence",        "none"),
        email           = email,
        price_level     = lead.get("price_level"),
        owner_responses = lead.get("owner_responses", 0),
        review_recency  = lead.get("review_recency"),
    )

    db.patch_lead(place_id,
        email          = email,
        email_source   = source,
        email_mx_valid = mx_valid,
        lead_score     = new_score,
    )

    return jsonify({
        "email":           email,
        "email_source":    source,
        "email_mx_valid":  mx_valid,
        "lead_score":      new_score,
    })


if __name__ == "__main__":
    app.run(debug=True, port=5001, threaded=True)
