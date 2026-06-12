import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import deserialize_payment, serialize_payment


def test_payment_payload_serializes_to_json():
    payload = {
        "amount": 1500,
        "currency": "GBP",
        "account_id": "ACC-001",
    }

    serialized = serialize_payment(payload)

    assert serialized == '{"amount":1500,"currency":"GBP","account_id":"ACC-001"}'


def test_payment_payload_deserializes_from_bytes():
    payload = b'{"amount":1500,"currency":"GBP","account_id":"ACC-001"}'

    assert deserialize_payment(payload) == {
        "amount": 1500,
        "currency": "GBP",
        "account_id": "ACC-001",
    }


if __name__ == "__main__":
    import pytest

    raise SystemExit(pytest.main([__file__]))
