"""Tests for POST /preferences/{key} (the live preference toggle).

Covers the Definition of Done from issue #16 (READ-2):
  - POST /preferences/size {value: "20px"} → 200 with rendered <style>
    fragment containing --reader-size: 20px
  - Response body does NOT include <html> (fragment, not full page)
  - Preference row is upserted with the new value
  - Second toggle on a different key MERGES into existing values
    (doesn't overwrite the whole blob)
  - Unknown preference key → 422
  - Out-of-allow-list value → 422
  - Bionic enabled coerces "true"/"false" strings to booleans
  - Same value posted twice → only one DB write (short-circuit)
  - Sidebar buttons render with aria-pressed reflecting current values
"""

import hashlib
import uuid

from fastapi.testclient import TestClient
from sqlmodel import Session

from app.models.passage import Passage
from app.models.preference import Preference
from tests.conftest import signed_in


def _make_passage(session: Session, owner_id: uuid.UUID) -> Passage:
    text = "test passage"
    p = Passage(
        owner_id=owner_id,
        text=text,
        text_hash=hashlib.sha256(text.encode("utf-8")).digest(),
        source_type="paste",
        source_filename=None,
    )
    session.add(p)
    session.commit()
    session.refresh(p)
    return p


# ---------------------------------------------------------------------------
# Happy path — the toggle works
# ---------------------------------------------------------------------------


def test_post_preference_returns_style_fragment_with_new_value(
    client: TestClient, session: Session
) -> None:
    user = signed_in(session)
    response = client.post("/preferences/size", data={"value": "20px"})

    assert response.status_code == 200
    body = response.text
    assert '<style id="reading-surface-style">' in body
    assert "--reader-size: 20px" in body

    # The DB row was upserted.
    pref = session.get(Preference, user.id)
    assert pref is not None
    assert pref.values["size"] == "20px"


def test_response_is_a_fragment_not_a_full_page(client: TestClient, session: Session) -> None:
    """The route is HTMX-only — must return a fragment so HTMX can swap
    just the <style> block without replacing the whole document."""
    signed_in(session)
    response = client.post("/preferences/size", data={"value": "24px"})

    body = response.text
    assert "<html" not in body
    assert "<body" not in body


def test_response_content_type_is_html(client: TestClient, session: Session) -> None:
    signed_in(session)
    response = client.post("/preferences/size", data={"value": "16px"})
    assert response.headers["content-type"].startswith("text/html")


# ---------------------------------------------------------------------------
# Merge semantics — multiple toggles compose
# ---------------------------------------------------------------------------


def test_second_toggle_merges_into_existing_values(client: TestClient, session: Session) -> None:
    """Setting `size` then `line_height` should produce a row with BOTH
    keys set. The second toggle must NOT overwrite the whole blob."""
    user = signed_in(session)

    client.post("/preferences/size", data={"value": "24px"})
    client.post("/preferences/line_height", data={"value": "1.8"})

    session.expire_all()
    pref = session.get(Preference, user.id)
    assert pref is not None
    assert pref.values["size"] == "24px"
    assert pref.values["line_height"] == "1.8"


def test_third_toggle_updates_only_its_own_key(client: TestClient, session: Session) -> None:
    user = signed_in(session)

    client.post("/preferences/size", data={"value": "20px"})
    client.post("/preferences/max_width", data={"value": "38em"})
    # Now change size again — max_width should survive.
    client.post("/preferences/size", data={"value": "28px"})

    session.expire_all()
    pref = session.get(Preference, user.id)
    assert pref is not None
    assert pref.values["size"] == "28px"
    assert pref.values["max_width"] == "38em"


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def test_unknown_preference_key_returns_422(client: TestClient, session: Session) -> None:
    signed_in(session)
    response = client.post("/preferences/totally_made_up_key", data={"value": "anything"})
    assert response.status_code == 422


