"""
TLV (Tag-Length-Value) encoding for ZATCA QR codes.

ZATCA mandates QR codes on all invoices using TLV format:
  - Tag:    1 byte (0x01 to 0x09)
  - Length: 1 byte (length of value in bytes)
  - Value:  UTF-8 encoded bytes

Tags 1-5: Mandatory (Phase 1 + Phase 2)
Tags 6-8: Phase 2 only (digital signature data)
"""

from __future__ import annotations

import base64
from dataclasses import dataclass


TAG_NAMES = {
    1: "seller_name",
    2: "vat_number",
    3: "timestamp",
    4: "total_amount",
    5: "vat_amount",
    6: "invoice_hash",
    7: "ecdsa_signature",
    8: "ecdsa_public_key",
    9: "ecdsa_stamp",
}


@dataclass
class TLVTag:
    """A single TLV segment."""

    tag: int
    value: str

    def encode(self) -> bytes:
        """Encode this tag as TLV bytes."""
        value_bytes = self.value.encode("utf-8")
        if len(value_bytes) > 255:
            raise ValueError(
                f"Tag {self.tag} value too long: {len(value_bytes)} bytes (max 255)"
            )
        if self.tag < 1 or self.tag > 9:
            raise ValueError(f"Invalid tag number: {self.tag} (must be 1-9)")
        return bytes([self.tag, len(value_bytes)]) + value_bytes


def encode_tlv(
    seller_name: str,
    vat_number: str,
    timestamp: str,
    total_amount: str,
    vat_amount: str,
    # Phase 2 optional
    invoice_hash: str | None = None,
    ecdsa_signature: str | None = None,
    ecdsa_public_key: str | None = None,
) -> str:
    """
    Encode invoice data as TLV and return Base64 string.

    Args:
        seller_name: Business name (Arabic or English)
        vat_number: 15-digit VAT registration number
        timestamp: ISO 8601 datetime string
        total_amount: Total including VAT (e.g., "1150.00")
        vat_amount: Total VAT (e.g., "150.00")
        invoice_hash: SHA-256 hash of invoice (Phase 2)
        ecdsa_signature: Digital signature (Phase 2)
        ecdsa_public_key: Public key from certificate (Phase 2)

    Returns:
        Base64-encoded TLV string for QR code
    """
    tags = [
        TLVTag(1, seller_name),
        TLVTag(2, vat_number),
        TLVTag(3, timestamp),
        TLVTag(4, total_amount),
        TLVTag(5, vat_amount),
    ]

    if invoice_hash is not None:
        tags.append(TLVTag(6, invoice_hash))
    if ecdsa_signature is not None:
        tags.append(TLVTag(7, ecdsa_signature))
    if ecdsa_public_key is not None:
        tags.append(TLVTag(8, ecdsa_public_key))

    tlv_bytes = b"".join(tag.encode() for tag in tags)
    return base64.b64encode(tlv_bytes).decode("ascii")


def decode_tlv(base64_string: str) -> dict[int, str]:
    """
    Decode a TLV-encoded QR code string.

    Args:
        base64_string: Base64-encoded TLV data

    Returns:
        Dict mapping tag numbers to their string values
    """
    data = base64.b64decode(base64_string)
    result = {}
    i = 0
    while i < len(data):
        if i + 1 >= len(data):
            raise ValueError(f"Truncated TLV data at position {i}")
        tag = data[i]
        length = data[i + 1]
        if i + 2 + length > len(data):
            raise ValueError(
                f"Tag {tag} claims length {length} but only "
                f"{len(data) - i - 2} bytes remain"
            )
        value = data[i + 2 : i + 2 + length].decode("utf-8")
        result[tag] = value
        i += 2 + length
    return result


def decode_tlv_named(base64_string: str) -> dict[str, str]:
    """Decode TLV and return human-readable tag names."""
    raw = decode_tlv(base64_string)
    return {TAG_NAMES.get(k, f"tag_{k}"): v for k, v in raw.items()}
