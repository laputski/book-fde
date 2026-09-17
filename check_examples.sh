#!/bin/sh
# Extract the listings from an assembled book and verify them with tools:
# parse, ruff, stub injection, mypy, and execution of the runnable ones.
# Usage: ./check_examples.sh            # the public book into examples/
#        ./check_examples.sh --private  # the private build into private/examples/
set -e
cd "$(dirname "$0")"
# Two runs at once would overwrite each other's extracted files: take the lock first.
if [ -z "$CHECK_EXAMPLES_LOCKED" ]; then
  CHECK_EXAMPLES_LOCKED=1 exec sh tools/with_lock.sh .check_examples.lock ./check_examples.sh "$@"
fi
SRC=fde-advanced.html
OUT=examples
if [ "$1" = "--private" ]; then
  SRC=fde-advanced.private.html
  OUT=private/examples
  mkdir -p "$OUT"
  cp examples/stubs.py examples/mypy.ini "$OUT"/
fi
python3 extract_examples.py "$SRC" "$OUT"
python3 -c '
import ast, pathlib, sys
out = pathlib.Path(sys.argv[1])
bad = 0
for f in sorted(out.glob("*.py")):
    try:
        ast.parse(f.read_text(encoding="utf-8"), filename=str(f))
    except SyntaxError as e:
        bad += 1
        print(f"{f.name}:{e.lineno}: {e.msg}")
print(f"syntax check: {bad} errors")
sys.exit(1 if bad else 0)' "$OUT"
ruff check --select E9,F63,F7,F82,B,SIM,RUF,PIE,C4,PERF \
  --ignore F821,F704,F706,F401,RUF001,RUF002,RUF003,SIM105,PERF203,PIE790,RUF005,RUF023,B905 \
  --output-format concise "$OUT"
python3 prepare_examples.py "$OUT"
python3 -m mypy --config-file "$OUT"/mypy.ini "$OUT"
python3 run_examples.py "$OUT"
