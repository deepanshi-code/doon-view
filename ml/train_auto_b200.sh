#!/usr/bin/env bash
# Doon View: the best model this data can give, chosen automatically.
#
#   bash ml/train_auto_b200.sh
#
# Final 5-platform Mussoorie dataset (data/reviews.csv) + 30,000 TripAdvisor reviews, the same teacher for both.
# Cross-validates xsmall and base (the app runs the model only when a market's data is built, never while serving,
# so the bigger model is allowed), picks the winner by a fixed rule (doonview_ml.pick), trains it on everything and
# exports it. The RESULT ends with a VERDICT: ship it, or keep the current model.
#
# In the folder of an earlier run, environments, the teacher model download and every label already made are reused:
# only new reviews are labelled. Earlier results stay where they are (this run writes *-auto names).
# Short on time? BACKBONES=microsoft/deberta-v3-base (skip xsmall) or EPOCHS=4.
export RUN_TAG="${RUN_TAG:-auto}"
export EXTERNAL_ROWS="${EXTERNAL_ROWS:-30000}"
export MUSSOORIE_REPEAT="${MUSSOORIE_REPEAT:-3}"
export BACKBONES="${BACKBONES:-microsoft/deberta-v3-xsmall microsoft/deberta-v3-base}"
export SEEDS="${SEEDS:-13}"
export EPOCHS="${EPOCHS:-6}"            # the mixed xsmall run was still improving at its maximum of 4
export AUTO_SELECT=1
export LAUNCHER=train_auto_b200.sh
exec bash "$(dirname "$0")/train_b200.sh"
