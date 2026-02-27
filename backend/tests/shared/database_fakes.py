"""
Shared test fakes for database repository unit tests.
"""

from __future__ import annotations

import contextlib
from typing import Any
from collections.abc import Iterator


class FakeCursor:
    """Minimal cursor that records executions and returns pre-configured results."""

    def __init__(
        self,
        *,
        fetchone_results: list[Any] | None = None,
        fetchall_results: list[list[Any]] | None = None,
        rowcounts: list[int] | None = None,
        execute_side_effect: Exception | None = None,
    ):
        self._fetchone_results = list(fetchone_results or [])
        self._fetchall_results = list(fetchall_results or [])
        self._rowcounts = list(rowcounts or [])
        self._execute_side_effect = execute_side_effect
        self.executed: list[tuple[str, object]] = []
        self.rowcount = 1

    def execute(self, sql: str, params: Any = None) -> None:
        if self._execute_side_effect is not None:
            raise self._execute_side_effect
        self.executed.append((sql, params))
        if self._rowcounts:
            self.rowcount = self._rowcounts.pop(0)

    def fetchone(self) -> Any:
        if self._fetchone_results:
            return self._fetchone_results.pop(0)
        return None

    def fetchall(self) -> list[Any]:
        if self._fetchall_results:
            return self._fetchall_results.pop(0)
        return []

    def __enter__(self) -> FakeCursor:
        return self

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> bool:
        return False


class FakeConnection:
    """Connection that returns pre-configured cursors."""

    def __init__(self, cursors: list[FakeCursor]) -> None:
        self._cursors = list(cursors)

    def cursor(self, *args: Any, **kwargs: Any) -> FakeCursor:
        if not self._cursors:
            raise AssertionError("No fake cursor available.")
        return self._cursors.pop(0)


def patch_connection(monkeypatch: Any, module: Any, cursors: list[FakeCursor]) -> None:
    """Replace ``module.connection.get_connection`` with a fake that yields *cursors*."""
    conn = FakeConnection(cursors)

    @contextlib.contextmanager
    def _get_connection() -> Iterator[FakeConnection]:
        yield conn

    monkeypatch.setattr(module.connection, "get_connection", _get_connection)


def patch_connection_error(monkeypatch: Any, module: Any, error: Exception) -> None:
    """Replace ``module.connection.get_connection`` so it raises *error* on entry."""

    @contextlib.contextmanager
    def _get_connection() -> Iterator[None]:
        raise error
        yield  # noqa: unreachable - keeps it a generator

    monkeypatch.setattr(module.connection, "get_connection", _get_connection)
