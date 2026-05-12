"""Tests for the HTMX todo routes.

These exercise the full request/response cycle including template
rendering, so they catch both API regressions and template breakage.
"""

from fastapi.testclient import TestClient
from sqlmodel import Session, select

from app.models.todo import Todo


def test_create_todo_returns_updated_list_fragment(
    client: TestClient,
    session: Session,
) -> None:
    response = client.post("/todos", data={"title": "buy milk"})
    assert response.status_code == 200
    assert "buy milk" in response.text
    # Fragment response should not include the full page chrome
    assert "<html" not in response.text
    assert 'id="todo-list"' in response.text

    # Verify persistence
    todos = session.exec(select(Todo)).all()
    assert len(todos) == 1
    assert todos[0].title == "buy milk"
    assert todos[0].done is False


def test_toggle_todo_flips_done_state(
    client: TestClient,
    session: Session,
) -> None:
    todo = Todo(title="read book", done=False)
    session.add(todo)
    session.commit()
    session.refresh(todo)

    response = client.post(f"/todos/{todo.id}/toggle")
    assert response.status_code == 200
    assert "todo-done" in response.text

    session.refresh(todo)
    assert todo.done is True


def test_toggle_nonexistent_todo_returns_404(client: TestClient) -> None:
    response = client.post("/todos/999/toggle")
    assert response.status_code == 404


def test_delete_todo_returns_empty_and_removes_record(
    client: TestClient,
    session: Session,
) -> None:
    todo = Todo(title="transient")
    session.add(todo)
    session.commit()
    session.refresh(todo)

    response = client.delete(f"/todos/{todo.id}")
    assert response.status_code == 200
    assert response.text == ""

    todos = session.exec(select(Todo)).all()
    assert len(todos) == 0


def test_delete_nonexistent_todo_is_idempotent(client: TestClient) -> None:
    response = client.delete("/todos/999")
    assert response.status_code == 200
    assert response.text == ""
