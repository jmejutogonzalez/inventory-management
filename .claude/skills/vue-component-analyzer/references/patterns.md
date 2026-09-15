# Vue 3 Optimization Patterns

Checklist for the analyzer. Each item: what to look for, why it matters, and what to suggest.

---

## 1. Rendering Performance

### 1.1 Function calls in templates that do real work
**Look for:** `v-for="x in getSomething(arg)"`, `{{ computeTotal() }}`, or `getX(item).slice(0, 5)` in templates.
**Why:** Template function calls re-run on *every* render of the component, including renders triggered by unrelated state (a modal opening, a hover ref changing). `computed` values are cached until their dependencies change.
**Suggest:** A `computed` per distinct argument, or one computed that groups the results:
```js
// Before: 3 full passes over forecasts per render
// <div v-for="item in getForecastsByTrend('increasing').slice(0, 5)">
const forecastsByTrend = computed(() => {
  const groups = { increasing: [], stable: [], decreasing: [] }
  for (const f of forecasts.value) groups[f.trend]?.push(f)
  return groups
})
// <div v-for="item in forecastsByTrend.increasing.slice(0, 5)">
```
**Not a problem:** Cheap per-item formatters (`getStatusClass(item)`) over small lists. Only flag them if they do lookups, allocate objects, or run over large lists.

### 1.2 Per-item work inside `v-for` rows
**Look for:** Per-row calls that rebuild lookup maps (e.g. `translateCategory` building a `categoryMap` object on every call), or repeated `new Date(...)` / `toLocaleString()` over many rows.
**Suggest:** Hoist constant maps to module scope. Precompute display fields in a `computed` that maps rows once.

### 1.3 Unstable or index keys
**Look for:** `:key="index"`, `:key="idx"`, `:key="i"`, or `v-for` with no `:key`.
**Why:** Index keys cause wrong DOM reuse when lists are filtered or sorted, which happens often here because of the filter system. They are also banned by CLAUDE.md.
**Suggest:** A domain key: `sku`, `id`, `month`, `quarter`. For nested items (`order.items`), use `item.sku`.

### 1.4 `v-if` and `v-for` on the same element
**Why:** In Vue 3, `v-if` has higher priority, so it can't access the loop variable and silently misbehaves.
**Suggest:** Filter in a `computed`, or wrap the element in `<template v-for>`.

### 1.5 Large static subtrees and heavy components
**Look for:** Big inline SVG icons repeated in many places, and static markup blocks inside frequently re-rendering components.
**Suggest:** Extract icons into small components (Vue hoists static content). Use `v-once` for truly static blocks. For long tables (>200 rows), consider pagination or virtualization. Check the actual data sizes in `server/data/` first.

### 1.6 Modals and conditional heavy content
**Look for:** Modals rendered with `v-show`, or modal content that computes derived data while closed.
**Suggest:** `v-if` guards (this codebase already uses `v-if="isOpen && data"`, so confirm consistency). Computeds inside modals should short-circuit when there is no data.

### 1.7 Component granularity
**Look for:** Very large views (Dashboard.vue ~1270 lines, Spending.vue ~850) where local UI state (hover, tooltip, selected row) lives at the top level.
**Why:** Any ref change re-renders the whole view template. Extracting a chart or table into a child component with props limits the re-render to that child.
**Suggest:** Extract a self-contained section (chart card, KPI row, table) that receives computed data as props.

---

## 2. Reactivity

### 2.1 `watch` that only derives state
**Look for:** `watch(src, () => { derived.value = f(src.value) })`.
**Suggest:** Replace with `computed`.

### 2.2 Watchers that refetch
**Look for:** `watch([selectedPeriod, selectedLocation, ...], () => loadX())` repeated per view.
**Check:** Is the watcher list consistent with the filters the endpoint actually supports? (Inventory: warehouse and category only.) Are rapid filter changes causing overlapping requests where a stale response can overwrite a newer one?
**Suggest:** A request-sequence guard or `AbortController`, and possibly a shared `useFilteredResource(fetchFn, filterKeys)` composable. Each view keeps its own filter-key list.

