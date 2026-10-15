"""Write every response the frontend asks for as static JSON, so the site runs without the API.

    python -m scripts.export_static --out ../frontend/public/data
    (then build the frontend with VITE_STATIC_DATA=1)

The responses come from the API's own route functions, so a static file holds exactly what /api would return for
the same request: aggregates and short quotes, never a cluster file's full review list. The frontend offers two
periods (format.js PERIODS), so each destination is written for both: since 2025-01 and all time.

Layout under --out (the frontend's api.js maps requests onto it):
  clusters.json
  clusters/<slug>/<period>.json                     destination view
  clusters/<slug>/<period>/grid.json                market grid
  clusters/<slug>/<period>/properties/<id>.json     hotel page; {"error": {...}} when the API would answer 404
"""
import argparse
import json
from pathlib import Path

from fastapi import HTTPException

from app import cluster, main

PERIODS = {"2025-01": "2025-01", "all": ""}  # file name -> the since= the frontend sends


def write(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")


def export(out: Path) -> int:
    count = 0
    clusters = main.get_clusters()
    write(out / "clusters.json", clusters)
    for summary in clusters:
        slug = summary["slug"]
        ids = list(cluster.load_cluster(slug).properties)
        for name, since in PERIODS.items():
            base = out / "clusters" / slug
            write(base / f"{name}.json", main.get_destination(slug, since, None))
            write(base / name / "grid.json", main.get_grid(slug, since, None))
            for pid in ids:
                try:
                    data = main.get_benchmark(slug, pid, since, None)
                except HTTPException as e:
                    data = {"error": {"status": e.status_code, "detail": e.detail}}
                write(base / name / "properties" / f"{pid}.json", data)
            count += 2 + len(ids)
    return count + 1


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--out", type=Path, required=True)
    args = p.parse_args()
    print(f"wrote {export(args.out)} files to {args.out}")
