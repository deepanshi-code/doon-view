# Doon View

Review intelligence for Uttarakhand's hill towns, built for the AI–Tourism Hackathon (UNWTO theme: digital agenda and
AI to redesign tourism). It reads every recent review of every property in a market together and shows:

- **Is this issue ours, or the market's?** Each hotel against the other hotels in its town, aspect by aspect: yours
  to fix, a complaint the whole town shares, or your edge. Ahead or behind only when the gap holds at 95%; no
  verdict when there are too few mentions to tell.
- **Where your stars go**: which complaint costs a hotel the most stars, estimated from guests' own ratings (a
  linear model of stars on per-aspect complaints, platform held apart), so an owner knows what to fix first.
- **What visitors say about the destination**: satisfaction per aspect with a 95% range, complaints per 100 reviews,
  turning points and emerging complaints, with real quotes.

Recent reviews only by default (2025-26); "All time" is one click away. The site (React, Tailwind, three.js for the
ridge relief behind each page, loaded lazily with a still frame under reduced motion and a fallback without WebGL)
has a home page, a page per hotel, a town page and a Method page.

## How it works

1. `backend/scripts/build_cluster.py` reads a CSV of reviews, drops duplicates, removes reviewer names, and labels
   each review: a fine-tuned DeBERTa-v3 model (int8 ONNX, CPU) for English reviews, Gemini for short or
   Hindi-English ones (names replaced with placeholders first), keyword rules as a last resort. It writes one file
   per market to `backend/clusters/` (gitignored: collected reviews are never committed).
2. `backend/app/cluster.py` computes everything from that file on request, using only the standard library.
3. The FastAPI app serves it read-only; the React app (`frontend/`) shows it.

The statistics and their limits are explained on the site's Method page.

## Run it locally

```bash
cd backend
python -m venv .venv && .venv/Scripts/pip install -r requirements.txt -r requirements-dev.txt   # Windows; bin/ elsewhere
cp .env.example .env            # optional: GEMINI_API_KEY for short/Hinglish reviews
.venv/Scripts/python -m uvicorn app.main:app --port 8000
```

```bash
cd frontend
npm install --ignore-scripts
npm run dev                     # http://localhost:5173 (proxies /api to :8000)
```

The model goes in `backend/model/` (labels.json, tokenizer.json, model.int8.onnx), or set `MODEL_URL` and run
`python -m scripts.fetch_model`. Serving the site doesn't need the model; building a cluster does.

## Add a market

A CSV with columns `property,platform,date,rating,reviewer,text` (template: `data/reviews.template.csv`; `property`,
`text` and `date` are required; dates like `2025-03-14`, `14/03/2025` or `Mar 2025`).

```bash
cd backend
python -m scripts.build_cluster --csv ../data/mussoorie.csv --slug mussoorie --name "Mussoorie hotels" --check
python -m scripts.build_cluster --csv ../data/mussoorie.csv --slug mussoorie --name "Mussoorie hotels" \
    --source "Collected <date> from public listings: <how>."
```

The team's own Mussoorie collection (`data/reviews.csv` and `data/hotels.csv`, format in `data/DATA_CHANGELOG.md`)
builds with `--doonview ../data/reviews.csv` in place of `--csv`.

`--check` reports per property how many reviews fall in the default period and whether verdicts will be possible,
without labelling anything. Collect reviews by hand or through official APIs within their terms; don't scrape sites
whose terms forbid it.

## Train the model on the Mussoorie reviews (B200)

`ml/` fine-tunes the classifier on the collected Mussoorie reviews only (`data/reviews.csv`, see
`data/DATA_CHANGELOG.md`), optionally mixed with outside TripAdvisor reviews (research licence: the resulting model
stays private). Sentiment comes from the guests' stars; aspects (including booking) from an open LLM teacher run
once on the GPU. Every candidate is scored by 5-fold cross-validation on the Mussoorie reviews only, with 95%
bootstrap intervals, against TF-IDF, keyword rules and the current app model; `pick` ships a candidate only if it
beats the current model on both sentiment and complaint F1.

```bash
mkdir -p /workspace/doonview && cd /workspace/doonview && python3 -m zipfile -e doon-view-train.zip .
export HF_TOKEN=<write token>   # optional: current-model comparison and private backup
bash ml/train_b200.sh           # Mussoorie only; ml/train_mix_b200.sh and ml/train_auto_b200.sh add outside data
```

The result is a model zip under `ml/artifacts/`, which the app loads through `MODEL_DIR` or `MODEL_URL`. Before
switching the app to a new model, rebuild the cluster with it and compare the labels on real reviews: an int8 export
is only checked against its full-precision model on sentiment, not on aspects.

## Tests

```bash
cd backend && .venv/Scripts/python -m pytest          # TEST_MODEL_DIR=model also runs the real-model tests
cd frontend && npm run lint && npm test && npm run build
cd ml && python -m pytest tests                         # needs the training environment (pandas, numpy)
```

## Data and licences

- The classifier was trained on research-licensed hotel reviews; keep the model files private.
- Cluster files hold review text for quotes: keep them out of git and out of public storage. The site shows
  aggregates and single-sentence quotes with reviewer names removed.
- `frontend/public/img/mussoorie-valley-*.webp`: "Mussoorie 5" by Gannu03, Wikimedia Commons, CC BY-SA 4.0
  (https://commons.wikimedia.org/wiki/File:Mussoorie_5.jpg), resized; shared under the same licence.
