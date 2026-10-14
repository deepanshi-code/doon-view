#!/usr/bin/env bash
# Doon View mixed model: Mussoorie reviews + a TripAdvisor sample, same teacher, same Mussoorie-only scoring.
#
#   bash ml/train_mix_b200.sh
#
# In the folder of an earlier train_b200.sh run, setup, data and the Mussoorie teacher labels are reused and its
# results are left alone: this run writes runs/cv-mix-*, runs/report-mix, runs/train-mix.log and
# artifacts/doon-view-mix-*.zip. In an empty folder it runs the whole pipeline first.
# Any setting can be overridden, e.g. SEEDS=13 for a quicker single-seed run, EXTERNAL_ROWS=8000 for a faster teacher.
export RUN_TAG="${RUN_TAG:-mix}"
export EXTERNAL_ROWS="${EXTERNAL_ROWS:-15000}"
export MUSSOORIE_REPEAT="${MUSSOORIE_REPEAT:-3}"
export BACKBONES="${BACKBONES:-microsoft/deberta-v3-xsmall}"   # the size the app can serve; add -base to compare
export EPOCHS="${EPOCHS:-4}"                                    # ~19,000 training rows per fold: fewer passes needed
export LAUNCHER=train_mix_b200.sh
exec bash "$(dirname "$0")/train_b200.sh"
