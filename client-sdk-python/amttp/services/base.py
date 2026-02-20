"""
AMTTP Python SDK — base service class.

Every service (Risk, KYC, Sanctions …) inherits from :class:`BaseService`
which holds the shared ``httpx.AsyncClient`` and ``EventEmitter`` references.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import httpx

    from amttp.events import EventEmitter


class BaseService:
    """Shared base for all AMTTP API service wrappers."""

    def __init__(self, http: "httpx.AsyncClient", events: "EventEmitter") -> None:
        self._http = http
        self._events = events
