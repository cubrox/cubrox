"""Default reading preferences.

These render for every user who has no Preference row yet — i.e., every
user before they've toggled anything. Per the architecture doc:

  - serif font stack (better for sustained reading per typography research)
  - 18px base size
  - 1.6 line-height
  - white background, near-black foreground (high but not maximum contrast)
  - 65ch max width (the classic readable measure)
  - bionic emphasis off (opt-in only; ships in READ-3 #17)

The keys here are the canonical preference keys for the rest of the
codebase. READ-2 (#16) will validate user input against this same set.

Values are CSS-ready strings (or booleans). The reading template inlines
them as :root CSS variable values without further conversion.
"""

from typing import Any

DEFAULT_PREFERENCES: dict[str, Any] = {
    "font": "Georgia, 'Iowan Old Style', 'Charter', 'Bitstream Charter', serif",
    "size": "18px",
    "line_height": "1.6",
    "bg": "#ffffff",
    "fg": "#1a1a1a",
    "max_width": "65ch",
    "bionic_enabled": False,
}


def with_defaults(stored: dict[str, Any] | None) -> dict[str, Any]:
    """Merge a stored preference dict on top of the defaults.

    Returns a new dict — never mutates either input. If `stored` is None
    or empty, the returned dict is exactly the defaults. If `stored`
    contains keys not in DEFAULT_PREFERENCES, they're carried through
    (forward-compat for new keys added later).
    """
    merged = dict(DEFAULT_PREFERENCES)
    if stored:
        merged.update(stored)
    return merged
