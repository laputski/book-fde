#!/bin/sh
# Every check of the repository, in order: the build, the structural
# invariants of both locales, the diagram rules, the public/private
# boundary, the listings, the unit tests of the tools, and the offline
# part of the staleness detector. With private/ present, the private
# build is checked as well (locally only; CI has no private/).
set -e
cd "$(dirname "$0")"
./build.sh
python3 tools/check_isomorphism.py fde-advanced.html
python3 tools/dia_lint.py fde-advanced.html
python3 tools/check_private.py fde-advanced.html
python3 tools/style_lint.py
python3 tools/check_reference.py fde-advanced.html
python3 tools/check_contrast.py
python3 tools/check_fictional_data.py
./check_examples.sh
if [ -d private/parts ] && ls private/parts/ru/*.html >/dev/null 2>&1; then
  ./build.sh --private
  python3 tools/check_isomorphism.py fde-advanced.private.html --private
  python3 tools/dia_lint.py fde-advanced.private.html
  ./check_examples.sh --private
fi
python3 -m pytest -q tests
python3 tools/check_drift.py --no-links
