#!/bin/bash
# progress_helpers.sh
#
# Shared live-progress monitor for long-running commands (recon-all,
# segmentBS.sh, ...). It is meant to be sourced, not executed:
#
#   source /path/to/progress_helpers.sh
#   run_with_progress "$LOG_PATH" command arg1 arg2 ...
#
# The function is tool-agnostic: "command" can be classic recon-all, FastSurfer,
# segmentBS.sh or anything else. It only needs the path of the log file that the
# tool writes while it runs, so progress can be reported while the command runs
# in the background.
#
# Progress is printed by an optional helper script (RECON_PROGRESS, default
# ~/recon_progress.py) that receives the log path as its only argument. If that
# script does not exist, the command simply runs without progress output.

RECON_PROGRESS="${RECON_PROGRESS:-$HOME/recon_progress.py}"
POLL_INLINE_INTERVAL="${POLL_INLINE_INTERVAL:-300}"   # seconds between progress reports

run_with_progress() {
    local log_path="$1"
    shift
    # "$@" is the full command, run in the background
    "$@" &
    local pid=$!

    if [ -f "$RECON_PROGRESS" ]; then
        while kill -0 "$pid" 2>/dev/null; do
            sleep "$POLL_INLINE_INTERVAL"
            if kill -0 "$pid" 2>/dev/null && [ -f "$log_path" ]; then
                python3 "$RECON_PROGRESS" "$log_path" 2>/dev/null
            fi
        done
    fi

    wait "$pid"
    return $?
}
