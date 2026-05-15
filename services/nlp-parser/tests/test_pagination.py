from __future__ import annotations

import base64

import pytest
from bson import ObjectId

from nlp_parser.api.messages import _decode_cursor, _encode_cursor


def test_cursor_roundtrip():
    oid = ObjectId()
    encoded = _encode_cursor(oid)
    assert isinstance(encoded, str)
    assert "=" not in encoded
    assert _decode_cursor(encoded) == oid


def test_cursor_accepts_string_input():
    oid = ObjectId()
    assert _decode_cursor(_encode_cursor(str(oid))) == oid


def test_decode_rejects_garbage():
    with pytest.raises(ValueError):
        _decode_cursor("!!!not-base64!!!")


def test_decode_rejects_non_objectid():
    bogus = base64.urlsafe_b64encode(b"not an object id").decode("ascii").rstrip("=")
    with pytest.raises(ValueError):
        _decode_cursor(bogus)
