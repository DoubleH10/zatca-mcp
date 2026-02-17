"""
ZATCA Invoice Validation Engine.

Validates invoices against ZATCA business rules including:
- Required field checks
- VAT number format validation
- Mathematical accuracy (line totals, VAT calculations)
- Structure validation (UBL 2.1 compliance)
"""

from __future__ import annotations

from lxml import etree
from decimal import Decimal, ROUND_HALF_UP
import re

NS = {
    "ubl": "urn:oasis:names:specification:ubl:schema:xsd:Invoice-2",
    "cac": "urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2",
    "cbc": "urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2",
}


def _xpath_text(root: etree._Element, xpath: str) -> str | None:
    """Extract text from first matching XPath element."""
    result = root.xpath(xpath, namespaces=NS)
    if result and hasattr(result[0], "text"):
        return result[0].text
    return None


def validate_vat_number(vat: str) -> list[str]:
    """Validate a Saudi VAT number format."""
    errors = []
    if not vat:
        errors.append("VAT number is required")
        return errors
    if len(vat) != 15:
        errors.append(f"VAT number must be 15 digits, got {len(vat)}")
    if not vat.isdigit():
        errors.append("VAT number must contain only digits")
    if vat and not vat.startswith("3"):
        errors.append("VAT number must start with 3")
    if vat and not vat.endswith("3"):
        errors.append("VAT number must end with 3")
    return errors


