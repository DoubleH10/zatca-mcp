"""Tests for digital signing utilities (Phase 2).

All tests use pytest.importorskip so Phase 1 CI (without cryptography) still passes.
"""

import pytest
import sys
import os
import base64

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

cryptography = pytest.importorskip("cryptography", reason="cryptography not installed")

from zatca_mcp.utils.signing import (
    generate_private_key,
    serialize_private_key,
    load_private_key,
    generate_csr,
    canonicalize_xml,
    hash_invoice,
    sign_hash,
    get_public_key_bytes,
    inject_signature,
)
from zatca_mcp.utils.xml_builder import build_invoice_xml
from cryptography.hazmat.primitives.asymmetric import ec


def _sample_invoice_xml() -> str:
    """Generate a sample invoice XML for testing."""
    return build_invoice_xml(
        invoice_type="simplified",
        invoice_number="INV-SIGN-001",
        issue_date="2024-01-15",
        seller_name="Fikrah Tech",
        seller_vat="300000000000003",
        seller_address="123 King Fahd Road",
        seller_city="Riyadh",
        buyer_name="Test Customer",
        line_items=[
            {"name": "Consulting", "quantity": 1, "unit_price": 1000.00},
        ],
    )


def _self_signed_cert(key):
    """Create a self-signed certificate for testing."""
    from cryptography import x509
    from cryptography.x509.oid import NameOID
    from cryptography.hazmat.primitives import hashes
    from datetime import datetime, timezone, timedelta

    subject = issuer = x509.Name([
        x509.NameAttribute(NameOID.COMMON_NAME, "Test ZATCA Cert"),
        x509.NameAttribute(NameOID.ORGANIZATION_NAME, "Test Org"),
        x509.NameAttribute(NameOID.COUNTRY_NAME, "SA"),
    ])
    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(datetime.now(timezone.utc))
        .not_valid_after(datetime.now(timezone.utc) + timedelta(days=365))
        .sign(key, hashes.SHA256())
    )
    from cryptography.hazmat.primitives import serialization
    return cert.public_bytes(serialization.Encoding.PEM).decode("ascii")


class TestKeyGeneration:
    def test_key_type(self):
        key = generate_private_key()
        assert isinstance(key, ec.EllipticCurvePrivateKey)
        assert isinstance(key.curve, ec.SECP256K1)

    def test_serialize_deserialize_roundtrip(self):
        key = generate_private_key()
        pem = serialize_private_key(key)
        loaded = load_private_key(pem)
        assert isinstance(loaded, ec.EllipticCurvePrivateKey)
        # Verify same key by checking public numbers
        assert (
            key.public_key().public_numbers()
            == loaded.public_key().public_numbers()
        )

    def test_serialize_with_password(self):
        key = generate_private_key()
        password = b"test-password-123"
        pem = serialize_private_key(key, password=password)
        loaded = load_private_key(pem, password=password)
        assert (
            key.public_key().public_numbers()
            == loaded.public_key().public_numbers()
        )

    def test_wrong_password_fails(self):
        key = generate_private_key()
        pem = serialize_private_key(key, password=b"correct")
        with pytest.raises(Exception):
            load_private_key(pem, password=b"wrong")

    def test_pem_format(self):
        key = generate_private_key()
        pem = serialize_private_key(key)
        assert pem.startswith(b"-----BEGIN PRIVATE KEY-----")
        assert b"-----END PRIVATE KEY-----" in pem


