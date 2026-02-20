"""
AMTTP Python SDK — lightweight event emitter.

Mirrors the TypeScript ``EventEmitter`` to support
``client.events.on("risk:assessed", callback)`` style usage.
"""

from __future__ import annotations

import asyncio
import logging
from collections import defaultdict
from typing import Any, Callable, Dict, List

logger = logging.getLogger("amttp.events")

Listener = Callable[..., Any]


class EventEmitter:
    """Simple synchronous + async event emitter."""

    def __init__(self) -> None:
        self._listeners: Dict[str, List[Listener]] = defaultdict(list)

    # ── registration ──────────────────────────────────────────────────────

    def on(self, event: str, listener: Listener) -> "EventEmitter":
        """Register *listener* for *event*. Returns ``self`` for chaining."""
        self._listeners[event].append(listener)
        return self

    def off(self, event: str, listener: Listener) -> "EventEmitter":
        """Remove *listener* from *event*."""
        try:
            self._listeners[event].remove(listener)
        except ValueError:
            pass
        return self

    def once(self, event: str, listener: Listener) -> "EventEmitter":
        """Register *listener* that fires at most once."""

        def _wrapper(*args: Any, **kwargs: Any) -> Any:
            self.off(event, _wrapper)
            return listener(*args, **kwargs)

        return self.on(event, _wrapper)

    def remove_all_listeners(self, event: str | None = None) -> "EventEmitter":
        if event is None:
            self._listeners.clear()
        else:
            self._listeners.pop(event, None)
        return self

    # ── emitting ──────────────────────────────────────────────────────────

    def emit(self, event: str, *args: Any, **kwargs: Any) -> bool:
        """Invoke all listeners for *event*. Returns ``True`` if any existed."""
        listeners = list(self._listeners.get(event, []))
        if not listeners:
            return False
        for fn in listeners:
            try:
                result = fn(*args, **kwargs)
                # If the listener is a coroutine, schedule it
                if asyncio.iscoroutine(result):
                    try:
                        loop = asyncio.get_running_loop()
                        loop.create_task(result)
                    except RuntimeError:
                        asyncio.run(result)
            except Exception:
                logger.exception("Error in listener for event %r", event)
        return True

    @property
    def event_names(self) -> List[str]:
        return list(self._listeners.keys())
