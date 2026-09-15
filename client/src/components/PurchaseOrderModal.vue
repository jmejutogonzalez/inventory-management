<template>
  <Teleport to="body">
    <Transition name="modal">
      <div v-if="isOpen && backlogItem" class="modal-overlay" @click="close">
        <div class="modal-container" @click.stop>
          <div class="modal-header">
            <h3 class="modal-title">
              {{
                mode === 'create' ? t('purchaseOrder.createTitle') : t('purchaseOrder.viewTitle')
              }}
            </h3>
            <button class="close-button" @click="close">
              <svg width="20" height="20" viewBox="0 0 20 20" fill="none">
                <path
                  d="M15 5L5 15M5 5L15 15"
                  stroke="currentColor"
                  stroke-width="2"
                  stroke-linecap="round"
                />
              </svg>
            </button>
          </div>

          <div class="modal-body">
            <div class="context-header">
              <div class="context-title-section">
                <h4 class="item-name">
                  {{ translateProductName(backlogItem.item_name) }}
                </h4>
                <div class="item-sku">SKU: {{ backlogItem.item_sku }}</div>
              </div>
              <span class="badge danger">
                {{ t('purchaseOrder.shortageOf', { count: shortage }) }}
              </span>
            </div>

            <div class="info-grid compact">
              <div class="info-item">
                <div class="info-label">
                  {{ t('dashboard.inventoryShortages.orderId') }}
                </div>
                <div class="info-value order-id">
                  {{ backlogItem.order_id }}
                </div>
              </div>
              <div class="info-item">
                <div class="info-label">
                  {{ t('dashboard.inventoryShortages.sku') }}
                </div>
                <div class="info-value sku">{{ backlogItem.item_sku }}</div>
              </div>
            </div>

            <!-- Create Mode -->
            <form v-if="mode === 'create'" class="po-form" @submit.prevent="submitForm">
              <div class="form-group">
                <label class="form-label">{{ t('purchaseOrder.supplierName') }} *</label>
                <input
                  v-model="form.supplier_name"
                  type="text"
                  class="form-input"
                  :placeholder="t('purchaseOrder.supplierNamePlaceholder')"
                  required
                />
              </div>

              <div class="form-row">
                <div class="form-group">
                  <label class="form-label">{{ t('purchaseOrder.quantity') }} *</label>
                  <input
                    v-model.number="form.quantity"
                    type="number"
                    min="1"
                    step="1"
                    class="form-input"
                    required
                  />
                </div>

                <div class="form-group">
                  <label class="form-label">{{ t('purchaseOrder.unitCost') }} ({{ currencySymbol }}) *</label>
                  <input
                    v-model.number="form.unit_cost"
                    type="number"
                    :min="currentCurrency === 'JPY' ? 1 : 0.01"
                    :step="currentCurrency === 'JPY' ? 1 : 0.01"
                    class="form-input"
                    required
                  />
                </div>
              </div>

              <div class="form-group">
                <label class="form-label">{{ t('purchaseOrder.expectedDeliveryDate') }} *</label>
                <input
                  v-model="form.expected_delivery_date"
                  type="date"
                  :min="todayString"
                  class="form-input"
                  required
                />
              </div>

              <div class="form-group">
                <label class="form-label">{{ t('purchaseOrder.notes') }}</label>
                <textarea
                  v-model="form.notes"
                  class="form-textarea"
                  rows="3"
                  :placeholder="t('purchaseOrder.notesPlaceholder')"
                ></textarea>
              </div>

              <div v-if="submitError" class="form-error">{{ submitError }}</div>
            </form>

            <!-- View Mode -->
            <div v-else-if="mode === 'view'">
              <div v-if="viewLoading" class="view-status">
                {{ t('purchaseOrder.loading') }}
              </div>
              <div v-else-if="viewError" class="view-status error">
                {{ viewError }}
              </div>
              <div v-else-if="purchaseOrder" class="info-grid">
                <div class="info-item">
                  <div class="info-label">{{ t('purchaseOrder.poId') }}</div>
                  <div class="info-value order-id">{{ purchaseOrder.id }}</div>
                </div>
                <div class="info-item">
                  <div class="info-label">
                    {{ t('purchaseOrder.supplier') }}
                  </div>
                  <div class="info-value">
                    {{ purchaseOrder.supplier_name }}
                  </div>
                </div>
                <div class="info-item">
                  <div class="info-label">
                    {{ t('purchaseOrder.quantity') }}
                  </div>
                  <div class="info-value">{{ purchaseOrder.quantity }}</div>
                </div>
                <div class="info-item">
                  <div class="info-label">
                    {{ t('purchaseOrder.unitCost') }}
                  </div>
                  <div class="info-value">
                    {{ formatCurrency(purchaseOrder.unit_cost, currentCurrency) }}
                  </div>
                </div>
                <div class="info-item">
                  <div class="info-label">{{ t('purchaseOrder.total') }}</div>
                  <div class="info-value">
                    {{
                      formatCurrency(
                        purchaseOrder.quantity * purchaseOrder.unit_cost,
                        currentCurrency
                      )
                    }}
                  </div>
                </div>
                <div class="info-item">
                  <div class="info-label">
                    {{ t('purchaseOrder.expectedDeliveryDate') }}
                  </div>
                  <div class="info-value">
                    {{ formatDate(purchaseOrder.expected_delivery_date) }}
                  </div>
                </div>
                <div class="info-item">
                  <div class="info-label">{{ t('purchaseOrder.status') }}</div>
                  <div class="info-value">
                    <span class="badge warning">{{
                      purchaseOrder.status === 'pending'
                        ? t('purchaseOrder.statusPending')
                        : purchaseOrder.status
                    }}</span>
                  </div>
                </div>
                <div class="info-item">
                  <div class="info-label">
                    {{ t('purchaseOrder.createdDate') }}
                  </div>
                  <div class="info-value">
                    {{ formatDate(purchaseOrder.created_date) }}
                  </div>
                </div>
                <div class="info-item full-width">
                  <div class="info-label">{{ t('purchaseOrder.notes') }}</div>
                  <div class="info-value">
                    {{ purchaseOrder.notes || t('purchaseOrder.noNotes') }}
                  </div>
                </div>
              </div>
            </div>
          </div>

          <div class="modal-footer">
            <button class="btn-secondary" @click="close">
              {{ mode === 'create' ? t('purchaseOrder.cancel') : t('purchaseOrder.close') }}
            </button>
            <button
              v-if="mode === 'create'"
              class="btn-primary"
              :disabled="!isFormValid || submitting"
              @click="submitForm"
            >
              {{ submitting ? t('purchaseOrder.submitting') : t('purchaseOrder.submit') }}
            </button>
          </div>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<script setup>
