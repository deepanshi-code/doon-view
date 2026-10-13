"""Label every review of a cluster (all properties in a town, or all restaurants in a locality) and write the cluster
file the /api/clusters endpoints read.

Usage (from backend/):
  # Your own collected sample: a CSV with columns property, text, date [, platform, rating, reviewer]
  python -m scripts.build_cluster --csv mussoorie.csv --slug mussoorie --name "Mussoorie hotels" \
      --source "Collected 2026-10-13 from public listings, 12 properties" [--kind hotels]
  # The OpinRank research dataset (TripAdvisor reviews, 2001-2009), one city as a stand-in cluster
  python -m scripts.build_cluster --opinrank path/to/opinrank.zip --city new-delhi \
      --slug new-delhi --name "New Delhi hotels"

Labels come from the same chain the app uses: the fine-tuned model (--model-dir, default backend/model)
for English reviews, Gemini for short or Hinglish ones when GEMINI_API_KEY is set, keyword rules otherwise. Each
review's label source is kept. Reviewer names, emails and phone numbers are removed from the stored text, which is
only used for short quotes. Output: clusters/<slug>.json (gitignored; don't commit or publish collected reviews).
"""
import argparse
import csv
import io
import json
import os
import re
import sys
import zipfile
from collections import Counter
from datetime import datetime
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
DEFAULT_MODEL = BACKEND / "model"
MONTHS = {m: i for i, m in enumerate(("jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov",
                                      "dec"), 1)}


def to_month(value: str) -> str | None:
    """YYYY-MM from the date formats review sites use; None if it can't be read."""
    value = (value or "").strip()
    for fmt in ("%Y-%m-%d", "%Y-%m", "%d/%m/%Y", "%d-%m-%Y", "%Y/%m/%d", "%d %b %Y", "%d %B %Y", "%b %d %Y",
                "%B %d %Y", "%b %Y", "%B %Y", "%b %d, %Y", "%B %d, %Y"):
        try:
            d = datetime.strptime(value, fmt)
            return f"{d.year:04d}-{d.month:02d}"
        except ValueError:
            pass
    m = re.match(r"([A-Za-z]{3})[a-z]*\.?\s+(?:\d{1,2},?\s+)?(\d{4})", value)
    if m and m.group(1).lower() in MONTHS:
        return f"{m.group(2)}-{MONTHS[m.group(1).lower()]:02d}"
    return None


def slugify(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:60] or "property"


def scrub(text: str, reviewer: str = "") -> str:
    """Remove the reviewer's name, emails, phone numbers and names after titles (Mr, Mrs, ...). Place and hotel
    names stay: the quotes need them, and they aren't personal data."""
    from app.redact import _AFTER_TITLE, _EMAIL, _PHONE
    text = _EMAIL.sub("[email]", text)
    text = _PHONE.sub("[phone]", text)
    for part in re.findall(r"[A-Za-z]{2,}", reviewer or ""):
        text = re.sub(rf"\b{re.escape(part)}\b", "[name]", text, flags=re.IGNORECASE)
    return _AFTER_TITLE.sub(lambda m: m.group(0)[: m.start(1) - m.start(0)] + "[name]", text)


