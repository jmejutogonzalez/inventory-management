import itertools
import threading
from datetime import date, datetime, timedelta
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from typing import List, Literal, Optional
from pydantic import BaseModel, Field
from mock_data import inventory_items, orders, demand_forecasts, backlog_items, spending_summary, monthly_spending, category_spending, recent_transactions, purchase_orders, restock_orders, tasks

app = FastAPI(title="Factory Inventory Management System")

# Quarter mapping for date filtering
QUARTER_MAP = {
    'Q1-2025': ['2025-01', '2025-02', '2025-03'],
    'Q2-2025': ['2025-04', '2025-05', '2025-06'],
    'Q3-2025': ['2025-07', '2025-08', '2025-09'],
    'Q4-2025': ['2025-10', '2025-11', '2025-12']
}

def filter_by_month(items: list, month: Optional[str]) -> list:
    """Filter items by month/quarter based on order_date field"""
    if not month or month == 'all':
        return items

    if month.startswith('Q'):
        # Handle quarters
        if month in QUARTER_MAP:
            months = QUARTER_MAP[month]
            return [item for item in items if any(m in item.get('order_date', '') for m in months)]
    else:
        # Direct month match
        return [item for item in items if month in item.get('order_date', '')]

    return items

def apply_filters(items: list, warehouse: Optional[str] = None, category: Optional[str] = None,
                 status: Optional[str] = None) -> list:
    """Apply common filters to a list of items"""
    filtered = items

    if warehouse and warehouse != 'all':
        filtered = [item for item in filtered if item.get('warehouse') == warehouse]

    if category and category != 'all':
        filtered = [item for item in filtered if item.get('category', '').lower() == category.lower()]

    if status and status != 'all':
        filtered = [item for item in filtered if item.get('status', '').lower() == status.lower()]

    return filtered

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Data models
class InventoryItem(BaseModel):
    id: str
    sku: str
    name: str
    category: str
    warehouse: str
    quantity_on_hand: int
    reorder_point: int
    unit_cost: float
    location: str
    last_updated: str

class Order(BaseModel):
    id: str
    order_number: str
    customer: str
    items: List[dict]
    status: str
    order_date: str
    expected_delivery: str
    total_value: float
    actual_delivery: Optional[str] = None
    warehouse: Optional[str] = None
    category: Optional[str] = None

class DemandForecast(BaseModel):
    id: str
    item_sku: str
    item_name: str
    current_demand: int
    forecasted_demand: int
    trend: str
    period: str
    unit_cost: float
    lead_time_days: int

class BacklogItem(BaseModel):
    id: str
    order_id: str
    item_sku: str
    item_name: str
    quantity_needed: int
    quantity_available: int
    days_delayed: int
    priority: str
    has_purchase_order: Optional[bool] = False
    # The dashboard switches "Create PO" to "View PO" based on this id, so it must
    # come from the server or the switch is lost on reload
    purchase_order_id: Optional[str] = None

class PurchaseOrder(BaseModel):
    id: str
    backlog_item_id: str
    supplier_name: str
    quantity: int
    unit_cost: float
    expected_delivery_date: str
    status: str
    created_date: str
    notes: Optional[str] = None

class CreatePurchaseOrderRequest(BaseModel):
    backlog_item_id: str
    supplier_name: str = Field(min_length=1)
    quantity: int = Field(gt=0)
    unit_cost: float = Field(gt=0)
    expected_delivery_date: date
    notes: Optional[str] = None

PURCHASE_ORDER_STATUS_PENDING = "pending"

TaskPriority = Literal["high", "medium", "low"]
TaskStatus = Literal["pending", "completed"]

# Field names are camelCase because the client's built-in demo tasks (useAuth.js)
# already use this shape and TasksModal renders both lists together.
class Task(BaseModel):
    id: str
    title: str
    priority: TaskPriority
    dueDate: str
    status: TaskStatus

class CreateTaskRequest(BaseModel):
    title: str = Field(min_length=1)
    priority: TaskPriority = "medium"
    dueDate: date

class RestockOrderItemRequest(BaseModel):
    sku: str
    quantity: int = Field(gt=0)

class CreateRestockOrderRequest(BaseModel):
    # Budget is sent so the server can re-check the total against its own prices.
    # This catches stale client data; it is not a security control.
    budget: float = Field(ge=0)
    items: List[RestockOrderItemRequest] = Field(min_length=1)

class RestockOrderItem(BaseModel):
    sku: str
    name: str
    quantity: int
    unit_cost: float
    line_total: float
    lead_time_days: int

