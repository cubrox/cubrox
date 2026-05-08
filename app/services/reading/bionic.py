"""Bionic-emphasis text transform.

Wraps the first half of each long alpha-only word in `<b>`, leaving
short words, numbers, punctuation, and whitespace structure untouched.
The bolded leading characters give the eye a fixation anchor — the
"bionic reading" approach popularly used as an ADHD reading aid.

Per the architecture's reading-surface design (and the READ-3 ticket
guardrails):

  - Server-side, never client-side. Screen readers see plain text via
    the surrounding `<article>`'s normal text content; the `<b>` tags
    are presentational only and don't change semantics.
  - Opt-in per user via `prefs.bionic_enabled`. The reading template
    only applies this filter when that flag is True; otherwise the
    user sees the raw passage text.
  - All user-supplied text is escape()'d BEFORE the `<b>` tags are
    inserted. The function returns Markup so Jinja doesn't double-
    escape the deliberate `<b>` tags we add. Adversarial input like
    `<script>` is rendered as visible escaped text, never as live HTML.
"""

import math
import re
from typing import Final

from markupsafe import Markup, escape

# Cap on how many characters get bolded — even very long words bold no
# more than this. Bolding ~all of a word defeats the purpose (the eye
# needs an unbolded "tail" to scan into).
MAX_BOLD_CHARS: Final[int] = 6

# Words shorter than this stay unmodified. Short words gain little from
# emphasis and the noise of bolding "the" or "of" hurts more than helps.
MIN_WORD_LEN: Final[int] = 4

# Splits the input into alternating runs of word-chars (\w+) and
# non-word-chars (\W+), preserving both. Capturing group keeps the
# separators in the output of re.split. \w includes letters, digits,
# and underscores in Python's default flavor; we further filter for
# pure-alpha tokens inside the loop so numbers and identifiers like
# `var_name` don't get bolded.
_TOKEN_RE: Final[re.Pattern[str]] = re.compile(r"(\W+)", re.UNICODE)


def bionicize(text: str) -> Markup:
    """Apply bionic emphasis to `text`. Returns a Jinja-safe Markup.

    Algorithm:
      1. Tokenize on word boundaries, keeping whitespace and punctuation.
      2. For each token: if it's pure alpha and at least MIN_WORD_LEN
         chars, bold the first ceil(len/2) chars (capped at
         MAX_BOLD_CHARS). Otherwise pass it through unchanged.
      3. Escape ALL user-provided text before assembling the output;
         only the literal `<b>` and `</b>` tags we emit are unescaped.
    """
    tokens = _TOKEN_RE.split(text)

    out_parts: list[Markup] = []
    for token in tokens:
        if not token:
            continue
        if len(token) >= MIN_WORD_LEN and token.isalpha():
            bold_count = min(math.ceil(len(token) / 2), MAX_BOLD_CHARS)
            head = escape(token[:bold_count])
            tail = escape(token[bold_count:])
            out_parts.append(Markup("<b>") + head + Markup("</b>") + tail)
        else:
            # Non-alpha (numbers, punctuation, whitespace) and short
            # words pass through. Still escape() to neutralise any
            # `<` / `>` / `&` the user pasted.
            out_parts.append(escape(token))

    return Markup("").join(out_parts)
