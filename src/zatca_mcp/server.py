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
) -> str:
    """Generate a ZATCA-compliant UBL 2.1 XML e-invoice.

    Creates a complete XML invoice following Saudi Arabia's ZATCA e-invoicing
    standard. Supports both Standard (B2B) and Simplified (B2C) invoice types.
    Automatically calculates VAT, line totals, and embeds QR code data.

    Args:
        invoice_type: "standard" (B2B, requires buyer VAT) or "simplified" (B2C)
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


def main():
    """Entry point for the ZATCA MCP server."""
    mcp.run()


if __name__ == "__main__":
    main()
