"""
UBL 2.1 XML Invoice Builder for ZATCA.

Generates XML invoices compliant with ZATCA's e-invoicing standard.
Supports both Standard (B2B) and Simplified (B2C) invoice types.

Reference: ZATCA Electronic Invoice XML Implementation Standard
"""

from __future__ import annotations

from lxml import etree
from decimal import Decimal, ROUND_HALF_UP
from datetime import datetime, timezone
import uuid

# UBL 2.1 Namespaces
NS = {
    "": "urn:oasis:names:specification:ubl:schema:xsd:Invoice-2",
    "cac": "urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2",
    "cbc": "urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2",
    "ext": "urn:oasis:names:specification:ubl:schema:xsd:CommonExtensionComponents-2",
}

# ZATCA Invoice Type Codes
INVOICE_TYPE_CODES = {
    "standard": "388",  # Tax Invoice (B2B)
    "simplified": "388",  # Simplified Tax Invoice (B2C)
    "credit_note": "381",
    "debit_note": "383",
}

# ZATCA Invoice Sub-Type Codes
INVOICE_SUBTYPE_CODES = {
    "standard": "0100000",  # Standard tax invoice
    "simplified": "0200000",  # Simplified tax invoice
}


def _qn(ns_prefix: str, local_name: str) -> str:
    """Create a Clark notation qualified name."""
    if ns_prefix == "":
        return f"{{{NS['']}}}{local_name}"
    return f"{{{NS[ns_prefix]}}}{local_name}"


def _round_decimal(value: Decimal, places: int = 2) -> Decimal:
    """Round a Decimal to specified places."""
    return value.quantize(Decimal(10) ** -places, rounding=ROUND_HALF_UP)


def _add_text_element(
    parent: etree._Element, ns_prefix: str, local_name: str, text: str, **attribs
) -> etree._Element:
    """Add a child element with text content."""
    elem = etree.SubElement(parent, _qn(ns_prefix, local_name))
    elem.text = str(text)
    for key, value in attribs.items():
        elem.set(key, str(value))
    return elem


def _build_party(
    parent: etree._Element,
    tag: str,
    name: str,
    vat_number: str | None,
    address: str = "",
    city: str = "",
    country_code: str = "SA",
) -> etree._Element:
    """Build an AccountingSupplierParty or AccountingCustomerParty element."""
    party_wrapper = etree.SubElement(parent, _qn("cac", tag))
    party = etree.SubElement(party_wrapper, _qn("cac", "Party"))

    # Postal Address
    postal = etree.SubElement(party, _qn("cac", "PostalAddress"))
    if address:
        _add_text_element(postal, "cbc", "StreetName", address)
    if city:
        _add_text_element(postal, "cbc", "CityName", city)
    country_elem = etree.SubElement(postal, _qn("cac", "Country"))
    _add_text_element(country_elem, "cbc", "IdentificationCode", country_code)

    # Tax Scheme (VAT)
    if vat_number:
        tax_scheme_wrapper = etree.SubElement(party, _qn("cac", "PartyTaxScheme"))
        _add_text_element(tax_scheme_wrapper, "cbc", "CompanyID", vat_number)
        tax_scheme = etree.SubElement(tax_scheme_wrapper, _qn("cac", "TaxScheme"))
        _add_text_element(tax_scheme, "cbc", "ID", "VAT")

    # Legal Entity
    legal = etree.SubElement(party, _qn("cac", "PartyLegalEntity"))
    _add_text_element(legal, "cbc", "RegistrationName", name)

    return party_wrapper


