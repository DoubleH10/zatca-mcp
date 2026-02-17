#!/usr/bin/env python3
"""
Fikra CLI — Claude Code-style ZATCA Invoice Agent.

A polished CLI chatbot powered by Claude that uses ZATCA MCP tools to generate
compliant Saudi e-invoices from natural conversation, with professional HTML
invoice output and embedded QR codes.

Usage:
    export ANTHROPIC_API_KEY="sk-ant-..."
    python examples/fikrah_agent.py
"""

import anthropic
import json
import sys
import os
import io
import base64
import webbrowser
from pathlib import Path
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP

from rich.console import Console
from rich.theme import Theme
from lxml import etree
import qrcode

# Add project root to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from zatca_mcp.utils.tlv import encode_tlv, decode_tlv_named
from zatca_mcp.utils.xml_builder import build_invoice_xml
from zatca_mcp.utils.validation import validate_invoice_xml, validate_vat_number

# ═══════════════════════════════════════════════════
# Theme & Console
# ═══════════════════════════════════════════════════

FIKRA_THEME = Theme({
    "fikra.brand": "bold #c8e64a",
    "fikra.accent": "#c8e64a",
    "fikra.dim": "#6b7c6e",
    "fikra.tool": "dim",
    "fikra.error": "bold red",
    "fikra.warn": "bold yellow",
    "fikra.success": "bold #c8e64a",
})

console = Console(theme=FIKRA_THEME)

# UBL 2.1 namespaces for XML parsing
NS = {
    "ubl": "urn:oasis:names:specification:ubl:schema:xsd:Invoice-2",
    "cac": "urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2",
    "cbc": "urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2",
}


# ═══════════════════════════════════════════════════
# Tool Definitions (Claude API format)
# ═══════════════════════════════════════════════════

