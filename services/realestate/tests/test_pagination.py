from __future__ import annotations

import pytest
from bson import ObjectId

from realestate.api.objects import _decode_cursor, _encode_cursor


def test_cursor_roundtrip():
    oid = ObjectId()
    encoded = _encode_cursor(oid)
    assert isinstance(encoded, str)
    assert "=" not in encoded
    decoded = _decode_cursor(encoded)
    assert decoded == oid


def test_cursor_accepts_string_input():
    oid = ObjectId()
    encoded_from_str = _encode_cursor(str(oid))
    assert _decode_cursor(encoded_from_str) == oid


def test_decode_rejects_garbage():
    with pytest.raises(ValueError):
        _decode_cursor("!!!not-base64!!!")


def test_decode_rejects_non_objectid():
    import base64

    bogus = base64.urlsafe_b64encode(b"not an object id").decode("ascii").rstrip("=")
    with pytest.raises(ValueError):
        _decode_cursor(bogus)
