"""
Tests for purchase order API endpoints.
"""
from datetime import date, timedelta

import pytest

import mock_data  # importable because conftest.py puts server/ on sys.path


@pytest.fixture(autouse=True)
def reset_purchase_orders():
    """POST appends to the list loaded from purchase_orders.json; restore it so tests stay independent."""
    original = list(mock_data.purchase_orders)
    yield
    mock_data.purchase_orders[:] = original


def make_payload(backlog_item_id="1", **overrides):
    """Build a valid purchase order request body."""
    payload = {
        "backlog_item_id": backlog_item_id,
        "supplier_name": "Acme Components",
        "quantity": 350,
        "unit_cost": 12.5,
        "expected_delivery_date": (date.today() + timedelta(days=14)).isoformat(),
        "notes": "Expedite if possible",
    }
    payload.update(overrides)
    return payload


def unused_backlog_item_id():
    """Return a backlog item id that has no purchase order in the seed data."""
    used = {po["backlog_item_id"] for po in mock_data.purchase_orders}
    return next(item["id"] for item in mock_data.backlog_items if item["id"] not in used)


class TestPurchaseOrderEndpoints:
    """Test suite for purchase order endpoints."""

    def test_create_purchase_order(self, client):
        """Test creating a purchase order returns 201 with the full structure."""
        backlog_item_id = unused_backlog_item_id()
        response = client.post("/api/purchase-orders", json=make_payload(backlog_item_id))
        assert response.status_code == 201

        po = response.json()
        for field in ["id", "backlog_item_id", "supplier_name", "quantity", "unit_cost",
                      "expected_delivery_date", "status", "created_date", "notes"]:
            assert field in po
        assert po["backlog_item_id"] == backlog_item_id
        assert po["status"] == "pending"
        assert po["quantity"] == 350
        assert isinstance(po["unit_cost"], (int, float))

    def test_get_purchase_order_by_backlog_item(self, client):
        """Test that a created purchase order can be fetched by its backlog item id."""
        backlog_item_id = unused_backlog_item_id()
        created = client.post("/api/purchase-orders", json=make_payload(backlog_item_id)).json()

        response = client.get(f"/api/purchase-orders/{backlog_item_id}")
        assert response.status_code == 200
        assert response.json() == created

    def test_get_nonexistent_purchase_order(self, client):
        """Test fetching a purchase order for a backlog item that has none."""
        response = client.get("/api/purchase-orders/nonexistent-999")
        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()

    def test_backlog_reflects_purchase_order(self, client):
        """Test that /api/backlog exposes the PO id so the dashboard shows View PO after reload."""
        backlog_item_id = unused_backlog_item_id()
        po = client.post("/api/purchase-orders", json=make_payload(backlog_item_id)).json()

        backlog = {item["id"]: item for item in client.get("/api/backlog").json()}
        assert backlog[backlog_item_id]["purchase_order_id"] == po["id"]
        assert backlog[backlog_item_id]["has_purchase_order"] is True

    def test_backlog_without_purchase_order(self, client):
        """Test that backlog items without a PO report a null id and false flag."""
        backlog_item_id = unused_backlog_item_id()
        backlog = {item["id"]: item for item in client.get("/api/backlog").json()}
        assert backlog[backlog_item_id]["purchase_order_id"] is None
        assert backlog[backlog_item_id]["has_purchase_order"] is False

    def test_create_duplicate_purchase_order(self, client):
        """Test that a second PO for the same backlog item is rejected."""
        backlog_item_id = unused_backlog_item_id()
        client.post("/api/purchase-orders", json=make_payload(backlog_item_id))

        response = client.post("/api/purchase-orders", json=make_payload(backlog_item_id))
        assert response.status_code == 409

    def test_create_purchase_order_unknown_backlog_item(self, client):
        """Test that a PO for a nonexistent backlog item is rejected."""
        response = client.post("/api/purchase-orders", json=make_payload("nonexistent-999"))
        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()

    @pytest.mark.parametrize("overrides", [
        {"quantity": 0},
        {"quantity": -5},
        {"unit_cost": 0},
        {"supplier_name": ""},
        {"supplier_name": "   "},
        {"expected_delivery_date": "not-a-date"},
        {"expected_delivery_date": (date.today() - timedelta(days=1)).isoformat()},
    ])
    def test_create_purchase_order_invalid_payload(self, client, overrides):
        """Test that invalid quantities, costs, supplier names and dates are rejected."""
        response = client.post("/api/purchase-orders", json=make_payload(unused_backlog_item_id(), **overrides))
        assert response.status_code == 422