TOOLS = [
    {
        "name": "generate_qr_code",
        "description": (
            "Generate a ZATCA-compliant TLV-encoded QR code. "
            "Creates a Base64 QR payload for Saudi e-invoices."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "seller_name": {
                    "type": "string",
                    "description": "Business name",
                },
                "vat_number": {
                    "type": "string",
                    "description": "15-digit Saudi VAT number (starts/ends with 3)",
                },
                "timestamp": {
                    "type": "string",
                    "description": "ISO 8601 datetime (e.g., 2024-01-15T10:30:00Z)",
                },
                "total_amount": {
                    "type": "string",
                    "description": "Total including VAT (e.g., '5750.00')",
                },
                "vat_amount": {
                    "type": "string",
                    "description": "VAT amount (e.g., '750.00')",
                },
            },
            "required": [
                "seller_name",
                "vat_number",
                "timestamp",
                "total_amount",
                "vat_amount",
            ],
        },
    },
    {
        "name": "generate_invoice",
        "description": (
            "Generate a ZATCA-compliant UBL 2.1 XML e-invoice. "
            "Supports standard (B2B) and simplified (B2C) types. "
            "Automatically calculates VAT and embeds QR code."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "invoice_type": {
                    "type": "string",
                    "enum": ["standard", "simplified"],
                    "description": "'standard' for B2B (requires buyer VAT) or 'simplified' for B2C",
                },
                "invoice_number": {
                    "type": "string",
                    "description": "Unique invoice ID (e.g., INV-2024-001)",
                },
                "issue_date": {
                    "type": "string",
                    "description": "Date in YYYY-MM-DD format",
                },
                "seller_name": {"type": "string"},
                "seller_vat": {
                    "type": "string",
                    "description": "Seller 15-digit VAT number",
                },
                "seller_address": {"type": "string"},
                "seller_city": {"type": "string"},
                "buyer_name": {"type": "string"},
                "buyer_vat": {
                    "type": "string",
                    "description": "Buyer VAT (required for standard invoices)",
                },
                "buyer_address": {"type": "string", "default": ""},
                "buyer_city": {"type": "string", "default": ""},
                "items": {
                    "type": "string",
                    "description": 'JSON array: [{"name": "...", "quantity": 1, "unit_price": 100.00}]',
                },
                "currency": {"type": "string", "default": "SAR"},
                "note": {"type": "string"},
            },
            "required": [
                "invoice_type",
                "invoice_number",
                "issue_date",
                "seller_name",
                "seller_vat",
                "seller_address",
                "seller_city",
                "buyer_name",
                "items",
            ],
        },
    },
    {
        "name": "validate_invoice",
        "description": (
            "Validate an invoice XML against ZATCA business rules. "
            "Checks required fields, VAT calculations, and structure."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "invoice_xml": {
                    "type": "string",
                    "description": "UBL 2.1 XML invoice to validate",
                },
            },
            "required": ["invoice_xml"],
        },
    },
    {
        "name": "decode_qr",
        "description": "Decode a ZATCA TLV-encoded QR code to inspect its contents.",
        "input_schema": {
            "type": "object",
            "properties": {
                "qr_base64": {
                    "type": "string",
                    "description": "Base64-encoded TLV QR string",
                },
            },
            "required": ["qr_base64"],
        },
    },
    {
        "name": "generate_csr",
        "description": (
            "Generate a ZATCA-compliant Certificate Signing Request (CSR). "
            "Creates an ECDSA key pair and CSR for ZATCA onboarding."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "common_name": {"type": "string", "description": "Certificate CN"},
                "organization": {"type": "string", "description": "Organization name"},
                "organizational_unit": {"type": "string", "description": "Department/unit"},
                "country": {"type": "string", "default": "SA"},
                "serial_number": {
                    "type": "string",
                    "description": "ZATCA device serial",
                    "default": "1-TST|2-TST|3-ed22f1d8-e6a2-1118-9b58-d9a8195e2f28",
                },
                "invoice_type": {"type": "string", "default": "1100"},
                "location": {"type": "string", "default": "Riyadh"},
                "industry": {"type": "string", "default": "IT"},
            },
            "required": ["common_name", "organization", "organizational_unit"],
        },
    },
    {
        "name": "sign_invoice",
        "description": (
            "Digitally sign a ZATCA invoice with XAdES-BES. "
            "Injects signature into UBLExtensions and rebuilds QR with Phase 2 tags."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "invoice_xml": {"type": "string", "description": "Unsigned invoice XML"},
                "certificate_pem": {"type": "string", "description": "PEM X.509 cert"},
                "private_key_pem": {"type": "string", "description": "PEM private key"},
            },
            "required": ["invoice_xml", "certificate_pem", "private_key_pem"],
        },
    },
    {
        "name": "submit_invoice",
        "description": (
            "Submit a signed invoice to ZATCA for reporting or clearance."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "signed_invoice_xml": {"type": "string"},
                "invoice_hash": {"type": "string"},
                "invoice_uuid": {"type": "string"},
                "certificate": {"type": "string", "description": "Base64 cert"},
                "secret": {"type": "string", "description": "API secret"},
                "mode": {
                    "type": "string",
                    "enum": ["reporting", "clearance"],
                    "default": "reporting",
                },
                "environment": {
                    "type": "string",
                    "enum": ["sandbox", "production"],
                    "default": "sandbox",
                },
            },
            "required": [
                "signed_invoice_xml",
                "invoice_hash",
                "invoice_uuid",
                "certificate",
                "secret",
            ],
        },
    },
    {
        "name": "check_compliance",
        "description": "Check a signed invoice against ZATCA compliance rules.",
        "input_schema": {
            "type": "object",
            "properties": {
                "signed_invoice_xml": {"type": "string"},
                "invoice_hash": {"type": "string"},
                "invoice_uuid": {"type": "string"},
                "certificate": {"type": "string"},
                "secret": {"type": "string"},
                "environment": {
                    "type": "string",
                    "enum": ["sandbox", "production"],
                    "default": "sandbox",
                },
            },
            "required": [
                "signed_invoice_xml",
                "invoice_hash",
                "invoice_uuid",
                "certificate",
                "secret",
            ],
        },
    },
]


# ═══════════════════════════════════════════════════
# XML → HTML Invoice Pipeline
# ═══════════════════════════════════════════════════

def _xpath_text(root, xpath):
    """Extract text from first matching XPath element."""
    result = root.xpath(xpath, namespaces=NS)
    if result and hasattr(result[0], "text"):
        return result[0].text
    return None


