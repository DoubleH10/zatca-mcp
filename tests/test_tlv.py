"""Tests for TLV encoding/decoding."""

import pytest
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from zatca_mcp.utils.tlv import encode_tlv, decode_tlv, decode_tlv_named, TLVTag


class TestTLVTag:
    def test_encode_basic(self):
        tag = TLVTag(1, "Fikrah Tech")
        encoded = tag.encode()
        assert encoded[0] == 1  # tag number
        assert encoded[1] == len("Fikrah Tech".encode("utf-8"))  # length
        assert encoded[2:] == b"Fikrah Tech"  # value

    def test_encode_arabic(self):
        tag = TLVTag(1, "شركة فكرة")
        encoded = tag.encode()
        assert encoded[0] == 1
        value_bytes = "شركة فكرة".encode("utf-8")
        assert encoded[1] == len(value_bytes)
        assert encoded[2:] == value_bytes

    def test_encode_invalid_tag(self):
        with pytest.raises(ValueError, match="Invalid tag number"):
            TLVTag(0, "test").encode()
        with pytest.raises(ValueError, match="Invalid tag number"):
            TLVTag(10, "test").encode()

    def test_encode_value_too_long(self):
        with pytest.raises(ValueError, match="too long"):
            TLVTag(1, "x" * 256).encode()


class TestEncodeDecode:
    def test_roundtrip_basic(self):
        encoded = encode_tlv(
            seller_name="Fikrah Tech",
            vat_number="300000000000003",
            timestamp="2024-01-15T10:30:00Z",
            total_amount="1150.00",
            vat_amount="150.00",
        )
        decoded = decode_tlv(encoded)
        assert decoded[1] == "Fikrah Tech"
        assert decoded[2] == "300000000000003"
        assert decoded[3] == "2024-01-15T10:30:00Z"
        assert decoded[4] == "1150.00"
        assert decoded[5] == "150.00"

    def test_roundtrip_arabic(self):
        encoded = encode_tlv(
            seller_name="شركة فكرة للتقنية",
            vat_number="310000000000003",
            timestamp="2024-06-01T14:00:00Z",
            total_amount="5750.00",
            vat_amount="750.00",
        )
        decoded = decode_tlv(encoded)
        assert decoded[1] == "شركة فكرة للتقنية"

    def test_phase2_tags(self):
        encoded = encode_tlv(
            seller_name="Test",
            vat_number="300000000000003",
            timestamp="2024-01-01T00:00:00Z",
            total_amount="100.00",
            vat_amount="15.00",
            invoice_hash="abc123hash",
            ecdsa_signature="sig456",
            ecdsa_public_key="pubkey789",
        )
        decoded = decode_tlv(encoded)
        assert decoded[6] == "abc123hash"
        assert decoded[7] == "sig456"
        assert decoded[8] == "pubkey789"

    def test_decode_named(self):
        encoded = encode_tlv(
            seller_name="Test Co",
            vat_number="300000000000003",
            timestamp="2024-01-01T00:00:00Z",
            total_amount="100.00",
            vat_amount="15.00",
        )
        named = decode_tlv_named(encoded)
        assert named["seller_name"] == "Test Co"
        assert named["vat_number"] == "300000000000003"
        assert named["total_amount"] == "100.00"

    def test_decode_truncated_data(self):
        import base64
        # Just one byte — truncated
        bad_data = base64.b64encode(b"\x01").decode()
        with pytest.raises(ValueError, match="Truncated"):
            decode_tlv(bad_data)

    def test_decode_length_exceeds_data(self):
        import base64
        # Tag 1, claims 10 bytes, but only 3 provided
        bad_data = base64.b64encode(b"\x01\x0aabc").decode()
        with pytest.raises(ValueError, match="only"):
            decode_tlv(bad_data)

    def test_max_boundary_value(self):
        """255-byte value (max allowed)."""
        tag = TLVTag(1, "x" * 255)
        encoded = tag.encode()
        assert encoded[1] == 255

    def test_empty_string_value(self):
        """Empty string value should encode with length 0."""
        tag = TLVTag(1, "")
        encoded = tag.encode()
        assert encoded[0] == 1
        assert encoded[1] == 0
        assert len(encoded) == 2

    def test_tag_boundary_values(self):
        """Tags 1 and 9 are the min/max valid tags."""
        tag_min = TLVTag(1, "a")
        tag_max = TLVTag(9, "b")
        assert tag_min.encode()[0] == 1
        assert tag_max.encode()[0] == 9
