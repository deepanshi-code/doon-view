"""Cluster review intelligence: where a property stands against the places it competes with, aspect by aspect,
and what visitors say about a destination as a whole.

A cluster file (built by scripts/build_cluster.py) holds labelled reviews for every property in a market. Everything
here is computed from it on request, with the uncertainty shown: a property with 8 food mentions isn't called
"behind on food" because its rate looks low.

Statistics, kept simple enough to explain on one slide:
  satisfaction   share of an aspect's mentions that are positive, with a Wilson 95% interval
  lead / lag     the property's whole interval sits above / below the rest of the cluster's rate
  shared issue   an aspect most of the cluster complains about, where few properties differ from the cluster
  turning point  the month that best splits an aspect's monthly complaint rate into before/after (binomial
                 likelihood ratio, chi-square 1 df at 1%)
  emerging       complaint rate over the last RECENT_MONTHS clearly above the year before it
"""
import html
import json
import math
import re
from collections import defaultdict
from dataclasses import dataclass, replace
from functools import lru_cache
from pathlib import Path

ASPECT_NAMES = {"cleanliness": "Cleanliness", "location": "Location", "wifi": "WiFi", "host": "Host & staff",
                "value": "Value for money", "amenities": "Amenities & room", "food": "Food",
                "booking": "Booking & check-in"}
SLUG = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")
Z95 = 1.959964
CHI2_1DF_1PCT = 6.635
MIN_MENTIONS = 10      # fewer mentions than this: "too few to tell"
MIN_SEGMENT = 3        # months on each side of a turning point
MIN_TREND_MENTIONS = 30
RECENT_MONTHS = 3
SHARED_MIN_NEGATIVE = 0.25   # an aspect counts as a shared issue only if at least this share of mentions are complaints
SHARED_MAX_OUTLIERS = 0.2    # ... and at most this share of properties differ significantly from the cluster
QUOTES = 3


def wilson(successes: int, n: int) -> tuple[float, float]:
    """95% Wilson score interval for a proportion; (0, 1) when n is 0."""
    if n == 0:
        return 0.0, 1.0
    p = successes / n
    denom = 1 + Z95**2 / n
    centre = (p + Z95**2 / (2 * n)) / denom
    half = Z95 * math.sqrt(p * (1 - p) / n + Z95**2 / (4 * n * n)) / denom
    return max(0.0, centre - half), min(1.0, centre + half)


def two_proportion_z(k1: int, n1: int, k2: int, n2: int) -> float:
    """z statistic for p1 - p2 (pooled); 0 when either side is empty."""
    if n1 == 0 or n2 == 0:
        return 0.0
    pooled = (k1 + k2) / (n1 + n2)
    se = math.sqrt(pooled * (1 - pooled) * (1 / n1 + 1 / n2))
    return 0.0 if se == 0 else (k1 / n1 - k2 / n2) / se


def _loglik(k: int, n: int) -> float:
    if n == 0 or k == 0 or k == n:
        return 0.0
    p = k / n
    return k * math.log(p) + (n - k) * math.log(1 - p)


def turning_point(months: list[str], negatives: list[int], mentions: list[int]) -> dict | None:
    """The single month that best splits a monthly complaint series, if the split is significant at 1%."""
    if len(months) < 2 * MIN_SEGMENT or sum(mentions) < MIN_TREND_MENTIONS:
        return None
    total = _loglik(sum(negatives), sum(mentions))
    best = None
    for i in range(MIN_SEGMENT, len(months) - MIN_SEGMENT + 1):
        k1, n1 = sum(negatives[:i]), sum(mentions[:i])
        k2, n2 = sum(negatives[i:]), sum(mentions[i:])
        if n1 < MIN_MENTIONS or n2 < MIN_MENTIONS:
            continue
        stat = 2 * (_loglik(k1, n1) + _loglik(k2, n2) - total)
        if best is None or stat > best[0]:
            best = (stat, i, k1 / n1, k2 / n2)
    if best is None or best[0] < CHI2_1DF_1PCT:
        return None
    _, i, before, after = best
    return {"month": months[i], "complaints_before": round(before, 3), "complaints_after": round(after, 3),
            "direction": "worse" if after > before else "better"}


# ── loading ────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class Review:
    property_id: str
    month: str           # YYYY-MM
    sentiment: str
    aspects: dict        # aspect -> "positive" | "negative" (mentioned only)
    text: str
    confidence: float | None


