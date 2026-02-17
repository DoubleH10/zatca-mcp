"""
Digital Signing Utilities for ZATCA Phase 2.

Provides ECDSA key generation, CSR creation, XML canonicalization,
invoice hashing, and XAdES-BES signature injection per ZATCA spec.

Requires: cryptography>=41.0.0
"""

from __future__ import annotations

import base64
import copy
import hashlib
from datetime import datetime, timezone

from lxml import etree

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509 import (
    CertificateSigningRequestBuilder,
    Name,
    NameAttribute,
)
from cryptography.x509.oid import NameOID
from cryptography.x509.name import _ASN1Type

# UBL / ZATCA namespaces
NS = {
    "ubl": "urn:oasis:names:specification:ubl:schema:xsd:Invoice-2",
    "cac": "urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2",
    "cbc": "urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2",
    "ext": "urn:oasis:names:specification:ubl:schema:xsd:CommonExtensionComponents-2",
    "ds": "http://www.w3.org/2000/09/xmldsig#",
    "xades": "http://uri.etsi.org/01903/v1.3.2#",
}

# Clark-notation helpers
_EXT = "urn:oasis:names:specification:ubl:schema:xsd:CommonExtensionComponents-2"
_DS = "http://www.w3.org/2000/09/xmldsig#"
_XADES = "http://uri.etsi.org/01903/v1.3.2#"
_UBL = "urn:oasis:names:specification:ubl:schema:xsd:Invoice-2"


# ═══════════════════════════════════════════════════
# Key Generation & CSR
# ═══════════════════════════════════════════════════


def generate_private_key() -> ec.EllipticCurvePrivateKey:
    """Generate an ECDSA private key on secp256k1 (ZATCA requirement)."""
    return ec.generate_private_key(ec.SECP256K1())


def serialize_private_key(
    key: ec.EllipticCurvePrivateKey,
    password: bytes | None = None,
) -> bytes:
    """Serialize private key to PEM format."""
    encryption = (
        serialization.BestAvailableEncryption(password)
        if password
        else serialization.NoEncryption()
    )
    return key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=encryption,
    )


def load_private_key(
    pem: bytes,
    password: bytes | None = None,
) -> ec.EllipticCurvePrivateKey:
    """Load a private key from PEM bytes."""
    key = serialization.load_pem_private_key(pem, password=password)
    if not isinstance(key, ec.EllipticCurvePrivateKey):
        raise TypeError("Expected an ECDSA private key")
    return key


def generate_csr(
    key: ec.EllipticCurvePrivateKey,
    common_name: str,
    organization: str,
    organizational_unit: str,
    country: str = "SA",
    serial_number: str = "1-TST|2-TST|3-ed22f1d8-e6a2-1118-9b58-d9a8195e2f28",
    invoice_type: str = "1100",
    location: str = "Riyadh",
    industry: str = "IT",
) -> bytes:
    """
    Generate a ZATCA-compliant Certificate Signing Request.

    The CSR includes ZATCA-required subject fields: SN (serial_number),
    UID (invoice_type), title (location), registered address (industry),
    and business category (industry).

    Args:
        key: ECDSA private key
        common_name: CN field
        organization: O field
        organizational_unit: OU field
        country: C field (default "SA")
        serial_number: ZATCA device serial (SN)
        invoice_type: ZATCA invoice type code (UID)
        location: Business location (Title)
        industry: Business category

    Returns:
        PEM-encoded CSR bytes
    """
    subject = Name([
        NameAttribute(NameOID.COUNTRY_NAME, country),
        NameAttribute(NameOID.ORGANIZATION_NAME, organization),
        NameAttribute(NameOID.ORGANIZATIONAL_UNIT_NAME, organizational_unit),
        NameAttribute(NameOID.COMMON_NAME, common_name),
        NameAttribute(NameOID.SERIAL_NUMBER, serial_number, _type=_ASN1Type.UTF8String),
        NameAttribute(NameOID.USER_ID, invoice_type, _type=_ASN1Type.UTF8String),
        NameAttribute(NameOID.TITLE, location, _type=_ASN1Type.UTF8String),
        NameAttribute(NameOID.STATE_OR_PROVINCE_NAME, industry, _type=_ASN1Type.UTF8String),
        NameAttribute(NameOID.BUSINESS_CATEGORY, industry, _type=_ASN1Type.UTF8String),
    ])

    csr = (
        CertificateSigningRequestBuilder()
        .subject_name(subject)
        .sign(key, hashes.SHA256())
    )
    return serialize_csr(csr)


def serialize_csr(csr) -> bytes:
    """Serialize a CSR to PEM format."""
    return csr.public_bytes(serialization.Encoding.PEM)


# ═══════════════════════════════════════════════════
# XML Canonicalization & Hashing
# ═══════════════════════════════════════════════════


