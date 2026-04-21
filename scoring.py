"""Lead scoring — pure function, no side-effects, no dependencies."""


def compute_lead_score(
    google_rating:   float,
    google_reviews:  int,
    presence:        str,
    email:           str | None,
    price_level:     int | None,
    owner_responses: int,
    review_recency:  str | None,
) -> int:
    """
    Returns an integer 0–100 representing lead quality.

    Component weights:
        Rating          0–25
        Review volume   0–20
        Presence gap    0–20   (none=20, social=12 — bigger gap = bigger opportunity)
        Has email       0–15
        Price level     0–10
        Owner engagement 0–5
        Review recency   0–5
    """
    score = 0

    # ── Rating (0–25) ──────────────────────────────────────────
    if   google_rating >= 4.8: score += 25
    elif google_rating >= 4.5: score += 20
    elif google_rating >= 4.0: score += 14
    elif google_rating >= 3.5: score += 8

    # ── Review volume (0–20) ───────────────────────────────────
    r = google_reviews or 0
    if   r >= 200: score += 20
    elif r >= 100: score += 17
    elif r >= 50:  score += 14
    elif r >= 25:  score += 10
    elif r >= 10:  score += 6
    elif r >= 5:   score += 3

    # ── Presence gap (0–20) ────────────────────────────────────
    if   presence == "none":   score += 20
    elif presence == "social": score += 12

    # ── Has email (0–15) ───────────────────────────────────────
    if email:
        score += 15

    # ── Price level (0–10) ────────────────────────────────────
    score += {4: 10, 3: 8, 2: 5, 1: 2}.get(price_level, 4)  # 4 = unknown/neutral

    # ── Owner engagement (0–5) ────────────────────────────────
    if   owner_responses >= 10: score += 5
    elif owner_responses >= 5:  score += 4
    elif owner_responses >= 2:  score += 2
    elif owner_responses >= 1:  score += 1

    # ── Review recency (0–5) ──────────────────────────────────
    score += {"active": 5, "moderate": 3, "quiet": 1}.get(review_recency, 2)

    return min(score, 100)
