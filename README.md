<div align="center">

# 🇸🇦 ZATCA MCP

**AI-native Saudi e-invoicing — generate ZATCA-compliant invoices from natural language.**

[![Python 3.10+](https://img.shields.io/badge/Python-3.10+-c8e64a?logo=python&logoColor=white)](https://python.org)
[![License: Apache 2.0](https://img.shields.io/badge/License-Apache_2.0-c8e64a)](LICENSE)
[![CI](https://img.shields.io/badge/CI-GitHub_Actions-c8e64a?logo=githubactions&logoColor=white)](.github/workflows/test.yml)
[![Tests: 100 passing](https://img.shields.io/badge/Tests-100_passing-c8e64a)]()
[![MCP Compatible](https://img.shields.io/badge/MCP-Compatible-c8e64a)](https://modelcontextprotocol.io)
[![ZATCA Phase 1 + 2](https://img.shields.io/badge/ZATCA-Phase_1_+_2_✓-c8e64a)]()

</div>

<!-- screenshot: add asciinema/VHS terminal recording here -->
<!-- <p align="center"><img src="docs/demo.gif" width="700" alt="Fikra CLI demo"></p> -->

---

## Why ZATCA MCP?

Saudi Arabia's ZATCA mandate requires **all businesses** to issue structured electronic invoices — Phase 1 (generation) since December 2021, Phase 2 (integration) rolling out across taxpayer waves through 2025. This is a cornerstone of **Vision 2030** digital transformation.

**The problem:** no open-source, AI-native tooling exists for ZATCA e-invoicing. Businesses either pay for proprietary ERP plugins or build compliance from scratch.

**This project:** the first open-source MCP server for Saudi e-invoicing — letting AI agents like Claude generate, validate, and manage ZATCA-compliant invoices through natural conversation.

## Features

- **8 MCP Tools** — generate, sign, validate, submit invoices + QR codes, CSR, compliance checks
- **UBL 2.1 XML** — full namespace-compliant invoice generation per OASIS standard
- **16-Rule Validation Engine** — BR-01 through BR-16 business rule checks
- **XAdES-BES Digital Signing** — ECDSA secp256k1 signatures with certificate embedding
- **ZATCA API Integration** — async client for compliance, reporting, and clearance endpoints
- **Credit/Debit Notes** — type codes 381/383 with BillingReference and InstructionNote
- **TLV QR Encoding** — Phase 1 + Phase 2 tag support (tags 1-8, cryptographic data)
- **Fikra CLI** — Claude Code-style conversational agent with HTML invoice output
- **100 Tests** — unit, integration, signing, API client, and edge-case coverage
- **CI/CD Pipeline** — ruff + mypy + pytest across Python 3.10/3.11/3.12 + Phase 2 job
- **Arabic Support** — full UTF-8 handling for seller/buyer names and addresses
- **Decimal Precision** — `Decimal` with `ROUND_HALF_UP` for all financial math
- **Multi-Rate VAT** — per-line-item VAT rates (default 15%)

## Architecture

```mermaid
graph TD
    subgraph Clients
        A[Claude Desktop]
        B[Claude Code]
        C[Fikra CLI]
    end

    subgraph MCP Server
        D[generate_invoice]
        E[generate_qr_code]
        F[validate_invoice]
        G[decode_qr]
        D2[generate_csr]
        D3[sign_invoice]
        D4[submit_invoice]
        D5[check_compliance]
    end

    subgraph Processing Engine
        H[XML Builder<br/>UBL 2.1]
        I[Validation Engine<br/>16 Business Rules]
        J[TLV Encoder<br/>QR Phase 1 + 2]
        S[Signing Engine<br/>XAdES-BES]
        API[ZATCA API Client<br/>httpx async]
    end

    A -- MCP Protocol --> D
    B -- MCP Protocol --> E
    A -- MCP Protocol --> F
    B -- MCP Protocol --> G

    C -- Direct Call --> H
    C -- Direct Call --> I
    C -- Direct Call --> J
    C -. HTML Pipeline .-> K[Browser Invoice<br/>with QR Image]

    D --> H
    D --> J
    E --> J
    F --> I
    G --> J
    D2 --> S
    D3 --> S
    D4 --> API
    D5 --> API
```

## Quick Start

### Install

```bash
pip install zatca-mcp              # Phase 1 (generation + validation)
pip install zatca-mcp[phase2]      # Phase 2 (signing + ZATCA API)
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

```bash
export ANTHROPIC_API_KEY="sk-ant-..."
pip install zatca-mcp[phase2]
fikra                              # works from any directory
```

## Fikra CLI

A Claude Code-style conversational agent that turns natural language into compliant invoices with professional HTML output.

**Features:**
- Gradient ASCII banner with `#c8e64a` brand theming
- `❯` prompt with streaming responses
- `⏺` tool-use indicators (mirrors Claude Code UX)
- Auto-generates HTML invoices with embedded QR code images
- Opens invoices in your browser automatically
- Token usage display (`↳ input · output tokens`)
- `/help` `/clear` `/quit` commands

```
     ◇
    ◇◆◇
     ◇       ███████╗██╗██╗  ██╗██████╗  █████╗ ██╗  ██╗
    ╱ ╲      ██╔════╝██║██║ ██╔╝██╔══██╗██╔══██╗██║  ██║
   ╱   ╲     █████╗  ██║█████╔╝ ██████╔╝███████║███████║
   ╰───╯     ██╔══╝  ██║██╔═██╗ ██╔══██╗██╔══██║██╔══██║
              ██║     ██║██║  ██╗██║  ██║██║  ██║██║  ██║
              ╚═╝     ╚═╝╚═╝  ╚═╝╚═╝  ╚═╝╚═╝  ╚═╝╚═╝  ╚═╝

  Model: claude-sonnet-4-20250514  |  Tools: 8 ZATCA tools  |  Phase 2 ✓  |  cwd: ~/zatca-mcp

  Tips: "I sold 10 laptops at 3000 SAR each to TechCo" to get started
        /help for commands, /quit to exit

❯ I just closed a deal with Al-Rajhi Corp for consulting — 10 hours at 500 SAR

  ⏺ generate_invoice

  ✓ Invoice saved & opened in browser
  ~/zatca-mcp/examples/invoices/INV-2026-001_20260217.html

  Great news on closing the deal! I've generated a ZATCA-compliant invoice
  for Al-Rajhi Corp — 10 hours of consulting at 500 SAR each.

  **Invoice Summary:**
  - Subtotal: 5,000.00 SAR
  - VAT (15%): 750.00 SAR
  - **Total: 5,750.00 SAR**

  The HTML invoice with embedded QR code is open in your browser.

  ↳ 1,847 input · 312 output tokens
```

## Tools API Reference

<details>
<summary><code>generate_invoice</code> — Create a ZATCA-compliant UBL 2.1 XML e-invoice</summary>

Creates a complete XML invoice following Saudi Arabia's ZATCA e-invoicing standard. Supports Standard (B2B), Simplified (B2C), Credit Note, and Debit Note types. Automatically calculates VAT, line totals, and embeds QR code data.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `invoice_type` | string | Yes | `"standard"`, `"simplified"`, `"credit_note"`, or `"debit_note"` |
| `invoice_number` | string | Yes | Unique identifier (e.g., `"INV-2024-001"`) |
| `issue_date` | string | Yes | `YYYY-MM-DD` format |
| `seller_name` | string | Yes | Seller business name |
| `seller_vat` | string | Yes | 15-digit VAT number |
| `seller_address` | string | Yes | Seller street address |
| `seller_city` | string | Yes | Seller city |
| `buyer_name` | string | Yes | Buyer/customer name |
| `items` | string | Yes | JSON array: `[{"name": "...", "quantity": 1, "unit_price": 100.00, "vat_rate": 0.15}]` |
| `currency` | string | No | ISO currency code (default: `"SAR"`) |
| `buyer_vat` | string | No | Required for standard (B2B) invoices |
| `buyer_address` | string | No | Buyer street address |
| `buyer_city` | string | No | Buyer city |
| `note` | string | No | Optional invoice note |
| `billing_reference_id` | string | No | Original invoice ID (required for credit/debit notes) |
| `billing_reference_date` | string | No | Original invoice date (for credit/debit notes) |
| `instruction_note` | string | No | Reason for credit/debit note |

**Returns:** Complete UBL 2.1 XML invoice string with embedded QR code.

</details>

<details>
<summary><code>generate_qr_code</code> — Generate a TLV-encoded QR code</summary>

Creates a Base64-encoded QR code payload following ZATCA's Tag-Length-Value (TLV) format for Phase 1 and Phase 2 compliance.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `seller_name` | string | Yes | Business/taxpayer name (Arabic or English) |
| `vat_number` | string | Yes | 15-digit Saudi VAT number |
| `timestamp` | string | Yes | ISO 8601 format (e.g., `"2024-01-15T10:30:00Z"`) |
| `total_amount` | string | Yes | Invoice total including VAT (e.g., `"1150.00"`) |
| `vat_amount` | string | Yes | Total VAT charged (e.g., `"150.00"`) |

**Returns:** JSON with `qr_base64` and `decoded_verification` data.

</details>

<details>
<summary><code>validate_invoice</code> — Check invoice XML against ZATCA business rules</summary>

Runs 16 business rule checks including required fields, VAT number format, mathematical accuracy of line totals and VAT calculations, credit/debit note references, and structural integrity of UBL 2.1 XML.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `invoice_xml` | string | Yes | Complete UBL 2.1 XML invoice string |

**Returns:** JSON with `is_valid` (boolean), `errors` (list), `warnings` (list), and `checks_run` (16).

</details>

<details>
<summary><code>generate_csr</code> — Generate a ZATCA-compliant Certificate Signing Request</summary>

Generates an ECDSA secp256k1 key pair and a CSR with ZATCA-required subject fields. Requires `cryptography` (install with `pip install zatca-mcp[phase2]`).

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `common_name` | string | Yes | Certificate CN field |
| `organization` | string | Yes | Organization name |
| `organizational_unit` | string | Yes | Organization unit |
| `country` | string | No | Country code (default: `"SA"`) |
| `serial_number` | string | No | ZATCA device serial number |
| `invoice_type` | string | No | ZATCA invoice type code (default: `"1100"`) |
| `location` | string | No | Business location (default: `"Riyadh"`) |
| `industry` | string | No | Business category (default: `"IT"`) |

**Returns:** JSON with `csr_pem`, `private_key_pem`, `warning`, and `next_step`.

</details>

<details>
<summary><code>sign_invoice</code> — Digitally sign an invoice with XAdES-BES</summary>

Injects an XAdES-BES digital signature into a UBL 2.1 invoice XML. Rebuilds the QR code with Phase 2 cryptographic tags (6-8). Requires `cryptography`.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `invoice_xml` | string | Yes | UBL 2.1 XML invoice string to sign |
| `certificate_pem` | string | Yes | PEM-encoded X.509 certificate |
| `private_key_pem` | string | Yes | PEM-encoded ECDSA private key |

**Returns:** JSON with `signed_xml`, `invoice_hash`, `qr_base64`, and `is_phase2_compliant`.

</details>

<details>
<summary><code>submit_invoice</code> — Submit a signed invoice to the ZATCA API</summary>

Submits a signed invoice to the ZATCA Fatoora API for reporting (simplified) or clearance (standard). Requires `httpx` and `pydantic`.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `signed_invoice_xml` | string | Yes | Signed UBL 2.1 XML invoice |
| `invoice_hash` | string | Yes | Base64-encoded SHA-256 hash |
| `invoice_uuid` | string | Yes | Invoice UUID |
| `certificate` | string | Yes | Base64-encoded certificate |
| `secret` | string | Yes | API secret from CSID |
| `mode` | string | No | `"reporting"` (default) or `"clearance"` |
| `environment` | string | No | `"sandbox"` (default) or `"production"` |

**Returns:** ZATCA API response with `status`, `validationResults`, `warnings`, and `errors`.

</details>

<details>
<summary><code>check_compliance</code> — Check invoice compliance with ZATCA servers</summary>

Submits an invoice to the ZATCA compliance endpoint for server-side validation. Requires `httpx` and `pydantic`.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `signed_invoice_xml` | string | Yes | Signed UBL 2.1 XML invoice |
| `invoice_hash` | string | Yes | Base64-encoded SHA-256 hash |
| `invoice_uuid` | string | Yes | Invoice UUID |
| `certificate` | string | Yes | Base64-encoded certificate |
| `secret` | string | Yes | API secret from CSID |

**Returns:** ZATCA compliance validation results.

</details>

<details>
<summary><code>decode_qr</code> — Decode a ZATCA TLV-encoded QR code string</summary>

Extracts all encoded tag values from an existing ZATCA QR code for verification or inspection.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `qr_base64` | string | Yes | Base64-encoded TLV string from a ZATCA QR code |

**Returns:** JSON with decoded tag names and their values.

</details>

## Programmatic Usage

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
print(f"Checks: {result['checks_run']}")  # 16

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

### Phase 2: Digital Signing

```python
from zatca_mcp.utils.signing import (
    generate_private_key,
    generate_csr,
    inject_signature,
    hash_invoice,
)

# Generate key pair and CSR
key = generate_private_key()
csr_pem = generate_csr(
    key,
    common_name="My Company",
    organization="My Org",
    organizational_unit="IT",
)
# Submit CSR to ZATCA to get a certificate, then sign:
# signed_xml = inject_signature(xml, cert_pem, key)
# invoice_hash = hash_invoice(xml)
```

## ZATCA Compliance

### Validation Rules (16 Business Rules)

| Rule | Check | Description |
|------|-------|-------------|
| BR-01 | Invoice ID | `cbc:ID` is mandatory |
| BR-02 | Issue Date | `cbc:IssueDate` mandatory, YYYY-MM-DD format |
| BR-03 | Type Code | `cbc:InvoiceTypeCode` must be 388, 381, or 383 |
| BR-04 | Currency | `cbc:DocumentCurrencyCode` is mandatory |
| BR-05 | Seller Name | Seller `RegistrationName` is mandatory |
| BR-06 | Seller VAT | 15-digit VAT number, starts/ends with 3 |
| BR-07 | Buyer Name | Buyer `RegistrationName` is mandatory |
| BR-08 | Buyer VAT (B2B) | Required for standard invoice subtype `01*` |
| BR-09 | — | Reserved |
| BR-10 | Line Items | At least one `cac:InvoiceLine` required |
| BR-11 | Line Math | qty × price = line extension amount (±0.01) |
| BR-12 | Tax Total | `cac:TaxTotal/cbc:TaxAmount` is mandatory |
| BR-13 | Payable Amount | `cbc:PayableAmount` is mandatory |
| BR-14 | Total Cross-Check | tax-exclusive + tax = tax-inclusive (±0.01) |
| BR-15 | Billing Reference | Credit/Debit notes must reference original invoice |
| BR-16 | Instruction Note | Credit/Debit notes should include a reason |

### Invoice Types

| Type | Code | Subtype | Use Case |
|------|------|---------|----------|
| Standard Tax Invoice | 388 | 0100000 | B2B transactions |
| Simplified Tax Invoice | 388 | 0200000 | B2C / POS transactions |
| Standard Credit Note | 381 | 0100000 | B2B returns/refunds |
| Simplified Credit Note | 381 | 0200000 | B2C returns/refunds |
| Standard Debit Note | 383 | 0100000 | B2B additional charges |
| Simplified Debit Note | 383 | 0200000 | B2C additional charges |

### QR Code TLV Tags

| Tag | Name | Phase |
|-----|------|-------|
| 1 | Seller Name | 1 |
| 2 | VAT Registration Number | 1 |
| 3 | Timestamp | 1 |
| 4 | Invoice Total (with VAT) | 1 |
| 5 | VAT Amount | 1 |
| 6 | Invoice Hash | 2 |
| 7 | ECDSA Signature | 2 |
| 8 | ECDSA Public Key | 2 |

> Tags 6-8 are populated by the `sign_invoice` tool with real cryptographic data (SHA-256 hash, ECDSA signature, public key).

## Engineering Quality

- **100 tests** across 6 test modules (TLV, validation, invoice, signing, credit/debit, API client)
- **CI/CD** — GitHub Actions: ruff lint + format check, mypy type checking, pytest with coverage across Python 3.10 / 3.11 / 3.12, plus a dedicated Phase 2 job
- **Decimal precision** — all financial calculations use `Decimal` with `ROUND_HALF_UP`, never floating point
- **UBL 2.1 compliance** — full OASIS namespace declarations (`ubl`, `cac`, `cbc`, `ext`, `ds`, `xades`)
- **Arabic/UTF-8** — `ensure_ascii=False` throughout; Arabic seller/buyer names work correctly
- **Graceful degradation** — Phase 2 tools return helpful errors if `cryptography`/`httpx` not installed

## Project Structure

```
zatca-mcp/
├── src/zatca_mcp/
│   ├── server.py              # MCP server — 8 tool definitions
│   ├── cli.py                 # Fikra CLI — global `fikra` command
│   ├── utils/
│   │   ├── xml_builder.py     # UBL 2.1 XML invoice generator
│   │   ├── validation.py      # 16-rule validation engine
│   │   ├── tlv.py             # TLV QR encoder/decoder
│   │   └── signing.py         # XAdES-BES digital signing (Phase 2)
│   └── api/
│       ├── __init__.py
│       ├── client.py          # ZATCA Fatoora API client (Phase 2)
│       └── models.py          # Pydantic v2 API models (Phase 2)
├── examples/
│   └── fikrah_agent.py        # Legacy entry point (redirects to fikra command)
├── tests/
│   ├── test_invoice.py        # Invoice generation tests
│   ├── test_tlv.py            # TLV encoding/decoding tests
│   ├── test_validation.py     # Validation engine tests
│   ├── test_signing.py        # Digital signing tests (Phase 2)
│   ├── test_credit_debit.py   # Credit/debit note tests (Phase 2)
│   └── test_api_client.py     # API client tests (Phase 2)
├── .github/workflows/
│   └── test.yml               # CI pipeline (Phase 1 + Phase 2 jobs)
├── pyproject.toml
└── LICENSE
```

## Development

```bash
git clone https://github.com/DoubleH10/zatca-mcp.git
cd zatca-mcp

# Phase 1 only
pip install -e ".[dev]"

# Phase 1 + Phase 2 (signing, API)
pip install -e ".[dev,phase2]"

# Tests
pytest tests/ -v                                    # All tests
pytest tests/ -v -m "not sandbox"                   # Skip live sandbox tests

# Linting & types
ruff check src/ tests/
mypy src/zatca_mcp/ --ignore-missing-imports

# MCP Inspector (interactive testing)
mcp dev src/zatca_mcp/server.py
```

## Roadmap

- [x] TLV QR code generation (Phase 1 + Phase 2 tags)
- [x] UBL 2.1 XML invoice generation
- [x] 16-rule validation engine (BR-01 through BR-16)
- [x] MCP server with 8 tools
- [x] Fikra CLI (streaming, HTML invoices, QR images)
- [x] CI/CD pipeline (ruff + mypy + pytest matrix + Phase 2 job)
- [x] XAdES-BES digital signing (ECDSA secp256k1)
- [x] ZATCA API integration (sandbox + production)
- [x] Certificate management (CSR generation)
- [x] Credit/debit note support (381/383)
- [ ] PyPI package publishing
- [ ] MCP Resources & Prompts
- [ ] HTTP/SSE transport
- [ ] Arabic RTL invoice template

## Built by Fikrah

[Fikrah](https://fikrah.ai) is building an agentic AI workforce for financial operations.
This MCP server is the foundation for our Saudi e-invoicing capabilities.

## License

Apache 2.0 — see [LICENSE](LICENSE)
