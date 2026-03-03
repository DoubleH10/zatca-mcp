"""
ZATCA MCP Server - Saudi E-Invoicing for AI Agents.

An MCP (Model Context Protocol) server that enables AI agents to generate,
validate, and manage ZATCA-compliant electronic invoices.

Usage:
    # With MCP Inspector (development)
    mcp dev src/zatca_mcp/server.py

    # With Claude Desktop
    Add to ~/.claude/claude_desktop_config.json:
    {
        "mcpServers": {
            "zatca": {
                "command": "python",
                "args": ["-m", "zatca_mcp.server"]
            }
        }
    }
"""

from __future__ import annotations

import json

from mcp.server.fastmcp import FastMCP

from zatca_mcp.utils.tlv import decode_tlv_named, encode_tlv
from zatca_mcp.utils.validation import validate_invoice_xml, validate_vat_number
from zatca_mcp.utils.xml_builder import build_invoice_xml

# Create the MCP server
mcp = FastMCP(
    "zatca-mcp",
    instructions=(
        "ZATCA e-invoicing MCP server for Saudi Arabia. "
        "Generate, validate, and manage compliant electronic invoices."
    ),
)


# ═══════════════════════════════════════════════════
# TOOL 1: QR Code Generation
# ═══════════════════════════════════════════════════


@mcp.tool()
async def generate_qr_code(
    seller_name: str,
    vat_number: str,
    timestamp: str,
    total_amount: str,
    vat_amount: str,
) -> str:
    """Generate a ZATCA-compliant TLV-encoded QR code.

    Creates a Base64-encoded QR code payload following ZATCA's
    Tag-Length-Value (TLV) format for Phase 1 and Phase 2 compliance.
    The resulting string can be used to generate a scannable QR code
    on printed invoices.

    Args:
        seller_name: Business/taxpayer name (Arabic or English)
        vat_number: 15-digit Saudi VAT registration number (starts and ends with 3)
        timestamp: Invoice date/time in ISO 8601 format (e.g., "2024-01-15T10:30:00Z")
        total_amount: Invoice total including VAT as string (e.g., "1150.00")
        vat_amount: Total VAT charged as string (e.g., "150.00")

    Returns:
        JSON with qr_base64 (the encoded string) and decoded verification data
    """
    # Validate VAT
    vat_errors = validate_vat_number(vat_number)
    if vat_errors:
        return json.dumps({"error": "Invalid VAT number", "details": vat_errors})

    qr_base64 = encode_tlv(
        seller_name=seller_name,
        vat_number=vat_number,
        timestamp=timestamp,
        total_amount=total_amount,
        vat_amount=vat_amount,
    )

    # Verify by decoding
    decoded = decode_tlv_named(qr_base64)

    return json.dumps(
        {"qr_base64": qr_base64, "decoded_verification": decoded},
        indent=2,
        ensure_ascii=False,
    )


# ═══════════════════════════════════════════════════
# TOOL 2: Invoice XML Generation
# ═══════════════════════════════════════════════════


