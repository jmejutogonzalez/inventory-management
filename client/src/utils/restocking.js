// Restocking recommendations built from demand forecasts.
// Pure functions (no Vue) so the plan can be recomputed on every slider move and checked from Node.

// Priority: rising demand first, falling demand last. Unknown trends sort to the end.
const TREND_RANK = { increasing: 0, stable: 1, decreasing: 2 }

// Growth % rather than absolute units, so cheap high-volume items
// (e.g. +150 filters) don't automatically outrank expensive ones.
export function growthRate(forecast) {
  if (forecast.current_demand > 0) {
    return (forecast.forecasted_demand - forecast.current_demand) / forecast.current_demand
  }
  return forecast.forecasted_demand > 0 ? 1 : 0
}

export function rankForecasts(forecasts) {
  const trendRank = f => TREND_RANK[f.trend?.toLowerCase()] ?? 3
  return [...forecasts].sort((a, b) =>
    trendRank(a) - trendRank(b) ||
    growthRate(b) - growthRate(a) ||
    (b.forecasted_demand - b.current_demand) - (a.forecasted_demand - a.current_demand) ||
    a.item_sku.localeCompare(b.item_sku)
  )
}

/**
 * Greedy priority fill.
 *
 * Items are funded at their full forecasted quantity in rank order. The first item that
 * doesn't fully fit gets floor(remaining / unit_cost) and filling stops there, so a
 * lower-priority item is never funded while a higher-priority one is short. The most
 * this can leave unspent is less than one unit of that boundary item.
 *
 * Excluded SKUs are skipped before filling, so their budget flows to the next item.
 * Money is handled in integer cents so totals match the server's budget check exactly.
 */
export function buildRestockPlan(forecasts, budgetUsd, excludedSkus = new Set()) {
  let remainingCents = Math.max(0, Math.floor((Number(budgetUsd) || 0) * 100))
  let boundaryReached = false
  let totalCents = 0

  const rows = rankForecasts(forecasts).map(f => {
    const unitCents = Math.round((f.unit_cost || 0) * 100)
    let quantity = 0
    let status

    if (excludedSkus.has(f.item_sku)) {
      status = 'excluded'
    } else if (boundaryReached || unitCents <= 0 || f.forecasted_demand <= 0) {
      status = 'unfunded'
    } else if (unitCents * f.forecasted_demand <= remainingCents) {
      quantity = f.forecasted_demand
      status = 'full'
    } else {
      quantity = Math.floor(remainingCents / unitCents)
      status = quantity > 0 ? 'partial' : 'unfunded'
      boundaryReached = true
    }

    const lineCents = quantity * unitCents
    remainingCents -= lineCents
    totalCents += lineCents

    return {
      sku: f.item_sku,
      name: f.item_name,
      trend: f.trend,
      forecastedDemand: f.forecasted_demand,
      unitCost: f.unit_cost,
      leadTimeDays: f.lead_time_days,
      quantity,
      lineTotal: lineCents / 100,
      status
    }
  })

  const lines = rows.filter(r => r.quantity > 0)

  return {
    rows,
    lines,
    totalCost: totalCents / 100,
    remaining: remainingCents / 100,
    // One shipment: it arrives when the slowest item arrives
    leadTimeDays: lines.length ? Math.max(...lines.map(r => r.leadTimeDays)) : 0
  }
}

export function toOrderPayload(plan, budgetUsd) {
  return {
    budget: budgetUsd,
    items: plan.lines.map(r => ({ sku: r.sku, quantity: r.quantity }))
  }
}

// Slider max: cost of buying every forecast at full quantity, rounded up to the step
export function computeBudgetMax(forecasts, step) {
  const total = forecasts.reduce((sum, f) => sum + (f.unit_cost || 0) * f.forecasted_demand, 0)
  return Math.ceil(total / step) * step
}