class RestockOrder(BaseModel):
    id: str
    order_number: str
    items: List[RestockOrderItem]
    total_cost: float
    budget: float
    lead_time_days: int
    created_at: str
    expected_delivery: str
    status: str

class QuarterlyReport(BaseModel):
    quarter: str
    total_orders: int
    total_revenue: float
    delivered_orders: int
    avg_order_value: float
    fulfillment_rate: float

class MonthlyTrend(BaseModel):
    month: str
    order_count: int
    revenue: float
    delivered_count: int

RESTOCK_STATUS_SUBMITTED = "Submitted"

# Sync endpoints run in FastAPI's thread pool, so two simultaneous POSTs could both
# read the same max id before either appends. The lock makes id assignment + append atomic.
restock_orders_lock = threading.Lock()
# Same race applies to the other in-memory collections that assign ids on create
purchase_orders_lock = threading.Lock()
tasks_lock = threading.Lock()
task_id_counter = itertools.count(1)

# API endpoints
@app.get("/")
def root():
    return {"message": "Factory Inventory Management System API", "version": "1.0.0"}

@app.get("/api/inventory", response_model=List[InventoryItem])
def get_inventory(
    warehouse: Optional[str] = None,
    category: Optional[str] = None
):
    """Get all inventory items with optional filtering"""
    return apply_filters(inventory_items, warehouse, category)

@app.get("/api/inventory/{item_id}", response_model=InventoryItem)
def get_inventory_item(item_id: str):
    """Get a specific inventory item"""
    item = next((item for item in inventory_items if item["id"] == item_id), None)
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")
    return item

@app.get("/api/orders", response_model=List[Order])
def get_orders(
    warehouse: Optional[str] = None,
    category: Optional[str] = None,
    status: Optional[str] = None,
    month: Optional[str] = None
):
    """Get all orders with optional filtering"""
    filtered_orders = apply_filters(orders, warehouse, category, status)
    filtered_orders = filter_by_month(filtered_orders, month)
    return filtered_orders

@app.get("/api/orders/{order_id}", response_model=Order)
def get_order(order_id: str):
    """Get a specific order"""
    order = next((order for order in orders if order["id"] == order_id), None)
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    return order

@app.get("/api/demand", response_model=List[DemandForecast])
def get_demand_forecasts():
    """Get demand forecasts"""
    return demand_forecasts

@app.get("/api/backlog", response_model=List[BacklogItem])
def get_backlog():
    """Get backlog items with purchase order status"""
    po_ids_by_backlog_item = {po["backlog_item_id"]: po["id"] for po in purchase_orders}
    result = []
    for item in backlog_items:
        item_dict = dict(item)
        item_dict["purchase_order_id"] = po_ids_by_backlog_item.get(item["id"])
        item_dict["has_purchase_order"] = item_dict["purchase_order_id"] is not None
        result.append(item_dict)
    return result

@app.get("/api/purchase-orders/{backlog_item_id}", response_model=PurchaseOrder)
def get_purchase_order_by_backlog_item(backlog_item_id: str):
    """Get the purchase order raised for a backlog item"""
    po = next((po for po in purchase_orders if po["backlog_item_id"] == backlog_item_id), None)
    if not po:
        raise HTTPException(status_code=404, detail="Purchase order not found")
    return po

@app.post("/api/purchase-orders", response_model=PurchaseOrder, status_code=201)
def create_purchase_order(request: CreatePurchaseOrderRequest):
    """Raise a purchase order for a backlog item. Stored in memory only (reset on restart)."""
    if not any(item["id"] == request.backlog_item_id for item in backlog_items):
        raise HTTPException(status_code=404, detail="Backlog item not found")

    supplier_name = request.supplier_name.strip()
    if not supplier_name:
        raise HTTPException(status_code=422, detail="Supplier name must not be blank")
    if request.expected_delivery_date < date.today():
        raise HTTPException(status_code=422, detail="Expected delivery date cannot be in the past")

    with purchase_orders_lock:
        # Checked inside the lock so two concurrent requests can't both raise a PO
        # for the same item; the lookup endpoint assumes at most one per backlog item
        if any(po["backlog_item_id"] == request.backlog_item_id for po in purchase_orders):
            raise HTTPException(status_code=409, detail="Backlog item already has a purchase order")
        next_id = max((int(po["id"]) for po in purchase_orders), default=0) + 1
        po = {
            "id": str(next_id),
            "backlog_item_id": request.backlog_item_id,
            "supplier_name": supplier_name,
            "quantity": request.quantity,
            "unit_cost": request.unit_cost,
            "expected_delivery_date": request.expected_delivery_date.isoformat(),
            "status": PURCHASE_ORDER_STATUS_PENDING,
            "created_date": datetime.now().replace(microsecond=0).isoformat(),
            "notes": request.notes
        }
        purchase_orders.append(po)
    return po