@dataclass(frozen=True)
class Cluster:
    slug: str
    name: str
    kind: str
    source: str
    properties: dict     # property_id -> display name
    reviews: tuple
    demo: bool = False   # synthetic data (scripts/make_demo_data.py): every view must say so


def cluster_dir() -> Path:
    import os
    return Path(os.getenv("CLUSTER_DIR") or Path(__file__).resolve().parent.parent / "clusters")


def list_clusters() -> list[dict]:
    out = []
    for path in sorted(cluster_dir().glob("*.json")):
        if SLUG.match(path.stem):
            c = load_cluster(path.stem)
            if c:
                out.append({"slug": c.slug, "name": c.name, "kind": c.kind, "source": c.source, "demo": c.demo,
                            "properties": len(c.properties), "reviews": len(c.reviews), **_period(c.reviews)})
    return out


def load_cluster(slug: str) -> Cluster | None:
    if not SLUG.match(slug):
        return None
    path = cluster_dir() / f"{slug}.json"
    if not path.is_file():
        return None
    return _load(str(path), path.stat().st_mtime)


@lru_cache(maxsize=16)
def _load(path: str, mtime: float) -> Cluster:  # mtime in the key: a rebuilt file is re-read
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    reviews = tuple(
        Review(r["property_id"], r["month"], r["sentiment"], r.get("aspects") or {}, r.get("text", ""),
               r.get("confidence"))
        for r in data["reviews"] if not r.get("is_spam"))
    return Cluster(data["slug"], data["name"], data.get("kind", "hotels"), data.get("source", ""),
                   data["properties"], reviews, bool(data.get("demo")))


MONTH = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")


def window(c: Cluster, since: str | None, until: str | None) -> Cluster:
    """Only the reviews dated within [since, until] (YYYY-MM, both inclusive). Undated reviews drop out once a
    window is set: a benchmark of 'the last year' can't use reviews of unknown date."""
    if not since and not until:
        return c
    kept = tuple(r for r in c.reviews
                 if r.month and (not since or r.month >= since) and (not until or r.month <= until))
    return replace(c, reviews=kept)


def _period(reviews) -> dict:
    months = sorted({r.month for r in reviews if r.month})
    return {"from": months[0] if months else None, "to": months[-1] if months else None}


# ── aspect counts and quotes ──────────────────────────────────────────────

def _counts(reviews) -> dict:
    """aspect -> [positive, negative]"""
    out = {a: [0, 0] for a in ASPECT_NAMES}
    for r in reviews:
        for a, v in r.aspects.items():
            if a in out:
                out[a][0 if v == "positive" else 1] += 1
    return out


KEYWORDS = {
    "cleanliness": r"clean|dirty|dust|smell|stain|bathroom|toilet|sheet|towel|hygien",
    "location": r"locat|area|walk|metro|station|airport|market|view|noisy|noise|traffic|road|parking",
    "wifi": r"wi-?fi|internet|connection|signal",
    "host": r"staff|service|manager|reception|owner|host|rude|helpful|friendly",
    "value": r"price|value|money|expensive|cheap|overpriced|cost|charge|worth",
    "amenities": r"room|bed|ac\b|air.?con|heater|heating|hot water|shower|pool|gym|lift|tv",
    "food": r"food|breakfast|dinner|lunch|restaurant|meal|buffet|tea|coffee|menu",
    "booking": r"book|booking|reservation|check.?in|check.?out|refund|deposit|makemytrip|mmt|agoda|charged|extra",
}


TONE = {
    "negative": re.compile(r"\b(not|no|never|n't|dirty|bad|poor|rude|worst|terrible|awful|broken|smell\w*|noisy|"
                           r"overpriced|expensive|cold|slow|disappoint\w*|filthy|stain\w*|unhelpful|lack\w*|problem\w*|"
                           r"complain\w*|horrible|small|old|tired)\b", re.I),
    "positive": re.compile(r"\b(great|excellent|good|lovely|clean|friendly|helpful|perfect|wonderful|amazing|"
                           r"comfortable|delicious|best|nice|spotless|superb|fantastic|convenient|recommend\w*)\b",
                           re.I),
}


