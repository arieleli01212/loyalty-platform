import secrets
import uuid
from datetime import datetime
from enum import Enum
from typing import Optional
from sqlmodel import Field, SQLModel, UniqueConstraint


class WalletPlatform(str, Enum):
    apple = "apple"
    google = "google"
    stub = "stub"
    none = "none"


class CardStatus(str, Enum):
    active = "active"
    suspended = "suspended"
    expired = "expired"


class LoyaltyCard(SQLModel, table=True):
    __tablename__ = "loyaltycard"
    __table_args__ = (UniqueConstraint("customer_id", "program_id", name="uq_customer_program"),)

    id: Optional[int] = Field(default=None, primary_key=True)
    business_id: int = Field(foreign_key="business.id", index=True)
    customer_id: int = Field(foreign_key="customer.id", index=True)
    program_id: int = Field(foreign_key="rewardprogram.id", index=True)
    current_stamps: int = Field(default=0)
    rewards_available: int = Field(default=0)
    lifetime_stamps: int = Field(default=0)
    pass_serial: str = Field(unique=True, default_factory=lambda: str(uuid.uuid4()))
    wallet_platform: WalletPlatform = Field(default=WalletPlatform.stub)
    barcode_token: str = Field(unique=True, default_factory=lambda: secrets.token_urlsafe(32))
    status: CardStatus = Field(default=CardStatus.active)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    last_activity_at: datetime = Field(default_factory=datetime.utcnow)
