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

from mcp.server.fastmcp import FastMCP
from zatca_mcp.utils.tlv import encode_tlv, decode_tlv_named
from zatca_mcp.utils.xml_builder import build_invoice_xml
from zatca_mcp.utils.validation import validate_invoice_xml, validate_vat_number
import json

# Create the MCP server
mcp = FastMCP(
    "zatca-mcp",
    description=(
        "ZATCA e-invoicing MCP server for Saudi Arabia. "
        "Generate, validate, and manage compliant electronic invoices."
    ),
    version="0.1.0",
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
        items: JSON array of line items. Each item: {"name": "Product", "quantity": 1, "unit_price": 100.00, "vat_rate": 0.15}
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
        return json.dumps(
            {"error": "Buyer VAT number is required for standard (B2B) invoices"}
        )

    # Generate QR code data
    from decimal import Decimal, ROUND_HALF_UP
    total_taxable = sum(
        Decimal(str(i["quantity"])) * Decimal(str(i["unit_price"]))
        for i in line_items
    )
    total_vat = sum(
        (Decimal(str(i["quantity"])) * Decimal(str(i["unit_price"])))
        * Decimal(str(i.get("vat_rate", "0.15")))
        for i in line_items
    )
    total_with_vat = (total_taxable + total_vat).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )
    total_vat_rounded = total_vat.quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )

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
            generate_private_key,
            serialize_private_key,
            generate_csr as _generate_csr,
        )
    except ImportError:
        return json.dumps({
            "error": "Phase 2 dependencies not installed",
            "fix": "pip install zatca-mcp[phase2]",
            "details": "The cryptography package is required for CSR generation",
        })

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

    return json.dumps({
        "csr_pem": csr_pem.decode("utf-8"),
        "private_key_pem": private_key_pem.decode("utf-8"),
        "warning": "Store the private key securely. It cannot be recovered.",
        "next_step": "Submit the CSR to ZATCA to obtain a compliance certificate",
    }, indent=2)


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
            inject_signature,
            hash_invoice,
            load_private_key,
            sign_hash as _sign_hash,
            get_public_key_bytes,
        )
    except ImportError:
        return json.dumps({
            "error": "Phase 2 dependencies not installed",
            "fix": "pip install zatca-mcp[phase2]",
            "details": "The cryptography package is required for invoice signing",
        })

    import base64
    import hashlib

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
        "//cac:AdditionalDocumentReference[cbc:ID='QR']"
        "//cbc:EmbeddedDocumentBinaryObject",
        namespaces=ns,
    )

    qr_base64 = ""
    if qr_els and qr_els[0].text:
        # Decode existing QR, add Phase 2 tags, re-encode
        existing_qr = qr_els[0].text
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
        qr_els[0].text = new_qr
        signed_xml_bytes = etree.tostring(
            root, pretty_print=True, xml_declaration=True, encoding="UTF-8",
        )

    return json.dumps({
        "signed_xml": signed_xml_bytes.decode("utf-8"),
        "invoice_hash": invoice_hash,
        "qr_base64": qr_base64,
        "is_phase2_compliant": True,
    }, indent=2, ensure_ascii=False)


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
        return json.dumps({
            "error": "Phase 2 dependencies not installed",
            "fix": "pip install zatca-mcp[phase2]",
            "details": "httpx and pydantic are required for ZATCA API integration",
        })

    import base64

    client = ZATCAClient(
        certificate=certificate,
        secret=secret,
        environment=environment,
    )

    xml_b64 = base64.b64encode(
        signed_invoice_xml.encode("utf-8")
    ).decode("ascii")

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
        return json.dumps({
            "error": "Phase 2 dependencies not installed",
            "fix": "pip install zatca-mcp[phase2]",
            "details": "httpx and pydantic are required for ZATCA API integration",
        })

    import base64

    client = ZATCAClient(
        certificate=certificate,
        secret=secret,
        environment=environment,
    )

    xml_b64 = base64.b64encode(
        signed_invoice_xml.encode("utf-8")
    ).decode("ascii")

    try:
        result = await client.check_compliance(xml_b64, invoice_hash, invoice_uuid)
        return json.dumps(result.model_dump(), indent=2, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"error": f"ZATCA compliance check failed: {str(e)}"})


def main():
    """Entry point for the ZATCA MCP server."""
    mcp.run()


if __name__ == "__main__":
    main()