@app.get("/api/tasks", response_model=List[Task])
def get_tasks():
    """Get tasks created through the API, newest first"""
    return list(reversed(tasks))

@app.post("/api/tasks", response_model=Task, status_code=201)
def create_task(request: CreateTaskRequest):
    """Create a task. Stored in memory only (reset on restart)."""
    title = request.title.strip()
    if not title:
        raise HTTPException(status_code=422, detail="Task title must not be blank")

    with tasks_lock:
        # A counter rather than max(id)+1: tasks can be deleted, and reusing a deleted
        # id would let a stale toggle/delete from another tab hit the wrong task
        next_number = next(task_id_counter)
        task = {
            # Prefixed because App.vue treats any id matching a built-in demo task
            # (numeric 1, 2, ...) as local-only and would never call the API for it
            "id": f"task-{next_number}",
            "title": title,
            "priority": request.priority,
            "dueDate": request.dueDate.isoformat(),
            "status": "pending"
        }
        tasks.append(task)
    return task

@app.patch("/api/tasks/{task_id}", response_model=Task)
def toggle_task(task_id: str):
    """Toggle a task between pending and completed"""
    with tasks_lock:
        task = next((task for task in tasks if task["id"] == task_id), None)
        if not task:
            raise HTTPException(status_code=404, detail="Task not found")
        task["status"] = "pending" if task["status"] == "completed" else "completed"
        return dict(task)

@app.delete("/api/tasks/{task_id}", status_code=204)
def delete_task(task_id: str):
    """Delete a task"""
    with tasks_lock:
        index = next((i for i, task in enumerate(tasks) if task["id"] == task_id), None)
        if index is None:
            raise HTTPException(status_code=404, detail="Task not found")
        # Delete in place: main.py and mock_data share this list object
        del tasks[index]

@app.get("/api/restock-orders", response_model=List[RestockOrder])
def get_restock_orders():
    """Get submitted restocking orders, newest first"""
    return list(reversed(restock_orders))

@app.post("/api/restock-orders", response_model=RestockOrder, status_code=201)
def create_restock_order(request: CreateRestockOrderRequest):
    """Create a restocking order. Prices, names and lead times come from forecast data, never the client."""
    forecasts_by_sku = {f["item_sku"]: f for f in demand_forecasts}

    skus = [item.sku for item in request.items]
    duplicates = sorted({sku for sku in skus if skus.count(sku) > 1})
    if duplicates:
        raise HTTPException(status_code=400, detail=f"Duplicate SKUs in order: {', '.join(duplicates)}")

    items = []
    total_cents = 0
    for requested in request.items:
        forecast = forecasts_by_sku.get(requested.sku)
        if not forecast:
            raise HTTPException(status_code=400, detail=f"SKU {requested.sku} is not in the demand forecast")
        if requested.quantity > forecast["forecasted_demand"]:
            raise HTTPException(
                status_code=400,
                detail=f"Quantity for {requested.sku} exceeds forecasted demand ({forecast['forecasted_demand']})"
            )
        # Integer cents keep the budget check identical to the client's plan (no float drift at the boundary)
        unit_cents = round(forecast["unit_cost"] * 100)
        line_cents = unit_cents * requested.quantity
        total_cents += line_cents
        items.append({
            "sku": requested.sku,
            "name": forecast["item_name"],
            "quantity": requested.quantity,
            "unit_cost": forecast["unit_cost"],
            "line_total": line_cents / 100,
            "lead_time_days": forecast["lead_time_days"]
        })

    if total_cents > round(request.budget * 100):
        raise HTTPException(
            status_code=400,
            detail=f"Order total {total_cents / 100:.2f} exceeds budget {request.budget:.2f}"
        )

    created = datetime.now().replace(microsecond=0)
    # A single shipment arrives when its slowest item arrives
    lead_time_days = max(item["lead_time_days"] for item in items)
    with restock_orders_lock:
        next_id = max((int(order["id"]) for order in restock_orders), default=0) + 1
        order = {
            "id": str(next_id),
            "order_number": f"RST-{created.year}-{next_id:04d}",
            "items": items,
            "total_cost": total_cents / 100,
            "budget": request.budget,
            "lead_time_days": lead_time_days,
            "created_at": created.isoformat(),
            "expected_delivery": (created + timedelta(days=lead_time_days)).isoformat(),
            "status": RESTOCK_STATUS_SUBMITTED
        }
        restock_orders.append(order)
    return order

