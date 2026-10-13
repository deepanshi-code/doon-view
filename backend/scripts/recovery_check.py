"""Did the analysis find what make_demo_data.py planted? A recovery test on synthetic data: it checks the pipeline end to
end (labelling + statistics), not anything about the real Mussoorie market.

    python -m scripts.recovery_check --slug mussoorie
"""
import argparse
import json

from app import cluster as C

NAMES = {"stay-a-mall-road": "Stay A", "stay-b-landour": "Stay B", "stay-c-kempty-road": "Stay C",
         "stay-d-library-chowk": "Stay D", "stay-f-happy-valley": "Stay F", "stay-h-kulri-bazaar": "Stay H"}


def aspect(rows, name):
    return next(r for r in rows if r["aspect"] == name)


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--slug", default="mussoorie")
    args = p.parse_args()
    c = C.load_cluster(args.slug)
    if c is None or not c.demo:
        raise SystemExit("needs the demo cluster (built with --demo)")
    dest = C.destination_view(c)
    bench = {pid: C.benchmark(c, pid)["aspects"] for pid in NAMES}

    checks = [
        ("Location is a market-wide complaint", aspect(dest["aspects"], "location")["shared_issue"],
         f"{aspect(dest['aspects'], 'location')['properties_that_differ']} of "
         f"{aspect(dest['aspects'], 'location')['properties_judged']} properties differ from the market"),
        ("Stay A leads on staff", aspect(bench["stay-a-mall-road"], "host")["verdict"] == "leads",
         aspect(bench["stay-a-mall-road"], "host")["verdict"]),
        ("Stay B lags on cleanliness", aspect(bench["stay-b-landour"], "cleanliness")["verdict"] == "lags",
         aspect(bench["stay-b-landour"], "cleanliness")["verdict"]),
        ("Stay D lags on value", aspect(bench["stay-d-library-chowk"], "value")["verdict"] == "lags",
         aspect(bench["stay-d-library-chowk"], "value")["verdict"]),
        ("Stay H lags on rooms", aspect(bench["stay-h-kulri-bazaar"], "amenities")["verdict"] == "lags",
         aspect(bench["stay-h-kulri-bazaar"], "amenities")["verdict"]),
    ]
    tp = aspect(bench["stay-c-kempty-road"], "food")["trend"]["turning_point"]
    checks.append(("Stay C's food turns around in June 2025",
                   bool(tp) and tp["direction"] == "better" and "2025-04" <= tp["month"] <= "2025-08",
                   json.dumps(tp)))
    em = aspect(bench["stay-f-happy-valley"], "wifi")["trend"]["emerging"]
    checks.append(("Stay F's WiFi complaints emerge in the 2026 monsoon", bool(em), json.dumps(em)))

    found = sum(ok for _, ok, _ in checks)
    for name, ok, detail in checks:
        print(f"{'FOUND ' if ok else 'MISSED'}  {name}  ({detail})")
    print(f"\n{found} of {len(checks)} planted patterns recovered")


if __name__ == "__main__":
    main()