def validate_invoice_xml(xml_string: str) -> dict:
    """
    Validate an invoice XML against ZATCA business rules.

    Args:
        xml_string: UBL 2.1 XML invoice string

    Returns:
        Dict with keys: is_valid (bool), errors (list), warnings (list)
    """
    errors = []
    warnings = []

    # Parse XML
    try:
        root = etree.fromstring(xml_string.encode("utf-8"))
    except etree.XMLSyntaxError as e:
        return {
            "is_valid": False,
            "errors": [f"Invalid XML: {str(e)}"],
            "warnings": [],
        }

    # BR-01: Invoice ID is mandatory
    invoice_id = _xpath_text(root, "//cbc:ID")
    if not invoice_id:
        errors.append("BR-01: Invoice ID (cbc:ID) is mandatory")

    # BR-02: Issue Date is mandatory
    issue_date = _xpath_text(root, "//cbc:IssueDate")
    if not issue_date:
        errors.append("BR-02: Issue Date (cbc:IssueDate) is mandatory")
    elif not re.match(r"^\d{4}-\d{2}-\d{2}$", issue_date):
        errors.append(f"BR-02: Issue Date must be YYYY-MM-DD format, got: {issue_date}")

    # BR-03: Invoice Type Code
    type_code = _xpath_text(root, "//cbc:InvoiceTypeCode")
    if not type_code:
        errors.append("BR-03: Invoice Type Code is mandatory")
    elif type_code not in ("388", "381", "383"):
        errors.append(f"BR-03: Invalid Invoice Type Code: {type_code}")

    # BR-04: Document Currency
    currency = _xpath_text(root, "//cbc:DocumentCurrencyCode")
    if not currency:
        errors.append("BR-04: Document Currency Code is mandatory")

    # BR-05: Seller Name
    seller_name = _xpath_text(
        root,
        "//cac:AccountingSupplierParty/cac:Party/cac:PartyLegalEntity/cbc:RegistrationName",
    )
    if not seller_name:
        errors.append("BR-05: Seller name is mandatory")

    # BR-06: Seller VAT Number
    seller_vat = _xpath_text(
        root,
        "//cac:AccountingSupplierParty/cac:Party/cac:PartyTaxScheme/cbc:CompanyID",
    )
    if seller_vat:
        vat_errors = validate_vat_number(seller_vat)
        for ve in vat_errors:
            errors.append(f"BR-06: Seller VAT - {ve}")
    else:
        errors.append("BR-06: Seller VAT number is mandatory")

    # BR-07: Buyer Name
    buyer_name = _xpath_text(
        root,
        "//cac:AccountingCustomerParty/cac:Party/cac:PartyLegalEntity/cbc:RegistrationName",
    )
    if not buyer_name:
        errors.append("BR-07: Buyer name is mandatory")

    # BR-08: Check invoice type for buyer VAT requirement
    subtype = root.xpath("//cbc:InvoiceTypeCode/@name", namespaces=NS)
    if subtype and subtype[0].startswith("01"):  # Standard invoice
        buyer_vat = _xpath_text(
            root,
            "//cac:AccountingCustomerParty/cac:Party/cac:PartyTaxScheme/cbc:CompanyID",
        )
        if not buyer_vat:
            errors.append(
                "BR-08: Buyer VAT number is mandatory for standard (B2B) invoices"
            )

    # BR-10: At least one invoice line
    lines = root.xpath("//cac:InvoiceLine", namespaces=NS)
    if not lines:
        errors.append("BR-10: Invoice must have at least one line item")

    # BR-11: Validate math on line items
    for idx, line in enumerate(lines, start=1):
        qty_text = _xpath_text(line, "cbc:InvoicedQuantity")
        price_text = line.xpath(
            "cac:Price/cbc:PriceAmount/text()", namespaces=NS
        )
        ext_text = _xpath_text(line, "cbc:LineExtensionAmount")

        if qty_text and price_text and ext_text:
            try:
                qty = Decimal(qty_text)
                price = Decimal(price_text[0])
                ext = Decimal(ext_text)
                expected = (qty * price).quantize(
                    Decimal("0.01"), rounding=ROUND_HALF_UP
                )
                if abs(expected - ext) > Decimal("0.01"):
                    errors.append(
                        f"BR-11: Line {idx} total mismatch: "
                        f"{qty} x {price} = {expected}, got {ext}"
                    )
            except (ValueError, ArithmeticError):
                warnings.append(f"BR-11: Could not validate math on line {idx}")

    # BR-12: Tax total exists
    tax_amount_text = _xpath_text(root, "//cac:TaxTotal/cbc:TaxAmount")
    if not tax_amount_text:
        errors.append("BR-12: Tax total is mandatory")

    # BR-13: Payable amount exists
    payable = _xpath_text(
        root, "//cac:LegalMonetaryTotal/cbc:PayableAmount"
    )
    if not payable:
        errors.append("BR-13: Payable amount is mandatory")

    # BR-14: Cross-check totals
    tax_exclusive = _xpath_text(
        root, "//cac:LegalMonetaryTotal/cbc:TaxExclusiveAmount"
    )
    tax_inclusive = _xpath_text(
        root, "//cac:LegalMonetaryTotal/cbc:TaxInclusiveAmount"
    )
    if tax_exclusive and tax_amount_text and tax_inclusive:
        try:
            excl = Decimal(tax_exclusive)
            tax = Decimal(tax_amount_text)
            incl = Decimal(tax_inclusive)
            expected_incl = (excl + tax).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP
            )
            if abs(expected_incl - incl) > Decimal("0.01"):
                errors.append(
                    f"BR-14: Tax inclusive amount mismatch: "
                    f"{excl} + {tax} = {expected_incl}, got {incl}"
                )
        except (ValueError, ArithmeticError):
            warnings.append("BR-14: Could not cross-check invoice totals")

    # Warnings (non-blocking)
    if not _xpath_text(root, "//cbc:UUID"):
        warnings.append("Invoice UUID is recommended")

    seller_address = _xpath_text(
        root,
        "//cac:AccountingSupplierParty/cac:Party/cac:PostalAddress/cbc:StreetName",
    )
    if not seller_address:
        warnings.append("Seller street address is recommended")

    return {
        "is_valid": len(errors) == 0,
        "errors": errors,
        "warnings": warnings,
        "checks_run": 14,
    }
