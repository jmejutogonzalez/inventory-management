<template>
  <div class="restocking">
    <div class="page-header">
      <h2>{{ t('restocking.title') }}</h2>
      <p>{{ t('restocking.description') }}</p>
    </div>

    <div v-if="loading" class="loading">{{ t('common.loading') }}</div>
    <div v-else-if="error" class="error">{{ error }}</div>
    <div v-else>
      <div class="stats-grid restock-stats">
        <div class="stat-card info">
          <div class="stat-label">{{ t('restocking.budget') }}</div>
          <div class="stat-value">{{ formatCurrency(budget) }}</div>
        </div>
        <div class="stat-card success">
          <div class="stat-label">{{ t('restocking.plannedSpend') }}</div>
          <div class="stat-value">{{ formatCurrency(plan.totalCost) }}</div>
        </div>
        <div class="stat-card">
          <div class="stat-label">{{ t('restocking.remaining') }}</div>
          <div class="stat-value">{{ formatCurrency(plan.remaining) }}</div>
        </div>
        <div class="stat-card">
          <div class="stat-label">{{ t('restocking.itemsSelected') }}</div>
          <div class="stat-value">{{ plan.lines.length }}</div>
        </div>
        <div class="stat-card">
          <div class="stat-label">{{ t('restocking.longestLeadTime') }}</div>
          <div class="stat-value">{{ plan.leadTimeDays > 0 ? t('restocking.days', { count: plan.leadTimeDays }) : '—' }}</div>
        </div>
      </div>

      <div class="card">
        <div class="card-header">
          <h3 class="card-title">{{ t('restocking.budget') }}</h3>
          <div class="budget-current">{{ formatCurrency(budget) }}</div>
        </div>
        <input
          type="range"
          class="budget-slider"
          v-model.number="budget"
          min="0"
          :max="budgetMax"
          :step="BUDGET_STEP"
          :disabled="budgetMax === 0 || submitting"
          :aria-label="t('restocking.budget')"
        >
        <div class="budget-range-labels">
          <span>{{ formatCurrency(0) }}</span>
          <span>{{ formatCurrency(budgetMax) }}</span>
        </div>
        <p class="budget-hint">{{ t('restocking.budgetHint') }}</p>
      </div>

      <div class="card">
        <div class="card-header">
          <h3 class="card-title">{{ t('restocking.recommendations') }}</h3>
          <div class="place-order-wrapper">
            <button
              class="restock-button"
              :disabled="plan.lines.length === 0 || submitting || !!submittedOrder"
              @click="placeOrder"
            >
              {{ placeOrderLabel }}
            </button>
            <!-- Only blame the checkboxes when every item is unchecked; otherwise the included items just don't fit the budget -->
            <p v-if="plan.lines.length === 0" class="place-order-hint">
              {{ plan.rows.length > 0 && plan.rows.every(row => row.status === 'excluded') ? t('restocking.nothingSelected') : t('restocking.increaseBudget') }}
            </p>
          </div>
        </div>

        <div class="table-container">
          <table>
            <thead>
              <tr>
                <th>{{ t('restocking.include') }}</th>
                <th>{{ t('restocking.table.sku') }}</th>
                <th>{{ t('restocking.table.itemName') }}</th>
                <th>{{ t('restocking.table.trend') }}</th>
                <th>{{ t('restocking.table.forecastQty') }}</th>
                <th>{{ t('restocking.table.recommendedQty') }}</th>
                <th>{{ t('restocking.table.fundingStatus') }}</th>
                <th>{{ t('restocking.table.unitCost') }}</th>
                <th>{{ t('restocking.table.lineTotal') }}</th>
                <th>{{ t('restocking.table.leadTime') }}</th>
              </tr>
            </thead>
            <tbody>
              <tr
                v-for="row in plan.rows"
                :key="row.sku"
                :class="{ 'row-muted': row.quantity === 0 }"
              >
                <td>
                  <input
                    type="checkbox"
                    :checked="!excludedSkus.has(row.sku)"
                    :disabled="submitting"
                    :aria-label="`${t('restocking.include')} ${row.sku}`"
                    @change="toggleSku(row.sku)"
                  >
                </td>
                <td>{{ row.sku }}</td>
                <td>{{ translateProductName(row.name) }}</td>
                <td><span :class="['badge', row.trend]">{{ t('trends.' + row.trend) }}</span></td>
                <td>{{ row.forecastedDemand.toLocaleString() }}</td>
                <td :class="{ 'qty-strong': row.quantity > 0 }">{{ row.quantity.toLocaleString() }}</td>
                <td>
                  <span :class="['badge', fundingBadgeClass(row.status)]">
                    {{ t('restocking.fundingStatus.' + row.status) }}
                  </span>
                </td>
                <td>{{ formatCurrencyWithDecimals(row.unitCost, currentCurrency, 2) }}</td>
                <td>{{ formatCurrencyWithDecimals(row.lineTotal, currentCurrency, 2) }}</td>
                <td>{{ t('restocking.days', { count: row.leadTimeDays }) }}</td>
              </tr>
            </tbody>
            <tfoot>
              <tr>
                <td colspan="8">{{ t('restocking.table.total') }}</td>
                <td>{{ formatCurrencyWithDecimals(plan.totalCost, currentCurrency, 2) }}</td>
                <td></td>
              </tr>
            </tfoot>
          </table>
        </div>
      </div>

      <div v-if="submittedOrder" class="success-banner">
        {{ t('restocking.orderSuccess', { orderNumber: submittedOrder.order_number, date: formatDate(submittedOrder.expected_delivery) }) }}
        <router-link to="/orders">{{ t('restocking.viewOrders') }}</router-link>
      </div>

      <div v-if="submitError" class="error">{{ submitError }}</div>
    </div>
  </div>
