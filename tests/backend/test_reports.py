"""
Tests for report API endpoints.
"""
import pytest

import mock_data  # importable because conftest.py puts server/ on sys.path


QUARTERLY_FIELDS = ["quarter", "total_orders", "total_revenue", "delivered_orders", "avg_order_value",
                    "fulfillment_rate"]
MONTHLY_FIELDS = ["month", "order_count", "revenue", "delivered_count"]


class TestQuarterlyReportEndpoints:
    """Test suite for the quarterly report endpoint."""

    def test_get_quarterly_reports(self, client):
        """Test getting quarterly reports without filters."""
        response = client.get("/api/reports/quarterly")
        assert response.status_code == 200

        data = response.json()
        assert isinstance(data, list)
        assert len(data) == 4
        for quarter in data:
            for field in QUARTERLY_FIELDS:
                assert field in quarter

    def test_quarterly_totals_match_orders(self, client):
        """Test that unfiltered quarterly totals add up to every order."""
        data = client.get("/api/reports/quarterly").json()

        assert sum(q["total_orders"] for q in data) == len(mock_data.orders)
        expected_revenue = sum(order["total_value"] for order in mock_data.orders)
        assert abs(sum(q["total_revenue"] for q in data) - expected_revenue) < 0.05

    def test_quarterly_calculations(self, client):
        """Test average order value and fulfillment rate are derived correctly."""
        for quarter in client.get("/api/reports/quarterly").json():
            assert abs(quarter["avg_order_value"] - quarter["total_revenue"] / quarter["total_orders"]) < 0.01
            expected_rate = quarter["delivered_orders"] / quarter["total_orders"] * 100
            assert abs(quarter["fulfillment_rate"] - expected_rate) < 0.1

    def test_get_quarterly_reports_by_month(self, client):
        """Test that a month filter narrows reports to that month's quarter."""
        data = client.get("/api/reports/quarterly?month=2025-01").json()

        january_orders = [o for o in mock_data.orders if o["order_date"].startswith("2025-01")]
        assert [q["quarter"] for q in data] == ["Q1-2025"]
        assert data[0]["total_orders"] == len(january_orders)

    def test_get_quarterly_reports_by_warehouse(self, client):
        """Test filtering quarterly reports by warehouse."""
        data = client.get("/api/reports/quarterly?warehouse=Tokyo").json()

        tokyo_orders = [o for o in mock_data.orders if o.get("warehouse") == "Tokyo"]
        assert sum(q["total_orders"] for q in data) == len(tokyo_orders)

    def test_get_quarterly_reports_by_delivered_status(self, client):
        """Test that filtering to delivered orders yields a 100% fulfillment rate."""
        data = client.get("/api/reports/quarterly?status=Delivered").json()

        assert len(data) > 0
        for quarter in data:
            assert quarter["fulfillment_rate"] == 100.0

    def test_quarterly_sorted_by_year_then_quarter(self, client, monkeypatch):
        """Test that quarters sort chronologically across years, not as strings."""
        extra = [
            {**mock_data.orders[0], "id": "x1", "order_date": "2026-01-15T00:00:00"},
            {**mock_data.orders[0], "id": "x2", "order_date": "2025-11-15T00:00:00"},
        ]
        monkeypatch.setattr("main.orders", extra)

        data = client.get("/api/reports/quarterly").json()
        assert [q["quarter"] for q in data] == ["Q4-2025", "Q1-2026"]

    def test_get_quarterly_reports_no_matches(self, client):
        """Test that filters matching nothing return an empty list."""
        response = client.get("/api/reports/quarterly?warehouse=Nowhere")
        assert response.status_code == 200
        assert response.json() == []


class TestMonthlyTrendEndpoints:
    """Test suite for the monthly trends endpoint."""

    def test_get_monthly_trends(self, client):
        """Test getting monthly trends without filters."""
        response = client.get("/api/reports/monthly-trends")
        assert response.status_code == 200

        data = response.json()
        assert len(data) == 12
        for month in data:
            for field in MONTHLY_FIELDS:
                assert field in month

    def test_monthly_trends_sorted(self, client):
        """Test that months are returned in chronological order."""
        months = [m["month"] for m in client.get("/api/reports/monthly-trends").json()]
        assert months == sorted(months)

    def test_monthly_revenue_is_rounded(self, client):
        """Test that summed revenue has no float artifacts like 1993655.7400000002."""
        for month in client.get("/api/reports/monthly-trends").json():
            assert round(month["revenue"], 2) == month["revenue"]

    @pytest.mark.parametrize("query, predicate", [
        ("warehouse=London", lambda o: o.get("warehouse") == "London"),
        ("category=sensors", lambda o: o.get("category", "").lower() == "sensors"),
        ("status=Shipped", lambda o: o["status"] == "Shipped"),
        ("month=2025-03", lambda o: o["order_date"].startswith("2025-03")),
        ("month=Q2-2025", lambda o: o["order_date"][:7] in ("2025-04", "2025-05", "2025-06")),
    ])
    def test_get_monthly_trends_by_filter(self, client, query, predicate):
        """Test each filter individually against the raw order data."""
        data = client.get(f"/api/reports/monthly-trends?{query}").json()

        expected = [o for o in mock_data.orders if predicate(o)]
        assert sum(m["order_count"] for m in data) == len(expected)

    def test_get_monthly_trends_multiple_filters(self, client):
        """Test filtering monthly trends by warehouse and month together."""
        data = client.get("/api/reports/monthly-trends?warehouse=Tokyo&month=2025-03").json()

        expected = [o for o in mock_data.orders
                    if o.get("warehouse") == "Tokyo" and o["order_date"].startswith("2025-03")]
        assert [m["month"] for m in data] == (["2025-03"] if expected else [])
        assert sum(m["order_count"] for m in data) == len(expected)

    def test_reports_match_dashboard_revenue(self, client):
        """Test that filtered report revenue agrees with the dashboard for the same filters."""
        query = "warehouse=San Francisco&month=2025-06"
        trends = client.get(f"/api/reports/monthly-trends?{query}").json()
        orders = client.get(f"/api/orders?{query}").json()

        assert abs(sum(m["revenue"] for m in trends) - sum(o["total_value"] for o in orders)) < 0.05
