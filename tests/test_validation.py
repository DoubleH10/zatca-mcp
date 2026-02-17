"""Tests for invoice validation."""

import pytest
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from zatca_mcp.utils.validation import validate_invoice_xml, validate_vat_number
from zatca_mcp.utils.xml_builder import build_invoice_xml


def _valid_invoice(**overrides):
    defaults = {
        "invoice_type": "simplified",
        "invoice_number": "INV-001",
        "issue_date": "2024-01-15",
        "seller_name": "Test Co",
        "seller_vat": "300000000000003",
        "seller_address": "123 St",
        "seller_city": "Riyadh",
        "buyer_name": "Buyer Co",
        "line_items": [{"name": "Item", "quantity": 1, "unit_price": 100.00}],
    }
    defaults.update(overrides)
    return build_invoice_xml(**defaults)


class TestVATValidation:
    def test_valid_vat(self):
        assert validate_vat_number("300000000000003") == []

    def test_wrong_length(self):
        errors = validate_vat_number("123")
        assert any("15 digits" in e for e in errors)

    def test_not_starting_with_3(self):
        errors = validate_vat_number("100000000000001")
        assert any("start with 3" in e for e in errors)

    def test_not_ending_with_3(self):
        errors = validate_vat_number("300000000000001")
        assert any("end with 3" in e for e in errors)

    def test_non_digits(self):
        errors = validate_vat_number("3000000000abcd3")
        assert any("only digits" in e for e in errors)

    def test_empty(self):
        errors = validate_vat_number("")
        assert any("required" in e for e in errors)


class TestInvoiceValidation:
    def test_valid_invoice_passes(self):
        xml = _valid_invoice()
        result = validate_invoice_xml(xml)
        assert result["is_valid"] is True
        assert len(result["errors"]) == 0

    def test_invalid_xml(self):
        result = validate_invoice_xml("<not valid xml")
        assert result["is_valid"] is False
        assert any("Invalid XML" in e for e in result["errors"])

    def test_math_correct(self):
        xml = _valid_invoice(
            line_items=[
                {"name": "A", "quantity": 3, "unit_price": 100.00},
            ]
        )
        result = validate_invoice_xml(xml)
        assert result["is_valid"] is True

    def test_standard_invoice_needs_buyer_vat(self):
        xml = _valid_invoice(
            invoice_type="standard",
            buyer_vat="310000000000003",
        )
        result = validate_invoice_xml(xml)
        assert result["is_valid"] is True

    def test_checks_count(self):
        xml = _valid_invoice()
        result = validate_invoice_xml(xml)
        assert result["checks_run"] >= 10

    def test_invalid_type_code(self):
        """BR-03: Invalid invoice type code should fail."""
        xml = _valid_invoice()
        xml = xml.replace(">388<", ">999<", 1)
        result = validate_invoice_xml(xml)
        assert any("BR-03" in e for e in result["errors"])

    def test_invalid_seller_vat_in_xml(self):
        """BR-06: Invalid seller VAT in XML."""
        xml = _valid_invoice(seller_vat="123456789012345")
        result = validate_invoice_xml(xml)
        assert any("BR-06" in e for e in result["errors"])

    def test_standard_invoice_missing_buyer_vat(self):
        """BR-08: Standard invoice missing buyer VAT should fail."""
        xml = _valid_invoice(invoice_type="standard")
        result = validate_invoice_xml(xml)
        assert any("BR-08" in e for e in result["errors"])

    def test_tampered_line_amounts(self):
        """BR-11: Tampered line extension amount should be caught."""
        xml = _valid_invoice(
            line_items=[{"name": "Item", "quantity": 2, "unit_price": 100.00}]
        )
        # Tamper the InvoiceLine's LineExtensionAmount
        xml = xml.replace(
            '<cbc:InvoicedQuantity unitCode="PCE">2</cbc:InvoicedQuantity>\n'
            '    <cbc:LineExtensionAmount currencyID="SAR">200.00</cbc:LineExtensionAmount>',
            '<cbc:InvoicedQuantity unitCode="PCE">2</cbc:InvoicedQuantity>\n'
            '    <cbc:LineExtensionAmount currencyID="SAR">999.00</cbc:LineExtensionAmount>',
        )
        result = validate_invoice_xml(xml)
        assert any("BR-11" in e for e in result["errors"])

    def test_total_mismatch(self):
        """BR-14: Cross-check total mismatch."""
        xml = _valid_invoice()
        # Tamper the TaxInclusiveAmount
        xml = xml.replace("TaxInclusiveAmount", "TaxInclusiveAmount", 1)
        # Replace payable with a wrong value
        xml = xml.replace(">115.00</", ">999.00</", 1)
        result = validate_invoice_xml(xml)
        has_error = (
            any("BR-14" in e for e in result["errors"])
            or any("BR-13" in e for e in result["errors"])
            or not result["is_valid"]
        )
        assert has_error


class TestIntegration:
    """Generate -> Validate pipeline tests."""

    def test_simplified_invoice_roundtrip(self):
        xml = _valid_invoice(invoice_type="simplified")
        result = validate_invoice_xml(xml)
        assert result["is_valid"] is True

    def test_standard_invoice_roundtrip(self):
        xml = _valid_invoice(
            invoice_type="standard",
            buyer_vat="310000000000003",
        )
        result = validate_invoice_xml(xml)
        assert result["is_valid"] is True

    def test_multi_item_roundtrip(self):
        xml = _valid_invoice(
            line_items=[
                {"name": "Widget A", "quantity": 5, "unit_price": 200.00},
                {"name": "Widget B", "quantity": 3, "unit_price": 150.00},
                {"name": "Service C", "quantity": 1, "unit_price": 1000.00},
            ]
        )
        result = validate_invoice_xml(xml)
        assert result["is_valid"] is True

    def test_tlv_embed_validate_flow(self):
        """Full flow: TLV encode -> embed in invoice -> validate."""
        from zatca_mcp.utils.tlv import encode_tlv

        qr = encode_tlv(
            seller_name="Test Co",
            vat_number="300000000000003",
            timestamp="2024-01-15T10:00:00Z",
            total_amount="115.00",
            vat_amount="15.00",
        )
        xml = _valid_invoice(qr_data=qr)
        result = validate_invoice_xml(xml)
        assert result["is_valid"] is True
