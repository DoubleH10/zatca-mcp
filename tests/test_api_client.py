"""Tests for ZATCA API client.

Unit tests use mocked httpx responses.
Integration tests hitting the live ZATCA sandbox are marked with @pytest.mark.sandbox.
"""

import pytest
import sys
import os
import base64
import json

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

pydantic = pytest.importorskip("pydantic", reason="pydantic not installed")
httpx = pytest.importorskip("httpx", reason="httpx not installed")

from zatca_mcp.api.client import (
    ZATCAClient,
    SANDBOX_BASE_URL,
    PRODUCTION_BASE_URL,
    COMMON_HEADERS,
)
from zatca_mcp.api.models import (
    ComplianceCSIDRequest,
    ComplianceCSIDResponse,
    InvoiceSubmissionRequest,
    InvoiceSubmissionResponse,
    ProductionCSIDRequest,
    ValidationResult,
)


class TestModels:
    def test_compliance_csid_request(self):
        req = ComplianceCSIDRequest(csr="dGVzdA==", otp="123456")
        assert req.csr == "dGVzdA=="
        assert req.otp == "123456"

    def test_compliance_csid_response(self):
        resp = ComplianceCSIDResponse(
            requestID="req-123",
            binarySecurityToken="cert-b64",
            secret="api-secret",
        )
        assert resp.requestID == "req-123"
        assert resp.binarySecurityToken == "cert-b64"
        assert resp.secret == "api-secret"
        assert resp.errors == []
        assert resp.warnings == []

    def test_invoice_submission_request(self):
        req = InvoiceSubmissionRequest(
            invoiceHash="hash-b64",
            uuid="test-uuid",
            invoice="invoice-b64",
        )
        assert req.invoiceHash == "hash-b64"

    def test_invoice_submission_response(self):
        resp = InvoiceSubmissionResponse(
            status="REPORTED",
            validationResults=[
                ValidationResult(
                    type="INFO",
                    code="XSD_VALID",
                    message="Schema valid",
                    status="PASS",
                )
            ],
        )
        assert resp.status == "REPORTED"
        assert len(resp.validationResults) == 1
        assert resp.clearedInvoice is None

    def test_production_csid_request(self):
        req = ProductionCSIDRequest(compliance_request_id="req-456")
        assert req.compliance_request_id == "req-456"

    def test_response_with_errors(self):
        resp = InvoiceSubmissionResponse(
            status="REJECTED",
            errors=[
                ValidationResult(
                    type="ERROR",
                    code="INVALID_HASH",
                    message="Hash mismatch",
                    status="FAIL",
                )
            ],
        )
        assert resp.status == "REJECTED"
        assert len(resp.errors) == 1
        assert resp.errors[0].code == "INVALID_HASH"


class TestClientInit:
    def test_sandbox_base_url(self):
        client = ZATCAClient(environment="sandbox")
        assert client.base_url == SANDBOX_BASE_URL

    def test_production_base_url(self):
        client = ZATCAClient(environment="production")
        assert client.base_url == PRODUCTION_BASE_URL

    def test_auth_header(self):
        client = ZATCAClient(
            certificate="test-cert",
            secret="test-secret",
        )
        headers = client._auth_header()
        expected = base64.b64encode(b"test-cert:test-secret").decode("ascii")
        assert headers["Authorization"] == f"Basic {expected}"

    def test_common_headers(self):
        assert COMMON_HEADERS["Content-Type"] == "application/json"
        assert COMMON_HEADERS["Accept-Version"] == "V2"
        assert COMMON_HEADERS["Accept-Language"] == "en"


