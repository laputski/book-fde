#!/bin/sh
# Run a command while holding a directory lock, so that two runs of the same
# check (for example two authors, or two editors working in parallel) do not
# overwrite each other's extracted files. mkdir is atomic, so exactly one run
# holds the lock; the others wait. A lock older than STALE_MINUTES (default
# 30) is taken to be left by a killed run and is removed.
# Usage: tools/with_lock.sh LOCKDIR command [args...]
# Exit status: the command's.
lock=$1
shift
stale=${STALE_MINUTES:-30}
while ! mkdir "$lock" 2>/dev/null; do
  if [ -n "$(find "$lock" -maxdepth 0 -mmin +"$stale" 2>/dev/null)" ]; then
    rmdir "$lock" 2>/dev/null
    continue
  fi
  sleep 0.2
done
trap 'rmdir "$lock" 2>/dev/null' EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
"$@"