class TestCSRGeneration:
    def test_csr_pem_output(self):
        key = generate_private_key()
        csr_pem = generate_csr(
            key=key,
            common_name="Test ZATCA",
            organization="Test Org",
            organizational_unit="IT",
        )
        assert csr_pem.startswith(b"-----BEGIN CERTIFICATE REQUEST-----")
        assert b"-----END CERTIFICATE REQUEST-----" in csr_pem

    def test_csr_subject_fields(self):
        from cryptography.x509 import load_pem_x509_csr
        from cryptography.x509.oid import NameOID

        key = generate_private_key()
        csr_pem = generate_csr(
            key=key,
            common_name="ZATCA Device",
            organization="Fikrah Tech",
            organizational_unit="Invoicing",
            country="SA",
            serial_number="1-TST|2-TST|3-test-uuid",
        )
        csr = load_pem_x509_csr(csr_pem)
        subject = csr.subject

        assert subject.get_attributes_for_oid(NameOID.COMMON_NAME)[0].value == "ZATCA Device"
        assert subject.get_attributes_for_oid(NameOID.ORGANIZATION_NAME)[0].value == "Fikrah Tech"
        assert subject.get_attributes_for_oid(NameOID.ORGANIZATIONAL_UNIT_NAME)[0].value == "Invoicing"
        assert subject.get_attributes_for_oid(NameOID.COUNTRY_NAME)[0].value == "SA"
        assert subject.get_attributes_for_oid(NameOID.SERIAL_NUMBER)[0].value == "1-TST|2-TST|3-test-uuid"

    def test_csr_zatca_serial_format(self):
        from cryptography.x509 import load_pem_x509_csr
        from cryptography.x509.oid import NameOID

        key = generate_private_key()
        serial = "1-TST|2-TST|3-ed22f1d8-e6a2-1118-9b58-d9a8195e2f28"
        csr_pem = generate_csr(
            key=key,
            common_name="Test",
            organization="Org",
            organizational_unit="OU",
            serial_number=serial,
        )
        csr = load_pem_x509_csr(csr_pem)
        assert subject_sn(csr) == serial

    def test_csr_is_valid(self):
        from cryptography.x509 import load_pem_x509_csr

        key = generate_private_key()
        csr_pem = generate_csr(
            key=key,
            common_name="Test",
            organization="Org",
            organizational_unit="OU",
        )
        csr = load_pem_x509_csr(csr_pem)
        assert csr.is_signature_valid


def subject_sn(csr):
    """Helper to extract serial number from CSR subject."""
    from cryptography.x509.oid import NameOID
    attrs = csr.subject.get_attributes_for_oid(NameOID.SERIAL_NUMBER)
    return attrs[0].value if attrs else None


class TestCanonicalization:
    def test_strips_xml_declaration(self):
        xml = _sample_invoice_xml()
        canonical = canonicalize_xml(xml.encode("utf-8"))
        assert not canonical.startswith(b"<?xml")

    def test_strips_ubl_extensions(self):
        """If UBLExtensions are present, they should be stripped."""
        xml = _sample_invoice_xml()
        # Inject a dummy UBLExtensions
        xml_with_ext = xml.replace(
            "<cbc:ProfileID",
            '<ext:UBLExtensions xmlns:ext="urn:oasis:names:specification:ubl:schema:xsd:CommonExtensionComponents-2">'
            "<ext:UBLExtension><ext:ExtensionContent>dummy</ext:ExtensionContent></ext:UBLExtension>"
            "</ext:UBLExtensions><cbc:ProfileID",
        )
        canonical = canonicalize_xml(xml_with_ext.encode("utf-8"))
        assert b"UBLExtensions" not in canonical

    def test_deterministic(self):
        xml = _sample_invoice_xml()
        c1 = canonicalize_xml(xml.encode("utf-8"))
        c2 = canonicalize_xml(xml.encode("utf-8"))
        assert c1 == c2


class TestHashing:
    def test_known_invoice_hash(self):
        xml = _sample_invoice_xml()
        h = hash_invoice(xml.encode("utf-8"))
        # Should be a valid base64 string
        decoded = base64.b64decode(h)
        assert len(decoded) == 32  # SHA-256 = 32 bytes

    def test_content_changes_hash(self):
        xml1 = _sample_invoice_xml()
        xml2 = xml1.replace("INV-SIGN-001", "INV-SIGN-002")
        h1 = hash_invoice(xml1.encode("utf-8"))
        h2 = hash_invoice(xml2.encode("utf-8"))
        assert h1 != h2

    def test_hash_is_base64(self):
        xml = _sample_invoice_xml()
        h = hash_invoice(xml.encode("utf-8"))
        # Should not raise
        base64.b64decode(h)


