#!/usr/bin/env bash
# Run all plenary-busted specs in nvim/tests/.
#
# Note: This script uses NVIM_APPNAME=nvim-rebuild to ensure plenary.nvim
# is available on the runtimepath, and sets rtp+=. to resolve the plugin's
# lua/local_library modules. This is a workaround for environments where
# the default nvim config doesn't have plenary installed. See phase_04.md
# for details and the tests/minimal_init.lua alternative for portability.

set -euo pipefail
cd "$(dirname "$0")/.."
NVIM_APPNAME=nvim-rebuild nvim --headless --cmd "set rtp+=." -c "PlenaryBustedDirectory tests/" -c "qa"