def parse_invoice_xml(xml_string: str) -> dict:
    """Parse a UBL 2.1 XML invoice into a structured dict for HTML rendering."""
    root = etree.fromstring(xml_string.encode("utf-8"))

    # Invoice metadata
    invoice_number = _xpath_text(root, "//cbc:ID") or ""
    uuid_val = _xpath_text(root, "//cbc:UUID") or ""
    issue_date = _xpath_text(root, "//cbc:IssueDate") or ""
    issue_time = _xpath_text(root, "//cbc:IssueTime") or ""
    currency = _xpath_text(root, "//cbc:DocumentCurrencyCode") or "SAR"
    note = _xpath_text(root, "//cbc:Note") or ""

    # Invoice type
    type_code_el = root.xpath("//cbc:InvoiceTypeCode", namespaces=NS)
    invoice_type_name = "Tax Invoice"
    if type_code_el:
        subtype = type_code_el[0].get("name", "")
        if subtype.startswith("02"):
            invoice_type_name = "Simplified Tax Invoice"

    # Seller
    seller_name = _xpath_text(
        root,
        "//cac:AccountingSupplierParty/cac:Party/cac:PartyLegalEntity/cbc:RegistrationName",
    ) or ""
    seller_vat = _xpath_text(
        root,
        "//cac:AccountingSupplierParty/cac:Party/cac:PartyTaxScheme/cbc:CompanyID",
    ) or ""
    seller_address = _xpath_text(
        root,
        "//cac:AccountingSupplierParty/cac:Party/cac:PostalAddress/cbc:StreetName",
    ) or ""
    seller_city = _xpath_text(
        root,
        "//cac:AccountingSupplierParty/cac:Party/cac:PostalAddress/cbc:CityName",
    ) or ""

    # Buyer
    buyer_name = _xpath_text(
        root,
        "//cac:AccountingCustomerParty/cac:Party/cac:PartyLegalEntity/cbc:RegistrationName",
    ) or ""
    buyer_vat = _xpath_text(
        root,
        "//cac:AccountingCustomerParty/cac:Party/cac:PartyTaxScheme/cbc:CompanyID",
    ) or ""
    buyer_address = _xpath_text(
        root,
        "//cac:AccountingCustomerParty/cac:Party/cac:PostalAddress/cbc:StreetName",
    ) or ""
    buyer_city = _xpath_text(
        root,
        "//cac:AccountingCustomerParty/cac:Party/cac:PostalAddress/cbc:CityName",
    ) or ""

    # Totals
    subtotal = _xpath_text(root, "//cac:LegalMonetaryTotal/cbc:TaxExclusiveAmount") or "0.00"
    total_vat = _xpath_text(root, "//cac:TaxTotal/cbc:TaxAmount") or "0.00"
    grand_total = _xpath_text(root, "//cac:LegalMonetaryTotal/cbc:TaxInclusiveAmount") or "0.00"

    # QR data
    qr_data = ""
    qr_els = root.xpath(
        "//cac:AdditionalDocumentReference[cbc:ID='QR']/cac:Attachment/cbc:EmbeddedDocumentBinaryObject",
        namespaces=NS,
    )
    if qr_els and qr_els[0].text:
        qr_data = qr_els[0].text

    # Line items
    items = []
    for line in root.xpath("//cac:InvoiceLine", namespaces=NS):
        line_id = _xpath_text(line, "cbc:ID") or ""
        name = _xpath_text(line, "cac:Item/cbc:Name") or ""
        qty = _xpath_text(line, "cbc:InvoicedQuantity") or "0"
        unit_price = _xpath_text(line, "cac:Price/cbc:PriceAmount") or "0.00"
        line_ext = _xpath_text(line, "cbc:LineExtensionAmount") or "0.00"
        line_vat = _xpath_text(line, "cac:TaxTotal/cbc:TaxAmount") or "0.00"
        vat_pct = _xpath_text(line, "cac:Item/cac:ClassifiedTaxCategory/cbc:Percent") or "15"
        line_total_val = Decimal(line_ext) + Decimal(line_vat)
        items.append({
            "id": line_id,
            "name": name,
            "quantity": qty,
            "unit_price": unit_price,
            "vat_percent": vat_pct,
            "vat_amount": line_vat,
            "line_total": str(line_total_val.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)),
        })

    return {
        "invoice_number": invoice_number,
        "uuid": uuid_val,
        "issue_date": issue_date,
        "issue_time": issue_time,
        "invoice_type": invoice_type_name,
        "currency": currency,
        "note": note,
        "seller_name": seller_name,
        "seller_vat": seller_vat,
        "seller_address": seller_address,
        "seller_city": seller_city,
        "buyer_name": buyer_name,
        "buyer_vat": buyer_vat,
        "buyer_address": buyer_address,
        "buyer_city": buyer_city,
        "subtotal": subtotal,
        "total_vat": total_vat,
        "grand_total": grand_total,
        "qr_data": qr_data,
        "items": items,
    }


def generate_qr_image_base64(tlv_base64: str) -> str:
    """Generate a QR code PNG image from TLV base64 data, returned as a data URI."""
    qr = qrcode.QRCode(version=None, error_correction=qrcode.constants.ERROR_CORRECT_M, box_size=6, border=2)
    qr.add_data(tlv_base64)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    b64 = base64.b64encode(buf.getvalue()).decode("ascii")
    return f"data:image/png;base64,{b64}"


