import pytest

from ach_intelligence.fixtures import make_file, mutate, scenarios
from ach_intelligence.parser import parse, routing_valid


@pytest.mark.parametrize("case", scenarios(), ids=lambda c: c["name"])
def test_labeled_scenarios(case):
    parsed = parse(case["data"])
    errors = any(f.severity == "error" for f in parsed.findings)
    status = "invalid" if errors else "needs_review" if parsed.findings else "valid"
    assert status == case["expected_status"]
    if case["expected_code"]:
        assert case["expected_code"] in {f.code for f in parsed.findings}


def test_exact_totals_and_redacted_entries():
    parsed = parse(make_file(batch_count=2))
    assert parsed.credit_cents == 24690
    assert parsed.debit_cents == 15200
    assert len(parsed.entries) == 4
    assert len(parsed.batches) == 2
    output = parsed.model_dump_json()
    assert "SYNTH101" not in output
    assert "SYNTHETIC PERSON" not in output
    assert len(parsed.entries[0].account_hash) == 64


def test_nine_digit_routing():
    assert routing_valid("123456780")
    assert not routing_valid("000000000")
    assert not routing_valid("123456789")
    assert not routing_valid("123")


def test_duplicate_keys_can_be_disabled_and_incomplete_files_keep_computed_totals():
    duplicate = next(c for c in scenarios() if c["name"] == "duplicate_trace")
    assert not parse(duplicate["data"], frozenset({"account_amount_date"})).findings
    no_control = mutate(make_file(), 5, 0, 1, "0")
    parsed = parse(no_control)
    assert parsed.credit_cents == 12345 and parsed.debit_cents == 7600


def test_out_of_order_and_extra_control_rejected():
    rows = make_file().decode().splitlines()
    rows[1], rows[2] = rows[2], rows[1]
    assert "RECORD_ORDER" in {f.code for f in parse("\n".join(rows).encode()).findings}
    rows = make_file().decode().splitlines()
    rows[6] = rows[5]
    assert "MISSING_CONTROL" in {f.code for f in parse("\n".join(rows).encode()).findings}


def test_malformed_numeric_mutations_never_crash():
    base = make_file()
    for row in (0, 1, 2, 4, 5):
        for column in range(94):
            parse(mutate(base, row, column, column + 1, "?"))


@pytest.mark.parametrize("separator", [b"\x0b", b"\x0c", b"\x1c", b"\r"])
def test_nonstandard_record_separators_are_rejected(separator):
    data = separator.join(make_file().splitlines())
    assert any(f.severity == "error" for f in parse(data).findings)
