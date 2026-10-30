"""Uniform error types mapped to the contract's error body."""

from __future__ import annotations


class AppError(Exception):
    status = 400
    code = "validation_failed"

    def __init__(self, message: str, details: list | None = None, code: str | None = None, status: int | None = None):
        super().__init__(message)
        self.message = message
        self.details = list(details or [])
        if code:
            self.code = code
        if status:
            self.status = status


class RowError(Exception):
    """One row failed validation; collected per row so callers can report line-level reasons."""

    def __init__(self, code: str, field: str, reason: str, row_no: int | None = None):
        super().__init__(f"{code}: {field}: {reason}")
        self.code = code
        self.field = field
        self.reason = reason
        self.row_no = row_no

    def as_detail(self) -> dict:
        detail = {"field": self.field, "reason": f"{self.code}: {self.reason}"}
        if self.row_no is not None:
            detail["row"] = self.row_no
        return detail
