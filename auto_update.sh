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
    # Right after boot/wake, the login keychain can still be mid-unlock,
    # which makes the osxkeychain credential helper fail non-interactively.
    # Retry a few times before giving up (marker stays stale on failure,
    # so the next boot/wake retries the whole thing).
    ok=0
    for i in 1 2 3 4 5; do
      if git push origin main; then ok=1; break; fi
      echo "  push attempt $i failed, retrying in 20s..."
      sleep 20
    done
    if [ "$ok" = "1" ]; then
      echo "Pushed update."
    else
      echo "Push failed after retries."
      exit 1
    fi
  else
    echo "No new notes, nothing to push."
  fi
} >> "$LOG_FILE" 2>&1

echo "$TODAY" > "$MARKER_FILE"