import { ref, computed, watch } from 'vue'
import { useI18n } from '../composables/useI18n'
import { formatCurrency, toUsd } from '../utils/currency'
import { api } from '../api'

const { t, translateProductName, currentCurrency, currentLocale } = useI18n()

const props = defineProps({
  isOpen: {
    type: Boolean,
    required: true
  },
  backlogItem: {
    type: Object,
    default: null
  },
  mode: {
    type: String,
    default: 'create'
  }
})

const emit = defineEmits(['close', 'po-created'])

const currencySymbol = computed(() => (currentCurrency.value === 'JPY' ? '¥' : '$'))

const shortage = computed(() => {
  if (!props.backlogItem) return 0
  return props.backlogItem.quantity_needed - props.backlogItem.quantity_available
})

// Build YYYY-MM-DD from local date parts: toISOString() is UTC, which shifts
// "today" by a day for users far from UTC and breaks the no-past-dates check
const toLocalDateString = (date) => {
  const month = String(date.getMonth() + 1).padStart(2, '0')
  const day = String(date.getDate()).padStart(2, '0')
  return `${date.getFullYear()}-${month}-${day}`
}

const todayString = computed(() => toLocalDateString(new Date()))

const defaultForm = () => ({
  supplier_name: '',
  quantity: shortage.value > 0 ? shortage.value : 1,
  unit_cost: '',
  expected_delivery_date: '',
  notes: ''
})

const form = ref(defaultForm())
const submitting = ref(false)
const submitError = ref(null)

const purchaseOrder = ref(null)
const viewLoading = ref(false)
const viewError = ref(null)

