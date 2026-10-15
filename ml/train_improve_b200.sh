#!/usr/bin/env bash
# Doon View: improve the model, judged by the guests' own ratings.
#
#   bash ml/train_improve_b200.sh
#
# Run it in the folder of the earlier "auto" run: environments, the teacher download and its v1 labels are reused.
#   diagnose  grades the v1 teacher, the auto run's out-of-fold models and its int8 export against the guests'
#             Google/TripAdvisor sub-ratings, so the report says whether labels or compression lost the complaints
#   teacher   relabels Mussoorie and the 30,000 outside reviews with guide v2 (brief complaints count), to
#             <model>-v2.jsonl; the v1 labels stay untouched
#   cv, evaluate, pick   xsmall and base on the v2 labels; a candidate that catches fewer guest-rated complaints than
#             the app's model can neither win nor ship
#   final, export        the int8 export must keep 90% of its fp32 complaints on every aspect, or it is refused
# Ends with a VERDICT, like the auto run. Results get their own names (*-improve), earlier runs stay.
export RUN_TAG="${RUN_TAG:-improve}"
export TEACHER_GUIDE="${TEACHER_GUIDE:-v2}"
export DIAGNOSE="${DIAGNOSE:-1}"
export DIAGNOSE_TAG="${DIAGNOSE_TAG:-auto}"
export EXTERNAL_ROWS="${EXTERNAL_ROWS:-30000}"
export MUSSOORIE_REPEAT="${MUSSOORIE_REPEAT:-3}"
export BACKBONES="${BACKBONES:-microsoft/deberta-v3-xsmall microsoft/deberta-v3-base}"
export SEEDS="${SEEDS:-13}"
export EPOCHS="${EPOCHS:-6}"
export AUTO_SELECT=1
export LAUNCHER=train_improve_b200.sh
# The unit tests changed with this run: run them again before anything expensive, unless this run already did
here="$(cd "$(dirname "$0")" && pwd)"
[[ -f "$here/runs/.improve_tests_rerun" ]] || { rm -f "$here/runs/.done_test"; mkdir -p "$here/runs"; touch "$here/runs/.improve_tests_rerun"; }
exec bash "$here/train_b200.sh"
