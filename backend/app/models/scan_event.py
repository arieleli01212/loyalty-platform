from datetime import datetime
from enum import Enum
from typing import Optional
from sqlmodel import Field, SQLModel


class ScanType(str, Enum):
    stamp = "stamp"
    redeem = "redeem"


class ScanSource(str, Enum):
    scanner = "scanner"
    manual = "manual"


class ScanEvent(SQLModel, table=True):
    __tablename__ = "scanevent"

    id: Optional[int] = Field(default=None, primary_key=True)
    card_id: int = Field(foreign_key="loyaltycard.id", index=True)
    business_id: int = Field(foreign_key="business.id", index=True)
    staff_user_id: int = Field(foreign_key="merchantuser.id", index=True)
    type: ScanType
    created_at: datetime = Field(default_factory=datetime.utcnow)
    source: ScanSource = Field(default=ScanSource.scanner)
    idempotency_key: Optional[str] = Field(default=None, index=True)
