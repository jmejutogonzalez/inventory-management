#!/usr/bin/env bash
# Heuristic scanner for Vue components. Output is a list of CANDIDATES that
# must be verified by reading the code — grep can't understand templates.
# Usage: scan.sh [path]   (file or directory, default: client/src)
set -uo pipefail

TARGET="${1:-client/src}"
if [ -f "$TARGET" ]; then
  FILES=("$TARGET")
  # Cross-file duplication checks still need the whole app to compare against
  SEARCH_ROOT="$(dirname "$TARGET")/.."
else
  FILES=()
  while IFS= read -r f; do FILES+=("$f"); done < <(find "$TARGET" -name '*.vue' -not -path '*/node_modules/*' | sort)
  SEARCH_ROOT="$TARGET"
fi

if [ ${#FILES[@]} -eq 0 ]; then
  echo "No .vue files found under $TARGET" >&2
  exit 1
fi

section() { printf '\n## %s\n' "$1"; }

section "Component size (lines: total / script / template)"
for f in "${FILES[@]}"; do
  total=$(wc -l < "$f" | tr -d ' ')
  script=$(awk '/<script/{s=1;next} /<\/script>/{s=0} s' "$f" | wc -l | tr -d ' ')
  # Only the outermost template: nested <template v-for> tags would otherwise end the count early
  tmpl=$(awk '/^<template/{s=1;next} /^<\/template>/{s=0} s' "$f" | wc -l | tr -d ' ')
  flag=""
  [ "$total" -gt 400 ] && flag="  <-- large"
  printf '%5s / %4s / %4s  %s%s\n' "$total" "$script" "$tmpl" "$f" "$flag"
done | sort -rn

section "API style"
for f in "${FILES[@]}"; do
  if grep -q '<script setup' "$f"; then echo "script-setup  $f"
  elif grep -q 'setup()' "$f"; then echo "options-setup $f"
  else echo "options       $f"; fi
done | sort

section "Index used as v-for key"
grep -nE ':key="(index|idx|i)"' "${FILES[@]}" || echo "(none)"

section "v-for without :key within 3 lines"
for f in "${FILES[@]}"; do
  # v-for attributes often span multiple lines, so look ahead a few lines for :key
  awk -v file="$f" '
    { lines[NR]=$0 }
    END {
      for (n=1; n<=NR; n++) if (lines[n] ~ /v-for=/) {
        ok=0
        for (k=n; k<=n+3 && k<=NR; k++) if (lines[k] ~ /:key=/) ok=1
        if (!ok) printf "%s:%d:%s\n", file, n, lines[n]
      }
    }' "$f"
done

section "Function call in v-for source (re-runs every render)"
grep -nE 'v-for="[^"]+ in [A-Za-z_$][A-Za-z0-9_$.]*\(' "${FILES[@]}" || echo "(none)"

section "Function calls in interpolations, excluding t() i18n lookups (top files by count)"
for f in "${FILES[@]}"; do
  # t('key') is a cheap lookup on every view; counting it would bury the real per-render work
  c=$(awk '/^<template/{s=1;next} /^<\/template>/{s=0} s' "$f" \
    | sed -E "s/(^|[^A-Za-z0-9_.])\\\$?t\([^)]*\)/\1/g" \
    | grep -oE '\{\{[^}]*[A-Za-z_]\([^}]*\}\}' | wc -l | tr -d ' ')
  [ "$c" -gt 0 ] && printf '%4s  %s\n' "$c" "$f"
done | sort -rn | head -10

section "v-if and v-for on same line"
grep -nE 'v-for=.*v-if=|v-if=.*v-for=' "${FILES[@]}" || echo "(none)"

section "Deep watchers"
grep -nE 'deep:\s*true' "${FILES[@]}" || echo "(none)"

section "Helper functions defined in multiple files (name: count files)"
grep -rhoE --include='*.vue' --include='*.js' \
  '(const|function) +[a-z][A-Za-z0-9]+ *(= *(async *)?\(|\()' "$SEARCH_ROOT" 2>/dev/null \
  | sed -E 's/(const|function) +([A-Za-z0-9]+).*/\2/' | sort | uniq -c | sort -rn \
  | awk '$1 > 1' | while read -r count name; do
      files=$(grep -rlE --include='*.vue' --include='*.js' "(const|function) +$name *(= *(async *)?\(|\()" "$SEARCH_ROOT" | tr '\n' ' ')
      printf '%-28s %s  %s\n' "$name" "$count" "$files"
    done | head -25

section "CSS class selectors repeated across 3+ files"
find "$SEARCH_ROOT" -name '*.vue' -not -path '*/node_modules/*' | while read -r f; do
  awk '/<style/{s=1;next} /<\/style>/{s=0} s' "$f" \
    | grep -oE '^\.[A-Za-z][A-Za-z0-9_-]*( *\{|,)' | sed -E 's/ *[{,]$//' | sort -u
done | sort | uniq -c | sort -rn | awk '$1 >= 3 { printf "%3s files  %s\n", $1, $2 }' | head -25

section "Inline SVG blocks per file (icon extraction candidates)"
for f in "${FILES[@]}"; do
  c=$(grep -c '<svg' "$f")
  [ "$c" -gt 2 ] && printf '%4s  %s\n' "$c" "$f"
done | sort -rn

echo
echo "Reminder: these are candidates. Verify each by reading the code before reporting."
