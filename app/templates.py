"""Shared Jinja2 templates instance.

Exported from a single module so routes and tests agree on the template
directory. This also makes it easy to override in tests.

Custom filters registered here:
  - `bionic` — server-side bionic-emphasis transform. Used by the
    reading view when `prefs.bionic_enabled` is True. See
    app/services/reading/bionic.py.
"""

from pathlib import Path

from fastapi.templating import Jinja2Templates

from app.services.reading.bionic import bionicize

TEMPLATE_DIR = Path(__file__).parent.parent / "templates"

templates = Jinja2Templates(directory=str(TEMPLATE_DIR))
templates.env.filters["bionic"] = bionicize