### 2.3 `deep: true` and large reactive objects
**Look for:** Deep watchers, or large read-only API payloads stored in `ref`/`reactive`.
**Suggest:** Watch specific getters. Use `shallowRef` for large arrays that are replaced wholesale rather than mutated (the typical API response pattern here).

### 2.4 Computed chains that sort/filter repeatedly
**Look for:** A sort comparator calling helpers that recompute the same thing for both `a` and `b` (e.g. `getStockStatusKey` called inside `.sort`).
**Suggest:** Precompute keys once per item (map, sort, map back) when lists are non-trivial. Note: this is low impact for small lists.

### 2.5 Mutating props or shared arrays
**Look for:** `.sort()` or `.reverse()` directly on props or refs without `.slice()`, and pushes into prop arrays.
**Suggest:** Copy before sorting, or emit events.

---

## 3. Code Reuse

### 3.1 Duplicated helpers → `utils/` or composables
**Look for:** The same function name (or same body under different names) in multiple files. Common here: currency formatting, `translateCategory`, status to class mappings, date formatting.
**Check:** `client/src/utils/currency.js` and `client/src/composables/` may already provide it. If so, the finding is "use the existing helper".
**Suggest:** Pure functions go in `client/src/utils/*.js`. Functions needing `t()` or reactive state go in a composable (e.g. `useCategoryLabels()` built on `useI18n`).

### 3.2 Duplicated markup → shared components
**Look for:** Near-identical template skeletons. Known candidate: the 5 `*DetailModal.vue` / `ProfileDetailsModal.vue` files all share Teleport → Transition → overlay → container → header with close SVG → body.
**Suggest:** A `BaseModal.vue` with `isOpen` prop, `close` emit, `title` prop/slot, and default slot for the body. Handle Escape-to-close and focus once in the base component.
Other candidates: stat/KPI cards, status badges, loading/error blocks, table wrappers, and bar chart rows.

### 3.3 Duplicated CSS across scoped styles
**Look for:** The same selectors and rules in multiple `<style scoped>` blocks (`.modal-overlay`, `.card`, `.badge`, table styles).
**Suggest:** Move them into the extracted shared component (preferred, because the styles travel with the markup), or into global styles in `App.vue` if purely presentational. Don't suggest a CSS framework.

### 3.4 Duplicated data-loading boilerplate
**Look for:** `loading` / `error` refs plus try/catch/finally plus `onMounted` plus `watch(filters)` repeated in each view.
**Suggest:** A composable returning `{ data, loading, error, reload }`. Keep it thin, and don't hide which filters are sent.

---

## 4. Structure

### 4.1 Oversized components
**Thresholds (guidance, not rules):** >400 lines total, >250 lines of script, >10 top-level refs, or >3 distinct concerns in one file.
**Suggest:** Concrete extraction boundaries (name the new components/composables and what props/emits they'd have), not "split this file".

### 4.2 Mixed API styles
**Observed:** Views use Options-API `export default { setup() { ... return {...} } }`, while most components use `<script setup>`.
**Why:** `<script setup>` is more concise, removes the manual `return {}` (where it's easy to forget or leak bindings), and compiles to slightly more efficient render code.
**Suggest:** Treat it as a consistency/maintenance finding (usually Low/Med impact). Recommend converting opportunistically when a file is already being refactored, not as a standalone mass change.

### 4.3 Prop and emit design
**Look for:** Missing `emits` declarations, props without types, parents passing whole objects when a child needs two fields, and `v-model` candidates implemented as prop plus manual event.
**Suggest:** Typed `defineProps`, declared `defineEmits`, and `defineModel` where it fits.

---

## Impact / Effort Rubric

| Impact | Meaning |
|--------|---------|
| High | Measurable render/fetch cost on common interactions, correctness risk (index keys on filtered lists, race conditions), or duplication across ≥4 files |
| Med | Noticeable maintenance cost, duplication across 2–3 files, perf cost only on large data |
| Low | Consistency/style, micro-optimizations |

| Effort | Meaning |
|--------|---------|
| S | < 30 min, single file |
| M | A few files, new composable/component |
| L | Cross-cutting refactor, touches most views |
