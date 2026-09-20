"""Stable machine-readable errors for v2 corpus construction."""

from __future__ import annotations


class V2Error(Exception):
    code = "INTERNAL_ERROR"
    exit_code = 10

    def __init__(self, message: str, *, code: str | None = None) -> None:
        super().__init__(message)
        if code is not None:
            self.code = code


class InputError(V2Error):
    exit_code = 2


class ParseError(V2Error):
    exit_code = 3


class ContractError(V2Error):
    exit_code = 4


class BuildGateError(ContractError):
    code = "MISSING_REQUIRED_TEXTBOOK"

    def __init__(self, message: str, *, report_path=None, manifest=None) -> None:
        super().__init__(message)
        self.report_path = report_path
        self.manifest = manifest


class PublishConflictError(V2Error):
    code = "PUBLISH_CONFLICT"
    exit_code = 5


class LockError(PublishConflictError):
    code = "PUBLISH_LOCKED"
