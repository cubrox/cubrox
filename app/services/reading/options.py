"""Allow-list of valid preference keys and per-key valid values.

This is the **dependent invariant** the READ-1 reviewer flagged: any
user-supplied preference value MUST be validated against this allow-list
before it reaches the rendered `<style>` block. Without it, a user who
posted `value=red;}body{display:none}` would get that string injected
verbatim into CSS via the `| safe` filter on the template (which is
necessary because legitimate CSS values like font stacks contain
apostrophes that auto-escape would mangle).

The keys here are the SAME keys used in app/services/reading/defaults.py.
Values are CSS-ready strings (or booleans for toggles) — directly
substitutable into `var(--reader-*)` declarations.
"""

from typing import Any

# Per-key allow-lists. Each list's first entry is the default (matches
# app/services/reading/defaults.py).
PREFERENCE_OPTIONS: dict[str, list[Any]] = {
    "font": [
        "Georgia, 'Iowan Old Style', 'Charter', 'Bitstream Charter', serif",
        "system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif",
        "ui-monospace, 'Cascadia Mono', 'Source Code Pro', Menlo, monospace",
    ],
    "size": ["14px", "16px", "18px", "20px", "24px", "28px"],
    "line_height": ["1.4", "1.5", "1.6", "1.8", "2.0"],
    "bg": ["#ffffff", "#f5e6d3", "#1a1a1a"],  # white, sepia, dark
    "fg": ["#1a1a1a", "#3d2914", "#e8e8e8"],  # near-black, brown, light
    "max_width": ["55ch", "65ch", "75ch", "85ch"],
    "bionic_enabled": [True, False],
}

# Friendly labels for sidebar UI section headings (the <legend> per
# fieldset). Falls back to the title-cased key with underscores replaced
# when no entry exists. Used by `label_for_key()` below.
KEY_LABELS: dict[str, str] = {
    "bg": "Background",
    "fg": "Foreground",
}

# Friendly labels for sidebar UI buttons. Keyed by (preference_key, value).
# Falls back to str(value) when no entry exists.
PREFERENCE_LABELS: dict[tuple[str, Any], str] = {
    ("font", "Georgia, 'Iowan Old Style', 'Charter', 'Bitstream Charter', serif"): "Serif",
    ("font", "system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif"): "Sans",
    ("font", "ui-monospace, 'Cascadia Mono', 'Source Code Pro', Menlo, monospace"): "Mono",
    ("bg", "#ffffff"): "Light bg",
    ("bg", "#f5e6d3"): "Sepia bg",
    ("bg", "#1a1a1a"): "Dark bg",
    ("fg", "#1a1a1a"): "Dark text",
    ("fg", "#3d2914"): "Sepia text",
    ("fg", "#e8e8e8"): "Light text",
    ("bionic_enabled", True): "On",
    ("bionic_enabled", False): "Off",
    ("max_width", "55ch"): "Narrow",
    ("max_width", "65ch"): "Standard",
    ("max_width", "75ch"): "Wide",
    ("max_width", "85ch"): "Extra wide",
}


def coerce_value(key: str, raw: str) -> Any:
    """Coerce a Form-submitted string into the right type for the given key.

    Form data arrives as strings. Most preference values are stored as
    strings already (e.g., '18px', '#ffffff', '1.6'). The exception is
    `bionic_enabled`, which is a boolean. Returns None if coercion fails.
    """
    if key == "bionic_enabled":
        if raw == "true":
            return True
        if raw == "false":
            return False
        return None
    return raw


def label_for(key: str, value: Any) -> str:
    """Return a friendly UI label for a (key, value) pair.

    Falls back to str(value) when no friendly label exists. Used by the
    sidebar template to render button text.
    """
    return PREFERENCE_LABELS.get((key, value), str(value))


def label_for_key(key: str) -> str:
    """Return a friendly UI label for a preference key (section heading).

    Falls back to the title-cased key with underscores replaced when no
    explicit label exists. Used by the sidebar template's <legend> for
    each fieldset. Examples: `bg` -> "Background", `line_height` ->
    "Line Height" (via fallback).
    """
    return KEY_LABELS.get(key, key.replace("_", " ").title())


def value_for_form(value: Any) -> str:
    """Render a preference value as the string the route expects to receive.

    The route's `coerce_value()` accepts lowercase 'true'/'false' for the
    bionic_enabled boolean. Python's str(True) is 'True' (capitalized),
    so a naive template render of `{{ opt | string }}` would emit a value
    the route then rejects with 422. This helper produces the lowercase
    form for booleans and str(value) for everything else.
    """
    if value is True:
        return "true"
    if value is False:
        return "false"
    return str(value)