def canonicalize_xml(xml_bytes: bytes) -> bytes:
    """
    Exclusive C14N canonicalization of invoice XML.

    Strips UBLExtensions and Signature elements before canonicalization,
    as required by ZATCA signing spec. Also removes XML declaration.
    """
    root = etree.fromstring(xml_bytes)
    root_copy = copy.deepcopy(root)

    # Remove UBLExtensions element if present
    for ext in root_copy.findall(f"{{{_EXT}}}UBLExtensions"):
        root_copy.remove(ext)

    # Remove Signature element if present
    for sig in root_copy.findall(f"{{{_DS}}}Signature"):
        root_copy.remove(sig)

    return etree.tostring(root_copy, method="c14n2", exclusive=True)


def hash_invoice(xml: bytes) -> str:
    """
    Compute SHA-256 hash of canonicalized invoice XML.

    Returns base64-encoded hash (used as TLV tag 6).
    """
    canonical = canonicalize_xml(xml)
    digest = hashlib.sha256(canonical).digest()
    return base64.b64encode(digest).decode("ascii")


# ═══════════════════════════════════════════════════
# ECDSA Signing
# ═══════════════════════════════════════════════════


def sign_hash(
    key: ec.EllipticCurvePrivateKey,
    hash_bytes: bytes,
) -> bytes:
    """
    Sign a hash with ECDSA (used for TLV tag 7).

    Args:
        key: ECDSA private key
        hash_bytes: Raw hash bytes to sign

    Returns:
        DER-encoded ECDSA signature bytes
    """
    return key.sign(hash_bytes, ec.ECDSA(hashes.SHA256()))


def get_public_key_bytes(key: ec.EllipticCurvePrivateKey) -> bytes:
    """
    Get the uncompressed public key point bytes (for TLV tag 8).
    """
    pub = key.public_key()
    return pub.public_bytes(
        serialization.Encoding.X962,
        serialization.PublicFormat.UncompressedPoint,
    )


# ═══════════════════════════════════════════════════
# XAdES-BES Signature Injection
# ═══════════════════════════════════════════════════


def _build_signed_properties(cert_pem: str, signing_time: str) -> etree._Element:
    """Build XAdES SignedProperties element."""
    sp = etree.Element(
        f"{{{_XADES}}}SignedProperties",
        attrib={"Id": "xadesSignedProperties"},
        nsmap={"xades": _XADES},
    )

    # SignedSignatureProperties
    ssp = etree.SubElement(sp, f"{{{_XADES}}}SignedSignatureProperties")
    st = etree.SubElement(ssp, f"{{{_XADES}}}SigningTime")
    st.text = signing_time

    # SigningCertificate
    sc = etree.SubElement(ssp, f"{{{_XADES}}}SigningCertificate")
    cert_ref = etree.SubElement(sc, f"{{{_XADES}}}Cert")

    # Compute certificate digest
    cert_der = _pem_to_der(cert_pem)
    cert_hash = base64.b64encode(hashlib.sha256(cert_der).digest()).decode("ascii")

    cd = etree.SubElement(cert_ref, f"{{{_XADES}}}CertDigest")
    dm = etree.SubElement(cd, f"{{{_DS}}}DigestMethod", nsmap={"ds": _DS})
    dm.set("Algorithm", "http://www.w3.org/2001/04/xmlenc#sha256")
    dv = etree.SubElement(cd, f"{{{_DS}}}DigestValue")
    dv.text = cert_hash

    return sp


def _pem_to_der(pem_str: str) -> bytes:
    """Extract DER bytes from a PEM certificate string."""
    lines = pem_str.strip().splitlines()
    b64_lines = [
        line for line in lines
        if not line.startswith("-----")
    ]
    return base64.b64decode("".join(b64_lines))


