"""Bounded deterministic validation of an explicitly limited PPD/CCD profile.

Money is integer cents. Raw names and account identifiers never leave this module.
Full ACH validation is additionally performed by the optional Moov HTTP adapter.
"""

import hashlib
from datetime import datetime
from typing import Literal

from .schemas import Batch, Entry, Finding, ParsedFile


def routing_valid(value: str) -> bool:
    return (
        len(value) == 9
        and value.isdigit()
        and value != "000000000"
        and sum(int(n) * w for n, w in zip(value, [3, 7, 1] * 3, strict=True)) % 10 == 0
    )


def parse(
    data: bytes, duplicate_keys: frozenset[str] = frozenset({"account_amount_date", "trace"})
) -> ParsedFile:
    text = data.decode("ascii")
    # splitlines() also accepts VT/FF and other control separators, which ACH does not.
    lines = text.replace("\r\n", "\n").split("\n") if text else []
    if lines and lines[-1] == "":
        lines.pop()
    result = ParsedFile(fingerprint=hashlib.sha256(data).hexdigest(), record_count=len(lines))

    def flag(code: str, message: str, line: int | None = None, **evidence: object) -> None:
        result.findings.append(Finding(code=code, message=message, line=line, evidence=evidence))

    def num(record: str, start: int, end: int, line: int) -> int:
        value = record[start:end]
        if not value.isdigit():
            flag(
                "NUMERIC_FIELD",
                "A numeric field contains invalid characters.",
                line,
                columns=f"{start + 1}-{end}",
            )
            return -1
        return int(value)

    def check_date(value: str, line: int) -> None:
        try:
            datetime.strptime(value, "%y%m%d")
        except ValueError:
            flag("INVALID_DATE", "A date is missing or invalid.", line)

    if not lines:
        flag("EMPTY_FILE", "The file contains no records.")
        return result
    if len(lines) % 10:
        flag("BLOCK_COUNT", "The record count must be a multiple of ten.", observed=len(lines))
    state = "header"
    header_count = control_count = 0
    batch_header: str | None = None
    batch_entries: list[Entry] = []
    batch_hash = 0
    batch_numbers: set[str] = set()
    seen_traces: dict[str, int] = {}
    seen_keys: dict[str, int] = {}
    for index, record in enumerate(lines, 1):
        if len(record) != 94 or any(ord(c) < 32 or ord(c) > 126 for c in record):
            flag(
                "RECORD_LENGTH",
                "Each record must contain 94 printable ASCII characters.",
                index,
                observed_length=len(record),
            )
            continue
        kind = record[0]
        if record == "9" * 94:
            if state != "done":
                flag("RECORD_ORDER", "Padding occurs before the file control.", index)
            continue
        if kind == "1":
            header_count += 1
            if state != "header" or index != 1:
                flag("RECORD_ORDER", "File header is out of sequence.", index)
            state = "batch"
            if record[1:3] != "01" or record[34:40] != "094101":
                flag(
                    "FILE_HEADER",
                    "File priority, record size, blocking factor or format is invalid.",
                    index,
                )
            if not routing_valid(record[3:13].strip()) or not routing_valid(record[13:23].strip()):
                flag("ROUTING", "File routing number has an invalid checksum.", index)
            check_date(record[23:29], index)
            try:
                datetime.strptime(record[29:33], "%H%M")
            except ValueError:
                flag("FILE_HEADER", "File creation time is invalid.", index)
            if not record[33].isalnum() or not record[40:63].strip() or not record[63:86].strip():
                flag("REQUIRED_FIELD", "Required file-header metadata is missing.", index)
        elif kind == "5":
            if state != "batch":
                flag("RECORD_ORDER", "Batch header is out of sequence.", index)
            batch_header = record
            batch_entries, batch_hash = [], 0
            state = "entries"
            if record[50:53] not in {"PPD", "CCD"}:
                flag(
                    "UNSUPPORTED_SEC",
                    "Only PPD and CCD without addenda are supported.",
                    index,
                    sec=record[50:53],
                )
            if record[1:4] not in {"200", "220", "225"}:
                flag("SERVICE_CLASS", "Unsupported service class.", index)
            if not all(record[a:b].strip() for a, b in [(4, 20), (40, 50), (53, 63), (79, 87)]):
                flag("REQUIRED_FIELD", "Required batch metadata is missing.", index)
            if record[78] != "1" or not record[79:87].isdigit() or not record[87:94].isdigit():
                flag("BATCH_HEADER", "Originator status, DFI or batch number is invalid.", index)
            if record[87:94] in batch_numbers:
                flag("BATCH_NUMBER", "A batch number is repeated.", index)
            batch_numbers.add(record[87:94])
            check_date(record[69:75], index)
        elif kind == "6":
            if state != "entries" or batch_header is None:
                flag("RECORD_ORDER", "Entry is outside an open batch.", index)
                continue
            amount = num(record, 29, 39, index)
            if record[1:3] not in {"22", "27", "32", "37"}:
                flag(
                    "TRANSACTION_CODE",
                    "Only ordinary checking/savings credits and debits are supported.",
                    index,
                )
                continue
            if not routing_valid(record[3:12]):
                flag("ROUTING", "Entry routing number has an invalid checksum.", index)
            if not record[12:29].strip() or not record[54:76].strip():
                flag("REQUIRED_FIELD", "Entry account or receiver name is missing.", index)
            if record[78] != "0":
                flag("UNSUPPORTED_ADDENDA", "This profile does not support addenda.", index)
            trace = record[79:94]
            if not trace.isdigit() or trace[:8] != batch_header[79:87]:
                flag(
                    "TRACE", "Trace number is invalid or does not match the originating DFI.", index
                )
            direction: Literal["credit", "debit"] = (
                "credit" if record[1:3] in {"22", "32"} else "debit"
            )
            if (batch_header[1:4] == "220" and direction == "debit") or (
                batch_header[1:4] == "225" and direction == "credit"
            ):
                flag(
                    "SERVICE_CLASS",
                    "Entry direction conflicts with the batch service class.",
                    index,
                )
            account_hash = hashlib.sha256(
                (record[3:12] + ":" + record[12:29].strip()).encode()
            ).hexdigest()
            key = hashlib.sha256(
                f"{account_hash}:{amount}:{direction}:{batch_header[69:75]}".encode()
            ).hexdigest()
            entry = Entry(
                line=index,
                batch_number=batch_header[87:94],
                trace=trace,
                account_hash=account_hash,
                account_mask="***" + record[12:29].strip()[-4:],
                routing_mask="*****" + record[8:12],
                amount_cents=max(0, amount),
                direction=direction,
                effective_date=batch_header[69:75],
                duplicate_key=key,
            )
            if trace in seen_traces and "trace" in duplicate_keys:
                result.findings.append(
                    Finding(
                        code="DUPLICATE_TRACE",
                        severity="warning",
                        message="A trace identifier occurs more than once in this file.",
                        line=index,
                        evidence={"other_line": seen_traces[trace]},
                    )
                )
            if key in seen_keys and "account_amount_date" in duplicate_keys:
                result.findings.append(
                    Finding(
                        code="DUPLICATE_ENTRY",
                        severity="warning",
                        message="Account, amount, direction and effective date repeat within this file.",
                        line=index,
                        evidence={"other_line": seen_keys[key], "duplicate_key": key},
                    )
                )
            seen_traces[trace], seen_keys[key] = index, index
            batch_entries.append(entry)
            result.entries.append(entry)
            if record[3:11].isdigit():
                batch_hash += int(record[3:11])
        elif kind == "7":
            flag(
                "UNSUPPORTED_ADDENDA",
                "Addenda records require a different validation profile.",
                index,
            )
        elif kind == "8":
            if state != "entries" or batch_header is None:
                flag("RECORD_ORDER", "Batch control has no matching header.", index)
                continue
            credit = sum(e.amount_cents for e in batch_entries if e.direction == "credit")
            debit = sum(e.amount_cents for e in batch_entries if e.direction == "debit")
            for start, end, expected, code in [
                (4, 10, len(batch_entries), "BATCH_COUNT"),
                (10, 20, batch_hash % 10**10, "BATCH_HASH"),
                (20, 32, debit, "BATCH_DEBIT_TOTAL"),
                (32, 44, credit, "BATCH_CREDIT_TOTAL"),
            ]:
                observed = num(record, start, end, index)
                if observed != expected:
                    flag(
                        code,
                        "Batch control differs from computed entries.",
                        index,
                        expected=expected,
                        observed=observed,
                    )
            if (
                any(record[a:b] != batch_header[a:b] for a, b in [(1, 4), (79, 87), (87, 94)])
                or record[44:54] != batch_header[40:50]
            ):
                flag("BATCH_METADATA", "Batch control metadata does not match its header.", index)
            if not batch_entries:
                flag("EMPTY_BATCH", "A batch has no supported entries.", index)
            result.batches.append(
                Batch(
                    number=batch_header[87:94],
                    sec=batch_header[50:53],
                    effective_date=batch_header[69:75],
                    entry_count=len(batch_entries),
                    credit_cents=credit,
                    debit_cents=debit,
                    entry_hash=batch_hash % 10**10,
                )
            )
            batch_header = None
            state = "batch"
        elif kind == "9":
            control_count += 1
            if state != "batch":
                flag("RECORD_ORDER", "File control is out of sequence.", index)
            state = "done"
            result.credit_cents = sum(
                e.amount_cents for e in result.entries if e.direction == "credit"
            )
            result.debit_cents = sum(
                e.amount_cents for e in result.entries if e.direction == "debit"
            )
            for start, end, expected, code in [
                (1, 7, len(result.batches), "FILE_BATCH_COUNT"),
                (7, 13, (len(lines) + 9) // 10, "BLOCK_COUNT"),
                (13, 21, len(result.entries), "FILE_ENTRY_COUNT"),
                (21, 31, sum(b.entry_hash for b in result.batches) % 10**10, "FILE_HASH"),
                (31, 43, result.debit_cents, "FILE_DEBIT_TOTAL"),
                (43, 55, result.credit_cents, "FILE_CREDIT_TOTAL"),
            ]:
                observed = num(record, start, end, index)
                if observed != expected:
                    flag(
                        code,
                        "File control differs from computed entries.",
                        index,
                        expected=expected,
                        observed=observed,
                    )
        else:
            flag("UNKNOWN_RECORD", "Unknown ACH record type.", index)
    if header_count != 1:
        flag("MISSING_HEADER", "Exactly one file header is required.", observed=header_count)
    if control_count != 1 or state != "done":
        flag(
            "MISSING_CONTROL",
            "Exactly one complete file control is required.",
            observed=control_count,
        )
    if not result.batches:
        flag("EMPTY_FILE", "At least one complete batch is required.")
    result.credit_cents = sum(e.amount_cents for e in result.entries if e.direction == "credit")
    result.debit_cents = sum(e.amount_cents for e in result.entries if e.direction == "debit")
    return result