const isFormValid = computed(() => {
  if (!form.value.supplier_name || !form.value.supplier_name.trim()) return false
  if (!form.value.quantity || form.value.quantity <= 0) return false
  if (!form.value.unit_cost || form.value.unit_cost <= 0) return false
  if (!form.value.expected_delivery_date) return false
  // Expected delivery date must not be in the past
  if (form.value.expected_delivery_date < todayString.value) return false
  return true
})

const close = () => {
  emit('close')
}

const submitForm = async () => {
  if (!isFormValid.value || submitting.value || !props.backlogItem) return
  submitting.value = true
  submitError.value = null
  try {
    const response = await api.createPurchaseOrder({
      backlog_item_id: props.backlogItem.id,
      supplier_name: form.value.supplier_name.trim(),
      quantity: form.value.quantity,
      // Entered in the currency shown on screen; the API stores USD
      unit_cost: toUsd(form.value.unit_cost, currentCurrency.value),
      expected_delivery_date: form.value.expected_delivery_date,
      notes: form.value.notes || undefined
    })
    emit('po-created', response)
  } catch (err) {
    submitError.value = extractErrorMessage(err)
  } finally {
    submitting.value = false
  }
}

// Server errors can be a plain string (custom 404/409 handlers) or an
// array of Pydantic validation error objects (422), so normalize both shapes.
const extractErrorMessage = (err) => {
  const detail = err.response?.data?.detail
  if (!detail) return err.message || 'Failed to create purchase order'
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail)) {
    return detail.map((d) => d.msg || JSON.stringify(d)).join('; ')
  }
  return 'Failed to create purchase order'
}

const loadPurchaseOrder = async () => {
  if (!props.backlogItem) return

  // Prefer the PO already attached to the backlog item to avoid a redundant fetch
  if (props.backlogItem.purchase_order) {
    purchaseOrder.value = props.backlogItem.purchase_order
    return
  }

  viewLoading.value = true
  viewError.value = null
  purchaseOrder.value = null
  try {
    purchaseOrder.value = await api.getPurchaseOrderByBacklogItem(props.backlogItem.id)
  } catch (err) {
    viewError.value =
      err.response?.status === 404 ? t('purchaseOrder.notFound') : t('purchaseOrder.loadError')
  } finally {
    viewLoading.value = false
  }
}

// Switching language also switches currency, which would silently reinterpret a typed
// price (12.50 USD becoming 12.50 JPY), so clear it and let the user re-enter
watch(currentCurrency, () => {
  form.value.unit_cost = ''
})

// Dashboard sets item, mode and isOpen in the same tick; one watcher over all three
// resets state once per open instead of firing separate (duplicate) loads
watch(
  () => [props.isOpen, props.backlogItem, props.mode],
  ([open, , mode]) => {
    if (!open) return
    form.value = defaultForm()
    submitError.value = null
    if (mode === 'view') {
      loadPurchaseOrder()
    }
  },
  { immediate: true }
)

const formatDate = (dateString) => {
  if (!dateString) return 'N/A'
  // Date-only strings ("2026-10-01") parse as UTC midnight and render as the
  // previous day west of UTC, so read them as a local calendar date instead
  const dateOnly = /^(\d{4})-(\d{2})-(\d{2})$/.exec(dateString)
  const date = dateOnly
    ? new Date(Number(dateOnly[1]), Number(dateOnly[2]) - 1, Number(dateOnly[3]))
    : new Date(dateString)
  if (isNaN(date.getTime())) return 'N/A'
  const locale = currentLocale.value === 'ja' ? 'ja-JP' : 'en-US'
  return date.toLocaleDateString(locale, {
    year: 'numeric',
    month: 'long',
    day: 'numeric'
  })
}
</script>

<style scoped>
.modal-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(0, 0, 0, 0.5);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 2000;
  padding: 1rem;
}

.modal-container {
  background: white;
  border-radius: 12px;
  box-shadow: 0 20px 50px rgba(0, 0, 0, 0.15);
  max-width: 600px;
  width: 100%;
  max-height: 90vh;
  overflow: hidden;
  display: flex;
  flex-direction: column;
}

.modal-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 1.5rem;
  border-bottom: 1px solid #e2e8f0;
}

.modal-title {
  font-size: 1.25rem;
  font-weight: 700;
  color: #0f172a;
  letter-spacing: -0.025em;
}

