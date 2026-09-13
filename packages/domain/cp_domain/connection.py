import enum
from datetime import datetime

from cp_shared.db import Base, TenantScopedMixin, TimestampMixin, UUIDPrimaryKeyMixin
from sqlalchemy import DateTime, String, Text
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.schema import UniqueConstraint


class ConnectionPlatform(str, enum.Enum):
    WOOCOMMERCE = "woocommerce"
    ALLEGRO = "allegro"
    SHOPER = "shoper"
    PRESTASHOP = "prestashop"
    IDOSELL = "idosell"


class ConnectionStatus(str, enum.Enum):
    CONNECTED = "connected"
    DISCONNECTED = "disconnected"
    ERROR = "error"


class Connection(UUIDPrimaryKeyMixin, TenantScopedMixin, TimestampMixin, Base):
    __tablename__ = "connections"
    __table_args__ = (UniqueConstraint("tenant_id", "name", name="uq_connection_tenant_name"),)

    platform: Mapped[ConnectionPlatform] = mapped_column(
        SAEnum(ConnectionPlatform, name="connection_platform"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    status: Mapped[ConnectionStatus] = mapped_column(
        SAEnum(ConnectionStatus, name="connection_status"),
        nullable=False,
        default=ConnectionStatus.DISCONNECTED,
    )
    # Fernet-encrypted JSON blob (see app/core/crypto.py) - never plaintext
    # API keys/tokens at rest, per CLAUDE.md.
    encrypted_credentials: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)

    offers: Mapped[list["Offer"]] = relationship(back_populates="connection")  # noqa: F821