@mcp.tool()
async def generate_invoice(
    invoice_type: str,
    invoice_number: str,
    issue_date: str,
    seller_name: str,
    seller_vat: str,
    seller_address: str,
    seller_city: str,
    buyer_name: str,
    items: str,
    currency: str = "SAR",
    buyer_vat: str | None = None,
    buyer_address: str = "",
    buyer_city: str = "",
    note: str | None = None,
    billing_reference_id: str | None = None,
    billing_reference_date: str | None = None,
    instruction_note: str | None = None,
) -> str:
    """Generate a ZATCA-compliant UBL 2.1 XML e-invoice.

    Creates a complete XML invoice following Saudi Arabia's ZATCA e-invoicing
    standard. Supports Standard (B2B), Simplified (B2C), Credit Note, and
    Debit Note invoice types. Automatically calculates VAT, line totals,
    and embeds QR code data.

    Args:
        invoice_type: "standard" (B2B), "simplified" (B2C), "credit_note", or "debit_note"
        invoice_number: Unique invoice identifier (e.g., "INV-2024-001")
        issue_date: Invoice date in YYYY-MM-DD format
        seller_name: Seller business name
        seller_vat: Seller 15-digit VAT number (e.g., "300000000000003")
        seller_address: Seller street address
        seller_city: Seller city name
        buyer_name: Buyer/customer name
        items: JSON array of line items. Each item:
            {"name": "Product", "quantity": 1, "unit_price": 100.00, "vat_rate": 0.15}
        currency: ISO currency code (default: "SAR")
        buyer_vat: Buyer VAT number (required for standard invoices)
        buyer_address: Buyer street address (optional)
        buyer_city: Buyer city (optional)
        note: Optional note to include on the invoice
        billing_reference_id: Original invoice ID (required for credit/debit notes)
        billing_reference_date: Original invoice date (for credit/debit notes)
        instruction_note: Reason for credit/debit note (recommended)

    Returns:
        Complete UBL 2.1 XML invoice string
    """
    import re

    # Validate date format
    if not re.match(r"^\d{4}-\d{2}-\d{2}$", issue_date):
        return json.dumps({"error": f"issue_date must be YYYY-MM-DD format, got: {issue_date}"})

    # Validate string lengths
    for field_name, field_val, max_len in [
        ("seller_name", seller_name, 200),
        ("buyer_name", buyer_name, 200),
        ("seller_address", seller_address, 500),
        ("seller_city", seller_city, 200),
        ("buyer_address", buyer_address, 500),
        ("buyer_city", buyer_city, 200),
    ]:
        if len(field_val) > max_len:
            return json.dumps({"error": f"{field_name} exceeds {max_len} character limit"})

    # Parse items
    try:
        line_items = json.loads(items)
    except json.JSONDecodeError as e:
        return json.dumps({"error": f"Invalid items JSON: {str(e)}"})

    if not line_items:
        return json.dumps({"error": "At least one line item is required"})

    # Validate line items
    for idx, item in enumerate(line_items, start=1):
        for required_field in ("name", "quantity", "unit_price"):
            if required_field not in item:
                return json.dumps(
                    {"error": f"Line item {idx} missing required field: {required_field}"}
                )
        try:
            qty = float(item["quantity"])
            price = float(item["unit_price"])
        except (TypeError, ValueError):
            return json.dumps(
                {"error": f"Line item {idx}: quantity and unit_price must be numeric"}
            )
        if qty <= 0:
            return json.dumps({"error": f"Line item {idx}: quantity must be positive"})
        if price < 0:
            return json.dumps({"error": f"Line item {idx}: unit_price must be non-negative"})

    # Validate seller VAT
    vat_errors = validate_vat_number(seller_vat)
    if vat_errors:
        return json.dumps({"error": "Invalid seller VAT", "details": vat_errors})

    # Standard invoices require buyer VAT
    if invoice_type == "standard" and not buyer_vat:
        return json.dumps({"error": "Buyer VAT number is required for standard (B2B) invoices"})

    # Generate QR code data
    from decimal import ROUND_HALF_UP, Decimal

    total_taxable = sum(
        (Decimal(str(i["quantity"])) * Decimal(str(i["unit_price"])) for i in line_items),
        Decimal("0"),
    )
    total_vat = sum(
        (
            (Decimal(str(i["quantity"])) * Decimal(str(i["unit_price"])))
            * Decimal(str(i.get("vat_rate", "0.15")))
            for i in line_items
        ),
        Decimal("0"),
    )
    total_with_vat = (total_taxable + total_vat).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    total_vat_rounded = total_vat.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    from datetime import datetime, timezone

    ts = f"{issue_date}T{datetime.now(timezone.utc).strftime('%H:%M:%S')}Z"

    qr_data = encode_tlv(
        seller_name=seller_name,
        vat_number=seller_vat,
        timestamp=ts,
        total_amount=str(total_with_vat),
        vat_amount=str(total_vat_rounded),
    )

    # Build XML
    xml = build_invoice_xml(
        invoice_type=invoice_type,
        invoice_number=invoice_number,
        issue_date=issue_date,
        seller_name=seller_name,
        seller_vat=seller_vat,
        seller_address=seller_address,
        seller_city=seller_city,
        buyer_name=buyer_name,
        buyer_vat=buyer_vat,
        buyer_address=buyer_address,
        buyer_city=buyer_city,
        line_items=line_items,
        currency=currency,
        note=note,
        qr_data=qr_data,
        billing_reference_id=billing_reference_id,
        billing_reference_date=billing_reference_date,
        instruction_note=instruction_note,
    )

    return xml


