#!/usr/bin/env bash
# Doon View: train the review model on the Mussoorie reviews only, on a B200 (a MIG slice is fine).
#
#   mkdir -p /workspace/doonview && cd /workspace/doonview && python3 -m zipfile -e /path/to/doon-view-train.zip .
#   export HF_TOKEN=<write token>      # optional: compare with the current model, and back up off the machine
#   bash ml/train_b200.sh
#
# The checks run in front of you; then the run moves to the background (it survives closing the terminal) and the
# log is shown live. Ctrl+C only stops watching. Run the same command again to watch, or to resume after a failure:
# finished stages are skipped (delete ml/runs/.done_<stage> to redo one).
#
#   setup     .venv (PyTorch for this driver, pinned) and .venv-teacher (vLLM), each isolated from the image's Python
#   test      unit tests
#   data      data/reviews.csv -> 1,657 text reviews with 5 grouped, stratified folds
#   teacher   an open LLM labels aspects for every review (Qwen3-30B-A3B-FP8, else Qwen3-8B)
#   cv        5-fold cross-validation per backbone: out-of-fold predictions for every review
#   evaluate  all candidates on the same reviews, incl. the current app model when HF_TOKEN is set
#   final     the shipped backbone trained on all reviews, for the epoch count cross-validation chose
#   export    int8 ONNX the app loads, with its CPU self-check answers, zipped
#   backup    model zip + results to a PRIVATE Hugging Face repo (never the review data)
set -euo pipefail
cd "$(dirname "$0")"
source ./python_env.sh

# ── settings (override with environment variables) ───────────────────────
TEACHER_MODEL="${TEACHER_MODEL:-Qwen/Qwen3-30B-A3B-FP8}"   # MoE, ~31 GB in FP8: fits a 45 GB slice
TEACHER_FALLBACK="${TEACHER_FALLBACK:-Qwen/Qwen3-8B}"
TEACHER_PORT="${TEACHER_PORT:-8001}"
BACKBONES="${BACKBONES:-microsoft/deberta-v3-xsmall microsoft/deberta-v3-small microsoft/deberta-v3-base}"
FINAL_BACKBONE="${FINAL_BACKBONE:-microsoft/deberta-v3-xsmall}"   # the size the app's small server can run
SEEDS="${SEEDS:-13 14 15}"
EPOCHS="${EPOCHS:-8}"                    # tried in cross-validation; the best count is used for the final model
COMPARE_REPO="${COMPARE_REPO:-strange-exe/revlens-classifier}"     # the model the app uses today
COMPARE_FILE="${COMPARE_FILE:-deberta-v3-xsmall-s13-food2-u8.zip}"
HF_REPO="${HF_REPO:-}"                   # default <your user>/doon-view-model (always private)
STAGES="${STAGES:-setup test data teacher cv evaluate final export backup}"
TORCH_CUDA="${TORCH_CUDA:-}"
DATA=data/processed
LOG=runs/train.log
PIDFILE=runs/train.pid
mkdir -p runs/logs

say()  { printf '\n\033[1;36m== %s\033[0m\n' "$*"; }
warn() { printf '\033[1;33m%s\033[0m\n' "$*"; }
die()  { printf '\n\033[1;31mSTOPPED: %s\033[0m\n' "$*"; rm -f "$PIDFILE"; exit 1; }
follow_log() {
  echo "Live log below. Ctrl+C stops WATCHING only; the run continues. Watch again or resume: bash $(pwd)/train_b200.sh"
  exec tail -n 200 -f "$LOG"
}