</template>

<script>
import { ref, computed, onMounted, watch } from 'vue'
import { api } from '../api'
import { useI18n } from '../composables/useI18n'
import { buildRestockPlan, toOrderPayload, computeBudgetMax } from '../utils/restocking'
import { formatCurrency as formatCurrencyUtil, formatCurrencyWithDecimals } from '../utils/currency'

// Slider granularity. Kept in sync with the 25% default calc below.
const BUDGET_STEP = 500

export default {
  name: 'Restocking',
  setup() {
    const { t, currentLocale, currentCurrency, translateProductName } = useI18n()

    const forecasts = ref([])
    const loading = ref(true)
    const error = ref(null)

    const budget = ref(0)
    const excludedSkus = ref(new Set())

    const submitting = ref(false)
    const submitError = ref(null)
    const submittedOrder = ref(null)

    const budgetMax = computed(() => computeBudgetMax(forecasts.value, BUDGET_STEP))
    const plan = computed(() => buildRestockPlan(forecasts.value, budget.value, excludedSkus.value))

    const loadData = async () => {
      loading.value = true
      error.value = null
      try {
        forecasts.value = await api.getDemandForecasts()
        // Default to a quarter of the max budget so the page opens with a meaningful
        // partial plan instead of either "nothing selected" or "buy everything".
        budget.value = Math.round(budgetMax.value * 0.25 / BUDGET_STEP) * BUDGET_STEP
      } catch (err) {
        error.value = 'Failed to load demand forecasts'
        console.error(err)
      } finally {
        loading.value = false
      }
    }

    const toggleSku = (sku) => {
      // Replace the Set (rather than mutate) so the `plan` computed re-evaluates
      const next = new Set(excludedSkus.value)
      next.has(sku) ? next.delete(sku) : next.add(sku)
      excludedSkus.value = next
    }

    const fundingBadgeClass = (status) => {
      if (status === 'full') return 'success'
      if (status === 'partial') return 'warning'
      return 'neutral'
    }

    const placeOrderLabel = computed(() => {
      if (submitting.value) return t('restocking.placing')
      if (submittedOrder.value) return t('restocking.orderPlaced')
      return t('restocking.placeOrder')
    })

    const placeOrder = async () => {
      // Guard in addition to :disabled; a fast double click can fire twice before re-render
      if (submitting.value || plan.value.lines.length === 0) return
      submitting.value = true
      submitError.value = null
      try {
        submittedOrder.value = await api.createRestockOrder(toOrderPayload(plan.value, budget.value))
      } catch (err) {
        const detail = err.response?.data?.detail
        const message = Array.isArray(detail) ? detail.map(d => d.msg).join(', ') : (detail || err.message)
        submitError.value = `${t('restocking.orderError')}: ${message}`
      } finally {
        submitting.value = false
      }
    }

    // Editing the plan after a successful order re-enables the button; that takes a
    // deliberate change, so accidental duplicate orders are unlikely
    watch([budget, excludedSkus], () => {
      submittedOrder.value = null
      submitError.value = null
    })

    const formatCurrency = (value) => formatCurrencyUtil(value, currentCurrency.value)

    const formatDate = (dateString) => {
      const date = new Date(dateString)
      if (isNaN(date.getTime())) return '—'
      const locale = currentLocale.value === 'ja' ? 'ja-JP' : 'en-US'
      return date.toLocaleDateString(locale, { year: 'numeric', month: 'short', day: 'numeric' })
    }

    onMounted(loadData)

    return {
      t,
      forecasts,
      loading,
      error,
      budget,
      excludedSkus,
      submitting,
      submitError,
      submittedOrder,
      budgetMax,
      plan,
      BUDGET_STEP,
      toggleSku,
      fundingBadgeClass,
      placeOrderLabel,
      placeOrder,
      formatCurrency,
      formatCurrencyWithDecimals,
      formatDate,
      currentCurrency,
      translateProductName
    }
  }
}
</script>

