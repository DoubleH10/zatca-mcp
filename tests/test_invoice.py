"""Tests for invoice XML generation."""

import pytest
import sys
import os
from lxml import etree

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from zatca_mcp.utils.xml_builder import build_invoice_xml

NS = {
    "ubl": "urn:oasis:names:specification:ubl:schema:xsd:Invoice-2",
    "cac": "urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2",
    "cbc": "urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2",
}


def _make_invoice(**overrides):
    """Create a test invoice with sensible defaults."""
    defaults = {
        "invoice_type": "simplified",
        "invoice_number": "INV-TEST-001",
        "issue_date": "2024-01-15",
        "seller_name": "Fikrah Tech",
        "seller_vat": "300000000000003",
        "seller_address": "123 King Fahd Road",
        "seller_city": "Riyadh",
        "buyer_name": "Test Customer",
        "line_items": [
            {"name": "Consulting", "quantity": 1, "unit_price": 1000.00},
        ],
    }
    defaults.update(overrides)
    return build_invoice_xml(**defaults)


class TestInvoiceGeneration:
    def test_basic_simplified_invoice(self):
        xml = _make_invoice()
        root = etree.fromstring(xml.encode())
        assert root is not None

        # Check invoice ID
        inv_id = root.xpath("//cbc:ID", namespaces=NS)
        assert inv_id[0].text == "INV-TEST-001"

    def test_invoice_type_codes(self):
        xml = _make_invoice(invoice_type="simplified")
        root = etree.fromstring(xml.encode())
        type_code = root.xpath("//cbc:InvoiceTypeCode", namespaces=NS)
        assert type_code[0].text == "388"
        assert type_code[0].get("name") == "0200000"

    def test_standard_invoice_type(self):
        xml = _make_invoice(
            invoice_type="standard",
            buyer_vat="310000000000003",
        )
        root = etree.fromstring(xml.encode())
        type_code = root.xpath("//cbc:InvoiceTypeCode", namespaces=NS)
        assert type_code[0].get("name") == "0100000"

    def test_seller_details(self):
        xml = _make_invoice()
        root = etree.fromstring(xml.encode())

        seller_name = root.xpath(
            "//cac:AccountingSupplierParty//cbc:RegistrationName",
            namespaces=NS,
        )
        assert seller_name[0].text == "Fikrah Tech"

        seller_vat = root.xpath(
            "//cac:AccountingSupplierParty//cac:PartyTaxScheme/cbc:CompanyID",
            namespaces=NS,
        )
        assert seller_vat[0].text == "300000000000003"

    def test_line_item_calculation(self):
        xml = _make_invoice(
            line_items=[
                {"name": "Widget A", "quantity": 5, "unit_price": 200.00},
            ]
        )
        root = etree.fromstring(xml.encode())

        # Line total should be 5 * 200 = 1000
        line_ext = root.xpath(
            "//cac:InvoiceLine/cbc:LineExtensionAmount",
            namespaces=NS,
        )
        assert line_ext[0].text == "1000.00"

    def test_vat_calculation(self):
        xml = _make_invoice(
            line_items=[
                {"name": "Service", "quantity": 1, "unit_price": 1000.00},
            ]
        )
        root = etree.fromstring(xml.encode())

        # VAT should be 15% of 1000 = 150
        tax_amount = root.xpath(
            "//cac:TaxTotal/cbc:TaxAmount",
            namespaces=NS,
        )
        assert tax_amount[0].text == "150.00"

        # Total inclusive should be 1150
        payable = root.xpath(
            "//cac:LegalMonetaryTotal/cbc:PayableAmount",
            namespaces=NS,
        )
        assert payable[0].text == "1150.00"

    def test_multiple_line_items(self):
        xml = _make_invoice(
            line_items=[
                {"name": "Item A", "quantity": 2, "unit_price": 500.00},
                {"name": "Item B", "quantity": 3, "unit_price": 100.00},
            ]
        )
        root = etree.fromstring(xml.encode())

        lines = root.xpath("//cac:InvoiceLine", namespaces=NS)
        assert len(lines) == 2

        # Total: (2*500) + (3*100) = 1300
        # VAT: 1300 * 0.15 = 195
        # Inclusive: 1495
        payable = root.xpath(
            "//cac:LegalMonetaryTotal/cbc:PayableAmount",
            namespaces=NS,
        )
        assert payable[0].text == "1495.00"

    def test_qr_code_embedded(self):
        xml = _make_invoice(qr_data="dGVzdF9xcl9kYXRh")
        root = etree.fromstring(xml.encode())

        qr_elem = root.xpath(
            "//cac:AdditionalDocumentReference[cbc:ID='QR']"
            "//cbc:EmbeddedDocumentBinaryObject",
            namespaces=NS,
        )
        assert len(qr_elem) == 1
        assert qr_elem[0].text == "dGVzdF9xcl9kYXRh"

    def test_currency(self):
        xml = _make_invoice(currency="USD")
        root = etree.fromstring(xml.encode())

        curr = root.xpath("//cbc:DocumentCurrencyCode", namespaces=NS)
        assert curr[0].text == "USD"

    def test_arabic_content(self):
        xml = _make_invoice(
            seller_name="شركة فكرة للتقنية",
            buyer_name="عميل تجريبي",
            line_items=[
                {"name": "خدمات استشارية", "quantity": 1, "unit_price": 5000.00},
            ],
        )
        root = etree.fromstring(xml.encode())

        seller = root.xpath(
            "//cac:AccountingSupplierParty//cbc:RegistrationName",
            namespaces=NS,
        )
        assert seller[0].text == "شركة فكرة للتقنية"

    def test_zero_vat_rate(self):
        xml = _make_invoice(
            line_items=[
                {"name": "Exempt Item", "quantity": 1, "unit_price": 500.00, "vat_rate": 0, "vat_category": "E"},
            ]
        )
        root = etree.fromstring(xml.encode())

        tax_amount = root.xpath("//cac:TaxTotal/cbc:TaxAmount", namespaces=NS)
        assert tax_amount[0].text == "0.00"

        payable = root.xpath("//cac:LegalMonetaryTotal/cbc:PayableAmount", namespaces=NS)
        assert payable[0].text == "500.00"

    def test_mixed_vat_rates(self):
        xml = _make_invoice(
            line_items=[
                {"name": "Taxed", "quantity": 1, "unit_price": 1000.00, "vat_rate": 0.15, "vat_category": "S"},
                {"name": "Exempt", "quantity": 1, "unit_price": 500.00, "vat_rate": 0, "vat_category": "E"},
            ]
        )
        root = etree.fromstring(xml.encode())

        # Should have two TaxSubtotals under TaxTotal
        subtotals = root.xpath("//cac:TaxTotal/cac:TaxSubtotal", namespaces=NS)
        assert len(subtotals) == 2

        # Total VAT = 150 (only from taxed item)
        tax_amount = root.xpath("//cac:TaxTotal/cbc:TaxAmount", namespaces=NS)
        assert tax_amount[0].text == "150.00"

        # Payable = 1000 + 500 + 150 = 1650
        payable = root.xpath("//cac:LegalMonetaryTotal/cbc:PayableAmount", namespaces=NS)
        assert payable[0].text == "1650.00"

    def test_large_quantity(self):
        xml = _make_invoice(
            line_items=[
                {"name": "Bulk Widget", "quantity": 100000, "unit_price": 0.50},
            ]
        )
        root = etree.fromstring(xml.encode())

        line_ext = root.xpath("//cac:InvoiceLine/cbc:LineExtensionAmount", namespaces=NS)
        assert line_ext[0].text == "50000.00"

    def test_fractional_quantity(self):
        xml = _make_invoice(
            line_items=[
                {"name": "Flour (kg)", "quantity": 2.5, "unit_price": 20.00},
            ]
        )
        root = etree.fromstring(xml.encode())

        line_ext = root.xpath("//cac:InvoiceLine/cbc:LineExtensionAmount", namespaces=NS)
        assert line_ext[0].text == "50.00"

    def test_optional_note(self):
        xml = _make_invoice(note="Payment due within 30 days")
        root = etree.fromstring(xml.encode())

        note = root.xpath("//cbc:Note", namespaces=NS)
        assert len(note) == 1
        assert note[0].text == "Payment due within 30 days"

    def test_no_note(self):
        xml = _make_invoice()
        root = etree.fromstring(xml.encode())

        note = root.xpath("//cbc:Note", namespaces=NS)
        assert len(note) == 0
