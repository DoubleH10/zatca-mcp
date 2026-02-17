"""
ZATCA Fatoora API Client.

Async HTTP client for ZATCA's e-invoicing API endpoints.
Supports compliance, reporting, clearance, and CSID management.

Requires: httpx>=0.25.0
"""

from __future__ import annotations

import base64

import httpx

from zatca_mcp.api.models import (
    ComplianceCSIDResponse,
    InvoiceSubmissionResponse,
)

SANDBOX_BASE_URL = (
    "https://gw-fatoora.zatca.gov.sa/e-invoicing/developer-portal"
)
PRODUCTION_BASE_URL = (
    "https://gw-fatoora.zatca.gov.sa/e-invoicing/core"
)

COMMON_HEADERS = {
    "Content-Type": "application/json",
    "Accept": "application/json",
    "Accept-Version": "V2",
    "Accept-Language": "en",
}


class ZATCAClient:
    """Async client for ZATCA Fatoora API."""

    def __init__(
        self,
        certificate: str = "",
        secret: str = "",
        environment: str = "sandbox",
    ):
        """
        Initialize ZATCA API client.

        Args:
            certificate: Base64-encoded compliance/production certificate
            secret: API secret from ZATCA
            environment: "sandbox" or "production"
        """
        self.certificate = certificate
        self.secret = secret
        self.base_url = (
            SANDBOX_BASE_URL if environment == "sandbox" else PRODUCTION_BASE_URL
        )

    def _auth_header(self) -> dict[str, str]:
        """Generate Basic auth header as base64(cert:secret)."""
        credentials = f"{self.certificate}:{self.secret}"
        encoded = base64.b64encode(credentials.encode("utf-8")).decode("ascii")
        return {"Authorization": f"Basic {encoded}"}

    async def get_compliance_csid(
        self,
        csr_b64: str,
        otp: str,
    ) -> ComplianceCSIDResponse:
        """
        Request a Compliance CSID from ZATCA.

        POST /compliance (no auth required, OTP in header)

        Args:
            csr_b64: Base64-encoded CSR
            otp: One-Time Password from ZATCA portal

        Returns:
            ComplianceCSIDResponse with certificate and secret
        """
        headers = {**COMMON_HEADERS, "OTP": otp}
        payload = {"csr": csr_b64}

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{self.base_url}/compliance",
                json=payload,
                headers=headers,
            )
            response.raise_for_status()
            return ComplianceCSIDResponse.model_validate(response.json())

    async def check_compliance(
        self,
        xml_b64: str,
        invoice_hash: str,
        uuid: str,
    ) -> InvoiceSubmissionResponse:
        """
        Check invoice compliance with ZATCA rules.

        POST /compliance/invoices

        Args:
            xml_b64: Base64-encoded signed invoice XML
            invoice_hash: Base64-encoded SHA-256 invoice hash
            uuid: Invoice UUID

        Returns:
            InvoiceSubmissionResponse with validation results
        """
        headers = {**COMMON_HEADERS, **self._auth_header()}
        payload = {
            "invoiceHash": invoice_hash,
            "uuid": uuid,
            "invoice": xml_b64,
        }

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{self.base_url}/compliance/invoices",
                json=payload,
                headers=headers,
            )
            response.raise_for_status()
            return InvoiceSubmissionResponse.model_validate(response.json())

    async def report_invoice(
        self,
        xml_b64: str,
        invoice_hash: str,
        uuid: str,
    ) -> InvoiceSubmissionResponse:
        """
        Report a simplified invoice to ZATCA.

        POST /invoices/reporting/single (Clearance-Status: 0)

        Args:
            xml_b64: Base64-encoded signed invoice XML
            invoice_hash: Invoice hash
            uuid: Invoice UUID

        Returns:
            InvoiceSubmissionResponse
        """
        headers = {
            **COMMON_HEADERS,
            **self._auth_header(),
            "Clearance-Status": "0",
        }
        payload = {
            "invoiceHash": invoice_hash,
            "uuid": uuid,
            "invoice": xml_b64,
        }

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{self.base_url}/invoices/reporting/single",
                json=payload,
                headers=headers,
            )
            response.raise_for_status()
            return InvoiceSubmissionResponse.model_validate(response.json())

    async def clear_invoice(
        self,
        xml_b64: str,
        invoice_hash: str,
        uuid: str,
    ) -> InvoiceSubmissionResponse:
        """
        Submit a standard invoice for clearance by ZATCA.

        POST /invoices/clearance/single (Clearance-Status: 1)

        Args:
            xml_b64: Base64-encoded signed invoice XML
            invoice_hash: Invoice hash
            uuid: Invoice UUID

        Returns:
            InvoiceSubmissionResponse (may include clearedInvoice)
        """
        headers = {
            **COMMON_HEADERS,
            **self._auth_header(),
            "Clearance-Status": "1",
        }
        payload = {
            "invoiceHash": invoice_hash,
            "uuid": uuid,
            "invoice": xml_b64,
        }

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{self.base_url}/invoices/clearance/single",
                json=payload,
                headers=headers,
            )
            response.raise_for_status()
            return InvoiceSubmissionResponse.model_validate(response.json())

    async def get_production_csid(
        self,
        request_id: str,
    ) -> ComplianceCSIDResponse:
        """
        Request a Production CSID from ZATCA.

        POST /production/csids

        Args:
            request_id: Compliance request ID

        Returns:
            ComplianceCSIDResponse with production certificate
        """
        headers = {**COMMON_HEADERS, **self._auth_header()}
        payload = {"compliance_request_id": request_id}

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{self.base_url}/production/csids",
                json=payload,
                headers=headers,
            )
            response.raise_for_status()
            return ComplianceCSIDResponse.model_validate(response.json())