@app.get("/api/dashboard/summary")
def get_dashboard_summary(
    warehouse: Optional[str] = None,
    category: Optional[str] = None,
    status: Optional[str] = None,
    month: Optional[str] = None
):
    """Get summary statistics for dashboard with optional filtering"""
    # Filter inventory
    filtered_inventory = apply_filters(inventory_items, warehouse, category)

    # Filter orders
    filtered_orders = apply_filters(orders, warehouse, category, status)
    filtered_orders = filter_by_month(filtered_orders, month)

    total_inventory_value = sum(item["quantity_on_hand"] * item["unit_cost"] for item in filtered_inventory)
    low_stock_items = len([item for item in filtered_inventory if item["quantity_on_hand"] <= item["reorder_point"]])
    pending_orders = len([order for order in filtered_orders if order["status"] in ["Processing", "Backordered"]])
    total_backlog_items = len(backlog_items)

    return {
        "total_inventory_value": round(total_inventory_value, 2),
        "low_stock_items": low_stock_items,
        "pending_orders": pending_orders,
        "total_backlog_items": total_backlog_items,
        "total_orders_value": sum(order["total_value"] for order in filtered_orders)
    }

@app.get("/api/spending/summary")
def get_spending_summary():
    """Get spending summary statistics"""
    return spending_summary

@app.get("/api/spending/monthly")
def get_monthly_spending():
    """Get monthly spending breakdown"""
    return monthly_spending

@app.get("/api/spending/categories")
def get_category_spending():
    """Get spending by category"""
    return category_spending

@app.get("/api/spending/transactions")
def get_recent_transactions():
    """Get recent transactions"""
    return recent_transactions

def filter_orders_for_reports(warehouse, category, status, month):
    """Apply the global filter bar to orders, same semantics as the dashboard summary"""
    return filter_by_month(apply_filters(orders, warehouse, category, status), month)

@app.get("/api/reports/quarterly", response_model=List[QuarterlyReport])
def get_quarterly_reports(
    warehouse: Optional[str] = None,
    category: Optional[str] = None,
    status: Optional[str] = None,
    month: Optional[str] = None
):
    """Get quarterly performance reports with optional filtering"""
    quarters = {}

    for order in filter_orders_for_reports(warehouse, category, status, month):
        order_date = order.get('order_date', '')
        try:
            year, month_number = int(order_date[:4]), int(order_date[5:7])
        except ValueError:
            continue
        if not 1 <= month_number <= 12:
            continue
        quarter_number = (month_number - 1) // 3 + 1
        quarter = f'Q{quarter_number}-{year}'

        if quarter not in quarters:
            quarters[quarter] = {
                'quarter': quarter,
                'total_orders': 0,
                'total_revenue': 0,
                'delivered_orders': 0,
                'avg_order_value': 0,
                'fulfillment_rate': 0,
                # Kept for sorting only; "Q1-2026" sorts before "Q2-2025" as a string
                '_sort_key': (year, quarter_number)
            }

        quarters[quarter]['total_orders'] += 1
        quarters[quarter]['total_revenue'] += order.get('total_value', 0)
        if order.get('status', '').lower() == 'delivered':
            quarters[quarter]['delivered_orders'] += 1

    result = sorted(quarters.values(), key=lambda q: q.pop('_sort_key'))
    for data in result:
        data['total_revenue'] = round(data['total_revenue'], 2)
        data['avg_order_value'] = round(data['total_revenue'] / data['total_orders'], 2)
        data['fulfillment_rate'] = round((data['delivered_orders'] / data['total_orders']) * 100, 1)
    return result

@app.get("/api/reports/monthly-trends", response_model=List[MonthlyTrend])
def get_monthly_trends(
    warehouse: Optional[str] = None,
    category: Optional[str] = None,
    status: Optional[str] = None,
    month: Optional[str] = None
):
    """Get month-over-month trends with optional filtering"""
    months = {}

    for order in filter_orders_for_reports(warehouse, category, status, month):
        order_date = order.get('order_date', '')
        if not order_date:
            continue

        # Extract month (format: YYYY-MM-DD)
        month_key = order_date[:7]

        if month_key not in months:
            months[month_key] = {
                'month': month_key,
                'order_count': 0,
                'revenue': 0,
                'delivered_count': 0
            }

        months[month_key]['order_count'] += 1
        months[month_key]['revenue'] += order.get('total_value', 0)
        if order.get('status', '').lower() == 'delivered':
            months[month_key]['delivered_count'] += 1

    result = sorted(months.values(), key=lambda x: x['month'])
    # Summing floats leaves artifacts like 1993655.7400000002 in the JSON
    for data in result:
        data['revenue'] = round(data['revenue'], 2)
    return result

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)