# ═══════════════════════════════════════════════════
# TOOL 3: Invoice Validation
# ═══════════════════════════════════════════════════


@mcp.tool()
async def validate_invoice(invoice_xml: str) -> str:
    """Validate an invoice XML against ZATCA business rules.

    Runs comprehensive checks including: required fields, VAT number
    format, mathematical accuracy of line totals and VAT calculations,
    and structural integrity of the UBL 2.1 XML.

    Args:
        invoice_xml: Complete UBL 2.1 XML invoice string to validate

    Returns:
        JSON with is_valid (boolean), errors (list of issues), warnings (list),
        and checks_run (number of rules checked)
    """
    result = validate_invoice_xml(invoice_xml)
    return json.dumps(result, indent=2, ensure_ascii=False)


# ═══════════════════════════════════════════════════
# TOOL 4: QR Code Decoder
# ═══════════════════════════════════════════════════


@mcp.tool()
async def decode_qr(qr_base64: str) -> str:
    """Decode a ZATCA TLV-encoded QR code string.

    Useful for verifying or inspecting existing QR codes from
    ZATCA-compliant invoices. Extracts all encoded tag values.

    Args:
        qr_base64: Base64-encoded TLV string from a ZATCA QR code

    Returns:
        JSON with decoded tag names and their values
    """
    try:
        decoded = decode_tlv_named(qr_base64)
        return json.dumps(decoded, indent=2, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"error": f"Failed to decode QR: {str(e)}"})


# ═══════════════════════════════════════════════════
# TOOL 5: CSR Generation (Phase 2)
# ═══════════════════════════════════════════════════


@mcp.tool()
async def generate_csr(
    common_name: str,
    organization: str,
    organizational_unit: str,
    country: str = "SA",
    serial_number: str = "1-TST|2-TST|3-ed22f1d8-e6a2-1118-9b58-d9a8195e2f28",
    invoice_type: str = "1100",
    location: str = "Riyadh",
    industry: str = "IT",
) -> str:
    """Generate a ZATCA-compliant Certificate Signing Request (CSR).

    Creates an ECDSA key pair and CSR with ZATCA-required subject fields.
    The CSR is used to obtain a compliance certificate from ZATCA.

    Args:
        common_name: Common name for the certificate (e.g., device or taxpayer name)
        organization: Organization name
        organizational_unit: Organizational unit (e.g., "Invoicing", "IT")
        country: Country code (default: "SA")
        serial_number: ZATCA device serial number
        invoice_type: ZATCA invoice type code (e.g., "1100")
        location: Business location
        industry: Business industry category

    Returns:
        JSON with csr_pem, private_key_pem, and next steps
    """
    try:
        from zatca_mcp.utils.signing import (
            generate_csr as _generate_csr,
        )
        from zatca_mcp.utils.signing import (
            generate_private_key,
            serialize_private_key,
        )
    except ImportError:
        return json.dumps(
            {
                "error": "Phase 2 dependencies not installed",
                "fix": "pip install zatca-mcp[phase2]",
                "details": "The cryptography package is required for CSR generation",
            }
        )

    key = generate_private_key()
    csr_pem = _generate_csr(
        key=key,
        common_name=common_name,
        organization=organization,
        organizational_unit=organizational_unit,
        country=country,
        serial_number=serial_number,
        invoice_type=invoice_type,
        location=location,
        industry=industry,
    )
    private_key_pem = serialize_private_key(key)

    return json.dumps(
        {
            "csr_pem": csr_pem.decode("utf-8"),
            "private_key_pem": private_key_pem.decode("utf-8"),
            "warning": "Store the private key securely. It cannot be recovered.",
            "next_step": "Submit the CSR to ZATCA to obtain a compliance certificate",
        },
        indent=2,
    )