HTML_TEMPLATE = """\
<!DOCTYPE html>
<html lang="en" dir="ltr">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Invoice {invoice_number}</title>
<style>
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
    color: #1a1a1a;
    background: #f5f5f5;
    padding: 24px;
    line-height: 1.5;
  }}
  .invoice {{
    max-width: 820px;
    margin: 0 auto;
    background: #fff;
    border-radius: 12px;
    box-shadow: 0 2px 12px rgba(0,0,0,0.08);
    overflow: hidden;
  }}
  .header {{
    background: linear-gradient(135deg, #2d3a2e 0%, #3a4a3d 100%);
    color: #fff;
    padding: 32px 40px;
    display: flex;
    justify-content: space-between;
    align-items: flex-start;
  }}
  .header-left h1 {{
    font-size: 28px;
    font-weight: 700;
    margin-bottom: 4px;
  }}
  .header-left .type-badge {{
    display: inline-block;
    background: rgba(255,255,255,0.2);
    padding: 2px 10px;
    border-radius: 4px;
    font-size: 12px;
    margin-top: 4px;
  }}
  .header-right {{
    text-align: right;
    font-size: 14px;
  }}
  .header-right .inv-number {{
    font-size: 22px;
    font-weight: 700;
  }}
  .body {{ padding: 32px 40px; }}
  .parties {{
    display: flex;
    gap: 40px;
    margin-bottom: 32px;
  }}
  .party {{
    flex: 1;
    background: #f9fafb;
    border-radius: 8px;
    padding: 20px;
  }}
  .party h3 {{
    font-size: 11px;
    text-transform: uppercase;
    letter-spacing: 1px;
    color: #2d3a2e;
    margin-bottom: 10px;
    font-weight: 600;
  }}
  .party .name {{ font-size: 16px; font-weight: 600; margin-bottom: 4px; }}
  .party .detail {{ font-size: 13px; color: #555; }}
  table {{
    width: 100%;
    border-collapse: collapse;
    margin-bottom: 24px;
    font-size: 14px;
  }}
  thead th {{
    background: #c8e64a;
    color: #2d3a2e;
    font-weight: 600;
    text-align: left;
    padding: 10px 12px;
    border-bottom: 2px solid #c8e64a;
    font-size: 12px;
    text-transform: uppercase;
    letter-spacing: 0.5px;
  }}
  thead th:nth-child(n+3) {{ text-align: right; }}
  tbody td {{
    padding: 10px 12px;
    border-bottom: 1px solid #eee;
  }}
  tbody td:nth-child(n+3) {{ text-align: right; }}
  tbody tr:hover {{ background: #fafafa; }}
  .totals {{
    display: flex;
    justify-content: flex-end;
    margin-bottom: 32px;
  }}
  .totals-table {{
    width: 280px;
  }}
  .totals-table .row {{
    display: flex;
    justify-content: space-between;
    padding: 6px 0;
    font-size: 14px;
    color: #555;
  }}
  .totals-table .row.grand {{
    border-top: 2px solid #c8e64a;
    margin-top: 6px;
    padding-top: 10px;
    font-size: 18px;
    font-weight: 700;
    color: #2d3a2e;
  }}
  .footer {{
    border-top: 1px solid #eee;
    padding: 24px 40px;
    display: flex;
    justify-content: space-between;
    align-items: flex-end;
    gap: 24px;
  }}
  .footer-left {{
    flex: 1;
  }}
  .zatca-badge {{
    display: inline-flex;
    align-items: center;
    gap: 6px;
    background: #c8e64a;
    border: 1px solid #b5d043;
    color: #2d3a2e;
    padding: 6px 14px;
    border-radius: 6px;
    font-size: 12px;
    font-weight: 600;
    margin-bottom: 8px;
  }}
  .uuid {{
    font-size: 11px;
    color: #999;
    word-break: break-all;
    font-family: "SF Mono", "Fira Code", monospace;
  }}
  .note {{
    font-size: 13px;
    color: #666;
    margin-top: 8px;
    font-style: italic;
  }}
  .qr-code img {{
    width: 120px;
    height: 120px;
    border: 1px solid #eee;
    border-radius: 6px;
  }}
  @media print {{
    body {{ background: #fff; padding: 0; }}
    .invoice {{ box-shadow: none; border-radius: 0; }}
    .header {{ -webkit-print-color-adjust: exact; print-color-adjust: exact; }}
  }}
</style>
</head>
<body>
<div class="invoice">
  <div class="header">
    <div class="header-left">
      <h1>{seller_name}</h1>
      <div class="type-badge">{invoice_type}</div>
    </div>
    <div class="header-right">
      <div class="inv-number">{invoice_number}</div>
      <div>{issue_date} &middot; {issue_time}</div>
      <div>{currency}</div>
    </div>
  </div>
  <div class="body">
    <div class="parties">
      <div class="party">
        <h3>From (Seller)</h3>
        <div class="name">{seller_name}</div>
        <div class="detail">VAT: {seller_vat}</div>
        <div class="detail">{seller_address}</div>
        <div class="detail">{seller_city}</div>
      </div>
      <div class="party">
        <h3>To (Buyer)</h3>
        <div class="name">{buyer_name}</div>
        <div class="detail">{buyer_vat_line}</div>
        <div class="detail">{buyer_address}</div>
        <div class="detail">{buyer_city}</div>
      </div>
    </div>
    <table>
      <thead>
        <tr>
          <th>#</th>
          <th>Description</th>
          <th>Qty</th>
          <th>Unit Price</th>
          <th>VAT %</th>
          <th>VAT</th>
          <th>Total</th>
        </tr>
      </thead>
      <tbody>
        {items_rows}
      </tbody>
    </table>
    <div class="totals">
      <div class="totals-table">
        <div class="row"><span>Subtotal</span><span>{subtotal} {currency}</span></div>
        <div class="row"><span>VAT</span><span>{total_vat} {currency}</span></div>
        <div class="row grand"><span>Grand Total</span><span>{grand_total} {currency}</span></div>
      </div>
    </div>
  </div>
  <div class="footer">
    <div class="footer-left">
      <div class="zatca-badge">ZATCA Compliant E-Invoice</div>
      <div class="uuid">UUID: {uuid}</div>
      {note_html}
    </div>
    <div class="qr-code">
      <img src="{qr_image_uri}" alt="ZATCA QR Code">
    </div>
  </div>
</div>
</body>
</html>
"""