def _quote(text: str, aspect: str, polarity: str, limit: int = 220) -> str | None:
    """The sentence of a review that talks about the aspect in the right tone; None if no sentence does (the label
    may rest on the review as a whole, and a quote that doesn't show the point misleads)."""
    # Reviews often skip the space after a full stop ("Delhi.The"), so a capital letter also starts a sentence
    sentences = re.split(r"(?<=[.!?])\s*(?=[A-Z])", " ".join(html.unescape(text).split()))
    about = re.compile(rf"\b(?:{KEYWORDS.get(aspect, '$^')})", re.I)
    fitting = [s for s in sentences if about.search(s) and TONE[polarity].search(s) and len(s) >= 25]
    if not fitting:
        return None
    chosen = min(fitting, key=len)  # the most to-the-point sentence
    return chosen if len(chosen) <= limit else chosen[: limit - 1].rsplit(" ", 1)[0] + "…"


def _quotes(reviews, aspect: str, polarity: str, used: set | None = None) -> list[str]:
    """Up to QUOTES sentences; `used` is shared across one view's aspects, so a sentence that covers several aspects
    is shown once."""
    picked = [r for r in reviews if r.aspects.get(aspect) == polarity]
    picked.sort(key=lambda r: (r.confidence or 0, r.month or ""), reverse=True)  # surest, then newest
    seen = used if used is not None else set()
    out = []
    for r in picked:
        q = _quote(r.text, aspect, polarity)
        if q and q not in seen and len(q) >= 25:
            seen.add(q)
            out.append(q)
        if len(out) == QUOTES:
            break
    return out


def _monthly(reviews, aspect: str) -> tuple[list[str], list[int], list[int]]:
    neg, men = defaultdict(int), defaultdict(int)
    for r in reviews:
        v = r.aspects.get(aspect)
        if v and r.month:
            men[r.month] += 1
            neg[r.month] += v == "negative"
    months = _month_range(min(men), max(men)) if men else []
    return months, [neg[m] for m in months], [men[m] for m in months]


def _month_range(first: str, last: str) -> list[str]:
    y, m = map(int, first.split("-"))
    ly, lm = map(int, last.split("-"))
    out = []
    while (y, m) <= (ly, lm):
        out.append(f"{y:04d}-{m:02d}")
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return out


def _quarterly(months, neg, men) -> list[dict]:
    """Quarterly points for charts (monthly is too sparse for most properties)."""
    buckets: dict[str, list[int]] = {}
    for m, k, n in zip(months, neg, men):
        y, mo = m.split("-")
        q = f"{y}-Q{(int(mo) - 1) // 3 + 1}"
        b = buckets.setdefault(q, [0, 0])
        b[0] += k
        b[1] += n
    return [{"period": q, "mentions": n, "complaint_rate": round(k / n, 3) if n else None}
            for q, (k, n) in buckets.items()]


def _emerging(months, neg, men) -> dict | None:
    """Complaints over the last RECENT_MONTHS clearly above the 12 months before them (z > 1.96)."""
    if len(months) < RECENT_MONTHS + 6:
        return None
    k1, n1 = sum(neg[-RECENT_MONTHS:]), sum(men[-RECENT_MONTHS:])
    k2, n2 = sum(neg[-RECENT_MONTHS - 12:-RECENT_MONTHS]), sum(men[-RECENT_MONTHS - 12:-RECENT_MONTHS])
    if n1 < MIN_MENTIONS or n2 < MIN_MENTIONS:
        return None
    z = two_proportion_z(k1, n1, k2, n2)
    if z <= Z95:
        return None
    return {"recent_rate": round(k1 / n1, 3), "earlier_rate": round(k2 / n2, 3), "since": months[-RECENT_MONTHS]}


def _trend(reviews, aspect) -> dict:
    months, neg, men = _monthly(reviews, aspect)
    return {"points": _quarterly(months, neg, men), "turning_point": turning_point(months, neg, men),
            "emerging": _emerging(months, neg, men)}


# ── the two views ─────────────────────────────────────────────────────────

def _by_property(c: Cluster) -> dict:
    out = defaultdict(list)
    for r in c.reviews:
        out[r.property_id].append(r)
    return out