# ═══════════════════════════════════════════════════
# TOOL 6: Invoice Signing (Phase 2)
# ═══════════════════════════════════════════════════


@mcp.tool()
async def sign_invoice(
    invoice_xml: str,
    certificate_pem: str,
    private_key_pem: str,
) -> str:
    """Digitally sign a ZATCA invoice with XAdES-BES.

    Takes an unsigned invoice XML and applies a digital signature using
    the provided certificate and private key. Produces a signed XML with
    embedded XAdES-BES signature in UBLExtensions, and rebuilds the QR
    code with Phase 2 tags (hash, signature, public key).

    Args:
        invoice_xml: Unsigned UBL 2.1 XML invoice string
        certificate_pem: PEM-encoded X.509 certificate from ZATCA
        private_key_pem: PEM-encoded ECDSA private key

    Returns:
        JSON with signed_xml, invoice_hash, qr_base64, and compliance status
    """
    try:
        from zatca_mcp.utils.signing import (
            get_public_key_bytes,
            hash_invoice,
            inject_signature,
            load_private_key,
        )
        from zatca_mcp.utils.signing import (
            sign_hash as _sign_hash,
        )
    except ImportError:
        return json.dumps(
            {
                "error": "Phase 2 dependencies not installed",
                "fix": "pip install zatca-mcp[phase2]",
                "details": "The cryptography package is required for invoice signing",
            }
        )

    import base64

    try:
        key = load_private_key(private_key_pem.encode("utf-8"))
    except Exception as e:
        return json.dumps({"error": f"Failed to load private key: {str(e)}"})

    xml_bytes = invoice_xml.encode("utf-8")

    # Hash the invoice
    invoice_hash = hash_invoice(xml_bytes)

    # Sign the invoice (inject XAdES-BES)
    try:
        signed_xml_bytes = inject_signature(xml_bytes, certificate_pem, key)
    except Exception as e:
        return json.dumps({"error": f"Signing failed: {str(e)}"})

    # Get signature and public key for QR TLV tags 6-8
    hash_bytes = base64.b64decode(invoice_hash)
    signature_bytes = _sign_hash(key, hash_bytes)
    pub_key_bytes = get_public_key_bytes(key)

    # Rebuild QR with Phase 2 tags
    from lxml import etree

    root = etree.fromstring(signed_xml_bytes)
    ns = {
        "cac": "urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2",
        "cbc": "urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2",
    }

    # Extract existing QR data to get seller info
    qr_els = root.xpath(
        "//cac:AdditionalDocumentReference[cbc:ID='QR']//cbc:EmbeddedDocumentBinaryObject",
        namespaces=ns,
    )

    qr_base64 = ""
    if qr_els and qr_els[0].text:  # type: ignore[index,union-attr]
        # Decode existing QR, add Phase 2 tags, re-encode
        existing_qr = qr_els[0].text  # type: ignore[index,union-attr]
        decoded = decode_tlv_named(existing_qr)
        new_qr = encode_tlv(
            seller_name=decoded.get("seller_name", ""),
            vat_number=decoded.get("vat_number", ""),
            timestamp=decoded.get("timestamp", ""),
            total_amount=decoded.get("total_amount", ""),
            vat_amount=decoded.get("vat_amount", ""),
            invoice_hash=invoice_hash,
            ecdsa_signature=base64.b64encode(signature_bytes).decode("ascii"),
            ecdsa_public_key=base64.b64encode(pub_key_bytes).decode("ascii"),
        )
        qr_base64 = new_qr
        # Update the QR in the signed XML
        qr_els[0].text = new_qr  # type: ignore[index,union-attr]
        signed_xml_bytes = etree.tostring(
            root,
            pretty_print=True,
            xml_declaration=True,
            encoding="UTF-8",
        )

    return json.dumps(
        {
            "signed_xml": signed_xml_bytes.decode("utf-8"),
            "invoice_hash": invoice_hash,
            "qr_base64": qr_base64,
            "is_phase2_compliant": True,
        },
        indent=2,
        ensure_ascii=False,
    )