def _build_signed_info(
    invoice_digest: str,
    signed_props_digest: str,
) -> etree._Element:
    """Build ds:SignedInfo element."""
    si = etree.Element(f"{{{_DS}}}SignedInfo", nsmap={"ds": _DS})

    # CanonicalizationMethod
    cm = etree.SubElement(si, f"{{{_DS}}}CanonicalizationMethod")
    cm.set("Algorithm", "http://www.w3.org/2006/12/xml-c14n11")

    # SignatureMethod
    sm = etree.SubElement(si, f"{{{_DS}}}SignatureMethod")
    sm.set("Algorithm", "http://www.w3.org/2001/04/xmldsig-more#ecdsa-sha256")

    # Reference to invoice body
    ref1 = etree.SubElement(si, f"{{{_DS}}}Reference")
    ref1.set("Id", "invoiceSignedData")
    ref1.set("URI", "")
    transforms = etree.SubElement(ref1, f"{{{_DS}}}Transforms")
    t = etree.SubElement(transforms, f"{{{_DS}}}Transform")
    t.set("Algorithm", "http://www.w3.org/TR/1999/REC-xpath-19991116")
    xpath_el = etree.SubElement(t, f"{{{_DS}}}XPath")
    xpath_el.text = "not(//ancestor-or-self::ext:UBLExtensions)"
    dm1 = etree.SubElement(ref1, f"{{{_DS}}}DigestMethod")
    dm1.set("Algorithm", "http://www.w3.org/2001/04/xmlenc#sha256")
    dv1 = etree.SubElement(ref1, f"{{{_DS}}}DigestValue")
    dv1.text = invoice_digest

    # Reference to SignedProperties
    ref2 = etree.SubElement(si, f"{{{_DS}}}Reference")
    ref2.set("Type", "http://www.w3.org/2000/09/xmldsig#SignatureProperties")
    ref2.set("URI", "#xadesSignedProperties")
    dm2 = etree.SubElement(ref2, f"{{{_DS}}}DigestMethod")
    dm2.set("Algorithm", "http://www.w3.org/2001/04/xmlenc#sha256")
    dv2 = etree.SubElement(ref2, f"{{{_DS}}}DigestValue")
    dv2.text = signed_props_digest

    return si


def inject_signature(
    xml: bytes,
    cert_pem: str,
    key: ec.EllipticCurvePrivateKey,
) -> bytes:
    """
    Main entry point: hash, build XAdES-BES, sign, and inject into invoice XML.

    1. Hash the canonicalized invoice (for SignedInfo + TLV tag 6)
    2. Build XAdES SignedProperties with cert digest
    3. Compute SignedProperties digest
    4. Build SignedInfo with both digests
    5. Canonicalize and sign SignedInfo
    6. Assemble ds:Signature
    7. Wrap in UBLExtensions and inject as first child of Invoice

    Args:
        xml: Invoice XML bytes
        cert_pem: PEM-encoded X.509 certificate
        key: ECDSA private key

    Returns:
        Signed invoice XML bytes
    """
    root = etree.fromstring(xml)

    # 1. Hash the invoice (sans extensions/signature)
    invoice_digest = hash_invoice(xml)

    # 2. Build SignedProperties
    signing_time = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    signed_props = _build_signed_properties(cert_pem, signing_time)

    # 3. Digest SignedProperties
    sp_canonical = etree.tostring(signed_props, method="c14n2", exclusive=True)
    sp_digest = base64.b64encode(
        hashlib.sha256(sp_canonical).digest()
    ).decode("ascii")

    # 4. Build SignedInfo
    signed_info = _build_signed_info(invoice_digest, sp_digest)

    # 5. Canonicalize and sign
    si_canonical = etree.tostring(signed_info, method="c14n2", exclusive=True)
    si_digest = hashlib.sha256(si_canonical).digest()
    signature_value = base64.b64encode(sign_hash(key, si_digest)).decode("ascii")

    # 6. Assemble ds:Signature
    ds_sig = etree.Element(f"{{{_DS}}}Signature", nsmap={"ds": _DS})

    ds_sig.append(signed_info)

    sv = etree.SubElement(ds_sig, f"{{{_DS}}}SignatureValue")
    sv.text = signature_value

    # KeyInfo with X509 certificate
    ki = etree.SubElement(ds_sig, f"{{{_DS}}}KeyInfo")
    x509_data = etree.SubElement(ki, f"{{{_DS}}}X509Data")
    x509_cert = etree.SubElement(x509_data, f"{{{_DS}}}X509Certificate")
    # Strip PEM headers and join lines
    cert_lines = cert_pem.strip().splitlines()
    cert_b64 = "".join(
        line for line in cert_lines if not line.startswith("-----")
    )
    x509_cert.text = cert_b64

    # QualifyingProperties with SignedProperties
    obj = etree.SubElement(ds_sig, f"{{{_DS}}}Object")
    qp = etree.SubElement(
        obj,
        f"{{{_XADES}}}QualifyingProperties",
        nsmap={"xades": _XADES},
    )
    qp.set("Target", "signature")
    qp.append(signed_props)

    # 7. Wrap in UBLExtensions and inject
    ext_ns = _EXT
    ubl_extensions = etree.Element(f"{{{ext_ns}}}UBLExtensions")
    ubl_extension = etree.SubElement(ubl_extensions, f"{{{ext_ns}}}UBLExtension")
    ext_content = etree.SubElement(ubl_extension, f"{{{ext_ns}}}ExtensionContent")
    ext_content.append(ds_sig)

    # Insert as first child of Invoice
    root.insert(0, ubl_extensions)

    return etree.tostring(
        root,
        pretty_print=True,
        xml_declaration=True,
        encoding="UTF-8",
    )
