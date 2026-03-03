"""Tests for MCP resources and prompts."""

import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from zatca_mcp.server import (
    INVOICE_TYPES,
    VALIDATION_RULES,
    create_invoice,
    credit_note,
    get_invoice_types,
    get_sample_invoice,
    get_validation_rules,
    validate_existing_invoice,
)


class TestValidationRulesResource:
    def test_returns_valid_json(self):
        result = get_validation_rules()
        data = json.loads(result)
        assert isinstance(data, list)

    def test_has_16_rules(self):
        data = json.loads(get_validation_rules())
        assert len(data) == 16

    def test_rule_structure(self):
        data = json.loads(get_validation_rules())
        for rule in data:
            assert "id" in rule
            assert "name" in rule
            assert "description" in rule
            assert "severity" in rule
            assert rule["severity"] in ("error", "warning")

    def test_rule_ids_sequential(self):
        data = json.loads(get_validation_rules())
        for i, rule in enumerate(data, start=1):
            assert rule["id"] == f"BR-{i:02d}"

    def test_constant_matches_output(self):
        data = json.loads(get_validation_rules())
        assert data == VALIDATION_RULES


class TestInvoiceTypesResource:
    def test_returns_valid_json(self):
        result = get_invoice_types()
        data = json.loads(result)
        assert isinstance(data, list)

    def test_has_6_types(self):
        data = json.loads(get_invoice_types())
        assert len(data) == 6

    def test_type_structure(self):
        data = json.loads(get_invoice_types())
        for inv_type in data:
            assert "name" in inv_type
            assert "type_code" in inv_type
            assert "subtype" in inv_type
            assert "invoice_type_param" in inv_type
            assert "use_case" in inv_type
            assert "vat_categories" in inv_type

    def test_type_codes_valid(self):
        data = json.loads(get_invoice_types())
        for inv_type in data:
            assert inv_type["type_code"] in ("388", "381", "383")

    def test_constant_matches_output(self):
        data = json.loads(get_invoice_types())
        assert data == INVOICE_TYPES


class TestSampleInvoiceResource:
    def test_returns_xml(self):
        result = get_sample_invoice()
        assert result.strip().startswith("<?xml") or result.strip().startswith("<Invoice")

    def test_valid_xml_parse(self):
        from lxml import etree

        result = get_sample_invoice()
        root = etree.fromstring(result.encode("utf-8"))
        assert root is not None

    def test_contains_seller_name(self):
        result = get_sample_invoice()
        assert "Acme Trading LLC" in result

    def test_contains_line_items(self):
        result = get_sample_invoice()
        assert "Consulting Services" in result
        assert "Setup Fee" in result

    def test_passes_validation(self):
        from zatca_mcp.utils.validation import validate_invoice_xml

        result = get_sample_invoice()
        validation = validate_invoice_xml(result)
        assert validation["is_valid"] is True


class TestCreateInvoicePrompt:
    def test_returns_message_list(self):
        messages = create_invoice()
        assert isinstance(messages, list)
        assert len(messages) == 2

    def test_has_system_and_user_roles(self):
        messages = create_invoice()
        assert messages[0]["role"] == "system"
        assert messages[1]["role"] == "user"

    def test_system_message_has_guidance(self):
        messages = create_invoice()
        system_content = messages[0]["content"]
        assert "generate_invoice" in system_content
        assert "VAT" in system_content
        assert "seller" in system_content.lower()

    def test_user_message_triggers_workflow(self):
        messages = create_invoice()
        user_content = messages[1]["content"]
        assert "invoice" in user_content.lower()


class TestValidateInvoicePrompt:
    def test_returns_message_list(self):
        messages = validate_existing_invoice(invoice_xml="<test/>")
        assert isinstance(messages, list)
        assert len(messages) == 2

    def test_has_system_and_user_roles(self):
        messages = validate_existing_invoice(invoice_xml="<test/>")
        assert messages[0]["role"] == "system"
        assert messages[1]["role"] == "user"

    def test_includes_xml_argument(self):
        sample_xml = "<Invoice>test</Invoice>"
        messages = validate_existing_invoice(invoice_xml=sample_xml)
        assert sample_xml in messages[1]["content"]

    def test_system_message_has_guidance(self):
        messages = validate_existing_invoice(invoice_xml="<test/>")
        system_content = messages[0]["content"]
        assert "validate_invoice" in system_content
        assert "BR-01" in system_content


class TestCreditNotePrompt:
    def test_returns_message_list(self):
        messages = credit_note()
        assert isinstance(messages, list)
        assert len(messages) == 2

    def test_has_system_and_user_roles(self):
        messages = credit_note()
        assert messages[0]["role"] == "system"
        assert messages[1]["role"] == "user"

    def test_system_message_has_guidance(self):
        messages = credit_note()
        system_content = messages[0]["content"]
        assert "credit" in system_content.lower()
        assert "debit" in system_content.lower()
        assert "billing_reference_id" in system_content

    def test_mentions_type_codes(self):
        messages = credit_note()
        system_content = messages[0]["content"]
        assert "381" in system_content
        assert "383" in system_content