# ═══════════════════════════════════════════════════
# TOOL 7: Invoice Submission (Phase 2)
# ═══════════════════════════════════════════════════


@mcp.tool()
async def submit_invoice(
    signed_invoice_xml: str,
    invoice_hash: str,
    invoice_uuid: str,
    certificate: str,
    secret: str,
    mode: str = "reporting",
    environment: str = "sandbox",
) -> str:
    """Submit a signed invoice to ZATCA for reporting or clearance.

    Sends the signed invoice to ZATCA's Fatoora API. Use "reporting" mode
    for simplified invoices (B2C) and "clearance" mode for standard
    invoices (B2B).

    Args:
        signed_invoice_xml: Signed UBL 2.1 XML invoice string
        invoice_hash: Base64-encoded SHA-256 hash of the invoice
        invoice_uuid: Invoice UUID
        certificate: Base64-encoded compliance/production certificate
        secret: API secret from ZATCA
        mode: "reporting" (simplified) or "clearance" (standard)
        environment: "sandbox" or "production"

    Returns:
        JSON with ZATCA's response (status, validation results)
    """
    try:
        from zatca_mcp.api.client import ZATCAClient
    except ImportError:
        return json.dumps(
            {
                "error": "Phase 2 dependencies not installed",
                "fix": "pip install zatca-mcp[phase2]",
                "details": "httpx and pydantic are required for ZATCA API integration",
            }
        )

    import base64

    client = ZATCAClient(
        certificate=certificate,
        secret=secret,
        environment=environment,
    )

    xml_b64 = base64.b64encode(signed_invoice_xml.encode("utf-8")).decode("ascii")

    try:
        if mode == "clearance":
            result = await client.clear_invoice(xml_b64, invoice_hash, invoice_uuid)
        else:
            result = await client.report_invoice(xml_b64, invoice_hash, invoice_uuid)

        return json.dumps(result.model_dump(), indent=2, ensure_ascii=False)

    except Exception as e:
        return json.dumps({"error": f"ZATCA API request failed: {str(e)}"})


# ═══════════════════════════════════════════════════
# TOOL 8: Compliance Check (Phase 2)
# ═══════════════════════════════════════════════════


@mcp.tool()
async def check_compliance(
    signed_invoice_xml: str,
    invoice_hash: str,
    invoice_uuid: str,
    certificate: str,
    secret: str,
    environment: str = "sandbox",
) -> str:
    """Check a signed invoice against ZATCA compliance rules.

    Validates the invoice with ZATCA's server-side checks before
    actual submission. Useful for testing compliance without affecting
    production records.

    Args:
        signed_invoice_xml: Signed UBL 2.1 XML invoice string
        invoice_hash: Base64-encoded SHA-256 hash of the invoice
        invoice_uuid: Invoice UUID
        certificate: Base64-encoded compliance certificate
        secret: API secret from ZATCA
        environment: "sandbox" or "production"

    Returns:
        JSON with ZATCA validation results
    """
    try:
        from zatca_mcp.api.client import ZATCAClient
    except ImportError:
        return json.dumps(
            {
                "error": "Phase 2 dependencies not installed",
                "fix": "pip install zatca-mcp[phase2]",
                "details": "httpx and pydantic are required for ZATCA API integration",
            }
        )

    import base64

    client = ZATCAClient(
        certificate=certificate,
        secret=secret,
        environment=environment,
    )

    xml_b64 = base64.b64encode(signed_invoice_xml.encode("utf-8")).decode("ascii")

    try:
        result = await client.check_compliance(xml_b64, invoice_hash, invoice_uuid)
        return json.dumps(result.model_dump(), indent=2, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"error": f"ZATCA compliance check failed: {str(e)}"})