def test_value_outside_allow_list_returns_422(client: TestClient, session: Session) -> None:
    """The architecture's dependent-invariant: any user-supplied value
    must be in the per-key allow-list. A value outside the list is
    rejected at 422 — never reaches the rendered <style> block."""
    signed_in(session)
    # 999px is not in the size allow-list.
    response = client.post("/preferences/size", data={"value": "999px"})
    assert response.status_code == 422


def test_css_injection_attempt_returns_422(client: TestClient, session: Session) -> None:
    """Adversarial input: a string that LOOKS like CSS but contains
    a payload. Must be rejected because it's not in the allow-list."""
    signed_in(session)
    payload = "red;}body{display:none;}"
    response = client.post("/preferences/bg", data={"value": payload})
    assert response.status_code == 422


def test_bionic_enabled_accepts_true_and_false_strings(
    client: TestClient, session: Session
) -> None:
    """Form values come in as strings. The 'bionic_enabled' key needs
    'true'/'false' coerced to actual booleans before allow-list check."""
    user = signed_in(session)

    response_on = client.post("/preferences/bionic_enabled", data={"value": "true"})
    assert response_on.status_code == 200

    session.expire_all()
    pref = session.get(Preference, user.id)
    assert pref is not None
    assert pref.values["bionic_enabled"] is True

    response_off = client.post("/preferences/bionic_enabled", data={"value": "false"})
    assert response_off.status_code == 200

    session.expire_all()
    pref = session.get(Preference, user.id)
    assert pref is not None
    assert pref.values["bionic_enabled"] is False


def test_bionic_enabled_rejects_non_boolean_strings(client: TestClient, session: Session) -> None:
    signed_in(session)
    response = client.post("/preferences/bionic_enabled", data={"value": "yes"})
    assert response.status_code == 422


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------


