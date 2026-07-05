#!/bin/bash
# Fetch latest WeRead notes and push to GitHub if anything changed.
set -euo pipefail

REPO_DIR="/Users/S/vibe/weread-notes"
LOG_FILE="$REPO_DIR/auto_update.log"
MARKER_FILE="$REPO_DIR/.last_run_date"
export WEREAD_API_KEY="wrk-Q8Wh0ww4TGiv01PqR1dp1wAA"

cd "$REPO_DIR"

TODAY="$(date '+%Y-%m-%d')"
if [ "$(cat "$MARKER_FILE" 2>/dev/null || true)" = "$TODAY" ]; then
  # This is a local backup for GitHub Actions' daily cron; launchd fires on
  # every boot/wake (RunAtLoad) to catch up if the Mac missed the 8am slot,
  # so skip re-running if we already synced today.
  exit 0
fi

{
  echo "===== $(date '+%Y-%m-%d %H:%M:%S') ====="
  python3 fetch_data.py

  if ! git diff --quiet -- data.js; then
    git add data.js
    git commit -m "自动同步笔记数据 $(date '+%Y-%m-%d')"
    git push origin main
    echo "Pushed update."
  else
    echo "No new notes, nothing to push."
  fi
} >> "$LOG_FILE" 2>&1

echo "$TODAY" > "$MARKER_FILE"