def generate_html_invoice(xml_string: str) -> str:
    """Generate a professional HTML invoice from UBL 2.1 XML."""
    data = parse_invoice_xml(xml_string)

    # Build line item rows
    rows = []
    for item in data["items"]:
        rows.append(
            f'        <tr><td>{item["id"]}</td><td>{item["name"]}</td>'
            f'<td>{item["quantity"]}</td><td>{item["unit_price"]}</td>'
            f'<td>{item["vat_percent"]}%</td><td>{item["vat_amount"]}</td>'
            f'<td>{item["line_total"]}</td></tr>'
        )

    # QR image
    qr_image_uri = ""
    if data["qr_data"]:
        qr_image_uri = generate_qr_image_base64(data["qr_data"])

    # Buyer VAT line
    buyer_vat_line = f"VAT: {data['buyer_vat']}" if data["buyer_vat"] else ""

    # Note
    note_html = f'<div class="note">{data["note"]}</div>' if data["note"] else ""

    return HTML_TEMPLATE.format(
        invoice_number=data["invoice_number"],
        invoice_type=data["invoice_type"],
        issue_date=data["issue_date"],
        issue_time=data["issue_time"],
        currency=data["currency"],
        seller_name=data["seller_name"],
        seller_vat=data["seller_vat"],
        seller_address=data["seller_address"],
        seller_city=data["seller_city"],
        buyer_name=data["buyer_name"],
        buyer_vat_line=buyer_vat_line,
        buyer_address=data["buyer_address"],
        buyer_city=data["buyer_city"],
        items_rows="\n".join(rows),
        subtotal=data["subtotal"],
        total_vat=data["total_vat"],
        grand_total=data["grand_total"],
        uuid=data["uuid"],
        note_html=note_html,
        qr_image_uri=qr_image_uri,
    )


def save_and_open_invoice(html: str, invoice_number: str) -> str:
    """Save HTML invoice to file and open in browser. Returns absolute path."""
    invoices_dir = Path(__file__).parent / "invoices"
    invoices_dir.mkdir(exist_ok=True)

    safe_name = invoice_number.replace("/", "-").replace(" ", "_")
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{safe_name}_{timestamp}.html"
    filepath = invoices_dir / filename

    filepath.write_text(html, encoding="utf-8")
    webbrowser.open(filepath.as_uri())

    return str(filepath.resolve())


# ═══════════════════════════════════════════════════
# Tool Execution
# ═══════════════════════════════════════════════════


