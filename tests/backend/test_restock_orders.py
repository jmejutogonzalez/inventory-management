"""
Tests for restocking order API endpoints.
"""
import re
import threading
import time
from datetime import datetime, timedelta

import pytest

import main
import mock_data  # importable because conftest.py puts server/ on sys.path
from main import CreateRestockOrderRequest, create_restock_order


@pytest.fixture(autouse=True)
def reset_restock_orders():
    """POST mutates the module-level list; clear it in place so main.py sees the same (empty) object."""
    mock_data.restock_orders.clear()
    yield
    mock_data.restock_orders.clear()


def make_payload(items, budget=100000):
    """Build a restock order request body from (sku, quantity) pairs."""
    return {"budget": budget, "items": [{"sku": sku, "quantity": qty} for sku, qty in items]}


class TestRestockOrderEndpoints:
    """Test suite for restocking order endpoints."""

    def test_get_restock_orders_empty(self, client):
        """Test that no restock orders exist before any are submitted."""
        response = client.get("/api/restock-orders")
        assert response.status_code == 200
        assert response.json() == []

    def test_create_restock_order(self, client):
        """Test creating a restock order returns 201 with the full order structure."""
        response = client.post("/api/restock-orders", json=make_payload([("FLT-405", 10)], budget=1000))
        assert response.status_code == 201

        order = response.json()
        for field in ["id", "order_number", "items", "total_cost", "budget",
                      "lead_time_days", "created_at", "expected_delivery", "status"]:
            assert field in order
        assert order["status"] == "Submitted"
        assert order["budget"] == 1000
        assert len(order["items"]) == 1

        item = order["items"][0]
        for field in ["sku", "name", "quantity", "unit_cost", "line_total", "lead_time_days"]:
            assert field in item

    def test_create_restock_order_uses_server_prices(self, client):
        """Test that client-supplied prices are ignored in favour of forecast data."""
        payload = make_payload([("FLT-405", 10)])
        payload["items"][0]["unit_cost"] = 0.01
        payload["items"][0]["name"] = "Tampered"

        response = client.post("/api/restock-orders", json=payload)
        assert response.status_code == 201

        item = response.json()["items"][0]
        assert item["unit_cost"] == 8.25
        assert item["name"] == "Oil Filter Cartridge"
        assert abs(item["line_total"] - 82.50) < 0.01

    def test_restock_order_total_cost_calculation(self, client):
        """Test that total cost is the sum of line totals."""
        response = client.post("/api/restock-orders", json=make_payload([("WDG-001", 3), ("GSK-203", 2)]))
        assert response.status_code == 201

        order = response.json()
        # 3 x 24.99 + 2 x 12.75
        assert abs(order["total_cost"] - 100.47) < 0.01
        assert abs(order["total_cost"] - sum(i["line_total"] for i in order["items"])) < 0.01

    def test_restock_order_lead_time_is_longest_item(self, client):
        """Test that the order lead time is the maximum item lead time."""
        response = client.post("/api/restock-orders", json=make_payload([("FLT-405", 1), ("MTR-304", 1)]))
        assert response.status_code == 201

        order = response.json()
        assert order["lead_time_days"] == 45
        assert sorted(i["lead_time_days"] for i in order["items"]) == [5, 45]

    def test_restock_order_expected_delivery_calculation(self, client):
        """Test that expected delivery is the creation date plus the lead time."""
        response = client.post("/api/restock-orders", json=make_payload([("VLV-506", 1)]))
        order = response.json()

        created = datetime.fromisoformat(order["created_at"])
        expected = datetime.fromisoformat(order["expected_delivery"])
        assert (expected - created).days == order["lead_time_days"] == 30

    def test_restock_order_number_format_and_sequence(self, client):
        """Test that order numbers follow RST-YYYY-NNNN and increment."""
        first = client.post("/api/restock-orders", json=make_payload([("FLT-405", 1)])).json()
        second = client.post("/api/restock-orders", json=make_payload([("GSK-203", 1)])).json()

        pattern = re.compile(r"^RST-\d{4}-\d{4}$")
        assert pattern.match(first["order_number"])
        assert pattern.match(second["order_number"])
        assert (first["id"], second["id"]) == ("1", "2")
        assert first["order_number"].endswith("-0001")
        assert second["order_number"].endswith("-0002")

    def test_concurrent_restock_orders_get_unique_numbers(self, client, monkeypatch):
        """Test that simultaneous submissions never share an id or order number."""
        # The race window (read max id -> append) is microseconds, so a plain threaded test
        # passes even without the lock. timedelta() is called inside that window; slowing it
        # down makes the test fail reliably if the lock is ever removed.
        def slow_timedelta(*args, **kwargs):
            time.sleep(0.01)
            return timedelta(*args, **kwargs)

        monkeypatch.setattr(main, "timedelta", slow_timedelta)

        thread_count = 20
        request = CreateRestockOrderRequest(budget=1000, items=[{"sku": "FLT-405", "quantity": 1}])
        # The barrier releases every thread at once to maximise overlap in the id assignment
        barrier = threading.Barrier(thread_count)
        errors = []

        def submit():
            try:
                barrier.wait()
                create_restock_order(request)
            except Exception as exc:  # surface failures from worker threads in the main assertion
                errors.append(exc)

        threads = [threading.Thread(target=submit) for _ in range(thread_count)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        assert errors == []
        data = client.get("/api/restock-orders").json()
        assert len(data) == thread_count
        assert len({o["id"] for o in data}) == thread_count
        assert len({o["order_number"] for o in data}) == thread_count

    def test_get_restock_orders_newest_first(self, client):
        """Test that submitted orders are listed newest first."""
        client.post("/api/restock-orders", json=make_payload([("FLT-405", 1)]))
        client.post("/api/restock-orders", json=make_payload([("GSK-203", 1)]))

        response = client.get("/api/restock-orders")
        assert response.status_code == 200

        data = response.json()
        assert [o["id"] for o in data] == ["2", "1"]

    def test_create_restock_order_unknown_sku(self, client):
        """Test that an SKU outside the demand forecast is rejected and nothing is stored."""
        response = client.post("/api/restock-orders", json=make_payload([("NOPE-999", 1)]))
        assert response.status_code == 400
        assert "NOPE-999" in response.json()["detail"]

        assert client.get("/api/restock-orders").json() == []

    @pytest.mark.parametrize("quantity", [0, -5])
    def test_create_restock_order_non_positive_quantity(self, client, quantity):
        """Test that zero or negative quantities fail validation."""
        response = client.post("/api/restock-orders", json=make_payload([("FLT-405", quantity)]))
        assert response.status_code == 422

    def test_create_restock_order_empty_items(self, client):
        """Test that an order with no items fails validation."""
        response = client.post("/api/restock-orders", json={"budget": 1000, "items": []})
        assert response.status_code == 422

    def test_create_restock_order_missing_budget(self, client):
        """Test that the budget is required."""
        response = client.post("/api/restock-orders", json={"items": [{"sku": "FLT-405", "quantity": 1}]})
        assert response.status_code == 422

    def test_create_restock_order_duplicate_skus(self, client):
        """Test that repeating an SKU in one order is rejected."""
        response = client.post("/api/restock-orders", json=make_payload([("FLT-405", 1), ("FLT-405", 2)]))
        assert response.status_code == 400
        assert "FLT-405" in response.json()["detail"]

    def test_create_restock_order_quantity_above_forecast(self, client):
        """Test that ordering more than the forecasted demand is rejected."""
        response = client.post("/api/restock-orders", json=make_payload([("FLT-405", 951)]))
        assert response.status_code == 400
        assert "forecasted demand" in response.json()["detail"].lower()

    def test_create_restock_order_over_budget(self, client):
        """Test that a total above the budget is rejected and nothing is stored."""
        response = client.post("/api/restock-orders", json=make_payload([("FLT-405", 10)], budget=82.49))
        assert response.status_code == 400
        assert "budget" in response.json()["detail"].lower()

        assert client.get("/api/restock-orders").json() == []

    def test_create_restock_order_exactly_on_budget(self, client):
        """Test that a total equal to the budget is accepted (cents boundary)."""
        response = client.post("/api/restock-orders", json=make_payload([("FLT-405", 10)], budget=82.50))
        assert response.status_code == 201

    def test_restock_orders_do_not_affect_revenue(self, client):
        """Test that restock orders stay out of customer orders and revenue aggregations."""
        before = {
            "orders": len(client.get("/api/orders").json()),
            "summary": client.get("/api/dashboard/summary").json(),
            "quarterly": client.get("/api/reports/quarterly").json(),
            "monthly": client.get("/api/reports/monthly-trends").json(),
        }

        response = client.post("/api/restock-orders", json=make_payload([("MTR-304", 35)]))
        assert response.status_code == 201

        assert len(client.get("/api/orders").json()) == before["orders"]
        assert client.get("/api/dashboard/summary").json() == before["summary"]
        assert client.get("/api/reports/quarterly").json() == before["quarterly"]
        assert client.get("/api/reports/monthly-trends").json() == before["monthly"]