# ═══════════════════════════════════════════════════
# TOOL 9: HTML Invoice Rendering
# ═══════════════════════════════════════════════════


@mcp.tool()
async def render_invoice_html(invoice_xml: str) -> str:
    """Render a ZATCA invoice XML as a professional HTML document.

    Takes a UBL 2.1 XML invoice (as generated by generate_invoice) and
    produces a styled HTML page with embedded QR code image, ready for
    viewing in a browser or printing.

    Args:
        invoice_xml: Complete UBL 2.1 XML invoice string

    Returns:
        Complete HTML document string with embedded styles and QR code image
    """
    try:
        from zatca_mcp.cli import generate_html_invoice

        return generate_html_invoice(invoice_xml)
    except Exception as e:
        return json.dumps({"error": f"HTML rendering failed: {str(e)}"})


# ═══════════════════════════════════════════════════
# RESOURCE 1: Validation Rules
# ═══════════════════════════════════════════════════

VALIDATION_RULES = [
    {
        "id": "BR-01",
        "name": "Invoice ID",
        "description": "Invoice ID (cbc:ID) is mandatory",
        "severity": "error",
    },
    {
        "id": "BR-02",
        "name": "Issue Date",
        "description": "Issue Date (cbc:IssueDate) is mandatory and must be YYYY-MM-DD format",
        "severity": "error",
    },
    {
        "id": "BR-03",
        "name": "Type Code",
        "description": "Invoice Type Code (cbc:InvoiceTypeCode) must be 388, 381, or 383",
        "severity": "error",
    },
    {
        "id": "BR-04",
        "name": "Currency",
        "description": "Document Currency Code (cbc:DocumentCurrencyCode) is mandatory",
        "severity": "error",
    },
    {
        "id": "BR-05",
        "name": "Seller Name",
        "description": "Seller RegistrationName is mandatory",
        "severity": "error",
    },
    {
        "id": "BR-06",
        "name": "Seller VAT",
        "description": "Seller VAT must be a 15-digit number starting and ending with 3",
        "severity": "error",
    },
    {
        "id": "BR-07",
        "name": "Buyer Name",
        "description": "Buyer RegistrationName is mandatory",
        "severity": "error",
    },
    {
        "id": "BR-08",
        "name": "Buyer VAT (B2B)",
        "description": "Buyer VAT number is mandatory for standard (B2B) invoices (subtype 01*)",
        "severity": "error",
    },
    {
        "id": "BR-09",
        "name": "Reserved",
        "description": "Reserved for future use",
        "severity": "warning",
    },
    {
        "id": "BR-10",
        "name": "Line Items",
        "description": "Invoice must have at least one line item (cac:InvoiceLine)",
        "severity": "error",
    },
    {
        "id": "BR-11",
        "name": "Line Math",
        "description": "Line extension amount must equal quantity × unit price (±0.01 tolerance)",
        "severity": "error",
    },
    {
        "id": "BR-12",
        "name": "Tax Total",
        "description": "Tax total (cac:TaxTotal/cbc:TaxAmount) is mandatory",
        "severity": "error",
    },
    {
        "id": "BR-13",
        "name": "Payable Amount",
        "description": "Payable amount (cbc:PayableAmount) is mandatory",
        "severity": "error",
    },
    {
        "id": "BR-14",
        "name": "Total Cross-Check",
        "description": (
            "Tax-exclusive + tax amount must equal tax-inclusive amount (±0.01 tolerance)"
        ),
        "severity": "error",
    },
    {
        "id": "BR-15",
        "name": "Billing Reference",
        "description": (
            "Credit/debit notes must reference the original invoice via BillingReference"
        ),
        "severity": "error",
    },
    {
        "id": "BR-16",
        "name": "Instruction Note",
        "description": "Credit/debit notes should include an InstructionNote explaining the reason",
        "severity": "warning",
    },
]


