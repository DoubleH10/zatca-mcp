"""Tests for credit note and debit note support."""

import pytest
import sys
import os
from lxml import etree

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from zatca_mcp.utils.xml_builder import build_invoice_xml
from zatca_mcp.utils.validation import validate_invoice_xml

NS = {
    "ubl": "urn:oasis:names:specification:ubl:schema:xsd:Invoice-2",
    "cac": "urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2",
    "cbc": "urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2",
}


def _make_credit_note(**overrides):
    """Create a test credit note with sensible defaults."""
    defaults = {
        "invoice_type": "credit_note",
        "invoice_number": "CN-2024-001",
        "issue_date": "2024-02-15",
        "seller_name": "Fikrah Tech",
        "seller_vat": "300000000000003",
        "seller_address": "123 King Fahd Road",
        "seller_city": "Riyadh",
        "buyer_name": "Test Customer",
        "buyer_vat": "310000000000003",
        "line_items": [
            {"name": "Consulting (refund)", "quantity": 1, "unit_price": 1000.00},
        ],
        "billing_reference_id": "INV-2024-001",
        "billing_reference_date": "2024-01-15",
        "instruction_note": "Customer requested full refund",
    }
    defaults.update(overrides)
    return build_invoice_xml(**defaults)


def _make_debit_note(**overrides):
    """Create a test debit note with sensible defaults."""
    defaults = {
        "invoice_type": "debit_note",
        "invoice_number": "DN-2024-001",
        "issue_date": "2024-02-15",
        "seller_name": "Fikrah Tech",
        "seller_vat": "300000000000003",
        "seller_address": "123 King Fahd Road",
        "seller_city": "Riyadh",
        "buyer_name": "Test Customer",
        "buyer_vat": "310000000000003",
        "line_items": [
            {"name": "Additional charges", "quantity": 1, "unit_price": 500.00},
        ],
        "billing_reference_id": "INV-2024-001",
        "billing_reference_date": "2024-01-15",
        "instruction_note": "Price adjustment for additional work",
    }
    defaults.update(overrides)
    return build_invoice_xml(**defaults)


class TestCreditNoteGeneration:
    def test_credit_note_type_code(self):
        xml = _make_credit_note()
        root = etree.fromstring(xml.encode())
        type_code = root.xpath("//cbc:InvoiceTypeCode", namespaces=NS)
        assert type_code[0].text == "381"

    def test_debit_note_type_code(self):
        xml = _make_debit_note()
        root = etree.fromstring(xml.encode())
        type_code = root.xpath("//cbc:InvoiceTypeCode", namespaces=NS)
        assert type_code[0].text == "383"

    def test_billing_reference_present(self):
        xml = _make_credit_note()
        root = etree.fromstring(xml.encode())
        billing_ref = root.xpath(
            "//cac:BillingReference/cac:InvoiceDocumentReference/cbc:ID",
            namespaces=NS,
        )
        assert len(billing_ref) == 1
        assert billing_ref[0].text == "INV-2024-001"

    def test_billing_reference_date(self):
        xml = _make_credit_note()
        root = etree.fromstring(xml.encode())
        ref_date = root.xpath(
            "//cac:BillingReference/cac:InvoiceDocumentReference/cbc:IssueDate",
            namespaces=NS,
        )
        assert len(ref_date) == 1
        assert ref_date[0].text == "2024-01-15"

    def test_instruction_note_present(self):
        xml = _make_credit_note()
        root = etree.fromstring(xml.encode())
        note = root.xpath(
            "//cac:PaymentMeans/cbc:InstructionNote",
            namespaces=NS,
        )
        assert len(note) == 1
        assert note[0].text == "Customer requested full refund"

    def test_credit_note_subtype_code(self):
        xml = _make_credit_note()
        root = etree.fromstring(xml.encode())
        type_code = root.xpath("//cbc:InvoiceTypeCode", namespaces=NS)
        assert type_code[0].get("name") == "0100000"


class TestCreditDebitValidation:
    def test_credit_note_validates(self):
        xml = _make_credit_note()
        result = validate_invoice_xml(xml)
        assert result["is_valid"] is True
        assert result["checks_run"] == 16

    def test_debit_note_validates(self):
        xml = _make_debit_note()
        result = validate_invoice_xml(xml)
        assert result["is_valid"] is True

    def test_credit_note_missing_billing_ref_fails(self):
        """BR-15: Credit note without BillingReference should fail."""
        xml = _make_credit_note(billing_reference_id=None)
        result = validate_invoice_xml(xml)
        assert any("BR-15" in e for e in result["errors"])
        assert result["is_valid"] is False

    def test_debit_note_missing_billing_ref_fails(self):
        """BR-15: Debit note without BillingReference should fail."""
        xml = _make_debit_note(billing_reference_id=None)
        result = validate_invoice_xml(xml)
        assert any("BR-15" in e for e in result["errors"])

    def test_credit_note_missing_instruction_note_warns(self):
        """BR-16: Credit note without InstructionNote gets a warning."""
        xml = _make_credit_note(instruction_note=None)
        result = validate_invoice_xml(xml)
        assert any("BR-16" in w for w in result["warnings"])
        # Should still be valid (warning, not error)
        # But BR-15 still passes since billing_reference_id is set
        assert result["is_valid"] is True

    def test_standard_invoice_no_billing_ref_ok(self):
        """Standard invoices should not require BillingReference."""
        xml = build_invoice_xml(
            invoice_type="standard",
            invoice_number="INV-001",
            issue_date="2024-01-15",
            seller_name="Test Co",
            seller_vat="300000000000003",
            seller_address="123 St",
            seller_city="Riyadh",
            buyer_name="Buyer Co",
            buyer_vat="310000000000003",
            line_items=[{"name": "Item", "quantity": 1, "unit_price": 100.00}],
        )
        result = validate_invoice_xml(xml)
        assert result["is_valid"] is True
        assert not any("BR-15" in e for e in result["errors"])


class TestCreditDebitIntegration:
    def test_credit_note_roundtrip(self):
        """Generate credit note -> validate -> should pass."""
        xml = _make_credit_note()
        result = validate_invoice_xml(xml)
        assert result["is_valid"] is True
        assert len(result["errors"]) == 0

    def test_debit_note_roundtrip(self):
        """Generate debit note -> validate -> should pass."""
        xml = _make_debit_note()
        result = validate_invoice_xml(xml)
        assert result["is_valid"] is True
        assert len(result["errors"]) == 0