<style scoped>
.restock-stats {
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
}

.budget-current {
  font-size: 1.5rem;
  font-weight: 700;
  color: #0f172a;
}

.budget-slider {
  width: 100%;
  accent-color: #3b82f6;
}

.budget-range-labels {
  display: flex;
  justify-content: space-between;
  font-size: 0.813rem;
  color: #64748b;
  margin-top: 0.375rem;
}

.budget-hint {
  margin-top: 0.875rem;
  color: #64748b;
  font-size: 0.875rem;
}

.place-order-wrapper {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: 0.375rem;
}

.place-order-hint {
  color: #64748b;
  font-size: 0.813rem;
}

.restock-button {
  padding: 0.5rem 1.25rem;
  border: none;
  border-radius: 6px;
  font-size: 0.875rem;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.2s ease;
  white-space: nowrap;
  background: #3b82f6;
  color: white;
}

.restock-button:hover:not(:disabled) {
  background: #2563eb;
  transform: translateY(-1px);
  box-shadow: 0 2px 4px rgba(59, 130, 246, 0.3);
}

.restock-button:disabled {
  background: #cbd5e1;
  cursor: not-allowed;
  transform: none;
  box-shadow: none;
}

.row-muted td {
  color: #94a3b8;
}

.qty-strong {
  font-weight: 700;
  color: #0f172a;
}

.badge.neutral {
  background: #e2e8f0;
  color: #475569;
}

tfoot td {
  font-weight: 700;
  color: #0f172a;
  border-top: 2px solid #e2e8f0;
}

.success-banner {
  background: #f0fdf4;
  border: 1px solid #16a34a;
  border-left: 4px solid #16a34a;
  color: #0f172a;
  padding: 1rem;
  border-radius: 8px;
  margin: 1rem 0;
  font-size: 0.938rem;
  display: flex;
  align-items: center;
  gap: 0.75rem;
  flex-wrap: wrap;
}

.success-banner a {
  color: #16a34a;
  font-weight: 600;
  text-decoration: underline;
}
</style>
