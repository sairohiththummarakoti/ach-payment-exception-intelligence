import re
from typing import Any

import httpx

from .schemas import Finding


class DependencyUnavailable(RuntimeError):
    pass


def redact(value: str, original: bytes = b"") -> str:
    for record in original.decode("ascii", errors="ignore").splitlines():
        if len(record) == 94 and record.startswith("6"):
            for start, end in [(3, 12), (12, 29), (39, 54), (54, 76)]:
                secret = record[start:end].strip()
                if secret:
                    value = value.replace(secret, "[redacted]")
    return re.sub(r"\b\d{4,}\b", "[redacted]", value)[:6000]


class MoovAdapter:
    """Only the parser create endpoint is allowed; no financial operations exist."""

    def __init__(self, base_url: str) -> None:
        self.base_url = base_url.rstrip("/")

    def ready(self) -> bool:
        try:
            response = httpx.get(self.base_url + "/ping", timeout=3, follow_redirects=False)
            return response.is_success
        except httpx.HTTPError:
            return False

    def validate(self, data: bytes) -> tuple[list[Finding], dict[str, Any]]:
        try:
            # Never retry this POST: its server-side parse object could already exist.
            response = httpx.post(
                self.base_url + "/files/create",
                content=data,
                headers={"Content-Type": "text/plain"},
                timeout=10,
                follow_redirects=False,
            )
        except httpx.HTTPError as exc:
            raise DependencyUnavailable(
                "Moov parser is unavailable; the file was not accepted."
            ) from exc
        if not response.is_success and response.status_code != 400:
            raise DependencyUnavailable("Moov parser failed; the file was not accepted.")
        try:
            payload = response.json()
        except ValueError as exc:
            raise DependencyUnavailable("Moov returned a non-JSON response.") from exc
        if not isinstance(payload, dict):
            raise DependencyUnavailable("Moov response violates its object contract.")
        raw_error = payload.get("error") or payload.get("errors")
        if not response.is_success or raw_error:
            detail = redact(str(raw_error or payload), data)
            return [
                Finding(
                    code="MOOV_VALIDATION",
                    message=detail,
                    source="moov",
                    evidence={"http_status": response.status_code},
                )
            ], {"adapter": "moov-ach", "version": "v1.68.0", "status": "invalid"}
        if (
            not isinstance(payload.get("id"), str)
            or not payload["id"].strip()
            or not isinstance(payload.get("file"), dict)
        ):
            raise DependencyUnavailable("Moov omitted the parsed file or its identifier.")
        return [], {
            "adapter": "moov-ach",
            "version": "v1.68.0",
            "status": "valid",
            "moov_file_id": str(payload["id"]),
        }
