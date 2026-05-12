"""Todo routes demonstrating HTMX patterns.

Each handler either renders a full page or returns an HTML fragment.
HTMX sends `HX-Request: true` on AJAX requests; the handlers detect this
and return fragments for swap, or full pages for initial loads.

This is the workshop's reference example. Attendees should study these
handlers, understand the pattern, then delete them and build their own
product's routes.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse
from sqlalchemy import desc
from sqlmodel import Session, select

from app.db import get_session
from app.models.todo import Todo
from app.templates import templates

router = APIRouter()

SessionDep = Annotated[Session, Depends(get_session)]


@router.post("/todos", response_class=HTMLResponse)
async def create_todo(
    request: Request,
    session: SessionDep,
    title: Annotated[str, Form()],
) -> HTMLResponse:
    """Create a new todo and return the updated list fragment."""
    todo = Todo(title=title.strip())
    session.add(todo)
    session.commit()
    session.refresh(todo)

    todos = session.exec(select(Todo).order_by(desc("created_at"))).all()
    return templates.TemplateResponse(
        request,
        "_fragments/todo_list.html",
        {"todos": todos},
    )


@router.post("/todos/{todo_id}/toggle", response_class=HTMLResponse)
async def toggle_todo(
    request: Request,
    session: SessionDep,
    todo_id: int,
) -> HTMLResponse:
    """Toggle a todo's done state and return the single item fragment."""
    todo = session.get(Todo, todo_id)
    if todo is None:
        return HTMLResponse("", status_code=404)

    todo.done = not todo.done
    session.add(todo)
    session.commit()
    session.refresh(todo)

    return templates.TemplateResponse(
        request,
        "_fragments/todo_item.html",
        {"todo": todo},
    )


@router.delete("/todos/{todo_id}", response_class=HTMLResponse)
async def delete_todo(
    session: SessionDep,
    todo_id: int,
) -> HTMLResponse:
    """Delete a todo and return an empty response.

    HTMX removes the element from the DOM via hx-swap="outerHTML" when
    it receives an empty 200 response.
    """
    todo = session.get(Todo, todo_id)
    if todo is not None:
        session.delete(todo)
        session.commit()

    return HTMLResponse("")