def read_csv(path: Path) -> list[dict]:
    with path.open(encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    if not rows:
        raise SystemExit(f"{path} has no rows")
    cols = {c.strip().lower(): c for c in rows[0]}
    missing = [c for c in ("property", "text", "date") if c not in cols]
    if missing:
        raise SystemExit(f"{path} needs columns property, text, date; missing {missing}. Found: {list(cols)}")
    get = lambda r, c: (r.get(cols[c]) or "").strip() if c in cols else ""  # noqa: E731
    return [{"property": get(r, "property"), "text": get(r, "text"), "date": get(r, "date"),
             "platform": get(r, "platform"), "rating": get(r, "rating"), "reviewer": get(r, "reviewer")}
            for r in rows if get(r, "property") and get(r, "text")]


def read_opinrank(zip_path: Path, city: str) -> list[dict]:
    """OpinRank: a zip holding OpinRankDataset.zip, with hotels/<city>/<country>_<city>_<hotel> files of
    tab-separated 'date, title, text' lines."""
    outer = zipfile.ZipFile(zip_path)
    inner = zipfile.ZipFile(io.BytesIO(outer.read("OpinRankDataset.zip")))
    rows = []
    prefix = f"hotels/{city}/"
    for name in inner.namelist():
        if not name.startswith(prefix) or name.endswith("/"):
            continue
        hotel = name[len(prefix):].split("_", 2)[-1].replace("_", " ").title()
        # Windows-1252, not Latin-1: its curly quotes (0x91-0x94) would otherwise become control characters
        for line in inner.read(name).decode("cp1252", errors="replace").splitlines():
            parts = line.split("\t")
            if len(parts) >= 3 and parts[2].strip():
                rows.append({"property": hotel, "date": parts[0].strip(), "text": f"{parts[1].strip()}. {parts[2].strip()}",
                             "platform": "tripadvisor", "rating": "", "reviewer": ""})
    if not rows:
        raise SystemExit(f"no reviews for city '{city}' in {zip_path}")
    return rows


def check(rows: list[dict], min_reviews: int, since: str) -> None:
    """What the app will be able to say with this data, before spending time on labelling."""
    months = [to_month(r["date"]) for r in rows]
    unreadable = [r["date"] for r, m in zip(rows, months) if m is None]
    dated = sorted(m for m in months if m)
    print(f"{len(rows)} reviews, {len(set(r['property'] for r in rows))} properties, "
          f"dates {dated[0] if dated else '-'} to {dated[-1] if dated else '-'}")
    print(f"platforms: {dict(Counter(r['platform'] or '(none)' for r in rows))}")
    if unreadable:
        print(f"{len(unreadable)} dates can't be read (they drop out of the {since}+ view), e.g. "
              f"{sorted(set(unreadable))[:5]}")
    recent = Counter(r["property"] for r, m in zip(rows, months) if m and m >= since)
    total = Counter(r["property"] for r in rows)
    print(f"\n{'property':40} {'all':>5} {since + '+':>9}  verdicts possible?")
    for name, n in total.most_common():
        k = recent.get(name, 0)
        if n < min_reviews:
            note = "dropped (too few reviews)"
        elif k >= 40:
            note = "yes"
        elif k >= 10:
            note = "some: many aspects will read 'too few to tell'"
        else:
            note = "no recent reviews" if k == 0 else "too few recent reviews for any verdict"
        print(f"{name[:40]:40} {n:5} {k:9}  {note}")
    print(f"\n{sum(recent.values())} reviews from {since} on. Rough guide: an aspect needs 10+ mentions for any verdict, "
          "so aim for 40+ recent reviews per property.")


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    src = p.add_mutually_exclusive_group(required=True)
    src.add_argument("--csv", type=Path)
    src.add_argument("--opinrank", type=Path)
    p.add_argument("--city", help="OpinRank city folder, e.g. new-delhi")
    p.add_argument("--slug", required=True)
    p.add_argument("--name", required=True)
    p.add_argument("--kind", default="hotels")
    p.add_argument("--source", default="")
    p.add_argument("--min-reviews", type=int, default=15, help="drop properties with fewer reviews than this")
    p.add_argument("--model-dir", type=Path, default=DEFAULT_MODEL)
    p.add_argument("--out", type=Path, default=BACKEND / "clusters")
    p.add_argument("--check", action="store_true", help="report on the data and stop: no labelling, nothing written")
    p.add_argument("--since", default="2025-01", help="--check: the period the app shows by default (YYYY-MM)")
    args = p.parse_args()

    from app.cluster import SLUG
    if not SLUG.match(args.slug):
        raise SystemExit("--slug: lowercase letters, digits and dashes only")
    if args.opinrank and not args.city:
        raise SystemExit("--opinrank needs --city")

    rows = read_opinrank(args.opinrank, args.city) if args.opinrank else read_csv(args.csv)
    # The same review copied from two platforms (or twice from one) counts once
    seen, unique = set(), []
    for r in rows:
        key = (r["property"].lower(), " ".join(r["text"].lower().split()))
        if key not in seen:
            seen.add(key)
            unique.append(r)
    if len(unique) < len(rows):
        print(f"dropped {len(rows) - len(unique)} duplicate reviews")
    rows = unique
    if args.check:
        check(rows, args.min_reviews, args.since)
        return
    per_property = Counter(r["property"] for r in rows)
    kept = {name for name, n in per_property.items() if n >= args.min_reviews}
    dropped = len(per_property) - len(kept)
    rows = [r for r in rows if r["property"] in kept]
    print(f"{len(rows)} reviews, {len(kept)} properties (dropped {dropped} with < {args.min_reviews} reviews)")

    os.environ.setdefault("MODEL_DIR", str(args.model_dir))
    from app import labelling
    if labelling.load_classifier() is None:
        print("WARNING: no fine-tuned model loaded: labels come from Gemini (if configured) or keyword rules",
              file=sys.stderr)

    out_reviews = []
    batch = 64
    for start in range(0, len(rows), batch):
        chunk = rows[start:start + batch]
        labels = labelling.classify_reviews([(r["text"], r["reviewer"]) for r in chunk])
        for r, lab in zip(chunk, labels):
            out_reviews.append({
                "property_id": slugify(r["property"]), "month": to_month(r["date"]), "platform": r["platform"],
                "rating": r["rating"], "sentiment": lab.sentiment, "is_spam": lab.is_spam,
                "aspects": lab.aspects or {}, "source": lab.source,
                "confidence": round(lab.confidence, 3) if lab.confidence is not None else None,
                "text": scrub(r["text"], r["reviewer"]),
            })
        print(f"  {min(start + batch, len(rows))}/{len(rows)}", flush=True)

    undated = sum(r["month"] is None for r in out_reviews)
    sources = Counter(r["source"] for r in out_reviews)
    cluster = {"slug": args.slug, "name": args.name, "kind": args.kind, "source": args.source,
               "built": datetime.now().strftime("%Y-%m-%d"), "label_sources": dict(sources),
               "properties": {slugify(n): n for n in sorted(kept)}, "reviews": out_reviews}
    args.out.mkdir(parents=True, exist_ok=True)
    path = args.out / f"{args.slug}.json"
    path.write_text(json.dumps(cluster, ensure_ascii=False), encoding="utf-8")
    print(f"wrote {path}: {len(out_reviews)} reviews, labels by {dict(sources)}, {undated} without a readable date")


if __name__ == "__main__":
    main()
