#!/usr/bin/env bash
# handoff_facts.sh - read-only. Writes docs/handoff/FACTS.md from the repo itself so no session has to read code to
# describe the project. Touches only this repo (talentsearch.ir). Never reads secrets, never contacts prod, eot.ir or
# app.sepehrtherapy.ir. Re-run after every ship: `bash tools/vps/handoff_facts.sh`.
set -euo pipefail
cd "$(dirname "$0")/../.."
OUT=docs/handoff/FACTS.md
mkdir -p docs/handoff
{
echo "# FACTS (generated, do not edit by hand)"
echo
echo "Generated: $(date -u +%Y-%m-%dT%H:%MZ) from commit $(git rev-parse --short HEAD) on branch $(git rev-parse --abbrev-ref HEAD)."
echo "Regenerate: \`bash tools/vps/handoff_facts.sh\`. Scope: talentsearch.ir only."
echo
echo "## Modules (addons/*, manifest version, python lines, test files)"
echo
echo "| module | version | py lines | in-module tests (suites live in tools/prod: tests_*.py, ts_http_*.py) | depends |"
echo "|---|---|---|---|---|"
for d in addons/*/; do
  m=$(basename "$d"); mf="$d/__manifest__.py"; [ -f "$mf" ] || continue
  v=$(grep -m1 -oP "'version':\s*'\K[^']+" "$mf" || echo "?")
  l=$(find "$d" -name '*.py' -not -path '*/tests/*' -not -name '__manifest__.py' -print0 | xargs -0 cat 2>/dev/null | wc -l)
  t=$(find "$d" -path '*tests*' -name '*.py' 2>/dev/null | wc -l)
  dep=$(grep -m1 -oP "'depends':\s*\[\K[^\]]*" "$mf" | tr -d "' " || true)
  echo "| $m | $v | $l | $t | $dep |"
done
echo
echo "## Routes (controllers, count per module)"
echo
for d in addons/*/; do
  c=$( (grep -rhoE "@http\.route\(" "$d" --include="*.py" 2>/dev/null || true) | wc -l)
  if [ "$c" -gt 0 ]; then echo "- $(basename "$d"): $c"; fi
done
echo
echo "## Docs"
echo
find docs -maxdepth 2 -name '*.md' | sort | sed 's/^/- /'
echo
echo "## Helper agents (.claude/agents)"
echo
ls .claude/agents 2>/dev/null | sed 's/^/- /'
echo
echo "## Toolkit scripts"
echo
ls tools tools/prod tools/vps 2>/dev/null | sed 's/^/- /' | head -80
echo
echo "## Recent commits"
echo
git log --oneline -15 | sed 's/^/- /'
} > "$OUT"
# safety: refuse to leave anything secret-looking in a public repo
if grep -nE '(api[_-]?key|secret|password|token)\s*[:=]\s*[A-Za-z0-9/+_-]{12,}|09[0-9]{9}' "$OUT"; then
  echo "SECRET-LOOKING TEXT in $OUT - removed file"; rm -f "$OUT"; exit 1
fi
wc -l "$OUT"
