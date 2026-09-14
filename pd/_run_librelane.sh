#!/bin/bash
set -e
cd /mnt/c/Users/bomma/projects/tensor-accel-coproc/pd
source /tmp/lltest/bin/activate
export PATH="$HOME/openroad-bin/bin:$HOME/opensta/bin:$PATH"
export _LLN_OVERRIDE_YOSYS="$(pwd)/_yosys_shim.py"
which openroad
openroad -version
echo "=== running librelane ==="
librelane --pdk-root "$HOME/.ciel" --pdk ihp-sg13g2 librelane/config.json
