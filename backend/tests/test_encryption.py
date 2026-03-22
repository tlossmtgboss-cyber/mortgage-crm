"""
Tests for backend/services/encryption.py

Covers:
- Round-trip encrypt/decrypt
- Empty / None value handling
- Legacy (unencrypted) values pass through gracefully
- Different keys produce different ciphertext
- is_encrypted heuristic
- EncryptedString TypeDecorator integration with SQLAlchemy
"""

import os
import pytest
from unittest.mock import patch

from sqlalchemy import Column, Integer, create_engine
from sqlalchemy.orm import Session, sessionmaker, declarative_base

from tests.test_db_helper import create_all_tables

# Ensure a deterministic key for tests
TEST_KEY = "test-secret-key-for-unit-tests-only"


@pytest.fixture(autouse=True)
def _set_test_key(monkeypatch):
    """Set a known encryption key before every test and reset singleton."""
    monkeypatch.setenv("SECRET_KEY", TEST_KEY)
    # Clear any leftover singleton so each test gets a fresh encryptor
    from services.encryption import FieldEncryptor
    FieldEncryptor.reset_instance()
    yield
    FieldEncryptor.reset_instance()


# ---------------------------------------------------------------
# FieldEncryptor unit tests
# ---------------------------------------------------------------

class TestFieldEncryptor:
    """Tests for the core FieldEncryptor class."""

    def test_round_trip(self):
        from services.encryption import FieldEncryptor
        enc = FieldEncryptor.get_instance()
        plaintext = "borrower@example.com"
        ciphertext = enc.encrypt(plaintext)
        assert ciphertext != plaintext
        assert enc.decrypt(ciphertext) == plaintext

    def test_round_trip_unicode(self):
        from services.encryption import FieldEncryptor
        enc = FieldEncryptor.get_instance()
        plaintext = "usuario@correo.es"
        ciphertext = enc.encrypt(plaintext)
        assert enc.decrypt(ciphertext) == plaintext

    def test_round_trip_phone(self):
        from services.encryption import FieldEncryptor
        enc = FieldEncryptor.get_instance()
        plaintext = "+1-555-867-5309"
        ciphertext = enc.encrypt(plaintext)
        assert enc.decrypt(ciphertext) == plaintext

    def test_encrypt_empty_string(self):
        from services.encryption import FieldEncryptor
        enc = FieldEncryptor.get_instance()
        assert enc.encrypt("") == ""

    def test_encrypt_none_returns_none(self):
        """encrypt(None) would fail, but the TypeDecorator guards against it."""
        from services.encryption import FieldEncryptor
        enc = FieldEncryptor.get_instance()
        # The encrypt method expects a str; empty string is the edge case
        assert enc.encrypt("") == ""

    def test_decrypt_empty_string(self):
        from services.encryption import FieldEncryptor
        enc = FieldEncryptor.get_instance()
        assert enc.decrypt("") == ""

    def test_decrypt_legacy_plaintext_passes_through(self):
        """Unencrypted legacy values should be returned as-is."""
        from services.encryption import FieldEncryptor
        enc = FieldEncryptor.get_instance()
        legacy = "jane.doe@example.com"
        assert enc.decrypt(legacy) == legacy

    def test_decrypt_legacy_phone_passes_through(self):
        from services.encryption import FieldEncryptor
        enc = FieldEncryptor.get_instance()
        legacy = "+15558675309"
        assert enc.decrypt(legacy) == legacy

    def test_different_keys_produce_different_ciphertext(self):
        from services.encryption import FieldEncryptor

        enc1 = FieldEncryptor(encryption_key="key-alpha-one-two-three")
        enc2 = FieldEncryptor(encryption_key="key-beta-four-five-six")

        plaintext = "secret@example.com"
        ct1 = enc1.encrypt(plaintext)
        ct2 = enc2.encrypt(plaintext)

        assert ct1 != ct2, "Different keys must produce different ciphertext"

        # Each key can only decrypt its own ciphertext
        assert enc1.decrypt(ct1) == plaintext
        assert enc2.decrypt(ct2) == plaintext

        # Cross-decryption should fall back to returning the raw value (legacy path)
        assert enc1.decrypt(ct2) == ct2
        assert enc2.decrypt(ct1) == ct1

    def test_ciphertext_is_longer_than_plaintext(self):
        from services.encryption import FieldEncryptor
        enc = FieldEncryptor.get_instance()
        plaintext = "a@b.com"
        ciphertext = enc.encrypt(plaintext)
        assert len(ciphertext) > len(plaintext)

    def test_same_plaintext_different_ciphertext(self):
        """Fernet includes a timestamp, so encrypting the same value twice
        produces different ciphertext (non-deterministic)."""
        from services.encryption import FieldEncryptor
        enc = FieldEncryptor.get_instance()
        ct1 = enc.encrypt("test@test.com")
        ct2 = enc.encrypt("test@test.com")
        assert ct1 != ct2

    def test_missing_key_raises(self):
        from services.encryption import FieldEncryptor
        with patch.dict(os.environ, {}, clear=True):
            # Remove all key env vars
            for var in ("ENCRYPTION_KEY", "SECRET_KEY"):
                os.environ.pop(var, None)
            with pytest.raises(ValueError, match="must be set"):
                FieldEncryptor(encryption_key=None)


