<template>
  <div class="backlog">
    <div class="page-header">
      <h2>{{ t('backlog.title') }}</h2>
      <p>{{ t('backlog.description') }}</p>
    </div>

    <div v-if="loading" class="loading">{{ t('backlog.loading') }}</div>
    <div v-else-if="error" class="error">{{ t('backlog.loadError') }}: {{ error }}</div>
    <div v-else>
      <div class="stats-grid">
        <div class="stat-card danger">
          <div class="stat-label">{{ t('backlog.highPriority') }}</div>
          <div class="stat-value">{{ priorityCounts.high }}</div>
        </div>
        <div class="stat-card warning">
          <div class="stat-label">{{ t('backlog.mediumPriority') }}</div>
          <div class="stat-value">{{ priorityCounts.medium }}</div>
        </div>
        <div class="stat-card info">
          <div class="stat-label">{{ t('backlog.lowPriority') }}</div>
          <div class="stat-value">{{ priorityCounts.low }}</div>
        </div>
        <div class="stat-card">
          <div class="stat-label">{{ t('backlog.totalItems') }}</div>
          <div class="stat-value">{{ backlogItems.length }}</div>
        </div>
      </div>

      <div class="card">
        <div class="card-header">
          <h3 class="card-title">{{ t('backlog.cardTitle') }}</h3>
        </div>
        <div v-if="backlogItems.length === 0" class="empty-state">
          <p class="empty-state-text">{{ t('backlog.noItems') }}</p>
        </div>
        <div v-else class="table-container">
          <table>
            <thead>
              <tr>
                <th>{{ t('dashboard.inventoryShortages.orderId') }}</th>
                <th>{{ t('dashboard.inventoryShortages.sku') }}</th>
                <th>{{ t('dashboard.inventoryShortages.itemName') }}</th>
                <th>{{ t('dashboard.inventoryShortages.quantityNeeded') }}</th>
                <th>{{ t('dashboard.inventoryShortages.quantityAvailable') }}</th>
                <th>{{ t('dashboard.inventoryShortages.shortage') }}</th>
                <th>{{ t('dashboard.inventoryShortages.daysDelayed') }}</th>
                <th>{{ t('dashboard.inventoryShortages.priority') }}</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="item in backlogItems" :key="item.id">
                <td>
                  <strong>{{ item.order_id }}</strong>
                </td>
                <td>
                  <strong>{{ item.item_sku }}</strong>
                </td>
                <td>{{ translateProductName(item.item_name) }}</td>
                <td>{{ item.quantity_needed }}</td>
                <td>{{ item.quantity_available }}</td>
                <td>
                  <span class="badge danger">
                    {{ item.quantity_needed - item.quantity_available }}
                    {{ t('dashboard.inventoryShortages.unitsShort') }}
                  </span>
                </td>
                <td>
                  <span :class="['days-delayed', item.days_delayed > 7 ? 'days-delayed-high' : 'days-delayed-medium']">
                    {{ item.days_delayed }} {{ t('dashboard.inventoryShortages.days') }}
                  </span>
                </td>
                <td>
                  <span :class="['badge', item.priority]">
                    {{ translatePriority(item.priority) }}
                  </span>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </div>
  </div>
</template>

<script>
import { ref, onMounted, watch, computed } from 'vue'
import { api } from '../api'
import { useFilters } from '../composables/useFilters'
import { useI18n } from '../composables/useI18n'

export default {
  name: 'Backlog',
  setup() {
    const { t, translateProductName } = useI18n()

    const loading = ref(true)
    const error = ref(null)
    const allBacklogItems = ref([])
    const inventoryItems = ref([])

    // Use shared filters
    const { selectedLocation, selectedCategory, getCurrentFilters } = useFilters()

    // Filter backlog based on inventory filters
    const backlogItems = computed(() => {
      if (selectedLocation.value === 'all' && selectedCategory.value === 'all') {
        return allBacklogItems.value
      }

      // Get SKUs of items that match the filters
      const validSkus = new Set(inventoryItems.value.map((item) => item.sku))
      return allBacklogItems.value.filter((b) => validSkus.has(b.item_sku))
    })

    const priorityCounts = computed(() => {
      const counts = { high: 0, medium: 0, low: 0 }
      backlogItems.value.forEach((item) => {
        if (counts[item.priority] !== undefined) counts[item.priority]++
      })
      return counts
    })

    const loadBacklog = async () => {
      loading.value = true
      error.value = null
      try {
        const filters = getCurrentFilters()

        const [backlogData, inventoryData] = await Promise.all([
          api.getBacklog(),
          api.getInventory({
            warehouse: filters.warehouse,
            category: filters.category
          })
        ])

        allBacklogItems.value = backlogData
        inventoryItems.value = inventoryData
      } catch (err) {
        // Raw detail only; the translated prefix lives in the template so it follows language switches
        error.value = err.message
        console.error(err)
      } finally {
        loading.value = false
      }
    }

    const translatePriority = (priority) => {
      const priorityMap = {
        high: t('priority.high'),
        medium: t('priority.medium'),
        low: t('priority.low')
      }
      return priorityMap[priority] || priority
    }

    // Backlog has no month/status dimension, so only location/category trigger a reload.
    watch([selectedLocation, selectedCategory], () => {
      loadBacklog()
    })

    onMounted(loadBacklog)

    return {
      t,
      loading,
      error,
      backlogItems,
      priorityCounts,
      translateProductName,
      translatePriority
    }
  }
}
</script>

<style scoped>
.empty-state {
  padding: 3rem;
  text-align: center;
}

.empty-state-text {
  font-size: 1.125rem;
  color: #10b981;
  font-weight: 600;
  margin: 0;
}

.days-delayed {
  font-weight: 600;
}

.days-delayed-high {
  color: #ef4444;
}

.days-delayed-medium {
  color: #f59e0b;
}
</style>