@mcp.resource("zatca://validation-rules")
def get_validation_rules() -> str:
    """ZATCA business rules (BR-01 through BR-16) with severity levels.

    Returns all 16 validation rules used by the validate_invoice tool,
    including rule ID, name, description, and whether violations are
    errors (blocking) or warnings (non-blocking).
    """
    return json.dumps(VALIDATION_RULES, indent=2)


# ═══════════════════════════════════════════════════
# RESOURCE 2: Invoice Types
# ═══════════════════════════════════════════════════

INVOICE_TYPES = [
    {
        "name": "Standard Tax Invoice",
        "type_code": "388",
        "subtype": "0100000",
        "invoice_type_param": "standard",
        "use_case": "B2B transactions — buyer VAT number required",
        "vat_categories": ["Standard rate (15%)", "Zero-rated", "Exempt"],
    },
    {
        "name": "Simplified Tax Invoice",
        "type_code": "388",
        "subtype": "0200000",
        "invoice_type_param": "simplified",
        "use_case": "B2C / point-of-sale transactions — no buyer VAT required",
        "vat_categories": ["Standard rate (15%)", "Zero-rated", "Exempt"],
    },
    {
        "name": "Standard Credit Note",
        "type_code": "381",
        "subtype": "0100000",
        "invoice_type_param": "credit_note",
        "use_case": "B2B refunds/returns — requires billing_reference_id to original invoice",
        "vat_categories": ["Standard rate (15%)", "Zero-rated", "Exempt"],
    },
    {
        "name": "Simplified Credit Note",
        "type_code": "381",
        "subtype": "0200000",
        "invoice_type_param": "credit_note",
        "use_case": "B2C refunds/returns — requires billing_reference_id to original invoice",
        "vat_categories": ["Standard rate (15%)", "Zero-rated", "Exempt"],
    },
    {
        "name": "Standard Debit Note",
        "type_code": "383",
        "subtype": "0100000",
        "invoice_type_param": "debit_note",
        "use_case": "B2B additional charges — requires billing_reference_id to original invoice",
        "vat_categories": ["Standard rate (15%)", "Zero-rated", "Exempt"],
    },
    {
        "name": "Simplified Debit Note",
        "type_code": "383",
        "subtype": "0200000",
        "invoice_type_param": "debit_note",
        "use_case": "B2C additional charges — requires billing_reference_id to original invoice",
        "vat_categories": ["Standard rate (15%)", "Zero-rated", "Exempt"],
    },
]


@mcp.resource("zatca://invoice-types")
def get_invoice_types() -> str:
    """ZATCA invoice types with type codes, subtypes, and usage guidance.

    Returns the 6 supported invoice types: standard, simplified,
    credit note (standard/simplified), and debit note (standard/simplified).
    Each includes the UBL type code, ZATCA subtype, applicable VAT categories,
    and when to use it.
    """
    return json.dumps(INVOICE_TYPES, indent=2)


# ═══════════════════════════════════════════════════
# RESOURCE 3: Sample Invoice
# ═══════════════════════════════════════════════════


@mcp.resource("zatca://sample-invoice")
def get_sample_invoice() -> str:
    """A complete sample ZATCA-compliant UBL 2.1 XML invoice.

    Returns a realistic simplified (B2C) invoice with two line items,
    generated via the same build_invoice_xml() function used by the
    generate_invoice tool. Useful as a reference for XML structure.
    """
    return build_invoice_xml(
        invoice_type="simplified",
        invoice_number="SAMPLE-2024-001",
        issue_date="2024-01-15",
        seller_name="Acme Trading LLC",
        seller_vat="300000000000003",
        seller_address="456 King Fahd Road",
        seller_city="Riyadh",
        buyer_name="Walk-in Customer",
        line_items=[
            {"name": "Consulting Services", "quantity": 10, "unit_price": 500.00, "vat_rate": 0.15},
            {"name": "Setup Fee", "quantity": 1, "unit_price": 1000.00, "vat_rate": 0.15},
        ],
        currency="SAR",
        note="Sample invoice for reference",
    )


