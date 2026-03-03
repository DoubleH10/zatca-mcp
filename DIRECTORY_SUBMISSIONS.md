# MCP Directory Submissions Checklist

Action items for getting zatca-mcp listed across MCP directories.

---

## 1. punkpeye/awesome-mcp-servers (PR) — DO FIRST

**This is the highest-impact listing. Glama.ai auto-syncs from it.**

1. Fork https://github.com/punkpeye/awesome-mcp-servers
2. Edit `README.md` — find the `## Finance & Fintech` section
3. Add this line in alphabetical order (after entries starting with "D"):

```markdown
- [DoubleH10/zatca-mcp](https://github.com/DoubleH10/zatca-mcp) 🐍 ☁️ - ZATCA e-invoicing for Saudi Arabia. Generate, validate, sign, and submit tax-compliant XML invoices via MCP.
```

4. Submit PR with title: `Add zatca-mcp — ZATCA e-invoicing server for Saudi Arabia`
5. PR description:

```
Adds zatca-mcp to the Finance & Fintech category.

- First MCP server for Saudi Arabia's ZATCA e-invoicing mandate
- 8 MCP tools: generate, validate, sign, submit invoices + QR codes
- UBL 2.1 XML, 16-rule validation engine, XAdES-BES signing
- Phase 1 + Phase 2 ZATCA compliance
- 100 tests, CI/CD, Python 3.10-3.12, Apache 2.0
- pip-installable: `pip install zatca-mcp`
```

---

## 2. mcpservers.org (web form) — DO SECOND

**This also feeds wong2/awesome-mcp-servers automatically.**

Go to: https://mcpservers.org/submit

Fill in:

| Field | Value |
|-------|-------|
| Server Name | `ZATCA MCP` |
| Short Description | `ZATCA e-invoicing for Saudi Arabia — generate, validate, sign, and submit tax-compliant XML invoices from natural language. 8 MCP tools, UBL 2.1, 16-rule validation, XAdES-BES signing, Phase 1 + Phase 2 support.` |
| Link | `https://github.com/DoubleH10/zatca-mcp` |
| Category | `cloud-service` (closest option — connects to ZATCA APIs) |
| Contact Email | `hadi.hijazi@bloqmedia.net` |

---

## 3. Glama.ai — DO AFTER punkpeye PR merges

Glama auto-syncs from punkpeye/awesome-mcp-servers. Once listed:

1. `glama.json` is already in the repo root (done)
2. Go to https://glama.ai and authenticate with GitHub
3. Search for zatca-mcp and claim ownership

---

## 4. mcp-awesome.com — SKIP FOR NOW

Likely auto-aggregates from other directories. No clear submission mechanism.
Check back after the punkpeye and mcpservers.org listings are live.

---

## Status

- [ ] punkpeye/awesome-mcp-servers PR submitted
- [ ] mcpservers.org form submitted
- [ ] Glama.ai ownership claimed
- [ ] mcp-awesome.com (auto or manual)