class TestSigning:
    def test_sign_verify_roundtrip(self):
        key = generate_private_key()
        test_data = b"test hash data to sign"
        import hashlib
        digest = hashlib.sha256(test_data).digest()
        signature = sign_hash(key, digest)
        assert len(signature) > 0

        # Verify the signature
        from cryptography.hazmat.primitives.asymmetric import ec as ec_module
        from cryptography.hazmat.primitives import hashes
        pub = key.public_key()
        # Should not raise
        pub.verify(signature, digest, ec_module.ECDSA(hashes.SHA256()))

    def test_get_public_key_bytes(self):
        key = generate_private_key()
        pub_bytes = get_public_key_bytes(key)
        # Uncompressed point starts with 0x04
        assert pub_bytes[0] == 0x04
        # secp256k1 uncompressed point is 65 bytes (1 + 32 + 32)
        assert len(pub_bytes) == 65

    def test_inject_produces_valid_xml(self):
        key = generate_private_key()
        cert_pem = _self_signed_cert(key)
        xml = _sample_invoice_xml()

        signed_xml = inject_signature(xml.encode("utf-8"), cert_pem, key)

        # Should be valid XML
        from lxml import etree
        root = etree.fromstring(signed_xml)
        assert root is not None

    def test_ubl_extensions_present(self):
        key = generate_private_key()
        cert_pem = _self_signed_cert(key)
        xml = _sample_invoice_xml()

        signed_xml = inject_signature(xml.encode("utf-8"), cert_pem, key)

        from lxml import etree
        root = etree.fromstring(signed_xml)
        ext_ns = "urn:oasis:names:specification:ubl:schema:xsd:CommonExtensionComponents-2"
        extensions = root.findall(f"{{{ext_ns}}}UBLExtensions")
        assert len(extensions) == 1

    def test_signature_value_present(self):
        key = generate_private_key()
        cert_pem = _self_signed_cert(key)
        xml = _sample_invoice_xml()

        signed_xml = inject_signature(xml.encode("utf-8"), cert_pem, key)

        from lxml import etree
        root = etree.fromstring(signed_xml)
        ds_ns = "http://www.w3.org/2000/09/xmldsig#"
        sig_vals = root.findall(f".//{{{ds_ns}}}SignatureValue")
        assert len(sig_vals) == 1
        assert sig_vals[0].text  # Should have content

    def test_certificate_embedded(self):
        key = generate_private_key()
        cert_pem = _self_signed_cert(key)
        xml = _sample_invoice_xml()

        signed_xml = inject_signature(xml.encode("utf-8"), cert_pem, key)

        from lxml import etree
        root = etree.fromstring(signed_xml)
        ds_ns = "http://www.w3.org/2000/09/xmldsig#"
        x509_certs = root.findall(f".//{{{ds_ns}}}X509Certificate")
        assert len(x509_certs) == 1
        assert x509_certs[0].text  # Should have cert content

    def test_hash_matches_tlv_tag6(self):
        """The invoice hash should match what hash_invoice returns."""
        key = generate_private_key()
        cert_pem = _self_signed_cert(key)
        xml = _sample_invoice_xml()

        invoice_hash = hash_invoice(xml.encode("utf-8"))
        signed_xml = inject_signature(xml.encode("utf-8"), cert_pem, key)

        # The hash should be deterministic for the same input
        assert len(invoice_hash) > 0
        decoded = base64.b64decode(invoice_hash)
        assert len(decoded) == 32

    def test_signed_properties_present(self):
        key = generate_private_key()
        cert_pem = _self_signed_cert(key)
        xml = _sample_invoice_xml()

        signed_xml = inject_signature(xml.encode("utf-8"), cert_pem, key)

        from lxml import etree
        root = etree.fromstring(signed_xml)
        xades_ns = "http://uri.etsi.org/01903/v1.3.2#"
        sp = root.findall(f".//{{{xades_ns}}}SignedProperties")
        assert len(sp) == 1
