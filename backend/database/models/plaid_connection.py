"""
Plaid Connection Model

Per-borrower Plaid connection records for automated bank account verification
and asset report generation. Each connection represents a single Plaid Item
(one financial institution linked by a borrower).

Security:
    - access_token_encrypted stores the Plaid access token encrypted with
      the PIIEncryptionService (Fernet / AES-128-CBC). The raw token is
      NEVER stored.
    - item_id is safe to store in plaintext (non-sensitive identifier).

Usage:
    from database.models.plaid_connection import PlaidConnection

    conn = db.query(PlaidConnection).filter(
        PlaidConnection.loan_id == loan_id,
        PlaidConnection.organization_id == org_id,
        PlaidConnection.connection_status == "active",
    ).all()
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Column,
    Integer,
    String,
    DateTime,
    Text,
    ForeignKey,
    Index,
)
from sqlalchemy.dialects.postgresql import JSON
from sqlalchemy.orm import relationship

from db import Base


class PlaidConnection(Base):
    """A single Plaid Item representing a borrower's linked bank account.

    One borrower may have multiple connections (one per institution). Each
    connection can produce asset reports and transaction data used for
    underwriting analysis.

    Lifecycle:
        active       -> The item is connected and data can be pulled.
        needs_reauth -> Plaid has flagged the item for re-authentication
                        (e.g., password rotation at the institution).
        revoked      -> The access token has been invalidated via the
                        /item/remove endpoint or the borrower disconnected.
    """

    __tablename__ = "plaid_connections"
    __table_args__ = (
        Index(
            "ix_plaid_connections_org_borrower",
            "organization_id",
            "borrower_id",
        ),
        Index("ix_plaid_connections_loan_id", "loan_id"),
        Index("ix_plaid_connections_item_id", "item_id"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    organization_id = Column(
        Integer,
        ForeignKey("organizations.id"),
        nullable=False,
        index=True,
    )
    borrower_id = Column(
        Integer,
        ForeignKey("leads.id"),
        nullable=False,
        index=True,
    )
    loan_id = Column(
        Integer,
        ForeignKey("loans.id"),
        nullable=True,
    )

    # Plaid institution info
    institution_name = Column(String(255), nullable=True)
    institution_id = Column(String(100), nullable=True)

    # Encrypted access token -- NEVER store raw
    access_token_encrypted = Column(Text, nullable=False)

    # Plaid item identifier (safe to store in plaintext)
    item_id = Column(String(255), nullable=False, unique=True)

    # Connected account IDs (list of Plaid account_id strings)
    account_ids = Column(JSON, default=list)

    # Connection lifecycle status
    connection_status = Column(
        String(50),
        nullable=False,
        default="active",
    )

    # Sync tracking
    last_synced_at = Column(DateTime, nullable=True)

    # Asset report (GSE-certified)
    asset_report_id = Column(String(255), nullable=True)
    asset_report_status = Column(
        String(50),
        nullable=True,
    )  # pending, ready, error

    # Timestamps
    created_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    # Relationships
    organization = relationship("Organization", backref="plaid_connections")
    borrower = relationship("Lead", backref="plaid_connections")
    loan = relationship("Loan", backref="plaid_connections")

    @property
    def is_active(self) -> bool:
        """True when the connection is usable for data retrieval."""
        return self.connection_status == "active"


__all__ = [
    "PlaidConnection",
]