def execute_tool(name: str, args: dict) -> str:
    """Execute a ZATCA tool and return the result."""
    try:
        if name == "generate_qr_code":
            vat_errors = validate_vat_number(args["vat_number"])
            if vat_errors:
                return json.dumps({"error": "Invalid VAT", "details": vat_errors})
            qr = encode_tlv(
                seller_name=args["seller_name"],
                vat_number=args["vat_number"],
                timestamp=args["timestamp"],
                total_amount=args["total_amount"],
                vat_amount=args["vat_amount"],
            )
            decoded = decode_tlv_named(qr)
            return json.dumps(
                {"qr_base64": qr, "decoded": decoded},
                indent=2,
                ensure_ascii=False,
            )

        elif name == "generate_invoice":
            items = json.loads(args["items"])

            # Generate QR
            total_taxable = sum(
                Decimal(str(i["quantity"])) * Decimal(str(i["unit_price"]))
                for i in items
            )
            total_vat = sum(
                (Decimal(str(i["quantity"])) * Decimal(str(i["unit_price"])))
                * Decimal(str(i.get("vat_rate", "0.15")))
                for i in items
            )
            total = (total_taxable + total_vat).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP
            )
            vat_rounded = total_vat.quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP
            )

            ts = f"{args['issue_date']}T{datetime.now(timezone.utc).strftime('%H:%M:%S')}Z"
            qr = encode_tlv(
                seller_name=args["seller_name"],
                vat_number=args["seller_vat"],
                timestamp=ts,
                total_amount=str(total),
                vat_amount=str(vat_rounded),
            )

            xml = build_invoice_xml(
                invoice_type=args["invoice_type"],
                invoice_number=args["invoice_number"],
                issue_date=args["issue_date"],
                seller_name=args["seller_name"],
                seller_vat=args["seller_vat"],
                seller_address=args["seller_address"],
                seller_city=args["seller_city"],
                buyer_name=args["buyer_name"],
                buyer_vat=args.get("buyer_vat"),
                buyer_address=args.get("buyer_address", ""),
                buyer_city=args.get("buyer_city", ""),
                line_items=items,
                currency=args.get("currency", "SAR"),
                note=args.get("note"),
                qr_data=qr,
            )

            # Generate HTML invoice as side-effect
            try:
                html = generate_html_invoice(xml)
                filepath = save_and_open_invoice(html, args["invoice_number"])
                console.print(f"\n  [fikra.success]✓ Invoice saved & opened in browser[/]")
                console.print(f"  [fikra.dim]{filepath}[/]")
            except Exception as e:
                console.print(f"  [fikra.warn]Warning: HTML invoice generation failed: {e}[/]")

            return xml

        elif name == "validate_invoice":
            result = validate_invoice_xml(args["invoice_xml"])
            return json.dumps(result, indent=2)

        elif name == "decode_qr":
            decoded = decode_tlv_named(args["qr_base64"])
            return json.dumps(decoded, indent=2, ensure_ascii=False)

        elif name == "generate_csr":
            try:
                from zatca_mcp.utils.signing import (
                    generate_private_key,
                    serialize_private_key,
                    generate_csr as _gen_csr,
                )
            except ImportError:
                return json.dumps({
                    "error": "Phase 2 deps not installed",
                    "fix": "pip install zatca-mcp[phase2]",
                })
            key = generate_private_key()
            csr_pem = _gen_csr(
                key=key,
                common_name=args["common_name"],
                organization=args["organization"],
                organizational_unit=args["organizational_unit"],
                country=args.get("country", "SA"),
                serial_number=args.get(
                    "serial_number",
                    "1-TST|2-TST|3-ed22f1d8-e6a2-1118-9b58-d9a8195e2f28",
                ),
                invoice_type=args.get("invoice_type", "1100"),
                location=args.get("location", "Riyadh"),
                industry=args.get("industry", "IT"),
            )
            pk_pem = serialize_private_key(key)
            return json.dumps({
                "csr_pem": csr_pem.decode("utf-8"),
                "private_key_pem": pk_pem.decode("utf-8"),
                "warning": "Store the private key securely.",
                "next_step": "Submit CSR to ZATCA to get compliance certificate",
            }, indent=2)

        elif name == "sign_invoice":
            try:
                from zatca_mcp.utils.signing import (
                    inject_signature,
                    hash_invoice,
                    load_private_key,
                )
            except ImportError:
                return json.dumps({
                    "error": "Phase 2 deps not installed",
                    "fix": "pip install zatca-mcp[phase2]",
                })
            key = load_private_key(args["private_key_pem"].encode("utf-8"))
            xml_bytes = args["invoice_xml"].encode("utf-8")
            inv_hash = hash_invoice(xml_bytes)
            signed = inject_signature(xml_bytes, args["certificate_pem"], key)
            return json.dumps({
                "signed_xml": signed.decode("utf-8"),
                "invoice_hash": inv_hash,
                "is_phase2_compliant": True,
            }, indent=2, ensure_ascii=False)

        elif name == "submit_invoice":
            return json.dumps({
                "error": "submit_invoice requires async ZATCA API. Use the MCP server.",
                "hint": "Run zatca-mcp server and call submit_invoice through MCP.",
            })

        elif name == "check_compliance":
            return json.dumps({
                "error": "check_compliance requires async ZATCA API. Use the MCP server.",
                "hint": "Run zatca-mcp server and call check_compliance through MCP.",
            })

        else:
            return json.dumps({"error": f"Unknown tool: {name}"})

    except Exception as e:
        return json.dumps({"error": str(e)})


