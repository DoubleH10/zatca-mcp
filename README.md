# 🇸🇦 ZATCA MCP

**ZATCA e-invoicing MCP server — let AI agents generate Saudi-compliant invoices.**

An open-source [Model Context Protocol](https://modelcontextprotocol.io) (MCP) server that enables AI agents like Claude to generate, validate, and manage ZATCA-compliant electronic invoices for Saudi Arabia.

## What It Does

| Tool | Description |
|------|-------------|
| `generate_invoice` | Create UBL 2.1 XML invoices (standard B2B + simplified B2C) |
| `generate_qr_code` | Generate TLV-encoded QR codes per ZATCA spec |
| `validate_invoice` | Check invoices against 14+ ZATCA business rules |
| `decode_qr` | Inspect and verify existing ZATCA QR codes |

## Quick Start

### Install

```bash
pip install zatca-mcp
```

### Use with Claude Desktop

Add to `~/.claude/claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "zatca": {
      "command": "zatca-mcp"
    }
  }
}
```

Restart Claude Desktop. You can now ask Claude to generate ZATCA-compliant invoices.

### Fikra CLI

Fikra CLI is a Claude Code-style conversational agent that turns natural language into compliant invoices with professional HTML output:

```bash
export ANTHROPIC_API_KEY="sk-ant-..."
git clone https://github.com/DoubleH10/zatca-mcp.git
cd zatca-mcp
pip install -e ".[dev]"
python examples/fikrah_agent.py
```

**Features:**
- Green-branded Rich terminal UI with spinners and Markdown rendering
- `fikra>` prompt inspired by Claude Code
- Auto-generates professional HTML invoices with embedded QR code images
- Opens invoices in your browser automatically
- Graceful Ctrl+C handling and `/quit` to exit

```
fikra> I just closed a deal with Al-Rajhi Corp for 5000 SAR for consulting services
  tool: generate_invoice
  ╭─ HTML Invoice ──────────────────────────────────╮
  │ Invoice saved & opened in browser               │
  │ /path/to/examples/invoices/INV-001_20240115.html│
  ╰─────────────────────────────────────────────────╯
```

## Example: Generate an Invoice Programmatically

```python
from zatca_mcp.utils.xml_builder import build_invoice_xml
from zatca_mcp.utils.tlv import encode_tlv
from zatca_mcp.utils.validation import validate_invoice_xml

# Generate invoice
xml = build_invoice_xml(
    invoice_type="simplified",
    invoice_number="INV-2024-001",
    issue_date="2024-01-15",
    seller_name="Fikrah Tech",
    seller_vat="300000000000003",
    seller_address="123 King Fahd Road",
    seller_city="Riyadh",
    buyer_name="Walk-in Customer",
    line_items=[
        {"name": "AI Consulting", "quantity": 10, "unit_price": 500.00},
        {"name": "Setup Fee", "quantity": 1, "unit_price": 1000.00},
    ],
)

# Validate
result = validate_invoice_xml(xml)
print(f"Valid: {result['is_valid']}")  # True
print(f"Checks: {result['checks_run']}")  # 14

# Generate QR code
qr = encode_tlv(
    seller_name="Fikrah Tech",
    vat_number="300000000000003",
    timestamp="2024-01-15T10:00:00Z",
    total_amount="6900.00",
    vat_amount="900.00",
)
print(f"QR: {qr}")
```

## ZATCA Compliance

This MCP implements:

- **Phase 1**: Invoice generation with QR codes (TLV encoding)
- **Phase 2** (partial): UBL 2.1 XML structure, validation rules

### Supported Invoice Types

| Type | Code | Use Case |
|------|------|----------|
| Standard Tax Invoice | 388 (0100000) | B2B transactions |
| Simplified Tax Invoice | 388 (0200000) | B2C / POS transactions |

### QR Code TLV Tags

| Tag | Name | Required |
|-----|------|----------|
| 1 | Seller Name | Yes |
| 2 | VAT Number | Yes |
| 3 | Timestamp | Yes |
| 4 | Total Amount | Yes |
| 5 | VAT Amount | Yes |
| 6 | Invoice Hash | Phase 2 |
| 7 | ECDSA Signature | Phase 2 |
| 8 | Public Key | Phase 2 |

## Development

```bash
git clone https://github.com/DoubleH10/zatca-mcp.git
cd zatca-mcp
pip install -e ".[dev]"

# Run tests
pytest tests/ -v

# Test MCP server interactively
mcp dev src/zatca_mcp/server.py
```

## Roadmap

- [x] QR code generation (TLV Phase 1 + Phase 2)
- [x] UBL 2.1 invoice XML generation
- [x] Validation engine (14+ business rules)
- [x] MCP server with 4 tools
- [x] Fikra CLI (Rich UI, HTML invoices, QR images)
- [ ] XAdES digital signing
- [ ] ZATCA API integration (sandbox + production)
- [ ] Certificate management (CSR generation)
- [ ] Credit/debit note support

## Built by Fikrah

[Fikrah](https://fikrah.ai) is building an agentic AI workforce for financial operations. This MCP is the foundation for our Saudi e-invoicing capabilities.

## License

Apache 2.0 — see [LICENSE](LICENSE)