def build_invoice_xml(
    invoice_type: str,
    invoice_number: str,
    issue_date: str,
    seller_name: str,
    seller_vat: str,
    seller_address: str,
    seller_city: str,
    buyer_name: str,
    line_items: list[dict],
    currency: str = "SAR",
    buyer_vat: str | None = None,
    buyer_address: str = "",
    buyer_city: str = "",
    note: str | None = None,
    qr_data: str | None = None,
) -> str:
    """
    Build a ZATCA-compliant UBL 2.1 invoice XML.

    Args:
        invoice_type: "standard" or "simplified"
        invoice_number: Unique invoice identifier
        issue_date: ISO date (YYYY-MM-DD)
        seller_name: Seller business name
        seller_vat: Seller 15-digit VAT number
        seller_address: Seller street address
        seller_city: Seller city
        buyer_name: Buyer name
        line_items: List of dicts with keys: name, quantity, unit_price, vat_rate (optional), vat_category (optional)
        currency: Currency code (default: SAR)
        buyer_vat: Buyer VAT number (required for standard invoices)
        buyer_address: Buyer street address
        buyer_city: Buyer city
        note: Optional invoice note
        qr_data: Optional Base64-encoded QR data to embed

    Returns:
        Pretty-printed XML string
    """
    # Create root element with namespaces
    nsmap = {None: NS[""], "cac": NS["cac"], "cbc": NS["cbc"], "ext": NS["ext"]}
    root = etree.Element(_qn("", "Invoice"), nsmap=nsmap)

    # Profile ID
    _add_text_element(
        root, "cbc", "ProfileID",
        "reporting:1.0"
    )

    # Invoice ID
    _add_text_element(root, "cbc", "ID", invoice_number)

    # UUID
    _add_text_element(root, "cbc", "UUID", str(uuid.uuid4()))

    # Issue Date and Time
    _add_text_element(root, "cbc", "IssueDate", issue_date)
    _add_text_element(root, "cbc", "IssueTime", datetime.now(timezone.utc).strftime("%H:%M:%S"))

    # Invoice Type Code with sub-type
    type_code_elem = _add_text_element(
        root, "cbc", "InvoiceTypeCode",
        INVOICE_TYPE_CODES.get(invoice_type, "388"),
        name=INVOICE_SUBTYPE_CODES.get(invoice_type, "0100000"),
    )

    # Document Currency
    _add_text_element(root, "cbc", "DocumentCurrencyCode", currency)

    # Tax Currency
    _add_text_element(root, "cbc", "TaxCurrencyCode", currency)

    # Note
    if note:
        _add_text_element(root, "cbc", "Note", note)

    # QR Code (Additional Document Reference)
    if qr_data:
        doc_ref = etree.SubElement(root, _qn("cac", "AdditionalDocumentReference"))
        _add_text_element(doc_ref, "cbc", "ID", "QR")
        attachment = etree.SubElement(doc_ref, _qn("cac", "Attachment"))
        embedded = etree.SubElement(attachment, _qn("cbc", "EmbeddedDocumentBinaryObject"))
        embedded.set("mimeCode", "text/plain")
        embedded.text = qr_data

    # Seller (AccountingSupplierParty)
    _build_party(
        root, "AccountingSupplierParty",
        name=seller_name,
        vat_number=seller_vat,
        address=seller_address,
        city=seller_city,
    )

    # Buyer (AccountingCustomerParty)
    _build_party(
        root, "AccountingCustomerParty",
        name=buyer_name,
        vat_number=buyer_vat,
        address=buyer_address,
        city=buyer_city,
    )

    # Calculate totals
    total_taxable = Decimal("0")
    total_vat = Decimal("0")
    processed_items = []

    for item in line_items:
        qty = Decimal(str(item["quantity"]))
        price = Decimal(str(item["unit_price"]))
        vat_rate = Decimal(str(item.get("vat_rate", "0.15")))
        vat_category = item.get("vat_category", "S")

        line_amount = _round_decimal(qty * price)
        line_vat = _round_decimal(line_amount * vat_rate)

        total_taxable += line_amount
        total_vat += line_vat

        processed_items.append({
            **item,
            "quantity": qty,
            "unit_price": price,
            "vat_rate": vat_rate,
            "vat_category": vat_category,
            "line_amount": line_amount,
            "line_vat": line_vat,
        })

    total_with_vat = _round_decimal(total_taxable + total_vat)

    # Group items by (vat_rate, vat_category) for multi-rate TaxTotal
    tax_groups: dict[tuple[Decimal, str], dict[str, Decimal]] = {}
    for item in processed_items:
        key = (item["vat_rate"], item["vat_category"])
        if key not in tax_groups:
            tax_groups[key] = {"taxable": Decimal("0"), "tax": Decimal("0")}
        tax_groups[key]["taxable"] += item["line_amount"]
        tax_groups[key]["tax"] += item["line_vat"]

    # Tax Total with one TaxSubtotal per rate group
    tax_total = etree.SubElement(root, _qn("cac", "TaxTotal"))
    _add_text_element(
        tax_total, "cbc", "TaxAmount", str(_round_decimal(total_vat)),
        currencyID=currency,
    )
    for (vat_rate, vat_category), amounts in tax_groups.items():
        subtotal = etree.SubElement(tax_total, _qn("cac", "TaxSubtotal"))
        _add_text_element(
            subtotal, "cbc", "TaxableAmount",
            str(_round_decimal(amounts["taxable"])), currencyID=currency,
        )
        _add_text_element(
            subtotal, "cbc", "TaxAmount",
            str(_round_decimal(amounts["tax"])), currencyID=currency,
        )
        category = etree.SubElement(subtotal, _qn("cac", "TaxCategory"))
        _add_text_element(category, "cbc", "ID", vat_category)
        _add_text_element(
            category, "cbc", "Percent", str(_round_decimal(vat_rate * 100, 0))
        )
        scheme = etree.SubElement(category, _qn("cac", "TaxScheme"))
        _add_text_element(scheme, "cbc", "ID", "VAT")

    # Legal Monetary Total
    monetary = etree.SubElement(root, _qn("cac", "LegalMonetaryTotal"))
    _add_text_element(
        monetary, "cbc", "LineExtensionAmount",
        str(_round_decimal(total_taxable)), currencyID=currency,
    )
    _add_text_element(
        monetary, "cbc", "TaxExclusiveAmount",
        str(_round_decimal(total_taxable)), currencyID=currency,
    )
    _add_text_element(
        monetary, "cbc", "TaxInclusiveAmount",
        str(_round_decimal(total_with_vat)), currencyID=currency,
    )
    _add_text_element(
        monetary, "cbc", "PayableAmount",
        str(_round_decimal(total_with_vat)), currencyID=currency,
    )

    # Invoice Lines
    for idx, item in enumerate(processed_items, start=1):
        line = etree.SubElement(root, _qn("cac", "InvoiceLine"))
        _add_text_element(line, "cbc", "ID", str(idx))
        _add_text_element(
            line, "cbc", "InvoicedQuantity",
            str(item["quantity"]), unitCode="PCE",
        )
        _add_text_element(
            line, "cbc", "LineExtensionAmount",
            str(_round_decimal(item["line_amount"])), currencyID=currency,
        )

        # Tax for this line
        line_tax = etree.SubElement(line, _qn("cac", "TaxTotal"))
        _add_text_element(
            line_tax, "cbc", "TaxAmount",
            str(_round_decimal(item["line_vat"])), currencyID=currency,
        )
        _add_text_element(
            line_tax, "cbc", "RoundingAmount",
            str(_round_decimal(item["line_amount"] + item["line_vat"])),
            currencyID=currency,
        )

        # Item details
        line_item = etree.SubElement(line, _qn("cac", "Item"))
        _add_text_element(line_item, "cbc", "Name", item["name"])

        classified_tax = etree.SubElement(line_item, _qn("cac", "ClassifiedTaxCategory"))
        _add_text_element(classified_tax, "cbc", "ID", item["vat_category"])
        _add_text_element(
            classified_tax, "cbc", "Percent",
            str(_round_decimal(item["vat_rate"] * 100, 0)),
        )
        tax_scheme = etree.SubElement(classified_tax, _qn("cac", "TaxScheme"))
        _add_text_element(tax_scheme, "cbc", "ID", "VAT")

        # Price
        price_elem = etree.SubElement(line, _qn("cac", "Price"))
        _add_text_element(
            price_elem, "cbc", "PriceAmount",
            str(_round_decimal(item["unit_price"])), currencyID=currency,
        )

    # Serialize
    return etree.tostring(
        root,
        pretty_print=True,
        xml_declaration=True,
        encoding="UTF-8",
    ).decode("utf-8")