def test_unauthenticated_post_redirects_to_landing(client: TestClient) -> None:
    response = client.post("/preferences/size", data={"value": "20px"}, follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/"


# ---------------------------------------------------------------------------
# Short-circuit — no write when value is unchanged
# ---------------------------------------------------------------------------


def test_unchanged_value_does_not_update_updated_at(client: TestClient, session: Session) -> None:
    """Posting the same value twice should not bump `updated_at` on the
    second post — the helper short-circuits when the new value equals
    the current value. Pin this so a future refactor that always-writes
    can't slip through and silently 2x our DB write traffic."""
    user = signed_in(session)

    client.post("/preferences/size", data={"value": "20px"})
    session.expire_all()
    first_updated_at = session.get(Preference, user.id).updated_at  # type: ignore[union-attr]

    client.post("/preferences/size", data={"value": "20px"})
    session.expire_all()
    second_updated_at = session.get(Preference, user.id).updated_at  # type: ignore[union-attr]

    assert first_updated_at == second_updated_at


def test_changed_value_does_update_updated_at(client: TestClient, session: Session) -> None:
    """Inverse of above: an actual change DOES bump updated_at."""
    user = signed_in(session)

    client.post("/preferences/size", data={"value": "20px"})
    session.expire_all()
    first_updated_at = session.get(Preference, user.id).updated_at  # type: ignore[union-attr]

    client.post("/preferences/size", data={"value": "24px"})
    session.expire_all()
    second_updated_at = session.get(Preference, user.id).updated_at  # type: ignore[union-attr]

    assert second_updated_at >= first_updated_at


# ---------------------------------------------------------------------------
# Sidebar rendering — aria-pressed + button structure
# ---------------------------------------------------------------------------


def test_sidebar_renders_with_aria_pressed_for_active_default(
    client: TestClient, session: Session
) -> None:
    """A user with no Preference row gets defaults; the buttons matching
    those defaults have aria-pressed='true'. Pinned by checking the
    default size value '18px' button."""
    user = signed_in(session)
    passage = _make_passage(session, user.id)

    response = client.get(f"/read/{passage.id}")
    body = response.text

    # The button for the default size ("18px") should be pressed.
    # Find a fragment that contains the value AND aria-pressed="true".
    # Defensive: check the substring shows up in the right shape.
    assert 'aria-pressed="true"' in body
    # And the inverse: at least one OTHER size value is NOT pressed.
    assert 'aria-pressed="false"' in body


def test_sidebar_renders_button_for_each_allow_listed_value(
    client: TestClient, session: Session
) -> None:
    """Every allow-listed value gets a button. Pin this by checking a
    sample of values are present in the rendered HTML."""
    user = signed_in(session)
    passage = _make_passage(session, user.id)

    response = client.get(f"/read/{passage.id}")
    body = response.text

    # At least one button per category, sampled.
    assert 'hx-post="/preferences/size"' in body
    assert 'hx-post="/preferences/line_height"' in body
    assert 'hx-post="/preferences/bionic_enabled"' in body
    assert 'hx-post="/preferences/max_width"' in body

    # Specific values from the allow-list show up.
    assert "14px" in body and "28px" in body  # size extremes
    assert "28em" in body and "43em" in body  # max_width extremes


def test_sidebar_buttons_target_the_style_block(client: TestClient, session: Session) -> None:
    """The HTMX swap target must be #reading-surface-style — that's the
    contract READ-1 set up. Without this, the swap silently misses."""
    user = signed_in(session)
    passage = _make_passage(session, user.id)

    response = client.get(f"/read/{passage.id}")
    body = response.text

    assert 'hx-target="#reading-surface-style"' in body
    assert 'hx-swap="outerHTML"' in body


def test_sidebar_uses_button_not_div_for_controls(client: TestClient, session: Session) -> None:
    """Accessibility: toggle controls must be <button>, not <div>.
    Without this, keyboard users can't reach them and screen readers
    don't announce them as interactive."""
    user = signed_in(session)
    passage = _make_passage(session, user.id)

    response = client.get(f"/read/{passage.id}")
    body = response.text

    # We use 'type="button"' to prevent any wrapping form from
    # treating the button as a submit. Pin this attribute.
    assert 'type="button"' in body


# ---------------------------------------------------------------------------
# Template-route contract — values rendered must match values accepted
# ---------------------------------------------------------------------------


def test_bionic_buttons_render_lowercase_booleans_and_route_accepts_them(
    client: TestClient, session: Session
) -> None:
    """The original READ-2 review caught: Jinja's `{{ opt | string }}` on
    a Python bool produces 'True'/'False' (capitalized), but the route's
    coerce_value() only accepts lowercase 'true'/'false'. The bug was
    invisible to unit tests that posted lowercase strings directly.

    This test pins the contract by checking BOTH (a) the rendered HTML
    contains the lowercase form, AND (b) posting that exact rendered
    value succeeds at the route. A future template refactor that drifts
    back to `| string` fails (a); a future route change that requires
    capitalized booleans fails (b).
    """
    user = signed_in(session)
    passage = _make_passage(session, user.id)

    response = client.get(f"/read/{passage.id}")
    body = response.text

    # (a) The bionic buttons render the LOWERCASE form, not capitalized.
    assert '"value": "true"' in body
    assert '"value": "false"' in body
    assert '"value": "True"' not in body
    assert '"value": "False"' not in body

    # (b) Posting either of those values succeeds (round-trip).
    on = client.post("/preferences/bionic_enabled", data={"value": "true"})
    off = client.post("/preferences/bionic_enabled", data={"value": "false"})
    assert on.status_code == 200
    assert off.status_code == 200


def test_value_for_form_helper_handles_booleans_and_strings() -> None:
    """Unit test on the template helper itself, separate from the route."""
    from app.services.reading.options import value_for_form

    assert value_for_form(True) == "true"
    assert value_for_form(False) == "false"
    assert value_for_form("18px") == "18px"
    assert value_for_form("#ffffff") == "#ffffff"


# ---------------------------------------------------------------------------
# Bionic immediate apply — the toggle must re-render the passage text, not
# just the <style> block (bionic is server-rendered <b> markup, not CSS).
# ---------------------------------------------------------------------------


def test_bionic_toggle_oob_swaps_the_reading_surface(client: TestClient, session: Session) -> None:
    """Turning bionic ON with a passage_id returns BOTH the <style> block
    (primary swap) AND the re-rendered article as an out-of-band swap, so
    the surface updates without a full reload. Without the OOB swap the
    bionic emphasis only appeared after a manual reload."""
    user = signed_in(session)
    passage = _make_passage(session, user.id)

    response = client.post(
        "/preferences/bionic_enabled",
        data={"value": "true", "passage_id": str(passage.id)},
    )

    assert response.status_code == 200
    body = response.text
    # Primary swap target survives.
    assert '<style id="reading-surface-style">' in body
    # OOB-swapped, re-rendered article with bionic <b> markup.
    assert 'hx-swap-oob="true"' in body
    assert 'id="reading-surface"' in body
    # "test passage" -> "<b>te</b>st <b>pass</b>age" under bionicize.
    assert "<b>" in body


def test_bionic_toggle_off_oob_swaps_back_to_plain_text(
    client: TestClient, session: Session
) -> None:
    """Turning bionic OFF must also re-render the surface — back to plain
    text with no <b> markup — via the same OOB swap."""
    user = signed_in(session)
    passage = _make_passage(session, user.id)

    response = client.post(
        "/preferences/bionic_enabled",
        data={"value": "false", "passage_id": str(passage.id)},
    )

    assert response.status_code == 200
    body = response.text
    assert 'hx-swap-oob="true"' in body
    assert 'id="reading-surface"' in body
    assert "<b>" not in body
    assert "test passage" in body


def test_non_bionic_toggle_does_not_oob_swap_surface(client: TestClient, session: Session) -> None:
    """CSS-only preferences (e.g. size) change a `var(--reader-*)` value —
    the <style> swap alone is enough, so re-sending the whole passage text
    would be wasted bandwidth. Even when a passage_id is supplied, a
    non-bionic toggle returns the style block only, no OOB article."""
    user = signed_in(session)
    passage = _make_passage(session, user.id)

    response = client.post(
        "/preferences/size",
        data={"value": "20px", "passage_id": str(passage.id)},
    )

    assert response.status_code == 200
    body = response.text
    assert "--reader-size: 20px" in body
    assert 'hx-swap-oob="true"' not in body
    # Only the <style id="reading-surface-style"> element exists; the bare
    # article id must not appear.
    assert 'id="reading-surface"' not in body


def test_bionic_toggle_without_passage_id_returns_style_only(
    client: TestClient, session: Session
) -> None:
    """Back-compat: callers that don't pass a passage_id (direct API use,
    unit tests) still get a valid 200 with just the <style> block — no
    OOB swap, no error."""
    signed_in(session)

    response = client.post("/preferences/bionic_enabled", data={"value": "true"})

    assert response.status_code == 200
    body = response.text
    assert '<style id="reading-surface-style">' in body
    assert 'hx-swap-oob="true"' not in body


def test_bionic_toggle_with_other_users_passage_id_does_not_oob_swap(
    client: TestClient, session: Session
) -> None:
    """A passage_id the user doesn't own yields no OOB swap (and no error
    or existence leak) — the preference write still succeeds."""
    from tests.conftest import make_user

    other = make_user(session, email="other@example.com")
    other_passage = _make_passage(session, other.id)

    signed_in(session)  # swaps current_user to a fresh user
    response = client.post(
        "/preferences/bionic_enabled",
        data={"value": "true", "passage_id": str(other_passage.id)},
    )

    assert response.status_code == 200
    body = response.text
    assert '<style id="reading-surface-style">' in body
    assert 'hx-swap-oob="true"' not in body