# ── foreground: checks, then hand over to a background copy ──────────────
if [[ -z "${TRAIN_INSIDE:-}" ]]; then
  if [[ -f $PIDFILE ]] && kill -0 "$(cat "$PIDFILE")" 2>/dev/null; then
    echo "already running (pid $(cat "$PIDFILE"))."; follow_log
  fi
  say "preflight"
  [[ -f ../backend/app/labelling.py ]] || die "backend/ must sit next to ml/: extract the whole zip into one empty folder"
  [[ -f ../data/reviews.csv ]] || die "data/reviews.csv is missing: it must sit next to ml/ (data/reviews.csv)"
  command -v nvidia-smi >/dev/null && nvidia-smi -L || die "no NVIDIA GPU visible (nvidia-smi)"
  command -v python3 >/dev/null || die "python3 is missing"
  python3 -c 'import sys; sys.exit(sys.version_info < (3, 10))' || die "Python 3.10+ needed, found $(python3 -V)"
  missing=()
  command -v curl >/dev/null || missing+=(curl)
  python3 -c 'import venv, ensurepip' 2>/dev/null \
    || missing+=("python$(python3 -c 'import sys; print(f"{sys.version_info[0]}.{sys.version_info[1]}")')-venv")
  if (( ${#missing[@]} )); then
    if [[ $(id -u) == 0 ]] && command -v apt-get >/dev/null; then
      DEBIAN_FRONTEND=noninteractive apt-get update -qq && DEBIAN_FRONTEND=noninteractive apt-get install -y -qq "${missing[@]}"
    else
      die "missing system packages: ${missing[*]} (sudo apt-get install -y ${missing[*]})"
    fi
  fi
  free_gb=$(( $(df -Pk . | awk 'NR==2 {print $4}') / 1024 / 1024 ))
  (( free_gb >= 80 )) || die "only ${free_gb} GB free; the teacher LLM (~31 GB), two environments and models need ~80 GB"
  [[ -n "${HF_TOKEN:-}" ]] || warn "HF_TOKEN not set: no comparison with the current model and no backup."
  echo "preflight OK: $(nvidia-smi -L | head -1 | cut -c1-70) | ${free_gb} GB free | $(python3 -V)"
  : > "$LOG"
  if command -v setsid >/dev/null; then
    TRAIN_INSIDE=1 setsid nohup bash "$(pwd)/train_b200.sh" >>"$LOG" 2>&1 </dev/null &
  else
    TRAIN_INSIDE=1 nohup bash "$(pwd)/train_b200.sh" >>"$LOG" 2>&1 </dev/null &
  fi
  echo $! > "$PIDFILE"
  say "started in the background (pid $!)"
  [[ -n "${TRAIN_NO_FOLLOW:-}" ]] || follow_log
  exit 0
fi

# ── background run: everything below goes to runs/train.log ──────────────
echo $$ > "$PIDFILE"
trap 'rc=$?; rm -f "$PIDFILE"; if (( rc )); then printf "\nSTOPPED with exit %s: see above. Run the same command to resume.\n" "$rc"; fi' EXIT
isolate_python_env
export DOONVIEW_BACKEND="$(cd ../backend && pwd)"
export HF_HOME="${HF_HOME:-$(cd .. && pwd)/hf-cache}"   # model downloads stay on this volume
mkdir -p "$HF_HOME"

log()  { printf '\n\033[1m[%s] %s\033[0m\n' "$(date +%H:%M:%S)" "$*"; }
want() { [[ " $STAGES " == *" $1 "* ]]; }
stage() {  # stage <name> <function>: run unless done; only mark done if it really succeeded
  local name=$1 fn=$2
  want "$name" || return 0
  if [[ -f "runs/.done_$name" ]]; then log "skip $name (done; rm runs/.done_$name to redo)"; return; fi
  log "stage: $name"
  set +e
  ( set -e; "$fn" ) 2>&1 | tee "runs/logs/$name.log"
  local rc=${PIPESTATUS[0]}
  set -e
  (( rc == 0 )) || { log "FAILED: $name (exit $rc), log runs/logs/$name.log"; exit "$rc"; }
  date > "runs/.done_$name"
}

driver_cuda_tag() {  # the PyTorch CUDA build this driver can run (Blackwell needs CUDA >= 12.8)
  local v major minor
  v=$(nvidia-smi | grep -oE 'CUDA Version: [0-9]+\.[0-9]+' | grep -oE '[0-9]+\.[0-9]+')
  major=${v%.*}; minor=${v#*.}
  if (( major >= 13 )); then echo cu130
  elif (( major == 12 && minor >= 8 )); then echo cu128
  else echo "driver supports CUDA $v; a B200 needs >= 12.8" >&2; return 1
  fi
}
gpu_ok() { "$1" -c "import torch; torch.zeros(1).cuda(); print('GPU:', torch.cuda.get_device_name(), '| torch', torch.__version__)"; }

setup() {
  local tag; tag=${TORCH_CUDA:-$(driver_cuda_tag)}
  echo "driver -> PyTorch build $tag"
  if [[ -d .venv ]] && { grep -qiE '^include-system-site-packages *= *true' .venv/pyvenv.cfg \
       || ! gpu_ok .venv/bin/python 2>/dev/null || ! torch_is_ours .venv >/dev/null 2>&1; }; then
    echo ".venv is not a clean GPU-ready env of its own: rebuilding it"; rm -rf .venv
  fi
  [[ -d .venv ]] || python3 -m venv .venv
  .venv/bin/pip install --upgrade pip
  if ! gpu_ok .venv/bin/python 2>/dev/null || ! torch_is_ours .venv >/dev/null 2>&1; then
    .venv/bin/pip install --force-reinstall torch --index-url "https://download.pytorch.org/whl/$tag"
  fi
  torch_is_ours .venv
  .venv/bin/python -c "import torch; print('torch==' + torch.__version__)" > runs/torch-pin.txt
  .venv/bin/pip install -r requirements.txt -c runs/torch-pin.txt
  gpu_ok .venv/bin/python
  .venv/bin/pip freeze > runs/pip-freeze.txt

  # vLLM in its own env: on a CUDA 12.8 driver, pin the last line built for 12.8, with transformers < 5
  rm -f runs/vllm_ok
  [[ -d .venv-teacher ]] || python3 -m venv .venv-teacher
  .venv-teacher/bin/pip install --upgrade pip uv
  local spec=(vllm)
  [[ $tag == cu128 ]] && spec=("vllm==0.11.0" "transformers>=4.56,<5")
  [[ -n ${VLLM_SPEC:-} ]] && read -ra spec <<< "$VLLM_SPEC"
  if .venv-teacher/bin/uv pip install --python .venv-teacher/bin/python "${spec[@]}" --torch-backend="$tag" \
     && gpu_ok .venv-teacher/bin/python && torch_is_ours .venv-teacher \
     && .venv-teacher/bin/python -c "import vllm; print('vLLM', vllm.__version__)"; then
    touch runs/vllm_ok
  else
    echo "vLLM is not usable here: the teacher will use transformers (slower, same guide)"
  fi
}

test_() { .venv/bin/python -m pytest tests -q; }

data() {
  .venv/bin/python -m doonview_ml.data --reviews ../data/reviews.csv --sub-ratings ../data/sub_ratings.csv --out "$DATA"
}

serve_and_label() {  # serve_and_label <model>: vLLM server, label everything, stop the server; 1 if it can't serve
  local model=$1 pid ready=0
  .venv-teacher/bin/vllm serve "$model" --port "$TEACHER_PORT" --max-model-len 4096 --gpu-memory-utilization 0.85 \
    > "runs/logs/vllm-${model##*/}.log" 2>&1 &
  pid=$!
  for _ in $(seq 1 180); do
    if curl -sf "http://localhost:$TEACHER_PORT/health" >/dev/null; then ready=1; break; fi
    kill -0 "$pid" 2>/dev/null || break
    sleep 10
  done
  if (( ! ready )); then
    echo "vLLM could not serve $model:"; tail -n 8 "runs/logs/vllm-${model##*/}.log" || true
    kill "$pid" 2>/dev/null || true; wait "$pid" 2>/dev/null || true
    return 1
  fi
  local rc=0
  .venv/bin/python -m doonview_ml.teacher --backend openai --model "$model" \
    --base-url "http://localhost:$TEACHER_PORT/v1" --data "$DATA" --workers 32 || rc=$?
  kill "$pid" 2>/dev/null || true; wait "$pid" 2>/dev/null || true   # free the GPU for training
  return $rc
}

teacher() {
  local used=""
  if [[ -f runs/vllm_ok ]]; then
    if serve_and_label "$TEACHER_MODEL"; then used=$TEACHER_MODEL
    elif serve_and_label "$TEACHER_FALLBACK"; then used=$TEACHER_FALLBACK
    fi
  fi
  if [[ -z $used ]]; then
    .venv/bin/python -m doonview_ml.teacher --backend hf --model "$TEACHER_FALLBACK" --data "$DATA" --batch-size 16
    used=$TEACHER_FALLBACK
  fi
  echo "${used##*/}" > runs/teacher-name
  local labels="$DATA/teacher/${used##*/}.jsonl"
  echo "teacher $used: $(wc -l < "$labels") labels"
  .venv/bin/python - "$labels" <<'PY'
import json, sys, itertools
for line in itertools.islice(open(sys.argv[1], encoding="utf-8"), 5):  # spot check: these should look sensible
    print(line.strip()[:240])
PY
}

teacher_labels() { echo "$DATA/teacher/$(cat runs/teacher-name).jsonl"; }

lr_for() {  # xsmall's model card fine-tunes at 4.5e-5; larger DeBERTa-v3 sizes at 2e-5
  [[ $1 == *xsmall* ]] && echo 4.5e-5 || echo 2e-5
}

cv() {
  for backbone in $BACKBONES; do
    for seed in $SEEDS; do
      local out="runs/cv-${backbone##*/}-s$seed"
      if [[ -f $out/cv.json ]]; then echo "skip $out (done)"; continue; fi
      echo "== cross-validation: $backbone seed $seed"
      .venv/bin/python -m doonview_ml.train cv --backbone "$backbone" --data "$DATA" --teacher "$(teacher_labels)" \
        --epochs "$EPOCHS" --lr "$(lr_for "$backbone")" --seed "$seed" --out "$out"
    done
  done
}

evaluate() {
  local compare=()
  if [[ -n "${HF_TOKEN:-}" && ! -f runs/current-model/labels.json ]]; then
    .venv/bin/python - "$COMPARE_REPO" "$COMPARE_FILE" runs/current-model <<'PY' || echo "could not download the current model: comparison skipped"
import sys, zipfile
from huggingface_hub import hf_hub_download
zipfile.ZipFile(hf_hub_download(sys.argv[1], sys.argv[2], repo_type="model")).extractall(sys.argv[3])
print(f"current model {sys.argv[2]} -> {sys.argv[3]}")
PY
  fi
  [[ -f runs/current-model/labels.json ]] && compare=(--compare-model runs/current-model)
  MODEL_THREADS=8 .venv/bin/python -m doonview_ml.evaluate --data "$DATA" --teacher "$(teacher_labels)" \
    --cv runs/cv-*/ "${compare[@]}" --out runs/report
}

final_name() { echo "final-${FINAL_BACKBONE##*/}"; }

final() {
  local seed=${SEEDS%% *} epochs
  epochs=$(.venv/bin/python -c "import json; print(json.load(open('runs/cv-${FINAL_BACKBONE##*/}-s$seed/cv.json'))['best_epochs'])")
  echo "final model: $FINAL_BACKBONE, all reviews, $epochs epochs (chosen by cross-validation)"
  .venv/bin/python -m doonview_ml.train final --backbone "$FINAL_BACKBONE" --data "$DATA" --teacher "$(teacher_labels)" \
    --epochs "$epochs" --lr "$(lr_for "$FINAL_BACKBONE")" --seed "$seed" --out "runs/$(final_name)"
}

export_() {
  local name; name="doon-view-${FINAL_BACKBONE##*/}"
  .venv/bin/python -m doonview_ml.export --run "runs/$(final_name)" --out "artifacts/$name" --data "$DATA/reviews.parquet"
  .venv/bin/python - "artifacts/$name" <<'PY'
import sys, zipfile
d = sys.argv[1]
with zipfile.ZipFile(d + ".zip", "w", zipfile.ZIP_DEFLATED) as z:
    for f in ("labels.json", "tokenizer.json", "model.int8.onnx"):
        z.write(f"{d}/{f}", f)
print(f"model zip: {d}.zip")
PY
}

backup() {
  local name; name="doon-view-${FINAL_BACKBONE##*/}"
  shopt -s nullglob
  local parts=(runs/report runs/cv-*/cv.json runs/logs "$DATA/manifest.json" "$DATA"/teacher/*.jsonl \
               artifacts/*/parity.json runs/pip-freeze.txt runs/torch-pin.txt)
  tar czf runs/doon-view-results.tgz "${parts[@]}"
  echo "results bundle: runs/doon-view-results.tgz (review IDs and labels only, no review text)"
  if [[ -z "${HF_TOKEN:-}" ]]; then
    warn "NOT BACKED UP (no HF_TOKEN). Copy artifacts/$name.zip and runs/doon-view-results.tgz off this machine now."
    return 0
  fi
  .venv/bin/python - "artifacts/$name.zip" runs/doon-view-results.tgz "$HF_REPO" <<'PY'
import os, sys
from huggingface_hub import HfApi
api = HfApi(token=os.environ["HF_TOKEN"])
repo = sys.argv[3] or f"{api.whoami()['name']}/doon-view-model"
api.create_repo(repo, repo_type="model", private=True, exist_ok=True)
if not api.repo_info(repo, repo_type="model").private:
    sys.exit(f"{repo} is PUBLIC: make it private or set HF_REPO to another name")
for path in sys.argv[1:3]:
    api.upload_file(path_or_fileobj=path, path_in_repo=os.path.basename(path), repo_id=repo, repo_type="model")
    print(f"uploaded {path} -> {repo}")
print(f"MODEL_URL=https://huggingface.co/{repo}/resolve/main/{os.path.basename(sys.argv[1])}")
PY
}

# ── run ──────────────────────────────────────────────────────────────────
log "run started $(date -u '+%F %T UTC') | teacher $TEACHER_MODEL | backbones: $BACKBONES | seeds: $SEEDS"
stage setup setup
stage test test_
stage data data
stage teacher teacher
stage cv cv
stage evaluate evaluate
stage final final
stage export export_
stage backup backup
log "FINISHED $(date -u '+%F %T UTC'). RESULT:"
cat runs/report/report.md 2>/dev/null || true
echo "Paste the RESULT table to Claude. Ctrl+C to stop watching."