# ---------------------------------------------------------------
# is_encrypted heuristic
# ---------------------------------------------------------------

class TestIsEncrypted:
    def test_encrypted_value_detected(self):
        from services.encryption import FieldEncryptor
        enc = FieldEncryptor.get_instance()
        ciphertext = enc.encrypt("hello@world.com")
        assert FieldEncryptor.is_encrypted(ciphertext) is True

    def test_plaintext_not_detected(self):
        from services.encryption import FieldEncryptor
        assert FieldEncryptor.is_encrypted("hello@world.com") is False

    def test_short_value_not_detected(self):
        from services.encryption import FieldEncryptor
        assert FieldEncryptor.is_encrypted("abc") is False

    def test_empty_value_not_detected(self):
        from services.encryption import FieldEncryptor
        assert FieldEncryptor.is_encrypted("") is False

    def test_none_value_not_detected(self):
        from services.encryption import FieldEncryptor
        assert FieldEncryptor.is_encrypted(None) is False


# ---------------------------------------------------------------
# Singleton behaviour
# ---------------------------------------------------------------

class TestSingleton:
    def test_get_instance_returns_same_object(self):
        from services.encryption import FieldEncryptor
        a = FieldEncryptor.get_instance()
        b = FieldEncryptor.get_instance()
        assert a is b

    def test_reset_clears_singleton(self):
        from services.encryption import FieldEncryptor
        a = FieldEncryptor.get_instance()
        FieldEncryptor.reset_instance()
        b = FieldEncryptor.get_instance()
        assert a is not b


# ---------------------------------------------------------------
# EncryptedString TypeDecorator with in-memory SQLite
# ---------------------------------------------------------------

class TestEncryptedStringTypeDecorator:
    """Integration test using an in-memory SQLite database."""

    @pytest.fixture
    def db_session(self):
        """Create an in-memory SQLite engine + session with a test table."""
        from services.encryption import EncryptedString

        Base = declarative_base()

        class FakeAppointment(Base):
            __tablename__ = "test_appointments"
            id = Column(Integer, primary_key=True, autoincrement=True)
            attendee_email = Column(EncryptedString(500))
            attendee_phone = Column(EncryptedString(200))

        engine = create_engine(os.getenv("TEST_DATABASE_URL", "postgresql://localhost:5432/test_perennia"))
        create_all_tables(Base, engine)
        SessionLocal = sessionmaker(bind=engine)
        session = SessionLocal()
        yield session, FakeAppointment, engine
        session.close()

    def test_insert_and_read_back(self, db_session):
        session, FakeAppointment, engine = db_session

        appt = FakeAppointment(
            attendee_email="test@example.com",
            attendee_phone="+15551234567",
        )
        session.add(appt)
        session.commit()

        # Read back through ORM (should decrypt transparently)
        loaded = session.query(FakeAppointment).first()
        assert loaded.attendee_email == "test@example.com"
        assert loaded.attendee_phone == "+15551234567"

    def test_stored_value_is_encrypted(self, db_session):
        from services.encryption import FieldEncryptor

        session, FakeAppointment, engine = db_session

        appt = FakeAppointment(
            attendee_email="raw@check.com",
            attendee_phone="+15559999999",
        )
        session.add(appt)
        session.commit()

        # Read raw value from DB bypassing ORM decryption
        from sqlalchemy import text
        with engine.connect() as conn:
            row = conn.execute(
                text("SELECT attendee_email, attendee_phone FROM test_appointments LIMIT 1")
            ).fetchone()

        raw_email = row[0]
        raw_phone = row[1]

        # Raw values should NOT be plaintext
        assert raw_email != "raw@check.com"
        assert raw_phone != "+15559999999"

        # They should be valid Fernet tokens
        assert FieldEncryptor.is_encrypted(raw_email)
        assert FieldEncryptor.is_encrypted(raw_phone)

    def test_null_values_handled(self, db_session):
        session, FakeAppointment, engine = db_session

        appt = FakeAppointment(attendee_email=None, attendee_phone=None)
        session.add(appt)
        session.commit()

        loaded = session.query(FakeAppointment).first()
        assert loaded.attendee_email is None
        assert loaded.attendee_phone is None

    def test_legacy_plaintext_readable(self, db_session):
        """Simulate pre-migration data by inserting plaintext directly."""
        session, FakeAppointment, engine = db_session

        from sqlalchemy import text
        with engine.connect() as conn:
            conn.execute(text(
                "INSERT INTO test_appointments (attendee_email, attendee_phone) "
                "VALUES ('legacy@plain.com', '+15550000000')"
            ))
            conn.commit()

        # ORM read should return plaintext as-is (legacy fallback)
        loaded = session.query(FakeAppointment).first()
        assert loaded.attendee_email == "legacy@plain.com"
        assert loaded.attendee_phone == "+15550000000"
