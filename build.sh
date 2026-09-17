#!/bin/sh
# Assemble the book: shell, Russian locale, English locale, page script.
# Each locale is the sorted concatenation of parts/<locale>/*.html; with
# --private the chapters of private/parts/<locale>/ join the same sorted
# sequence and the output is fde-advanced.private.html (never committed).
# The {{SOURCES_CHECKED_AT}} placeholder is filled from data/sources_meta.json,
# and every {{DIA}} placeholder becomes a diagram number, continuous per locale.
cd "$(dirname "$0")"
OUT=fde-advanced.html
PRIVATE=""
if [ "$1" = "--private" ]; then OUT=fde-advanced.private.html; PRIVATE=1; fi
CHECKED_AT=$(python3 -c "import json; print(json.load(open('data/sources_meta.json'))['checked_at'])")

locale_files() {
  # $1 = locale. Files of both roots, ordered by basename.
  if [ -n "$PRIVATE" ] && [ -d "private/parts/$1" ]; then
    ls parts/"$1"/*.html private/parts/"$1"/*.html 2>/dev/null
  else
    ls parts/"$1"/*.html 2>/dev/null
  fi | awk -F/ '{print $NF "\t" $0}' | LC_ALL=C sort | cut -f2
}

{
  cat parts/00-head.html
  printf '\n<div class="locale" data-locale="ru">\n'
  for f in $(locale_files ru); do cat "$f"; printf '\n'; done
  printf '\n</div>\n<div class="locale" data-locale="en">\n'
  for f in $(locale_files en); do cat "$f"; printf '\n'; done
  printf '\n</div>\n'
  cat parts/99-tail.html
} | sed "s/{{SOURCES_CHECKED_AT}}/$CHECKED_AT/g" | python3 tools/number_figures.py > "$OUT"
echo "built: $OUT, $(wc -c < "$OUT") bytes, sources checked $CHECKED_AT"
