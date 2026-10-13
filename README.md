# Doon View

Review intelligence for Uttarakhand's hill towns, built for the AI–Tourism Hackathon (UNWTO theme: digital agenda and
AI to redesign tourism). It reads every recent review of every property in a market together and shows:

- **What visitors say about the destination**: satisfaction per aspect with a 95% range, complaints per 100 reviews,
  market-wide issues (a gap for whoever fixes them first), turning points and emerging complaints, with real quotes.
- **One property against its market**: ahead, behind or in line on each aspect, and no verdict when there are too
  few mentions to tell.

Recent reviews only by default (2025–26); "All time" is one click away.

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

`--check` reports per property how many reviews fall in the default period and whether verdicts will be possible,
without labelling anything. Collect reviews by hand or through official APIs within their terms; don't scrape sites
whose terms forbid it.

## Train the model on the Mussoorie reviews (B200)

`ml/` fine-tunes the classifier on the collected Mussoorie reviews only (`data/reviews.csv`, see
`data/DATA_CHANGELOG.md`). Sentiment comes from the guests' stars; aspects (including booking) from an open LLM
teacher run once on the GPU. Every candidate is scored by 5-fold cross-validation on the same 1,657 reviews, with
95% bootstrap intervals, against TF-IDF, keyword rules and the current app model.

```bash
mkdir -p /workspace/doonview && cd /workspace/doonview && python3 -m zipfile -e doon-view-train.zip .
export HF_TOKEN=<write token>   # optional: current-model comparison and private backup
bash ml/train_b200.sh
```

The result is `ml/artifacts/doon-view-deberta-v3-xsmall.zip`, which the app loads through `MODEL_DIR` or `MODEL_URL`.

## Tests

```bash
cd backend && .venv/Scripts/python -m pytest          # TEST_MODEL_DIR=model also runs the real-model tests
cd frontend && npm run lint && npm test && npm run build
```

## Data and licences

- The classifier was trained on research-licensed hotel reviews; keep the model files private.
- Cluster files hold review text for quotes: keep them out of git and out of public storage. The site shows
  aggregates and single-sentence quotes with reviewer names removed.