.close-button {
  background: none;
  border: none;
  color: #64748b;
  cursor: pointer;
  padding: 0.5rem;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 6px;
  transition: all 0.15s ease;
}

.close-button:hover {
  background: #f1f5f9;
  color: #0f172a;
}

.modal-body {
  flex: 1;
  overflow-y: auto;
  padding: 2rem;
}

.context-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 1rem;
  padding-bottom: 1.5rem;
  border-bottom: 1px solid #e2e8f0;
  margin-bottom: 1.5rem;
}

.context-title-section {
  flex: 1;
  min-width: 0;
}

.item-name {
  font-size: 1.25rem;
  font-weight: 700;
  color: #0f172a;
  margin: 0 0 0.375rem 0;
}

.item-sku {
  font-size: 0.875rem;
  color: #64748b;
  font-family: 'Monaco', 'Courier New', monospace;
}

.info-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
  gap: 1.5rem;
}

.info-grid.compact {
  margin-bottom: 1.5rem;
}

.info-item {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.info-item.full-width {
  grid-column: 1 / -1;
}

.info-label {
  font-size: 0.813rem;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: #64748b;
}

.info-value {
  font-size: 0.938rem;
  color: #0f172a;
  font-weight: 500;
}

.info-value.order-id,
.info-value.sku {
  font-family: 'Monaco', 'Courier New', monospace;
  color: #2563eb;
}

.badge {
  display: inline-block;
  padding: 0.375rem 0.75rem;
  border-radius: 6px;
  font-size: 0.813rem;
  font-weight: 600;
  text-transform: capitalize;
  white-space: nowrap;
}

.badge.danger {
  background: #fecaca;
  color: #991b1b;
}

.badge.warning {
  background: #fed7aa;
  color: #92400e;
}

.po-form {
  display: flex;
  flex-direction: column;
  gap: 1.25rem;
}

.form-row {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 1.25rem;
}

.form-group {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.form-label {
  font-size: 0.813rem;
  font-weight: 600;
  color: #475569;
}

.form-input,
.form-textarea {
  padding: 0.625rem 0.75rem;
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  font-size: 0.938rem;
  font-family: inherit;
  color: #0f172a;
  transition: border-color 0.15s ease;
}

.form-input:focus,
.form-textarea:focus {
  outline: none;
  border-color: #3b82f6;
}

.form-textarea {
  resize: vertical;
  min-height: 4rem;
}

.form-error {
  padding: 0.75rem 1rem;
  background: #fef2f2;
  border: 1px solid #fecaca;
  border-radius: 8px;
  color: #991b1b;
  font-size: 0.875rem;
}

.view-status {
  padding: 2rem;
  text-align: center;
  color: #64748b;
  font-size: 0.938rem;
}

.view-status.error {
  color: #991b1b;
}

.modal-footer {
  padding: 1.5rem;
  border-top: 1px solid #e2e8f0;
  display: flex;
  justify-content: flex-end;
  gap: 0.75rem;
}

.btn-secondary {
  padding: 0.625rem 1.25rem;
  background: #f1f5f9;
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  font-weight: 500;
  font-size: 0.875rem;
  color: #334155;
  cursor: pointer;
  transition: all 0.15s ease;
  font-family: inherit;
}

.btn-secondary:hover {
  background: #e2e8f0;
  border-color: #cbd5e1;
}

.btn-primary {
  padding: 0.625rem 1.25rem;
  background: #3b82f6;
  border: 1px solid #3b82f6;
  border-radius: 8px;
  font-weight: 600;
  font-size: 0.875rem;
  color: white;
  cursor: pointer;
  transition: all 0.15s ease;
  font-family: inherit;
}

.btn-primary:hover:not(:disabled) {
  background: #2563eb;
  border-color: #2563eb;
}

.btn-primary:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

/* Modal transition animations */
.modal-enter-active,
.modal-leave-active {
  transition: opacity 0.2s ease;
}

.modal-enter-from,
.modal-leave-to {
  opacity: 0;
}

.modal-enter-active .modal-container,
.modal-leave-active .modal-container {
  transition: transform 0.2s ease;
}

.modal-enter-from .modal-container,
.modal-leave-to .modal-container {
  transform: scale(0.95);
}
</style>
