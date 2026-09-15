"""
Tests for task API endpoints.
"""
from datetime import date, timedelta

import pytest

import mock_data  # importable because conftest.py puts server/ on sys.path


@pytest.fixture(autouse=True)
def reset_tasks():
    """Writes mutate the module-level list; clear it in place so main.py sees the same object."""
    mock_data.tasks.clear()
    yield
    mock_data.tasks.clear()


def make_task(client, title="Review stock levels", priority="high", due_date=None):
    """Create a task through the API and return the response."""
    due_date = due_date or (date.today() + timedelta(days=3)).isoformat()
    return client.post("/api/tasks", json={"title": title, "priority": priority, "dueDate": due_date})


class TestTaskEndpoints:
    """Test suite for task endpoints."""

    def test_get_tasks_empty(self, client):
        """Test that no API tasks exist before any are created."""
        response = client.get("/api/tasks")
        assert response.status_code == 200
        assert response.json() == []

    def test_create_task(self, client):
        """Test creating a task returns 201 with the shape TasksModal renders."""
        response = make_task(client, title="Approve Tokyo orders", priority="medium", due_date="2030-01-15")
        assert response.status_code == 201

        task = response.json()
        assert task["title"] == "Approve Tokyo orders"
        assert task["priority"] == "medium"
        assert task["dueDate"] == "2030-01-15"
        assert task["status"] == "pending"

    def test_task_ids_do_not_collide_with_demo_tasks(self, client):
        """Test that API task ids are not plain numbers, which App.vue reserves for demo tasks."""
        task = make_task(client).json()
        assert isinstance(task["id"], str)
        assert not task["id"].isdigit()

    def test_task_ids_not_reused_after_delete(self, client):
        """Test that deleting a task does not free its id for the next task."""
        first = make_task(client).json()
        client.delete(f"/api/tasks/{first['id']}")

        second = make_task(client).json()
        assert second["id"] != first["id"]

    def test_get_tasks_newest_first(self, client):
        """Test that tasks are listed newest first, matching the client's unshift on create."""
        make_task(client, title="First")
        make_task(client, title="Second")

        titles = [task["title"] for task in client.get("/api/tasks").json()]
        assert titles == ["Second", "First"]

    def test_create_task_trims_title(self, client):
        """Test that surrounding whitespace is stripped from titles."""
        task = make_task(client, title="  Call supplier  ").json()
        assert task["title"] == "Call supplier"

    @pytest.mark.parametrize("payload", [
        {"title": "", "priority": "high", "dueDate": "2030-01-01"},
        {"title": "   ", "priority": "high", "dueDate": "2030-01-01"},
        {"title": "Task", "priority": "urgent", "dueDate": "2030-01-01"},
        {"title": "Task", "priority": "high", "dueDate": "not-a-date"},
        {"title": "Task", "priority": "high"},
    ])
    def test_create_task_invalid_payload(self, client, payload):
        """Test that blank titles, unknown priorities and bad dates are rejected."""
        response = client.post("/api/tasks", json=payload)
        assert response.status_code == 422

    def test_toggle_task(self, client):
        """Test that PATCH flips status to completed and back to pending."""
        task_id = make_task(client).json()["id"]

        response = client.patch(f"/api/tasks/{task_id}")
        assert response.status_code == 200
        assert response.json()["status"] == "completed"

        response = client.patch(f"/api/tasks/{task_id}")
        assert response.json()["status"] == "pending"

    def test_toggle_nonexistent_task(self, client):
        """Test toggling a task that doesn't exist."""
        response = client.patch("/api/tasks/task-999")
        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()

    def test_delete_task(self, client):
        """Test that a deleted task no longer appears in the list."""
        task_id = make_task(client).json()["id"]

        response = client.delete(f"/api/tasks/{task_id}")
        assert response.status_code == 204
        assert client.get("/api/tasks").json() == []

    def test_delete_nonexistent_task(self, client):
        """Test deleting a task that doesn't exist."""
        response = client.delete("/api/tasks/task-999")
        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()
