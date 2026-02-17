"""
Pydantic v2 models for ZATCA Fatoora API requests and responses.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class ComplianceCSIDRequest(BaseModel):
    """Request to obtain a Compliance CSID from ZATCA."""

    csr: str = Field(description="Base64-encoded CSR")
    otp: str = Field(description="One-Time Password from ZATCA portal")


class ValidationResult(BaseModel):
    """A single validation result from ZATCA."""

    type: str = Field(default="", description="INFO, WARNING, or ERROR")
    code: str = Field(default="", description="Validation rule code")
    category: str = Field(default="", description="Validation category")
    message: str = Field(default="", description="Human-readable message")
    status: str = Field(default="", description="PASS or FAIL")


class ComplianceCSIDResponse(BaseModel):
    """Response from ZATCA Compliance CSID endpoint."""

    requestID: str = Field(default="", description="Request tracking ID")
    binarySecurityToken: str = Field(
        default="", description="Base64-encoded compliance certificate"
    )
    secret: str = Field(default="", description="API secret for authentication")
    errors: list[ValidationResult] = Field(default_factory=list)
    warnings: list[ValidationResult] = Field(default_factory=list)


class InvoiceSubmissionRequest(BaseModel):
    """Request to submit an invoice to ZATCA."""

    invoiceHash: str = Field(description="Base64-encoded SHA-256 hash of the invoice")
    uuid: str = Field(description="Invoice UUID")
    invoice: str = Field(description="Base64-encoded signed invoice XML")


class InvoiceSubmissionResponse(BaseModel):
    """Response from ZATCA invoice submission."""

    status: str = Field(
        default="",
        description="REPORTED, CLEARED, or REJECTED",
    )
    validationResults: list[ValidationResult] = Field(default_factory=list)
    clearedInvoice: str | None = Field(
        default=None,
        description="Base64-encoded cleared invoice (clearance mode only)",
    )
    errors: list[ValidationResult] = Field(default_factory=list)
    warnings: list[ValidationResult] = Field(default_factory=list)


class ProductionCSIDRequest(BaseModel):
    """Request to obtain a Production CSID."""

    compliance_request_id: str = Field(
        description="Request ID from compliance CSID response"
    )
