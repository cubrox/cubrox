"""Anthropic client factory + FastAPI dependency.

One client instance per process, built lazily on first use. The
`get_anthropic_client` dependency is injected into routes that need to
generate comprehension questions; tests override it with a MagicMock.

The client is built from `settings.anthropic_api_key`. An empty key is
not a startup error — the route layer catches GeneratorError on the
first call and degrades gracefully ("temporarily unavailable").
"""

from functools import lru_cache
from typing import Annotated

import anthropic
from fastapi import Depends

from app.config import Settings, get_settings


@lru_cache(maxsize=1)
def _build_client(api_key: str) -> anthropic.Anthropic:
    """Build one Anthropic client per unique api_key.

    Module-level lru_cache survives across requests so the client's
    HTTP connection pool is reused. Tests that need a fresh client
    can call `_build_client.cache_clear()`.
    """
    return anthropic.Anthropic(api_key=api_key)


def get_anthropic_client(
    settings: Annotated[Settings, Depends(get_settings)],
) -> anthropic.Anthropic:
    """FastAPI dependency that yields the shared Anthropic client.

    Tests override via `app.dependency_overrides[get_anthropic_client]`
    to inject a MagicMock. Production routes get the real client.
    """
    return _build_client(settings.anthropic_api_key)