def destination_view(c: Cluster) -> dict:
    """What visitors say about the place as a whole: for a tourism board or municipality."""
    counts = _counts(c.reviews)
    groups = _by_property(c)
    per_property = {pid: _counts(rs) for pid, rs in groups.items()}
    total = max(1, len(c.reviews))  # an empty date window still answers, with zeros
    aspects = []
    for a, (pos, neg) in counts.items():
        n = pos + neg
        low, high = wilson(pos, n)
        # shared issue: complaints common AND few properties differ significantly from the cluster rate
        judged = [(p, q) for p, q in (counts_[a] for counts_ in per_property.values()) if p + q >= MIN_MENTIONS]
        outliers = sum(abs(two_proportion_z(q, p + q, neg - q, n - p - q)) > Z95 for p, q in judged)
        shared = (n >= MIN_MENTIONS and neg / n >= SHARED_MIN_NEGATIVE and len(judged) >= 3
                  and outliers / len(judged) <= SHARED_MAX_OUTLIERS)
        aspects.append({
            "aspect": a, "label": ASPECT_NAMES[a], "mentions": n, "mention_rate": round(n / total, 3),
            "satisfaction": round(pos / n, 3) if n else None, "interval": [round(low, 3), round(high, 3)],
            "complaints": neg, "complaints_per_100_reviews": round(100 * neg / total, 1),
            "properties_judged": len(judged), "properties_that_differ": outliers, "shared_issue": shared,
            "trend": _trend(c.reviews, a),
        })
    aspects.sort(key=lambda x: -x["complaints_per_100_reviews"])
    used: set = set()  # in display order, so the top aspects get first pick of the sentences
    for row in aspects:
        row["complaint_quotes"] = _quotes(c.reviews, row["aspect"], "negative", used)
        row["praise_quotes"] = _quotes(c.reviews, row["aspect"], "positive", used)
    sentiment = defaultdict(int)
    for r in c.reviews:
        sentiment[r.sentiment] += 1
    return {
        "slug": c.slug, "name": c.name, "kind": c.kind, "source": c.source, "demo": c.demo, **_period(c.reviews),
        "reviews": len(c.reviews), "sentiment": dict(sentiment),
        "trend_note": ("Destination trends mix every property: a change can come from which places were reviewed, "
                       "not only from how visits went. Check a property's own trend before acting on one."),
        "aspects": aspects,
        "properties": sorted(({"id": pid, "name": c.properties.get(pid, pid), "reviews": len(rs)}
                              for pid, rs in groups.items()), key=lambda p: -p["reviews"]),
    }


def benchmark(c: Cluster, property_id: str) -> dict | None:
    """One property against the rest of its cluster, aspect by aspect."""
    groups = _by_property(c)
    mine = groups.get(property_id)
    if not mine:
        return None
    rest = [r for pid, rs in groups.items() if pid != property_id for r in rs]
    my_counts, rest_counts = _counts(mine), _counts(rest)
    shared = {a["aspect"] for a in destination_view(c)["aspects"] if a["shared_issue"]}
    rows = []
    for a in ASPECT_NAMES:
        pos, neg = my_counts[a]
        rpos, rneg = rest_counts[a]
        n, rn = pos + neg, rpos + rneg
        low, high = wilson(pos, n)
        market = rpos / rn if rn else None
        if n < MIN_MENTIONS or market is None:
            verdict = "too_few"
        elif low > market:
            verdict = "leads"
        elif high < market:
            verdict = "lags"
        else:
            verdict = "in_line"
        rows.append({
            "aspect": a, "label": ASPECT_NAMES[a], "mentions": n,
            "satisfaction": round(pos / n, 3) if n else None, "interval": [round(low, 3), round(high, 3)],
            "market_satisfaction": round(market, 3) if market is not None else None, "verdict": verdict,
            "shared_issue": a in shared,
            "trend": _trend(mine, a),
        })
    order = {"lags": 0, "in_line": 1, "leads": 2, "too_few": 3}
    rows.sort(key=lambda r: (order[r["verdict"]], -(r["mentions"])))
    used: set = set()
    for row in rows:
        row["complaint_quotes"] = (_quotes(mine, row["aspect"], "negative", used)
                                   if row["verdict"] in ("lags", "in_line") else [])
    return {"cluster": c.slug, "cluster_name": c.name, "demo": c.demo, "property": {"id": property_id,
            "name": c.properties.get(property_id, property_id), "reviews": len(mine)},
            "competitors": len(groups) - 1, "aspects": rows}