# ═══════════════════════════════════════════════════
# PROMPT 1: Create Invoice
# ═══════════════════════════════════════════════════


@mcp.prompt()
def create_invoice() -> list[dict[str, str]]:
    """Guided workflow for creating a ZATCA-compliant invoice step by step.

    Walks through gathering seller details, buyer details, and line items,
    then calls generate_invoice to produce the XML.
    """
    return [
        {
            "role": "system",
            "content": (
                "You are a ZATCA e-invoicing assistant. Help the user create a "
                "ZATCA-compliant invoice by gathering the required information step by step. "
                "Use the generate_invoice tool to produce the final XML.\n\n"
                "Required information:\n"
                "1. Invoice type: standard (B2B) or simplified (B2C)\n"
                "2. Seller: name, VAT number (15 digits), address, city\n"
                "3. Buyer: name (and VAT number if B2B)\n"
                "4. Line items: name, quantity, unit price, VAT rate (default 15%)\n"
                "5. Invoice number and date\n\n"
                "Ask for each piece of information conversationally. "
                "Validate the VAT number format (15 digits, starts and ends with 3) "
                "before proceeding. When all data is collected, call generate_invoice."
            ),
        },
        {
            "role": "user",
            "content": (
                "I need to create a new ZATCA-compliant invoice. "
                "Please guide me through the process."
            ),
        },
    ]


# ═══════════════════════════════════════════════════
# PROMPT 2: Validate Invoice
# ═══════════════════════════════════════════════════


@mcp.prompt()
def validate_existing_invoice(invoice_xml: str) -> list[dict[str, str]]:
    """Validate a ZATCA invoice XML and explain the results clearly.

    Accepts the invoice XML as an argument, runs validation, and provides
    a human-friendly explanation of any errors or warnings.
    """
    return [
        {
            "role": "system",
            "content": (
                "You are a ZATCA compliance expert. The user has provided an invoice XML "
                "to validate. Use the validate_invoice tool to check it against all 16 "
                "business rules (BR-01 through BR-16).\n\n"
                "After validation:\n"
                "- If valid: confirm compliance and highlight any warnings\n"
                "- If invalid: list each error with its rule ID, explain what's wrong, "
                "and suggest how to fix it\n"
                "- Always mention the total number of checks run"
            ),
        },
        {
            "role": "user",
            "content": f"Please validate this ZATCA invoice XML:\n\n```xml\n{invoice_xml}\n```",
        },
    ]


# ═══════════════════════════════════════════════════
# PROMPT 3: Credit Note
# ═══════════════════════════════════════════════════


@mcp.prompt()
def credit_note() -> list[dict[str, str]]:
    """Guided workflow for creating a credit or debit note.

    Walks through gathering the original invoice reference, reason for
    the note, and items to credit/debit, then calls generate_invoice
    with the appropriate type and billing reference.
    """
    return [
        {
            "role": "system",
            "content": (
                "You are a ZATCA e-invoicing assistant helping create a credit or debit note. "
                "Credit notes (type code 381) are for refunds/returns. "
                "Debit notes (type code 383) are for additional charges.\n\n"
                "Gather the following step by step:\n"
                "1. Credit note or debit note?\n"
                "2. Original invoice ID (billing_reference_id) and date\n"
                "3. Reason for the note (instruction_note)\n"
                "4. Seller details: name, VAT number, address, city\n"
                "5. Buyer details: name (and VAT if B2B)\n"
                "6. Line items to credit/debit: name, quantity, unit price\n\n"
                "When all data is collected, call generate_invoice with "
                "invoice_type='credit_note' or 'debit_note', including the "
                "billing_reference_id, billing_reference_date, and instruction_note."
            ),
        },
        {
            "role": "user",
            "content": (
                "I need to create a credit or debit note for an existing invoice. "
                "Please guide me through the process."
            ),
        },
    ]


def main():
    """Entry point for the ZATCA MCP server."""
    mcp.run()


if __name__ == "__main__":
    main()
