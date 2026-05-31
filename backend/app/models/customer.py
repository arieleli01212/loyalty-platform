from datetime import datetime
from enum import Enum
from typing import Optional
from sqlmodel import Field, SQLModel


class ContactType(str, Enum):
    email = "email"
    phone = "phone"


class Customer(SQLModel, table=True):
    __tablename__ = "customer"

    id: Optional[int] = Field(default=None, primary_key=True)
    business_id: int = Field(foreign_key="business.id", index=True)
    name: str
    contact: str
    contact_type: ContactType
    enrolled_at: datetime = Field(default_factory=datetime.utcnow)
    enrollment_channel: str
