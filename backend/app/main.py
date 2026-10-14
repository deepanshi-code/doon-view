"""Doon View API: read-only views over cluster files (scripts/build_cluster.py).

No accounts and no database: a cluster file holds aggregated, labelled reviews with reviewer names removed.
"""
import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from . import cluster, labelling

logging.basicConfig(level=logging.INFO)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    # The model is only needed to build clusters; serving works without it. Loading it here runs its CPU self-check
    # at start-up and makes /api/status honest about what labelled the data on this server.
    labelling.load_classifier()
    yield


app = FastAPI(title="Doon View API", version="1.0.0", lifespan=lifespan)

ALLOWED_ORIGINS = [o.strip() for o in os.getenv("ALLOWED_ORIGINS", "http://localhost:5173").split(",") if o.strip()]
app.add_middleware(CORSMiddleware, allow_origins=ALLOWED_ORIGINS, allow_credentials=False, allow_methods=["GET"],
                   allow_headers=["*"])


@app.get("/api/status")
def get_status():
    return {"app": "Doon View", "clusters": len(cluster.list_clusters()), **labelling.status()}


@app.get("/api/clusters")
def get_clusters():
    return cluster.list_clusters()


# Recent reviews by default: a market changes, so 2019's breakfast complaints shouldn't rank a hotel today.
# Override per request (?since=&until=, YYYY-MM) or per deployment (DEFAULT_SINCE; empty = all time).
DEFAULT_SINCE = os.getenv("DEFAULT_SINCE", "2025-01")
MONTH = r"^\d{4}-(0[1-9]|1[0-2])$"


def _windowed(slug: str, since: str | None, until: str | None):
    c = cluster.load_cluster(slug)
    if c is None:
        return None, None
    if since is None:
        since = DEFAULT_SINCE or None
    elif since == "":  # ?since= asks for all time
        since = None
    return cluster.window(c, since, until), {"since": since, "until": until}


@app.get("/api/clusters/{slug}")
def get_destination(slug: str, since: str | None = Query(None, pattern=f"{MONTH}|^$"),
                    until: str | None = Query(None, pattern=MONTH)):
    c, win = _windowed(slug, since, until)
    if c is None:
        raise HTTPException(status_code=404, detail="Destination not found")
    return {**cluster.destination_view(c), "window": win}


@app.get("/api/clusters/{slug}/grid")
def get_grid(slug: str, since: str | None = Query(None, pattern=f"{MONTH}|^$"),
             until: str | None = Query(None, pattern=MONTH)):
    c, win = _windowed(slug, since, until)
    if c is None:
        raise HTTPException(status_code=404, detail="Destination not found")
    return {**cluster.market_grid(c), "window": win}


@app.get("/api/clusters/{slug}/properties/{property_id}")
def get_benchmark(slug: str, property_id: str, since: str | None = Query(None, pattern=f"{MONTH}|^$"),
                  until: str | None = Query(None, pattern=MONTH)):
    c, win = _windowed(slug, since, until)
    result = cluster.benchmark(c, property_id) if c else None
    if result is None:
        raise HTTPException(status_code=404, detail="Destination or property not found in this period")
    return {**result, "window": win}
