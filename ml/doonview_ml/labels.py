"""Label spaces and the labelling guide, imported from the backend so the app, the teacher and the model agree."""
import os
import sys
from pathlib import Path

# backend/ next to ml/ (the repo layout and the training zip), or set DOONVIEW_BACKEND
BACKEND_DIR = Path(os.getenv("DOONVIEW_BACKEND") or Path(__file__).resolve().parents[2] / "backend").resolve()
if not (BACKEND_DIR / "app" / "labelling.py").is_file():
    raise SystemExit(f"backend not found at {BACKEND_DIR}: keep backend/ next to ml/ or set DOONVIEW_BACKEND")
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.labelling import (  # noqa: E402
    ASPECT_GUIDE,
    ASPECT_VALUES,
    CLASSIFICATION_SCHEMA,
    SENTIMENTS,
    build_prompt,
    parse_classification,
)

ASPECTS = tuple(ASPECT_GUIDE)  # cleanliness, location, wifi, host, value, amenities, food, booking

# Google's per-review sub-ratings -> our aspect. An independent check on aspect polarity: the guest rated it.
SUBRATING_ASPECT = {"rooms": "amenities", "service": "host", "location": "location"}


def rating_to_sentiment(stars: float) -> str:
    """The guest's own star rating: 1-2 negative, 3 neutral, 4-5 positive."""
    return "negative" if stars <= 2 else "neutral" if stars < 4 else "positive"


def rating_to_polarity(score: float | None) -> str | None:
    """A 1-5 sub-rating as a polarity; 3 (and missing) say nothing either way."""
    if score is None or score != score:  # NaN
        return None
    return "negative" if score <= 2 else "positive" if score >= 4 else None
