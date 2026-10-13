# Sourced by run_b200.sh and retrain.sh: make our virtualenvs ignore the machine's own Python packages.
#
# GPU images ship their own stack. NVIDIA's PyTorch container, for example, installs PyTorch 2.7.0a0 system-wide and
# pins every bundled package in /etc/pip/constraint.txt
# (https://docs.nvidia.com/deeplearning/frameworks/pytorch-release-notes/rel-25-03.html). Through PYTHONPATH,
# PIP_*/UV_* variables or global pip/uv config, those leak into a venv: pip then refuses (or silently undoes) the
# CUDA 12.8 torch our .venv needs, or the venv imports the system torch. This clears every such channel:
#   - PIP_CONFIG_FILE=/dev/null disables ALL pip config files (https://pip.pypa.io/en/stable/topics/configuration/)
#   - UV_NO_CONFIG / UV_NO_SYSTEM_CONFIG do the same for uv (https://docs.astral.sh/uv/reference/environment/)
#   - inherited constraint/override/path variables are unset (names are reported, values never printed)
isolate_python_env() {
  local v leaked=()
  for v in PYTHONPATH PYTHONHOME PYTHONSTARTUP PYTHONUSERBASE \
           PIP_CONSTRAINT PIP_REQUIREMENT PIP_PREFIX PIP_TARGET PIP_USER PIP_ROOT PIP_NO_DEPS PIP_NO_BUILD_ISOLATION \
           UV_CONSTRAINT UV_OVERRIDE UV_BUILD_CONSTRAINT UV_SYSTEM_PYTHON UV_PYTHON UV_PROJECT_ENVIRONMENT \
           VIRTUAL_ENV CONDA_PREFIX; do
    if [[ -n "${!v:-}" ]]; then leaked+=("$v"); unset "$v"; fi
  done
  export PIP_CONFIG_FILE=/dev/null UV_NO_CONFIG=1 UV_NO_SYSTEM_CONFIG=1 PYTHONNOUSERSITE=1 PIP_DISABLE_PIP_VERSION_CHECK=1
  if (( ${#leaked[@]} )); then echo "python env: ignoring inherited ${leaked[*]}"; fi
  if [[ -f /etc/pip/constraint.txt ]]; then
    echo "python env: this image pins its packages in /etc/pip/constraint.txt ($(grep -iE '^torch[=<>~ ]' /etc/pip/constraint.txt | head -1 || echo 'torch not listed')); our venvs ignore it"
  fi
}

# torch_is_ours <venv>: the venv's torch is its OWN install, not the image's system torch
torch_is_ours() {
  "$1/bin/python" - "$1" <<'PY'
import os, sys
import torch
venv = os.path.realpath(sys.argv[1])
where = os.path.realpath(torch.__file__)
if not where.startswith(venv + os.sep):
    sys.exit(f"torch {torch.__version__} is loaded from {where}, outside {venv}")
print(f"torch {torch.__version__} from {sys.argv[1]} (not the system install)")
PY
}