class TestClientRequests:
    """Tests using httpx mock transport to verify request structure."""

    @pytest.mark.asyncio
    async def test_compliance_csid_request_structure(self):
        """Verify the compliance CSID request is properly formed."""
        captured = {}

        async def mock_handler(request: httpx.Request):
            captured["url"] = str(request.url)
            captured["method"] = request.method
            captured["headers"] = dict(request.headers)
            captured["body"] = json.loads(request.content)
            return httpx.Response(
                200,
                json={
                    "requestID": "req-1",
                    "binarySecurityToken": "token",
                    "secret": "secret",
                    "errors": [],
                    "warnings": [],
                },
            )

        transport = httpx.MockTransport(mock_handler)
        client = ZATCAClient(environment="sandbox")

        # Monkey-patch to use mock transport
        import httpx as httpx_mod

        original_init = httpx_mod.AsyncClient.__init__

        def patched_init(self_client, **kwargs):
            kwargs["transport"] = transport
            original_init(self_client, **kwargs)

        httpx_mod.AsyncClient.__init__ = patched_init
        try:
            result = await client.get_compliance_csid("csr-b64", "123456")
        finally:
            httpx_mod.AsyncClient.__init__ = original_init

        assert captured["method"] == "POST"
        assert "/compliance" in captured["url"]
        assert captured["headers"]["otp"] == "123456"
        assert captured["body"]["csr"] == "csr-b64"
        assert result.requestID == "req-1"

    @pytest.mark.asyncio
    async def test_report_invoice_request_structure(self):
        """Verify the reporting request includes proper auth and clearance status."""
        captured = {}

        async def mock_handler(request: httpx.Request):
            captured["url"] = str(request.url)
            captured["headers"] = dict(request.headers)
            captured["body"] = json.loads(request.content)
            return httpx.Response(
                200,
                json={
                    "status": "REPORTED",
                    "validationResults": [],
                    "errors": [],
                    "warnings": [],
                },
            )

        transport = httpx.MockTransport(mock_handler)
        client = ZATCAClient(
            certificate="cert-b64",
            secret="secret-123",
            environment="sandbox",
        )

        import httpx as httpx_mod

        original_init = httpx_mod.AsyncClient.__init__

        def patched_init(self_client, **kwargs):
            kwargs["transport"] = transport
            original_init(self_client, **kwargs)

        httpx_mod.AsyncClient.__init__ = patched_init
        try:
            result = await client.report_invoice("inv-b64", "hash-b64", "uuid-1")
        finally:
            httpx_mod.AsyncClient.__init__ = original_init

        assert "/invoices/reporting/single" in captured["url"]
        assert captured["headers"]["clearance-status"] == "0"
        assert "authorization" in captured["headers"]
        assert captured["body"]["invoiceHash"] == "hash-b64"
        assert result.status == "REPORTED"

    @pytest.mark.asyncio
    async def test_clear_invoice_request_structure(self):
        """Verify clearance request has Clearance-Status: 1."""
        captured = {}

        async def mock_handler(request: httpx.Request):
            captured["headers"] = dict(request.headers)
            return httpx.Response(
                200,
                json={
                    "status": "CLEARED",
                    "validationResults": [],
                    "clearedInvoice": "cleared-b64",
                    "errors": [],
                    "warnings": [],
                },
            )

        transport = httpx.MockTransport(mock_handler)
        client = ZATCAClient(
            certificate="cert",
            secret="secret",
            environment="sandbox",
        )

        import httpx as httpx_mod

        original_init = httpx_mod.AsyncClient.__init__

        def patched_init(self_client, **kwargs):
            kwargs["transport"] = transport
            original_init(self_client, **kwargs)

        httpx_mod.AsyncClient.__init__ = patched_init
        try:
            result = await client.clear_invoice("inv-b64", "hash", "uuid")
        finally:
            httpx_mod.AsyncClient.__init__ = original_init

        assert captured["headers"]["clearance-status"] == "1"
        assert result.status == "CLEARED"
        assert result.clearedInvoice == "cleared-b64"

    @pytest.mark.asyncio
    async def test_check_compliance_request_structure(self):
        """Verify compliance check request is properly formed."""
        captured = {}

        async def mock_handler(request: httpx.Request):
            captured["url"] = str(request.url)
            captured["body"] = json.loads(request.content)
            return httpx.Response(
                200,
                json={
                    "status": "REPORTED",
                    "validationResults": [
                        {
                            "type": "INFO",
                            "code": "XSD_VALID",
                            "category": "XSD",
                            "message": "Valid",
                            "status": "PASS",
                        }
                    ],
                    "errors": [],
                    "warnings": [],
                },
            )

        transport = httpx.MockTransport(mock_handler)
        client = ZATCAClient(
            certificate="cert",
            secret="secret",
            environment="sandbox",
        )

        import httpx as httpx_mod

        original_init = httpx_mod.AsyncClient.__init__

        def patched_init(self_client, **kwargs):
            kwargs["transport"] = transport
            original_init(self_client, **kwargs)

        httpx_mod.AsyncClient.__init__ = patched_init
        try:
            result = await client.check_compliance("inv-b64", "hash", "uuid")
        finally:
            httpx_mod.AsyncClient.__init__ = original_init

        assert "/compliance/invoices" in captured["url"]
        assert result.validationResults[0].code == "XSD_VALID"


@pytest.mark.sandbox
class TestLiveSandbox:
    """Integration tests that hit the real ZATCA sandbox.

    Run with: pytest tests/test_api_client.py -m sandbox
    These are skipped in normal CI.
    """

    @pytest.mark.asyncio
    async def test_sandbox_compliance_csid(self):
        """Test compliance CSID flow against live sandbox."""
        pytest.skip("Run manually with valid CSR and OTP")