# ═══════════════════════════════════════════════════
# System Prompt
# ═══════════════════════════════════════════════════

SYSTEM_PROMPT = """You are Fikrah, an AI financial operations assistant specialized in Saudi Arabian e-invoicing compliance.

Your role is to help businesses create ZATCA-compliant electronic invoices through natural conversation. When a user tells you about a deal, sale, or transaction, you should:

1. GATHER the necessary information conversationally:
   - Ask for missing details one or two at a time, not all at once
   - Be smart about defaults (currency is SAR, country is SA, today's date)
   - Infer what you can (e.g., simplified invoice for consumers, standard for businesses)

2. REQUIRED information for an invoice:
   - Invoice type: standard (B2B, needs buyer VAT), simplified (B2C), credit_note, or debit_note
   - Seller details: name, VAT number, address, city
   - Buyer details: name (+ VAT for B2B)
   - Line items: what was sold, quantity, unit price
   - Issue date (default to today)
   - For credit/debit notes: original invoice ID, reason

3. GENERATE the invoice using your tools:
   - First generate the invoice XML
   - Then validate it
   - Show a human-readable summary of the invoice
   - Mention the QR code was embedded

4. PHASE 2 WORKFLOW (Digital Signing & ZATCA Integration):
   When the user needs ZATCA Phase 2 compliance:
   a. generate_csr → Create CSR and private key for ZATCA onboarding
   b. Submit CSR to ZATCA portal to get compliance certificate
   c. sign_invoice → Digitally sign the invoice with XAdES-BES
   d. submit_invoice → Send to ZATCA for reporting/clearance
   e. check_compliance → Validate against ZATCA's server-side rules

5. COMMUNICATION STYLE:
   - Be conversational and efficient — no jargon dumps
   - Ask focused questions, not a checklist
   - Confirm details before generating
   - Show excitement about closing deals!
   - Use Arabic business terms naturally if the user does

6. IMPORTANT:
   - VAT rate in Saudi is 15% (standard)
   - VAT numbers are 15 digits, start and end with 3
   - Always validate after generating
   - If validation fails, fix and regenerate

7. HTML INVOICE:
   - When you generate an invoice XML, a professional HTML invoice is automatically created and opened in the user's browser with a QR code image
   - Mention this to the user so they know a visual invoice was generated

You have access to these ZATCA tools:
- generate_invoice: Create UBL 2.1 XML invoices (standard, simplified, credit_note, debit_note)
- generate_qr_code: Create TLV QR codes
- validate_invoice: Check compliance (16 business rules)
- decode_qr: Inspect QR code data
- generate_csr: Create CSR for ZATCA onboarding (Phase 2)
- sign_invoice: XAdES-BES digital signing (Phase 2)
- submit_invoice: Report/clear invoices with ZATCA API (Phase 2)
- check_compliance: Server-side ZATCA validation (Phase 2)

Today's date is: """ + datetime.now(timezone.utc).strftime("%Y-%m-%d")


# ═══════════════════════════════════════════════════
# Chat Loop
# ═══════════════════════════════════════════════════


BANNER = """\
[#c8e64a]     ◇[/]
[#b0e14d]    ◇◆◇[/]
[#99dd50]     ◇       ███████╗██╗██╗  ██╗██████╗  █████╗ ██╗  ██╗[/]
[#81d853]    ╱ ╲      ██╔════╝██║██║ ██╔╝██╔══██╗██╔══██╗██║  ██║[/]
[#69d356]   ╱   ╲     █████╗  ██║█████╔╝ ██████╔╝███████║███████║[/]
[#52cf58]   ╰───╯     ██╔══╝  ██║██╔═██╗ ██╔══██╗██╔══██║██╔══██║[/]
[#3aca5b]              ██║     ██║██║  ██╗██║  ██║██║  ██║██║  ██║[/]
[#22c55e]              ╚═╝     ╚═╝╚═╝  ╚═╝╚═╝  ╚═╝╚═╝  ╚═╝╚═╝  ╚═╝[/]
"""

MODEL_NAME = os.environ.get("FIKRAH_MODEL", "claude-sonnet-4-20250514")


def _check_phase2():
    """Check if Phase 2 dependencies are available."""
    try:
        import cryptography  # noqa: F401
        import httpx  # noqa: F401
        import pydantic  # noqa: F401
        return True
    except ImportError:
        return False


