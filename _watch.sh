#!/bin/bash
LOG=/opt/securetrans/watch.log
: > "$LOG"
LAST_UP=-1
LAST_PID=""
while true; do
  UP=$(awk '{print int($1)}' /proc/uptime)
  PID=$(pgrep -f 'act_runner daemon' | head -1)
  NOW=$(date '+%F %T')
  if [ -n "$UP" ] && [ "$LAST_UP" -ge 0 ] && [ "$UP" -lt "$LAST_UP" ]; then
    echo "$NOW KERNEL-UPTIME-BACKTRACK $UP <- $LAST_UP (内核重启!)" >> "$LOG"
  fi
  if [ "$PID" != "$LAST_PID" ]; then
    echo "$NOW RUNNER-PID $PID (was $LAST_PID)" >> "$LOG"
    LAST_PID="$PID"
  fi
  LAST_UP="$UP"
  sleep 2
done
