---
name: vue-component-analyzer
description: Analyze Vue 3 component structure and suggest optimizations for rendering performance and code reuse (duplicated logic, extractable components/composables, reactivity pitfalls, template inefficiencies). Use when asked to audit, review, or optimize .vue files, find duplication across components, or suggest refactors in client/src. Produces a prioritized report; does not edit code.
---

# Vue Component Analyzer

Analyze Vue components in `client/src/` and produce a prioritized, evidence-backed report of performance and reuse optimizations. This skill **reports only** — it never edits `.vue` files. Per CLAUDE.md, implementation of any accepted suggestion must be delegated to the **vue-expert** subagent.

## Scope

Determine the target from the user's request:
- **Single file** (e.g. "analyze Dashboard.vue") — deep analysis of that component, plus cross-file duplication checks against the rest of `client/src`.
- **Directory / whole app** (default: `client/src`) — breadth-first: run the scanner, rank the largest/most-flagged files, deep-read the top offenders.

## Workflow

### 1. Run the scanner for signals

```bash
bash .claude/skills/vue-component-analyzer/scripts/scan.sh client/src   # or a single file/dir
```

The scanner is grep-based and emits **candidates, not verdicts**. It covers: component size, API style mix, index keys, missing keys, function calls in `v-for` sources, `v-if`+`v-for` on one element, deep watchers, helper functions defined in multiple files, and CSS selectors repeated across scoped style blocks.

### 2. Verify every candidate by reading the code

Never report a scanner hit without reading the surrounding code. Discard false positives, for example:
- An index key on a static list that never reorders is low-impact — downgrade rather than drop, since CLAUDE.md still prohibits it.
- A "duplicate" helper with the same name but different logic is not duplication.
- A method call in a template over a 5-item static array is not a real performance problem.

### 3. Deep-analyze with the checklist

Read [references/patterns.md](references/patterns.md) and walk the target components through each category:
1. **Rendering performance** — work done per render, list rendering, component boundaries
2. **Reactivity** — overly broad reactivity, watchers vs computed, redundant fetches
3. **Code reuse** — duplicated logic → composables/utils; duplicated markup → components
4. **Structure** — oversized components, mixed API styles, prop/emit design

### 4. Quantify impact where possible

Prefer concrete evidence over generic advice:
- Count how many times a function runs per render (e.g. "called 3x per render, each filtering all N forecasts").
- Count duplicated lines/files (e.g. "`.modal-overlay` styles repeated in 5 files, ~40 lines each").
- Note data sizes from `server/data/*.json` when judging whether an O(n) cost matters.

### 5. Write the report

Use the format below. Rank by **impact ÷ effort**. Cap at ~10 findings for a whole-app run; group minor items into a single "Low priority" list.

## Report Format

````markdown
# Vue Component Analysis: <target>

## Summary
<2–3 sentences: overall health, the single most valuable change, rough total effort>

| # | Finding | Category | Impact | Effort | Files |
|---|---------|----------|--------|--------|-------|
| 1 | ... | Performance / Reuse / Reactivity / Structure | High/Med/Low | S/M/L | n |

## Findings

### 1. <Title>
**Where:** [File.vue:42](client/src/views/File.vue#L42), [Other.vue:10](client/src/components/Other.vue#L10)
**Problem:** <what happens and why it costs something — be specific>
**Suggestion:** <concrete change>

```js
// Before (excerpt)
...
// After (sketch)
...
```

**Risk / notes:** <behavior changes, i18n or filter interactions, what to test>

## Low priority
- <one-liners>

## Suggested next step
<Which findings to hand to vue-expert first, grouped into coherent PR-sized batches>
````

## Project-Specific Rules to Respect

Suggestions must not contradict these (from CLAUDE.md):
- Keys in `v-for` must be unique domain IDs (`sku`, `id`, `month`), never `index`.
- Raw data lives in refs (`allOrders`, `inventoryItems`); derived data in `computed`.
- Inventory has no month dimension — never suggest a shared filter composable that applies `month` to inventory.
- Charts are custom SVG; do not suggest adding a charting library.
- No emojis in UI; styles follow the slate/gray design system in `client/src/App.vue`.
- Any suggested new comments should explain *why*, not *what*.

## Handoff

End by offering to delegate the top batch to **vue-expert**. Do not make the edits yourself.