def print_banner():
    """Display the Fikra CLI welcome banner."""
    console.print(BANNER)
    phase2_available = _check_phase2()
    phase_str = "[fikra.success]Phase 2 ✓[/]" if phase2_available else "[fikra.dim]Phase 1 only[/]"
    console.print(
        f"  [fikra.dim]Model: {MODEL_NAME}  |  Tools: {len(TOOLS)} ZATCA tools"
        f"  |  {phase_str}  |  cwd: {os.getcwd()}[/]"
    )
    console.print()
    console.print(
        '  [fikra.dim]Tips: "I sold 10 laptops at 3000 SAR each to TechCo" to get started[/]'
    )
    console.print(
        "  [fikra.dim]      /help for commands, /quit to exit[/]"
    )


def _stream_response(client, messages):
    """Stream a Claude response, printing text in real-time. Returns the final Message or None on error."""
    try:
        with client.messages.stream(
            model=MODEL_NAME,
            max_tokens=4096,
            system=SYSTEM_PROMPT,
            tools=TOOLS,
            messages=messages,
        ) as stream:
            console.print()
            streamed_any_text = False
            for chunk in stream.text_stream:
                console.file.write(chunk)
                console.file.flush()
                streamed_any_text = True
            if streamed_any_text:
                console.file.write("\n")
                console.file.flush()

            response = stream.get_final_message()

        # Token usage
        if response.usage:
            inp = f"{response.usage.input_tokens:,}"
            out = f"{response.usage.output_tokens:,}"
            console.print(f"\n  [fikra.dim]↳ {inp} input · {out} output tokens[/]")

        return response

    except KeyboardInterrupt:
        console.print("\n[fikra.dim]Cancelled.[/]")
        return None
    except anthropic.APIError as e:
        console.print(f"\n[fikra.error]API Error: {e}[/]")
        return None


def main():
    # Check for API key
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        console.print()
        console.print("  [fikra.error]✗ ANTHROPIC_API_KEY not set[/]")
        console.print("    [dim]export ANTHROPIC_API_KEY='sk-ant-...'[/]")
        console.print()
        sys.exit(1)

    client = anthropic.Anthropic(api_key=api_key)
    messages = []

    print_banner()

    while True:
        # Get user input
        try:
            user_input = console.input("\n[#c8e64a]❯[/] ")
        except (KeyboardInterrupt, EOFError):
            console.print("\n[fikra.dim]Ma'a salama![/]")
            break

        stripped = user_input.strip().lower()

        if stripped in ("quit", "exit", "q", "/quit", "/exit"):
            console.print("[fikra.dim]Ma'a salama![/]")
            break

        if stripped == "/help":
            console.print()
            console.print("  [fikra.brand]Fikra CLI — Commands[/]")
            console.print("  [fikra.dim]─────────────────────────────[/]")
            console.print("  [bold]/help[/]   Show this help message")
            console.print("  [bold]/clear[/]  Clear conversation and screen")
            console.print("  [bold]/quit[/]   Exit Fikra CLI")
            console.print()
            console.print("  [fikra.dim]Examples:[/]")
            console.print('  [dim]"I sold 10 laptops at 3000 SAR each to TechCo"[/]')
            console.print('  [dim]"Generate a simplified invoice for a walk-in customer"[/]')
            console.print('  [dim]"Decode this QR code: AQ..."[/]')
            continue

        if stripped == "/clear":
            messages.clear()
            os.system("clear" if os.name != "nt" else "cls")
            print_banner()
            console.print("\n  [fikra.dim]Conversation cleared.[/]")
            continue

        if not user_input.strip():
            continue

        messages.append({"role": "user", "content": user_input})

        # Stream response from Claude
        response = _stream_response(client, messages)
        if response is None:
            messages.pop()
            continue

        # Handle tool use loop (capped at 10 iterations)
        tool_iterations = 0
        while response.stop_reason == "tool_use" and tool_iterations < 10:
            tool_iterations += 1
            assistant_content = response.content
            messages.append({"role": "assistant", "content": assistant_content})

            # Execute each tool call
            tool_results = []
            for block in assistant_content:
                if block.type == "tool_use":
                    console.print(f"  [dim]⏺ {block.name}[/]")
                    result = execute_tool(block.name, block.input)
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": result,
                    })

            messages.append({"role": "user", "content": tool_results})

            # Continue streaming
            response = _stream_response(client, messages)
            if response is None:
                break

        if response is None:
            continue

        # Record final assistant message
        messages.append({"role": "assistant", "content": response.content})


if __name__ == "__main__":
    main()
