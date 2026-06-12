"""Default reading preferences.

These render for every user who has no Preference row yet — i.e., every
user before they've toggled anything. Per the architecture doc:

  - serif font stack (better for sustained reading per typography research)
  - 18px base size
  - 1.6 line-height
  - white background, near-black foreground (high but not maximum contrast)
  - 33em max width (~65 characters; in `em` not `ch` so the column is the
    same width across computers regardless of the rendered font)
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
    "max_width": "33em",
    "bionic_enabled": False,
}


# Map legacy `ch`-based max_width values (stored before the switch to `em`)
# to their em equivalents, so existing users get the cross-machine-consistent
# width without having to re-pick. Any other stale `ch` value falls back to
# the default. See the width-unit fix.
_LEGACY_CH_TO_EM: dict[str, str] = {
    "55ch": "28em",
    "65ch": "33em",
    "75ch": "38em",
    "85ch": "43em",
}


def with_defaults(stored: dict[str, Any] | None) -> dict[str, Any]:
    """Merge a stored preference dict on top of the defaults.

    Returns a new dict — never mutates either input. If `stored` is None
    or empty, the returned dict is exactly the defaults. If `stored`
    contains keys not in DEFAULT_PREFERENCES, they're carried through
    (forward-compat for new keys added later). A legacy `ch` max_width is
    normalized to its `em` equivalent on the way out.
    """
    merged = dict(DEFAULT_PREFERENCES)
    if stored:
        merged.update(stored)
    width = merged.get("max_width")
    if isinstance(width, str) and width.endswith("ch"):
        merged["max_width"] = _LEGACY_CH_TO_EM.get(width, DEFAULT_PREFERENCES["max_width"])
    return merged
