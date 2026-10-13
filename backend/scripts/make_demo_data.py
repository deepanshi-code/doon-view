"""Generate a SYNTHETIC Mussoorie demo dataset, for showing the prototype before real reviews are collected.

    python -m scripts.make_demo_data --out ../data/mussoorie-demo.csv
    python -m scripts.build_cluster --csv ../data/mussoorie-demo.csv --slug mussoorie --name "Mussoorie hotels" --demo

Every review is generated from templates. The properties are fictional (named only by real Mussoorie localities, never
by a real business), and the cluster is flagged demo=true so the app labels every view "Demo data". The planted
patterns exist so each feature has something to show, and they are listed in PATTERNS below: nothing the app finds in
this data is a finding about Mussoorie.
"""
import argparse
import csv
import random
from datetime import date
from pathlib import Path

PROPERTIES = [  # (name, base quality per aspect: probability a mention is positive)
    ("Stay A, Mall Road", {"host": 0.92}),
    ("Stay B, Landour", {"cleanliness": 0.45}),
    ("Stay C, Kempty Road", {}),            # food turns around in mid-2025, see PATTERNS
    ("Stay D, Library Chowk", {"value": 0.42}),
    ("Stay E, Camel's Back Road", {"location": 0.7}),
    ("Stay F, Happy Valley", {}),           # WiFi complaints emerge in the 2026 monsoon
    ("Stay G, Barlowganj", {"food": 0.9}),
    ("Stay H, Kulri Bazaar", {"amenities": 0.48}),
    ("Stay I, Jharipani", {}),
    ("Stay J, Company Garden", {"cleanliness": 0.9, "amenities": 0.85}),
]
DEFAULT_QUALITY = {"cleanliness": 0.72, "location": 0.45, "wifi": 0.6, "host": 0.78, "value": 0.6,
                   "amenities": 0.68, "food": 0.7}
PATTERNS = [
    "location (parking, traffic, steep roads) draws complaints at every property: a market-wide issue",
    "Stay C's food is poor until June 2025, then good: a turning point",
    "Stay F's WiFi complaints rise from July 2026 (monsoon outages): an emerging issue",
    "heating complaints rise in winter months at every property",
    "Stay A leads on staff; Stay B lags on cleanliness; Stay D lags on value; Stay H lags on rooms",
]

SENTENCES = {
    "cleanliness": (["The room was spotless and the bathroom was very clean.",
                     "Fresh sheets and towels every day, everything was clean."],
                    ["The bathroom was dirty and the sheets had stains.",
                     "The room smelled damp and the carpet was dusty."]),
    "location": (["The view of the Doon valley from the balcony was beautiful.",
                  "A short walk to Mall Road, the location was perfect."],
                 ["Parking was a nightmare and the road up to the hotel was steep and narrow.",
                  "We were stuck in traffic for an hour and there was no parking near the hotel."]),
    "wifi": (["The WiFi was fast enough to work from the room.",
              "Internet worked well throughout our stay."],
             ["The WiFi kept dropping and there was no mobile signal in the room.",
              "Internet did not work for most of our stay."]),
    "host": (["The staff were friendly and helped us plan our day trips.",
              "The manager was very helpful and check-in was quick."],
             ["The staff were rude and nobody answered the reception phone.",
              "Check-in took forever and the staff were unhelpful."]),
    "value": (["Good value for money for a hill station in peak season.",
               "Worth every rupee for the comfort we got."],
              ["Overpriced for such a basic room.",
               "Far too expensive for what we got."]),
    "amenities": (["The bed was comfortable and the room was spacious.",
                   "Hot water was always available and the heater worked well."],
                  ["The heater did not work and the room was freezing at night.",
                   "No hot water in the morning and the bed was uncomfortable."]),
    "food": (["Breakfast was delicious, the parathas were excellent.",
              "Lovely dinner at the hotel restaurant with fresh food."],
             ["Breakfast was cold and the same every day.",
              "The food was bland and overpriced."]),
}
HINGLISH = ["Khana bahut accha tha aur staff bhi friendly tha.", "Room ganda tha, paise vasool nahi hua.",
            "View mast tha par parking ki bahut problem thi.", "Theek thaak stay tha, kuch khaas nahi."]
OPENERS = ["We stayed two nights.", "Came for a weekend from Delhi.", "Family trip with our parents.",
           "Stayed here on our honeymoon.", "Short work trip."]
WINTER = {12, 1, 2}


def quality(prop: str, base: dict, aspect: str, d: date) -> float:
    q = base.get(aspect, DEFAULT_QUALITY[aspect])
    if prop.startswith("Stay C") and aspect == "food":
        q = 0.25 if d < date(2025, 6, 1) else 0.85
    if prop.startswith("Stay F") and aspect == "wifi" and d >= date(2026, 7, 1):
        q = 0.15
    if aspect == "amenities" and d.month in WINTER:
        q -= 0.25
    return min(0.97, max(0.03, q))


def review(rng: random.Random, prop: str, base: dict, d: date) -> tuple[str, int]:
    if rng.random() < 0.06:
        text = rng.choice(HINGLISH)
        return text, 4 if "accha" in text or "mast" in text else 3 if "Theek" in text else 2
    aspects = rng.sample(list(DEFAULT_QUALITY), k=rng.choice([2, 2, 3, 3, 4]))
    if prop.startswith("Stay F") and d >= date(2026, 7, 1) and "wifi" not in aspects and rng.random() < 0.6:
        aspects.append("wifi")
    good = 0
    parts = [rng.choice(OPENERS)] if rng.random() < 0.5 else []
    for a in aspects:
        positive = rng.random() < quality(prop, base, a, d)
        good += positive
        parts.append(rng.choice(SENTENCES[a][0 if positive else 1]))
    share = good / len(aspects)
    rating = 5 if share > 0.8 else 4 if share >= 0.6 else 3 if share >= 0.4 else 2 if share > 0.1 else 1
    return " ".join(parts), rating


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--seed", type=int, default=2026)
    p.add_argument("--start", default="2025-01")
    p.add_argument("--end", default="2026-09")
    args = p.parse_args()
    rng = random.Random(args.seed)
    y, m = map(int, args.start.split("-"))
    ey, em = map(int, args.end.split("-"))
    rows = []
    while (y, m) <= (ey, em):
        peak = m in (5, 6, 10, 12)  # summer and festive peaks bring more reviews
        for name, base in PROPERTIES:
            for _ in range(rng.randint(4, 9) + (3 if peak else 0)):
                d = date(y, m, rng.randint(1, 28))
                text, rating = review(rng, name, base, d)
                rows.append({"property": name, "platform": rng.choice(["google", "booking", "tripadvisor"]),
                             "date": d.isoformat(), "rating": rating, "reviewer": "", "text": text})
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    print(f"wrote {len(rows)} SYNTHETIC reviews of {len(PROPERTIES)} fictional properties to {args.out}")
    print("planted patterns:\n  - " + "\n  - ".join(PATTERNS))


if __name__ == "__main__":
    main()
