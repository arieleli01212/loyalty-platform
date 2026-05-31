from datetime import datetime
from enum import Enum
from typing import Optional
from sqlmodel import Field, SQLModel


class UserRole(str, Enum):
    owner = "owner"
    staff = "staff"


class MerchantUser(SQLModel, table=True):
    __tablename__ = "merchantuser"

    id: Optional[int] = Field(default=None, primary_key=True)
    business_id: Optional[int] = Field(default=None, foreign_key="business.id")
    email: str = Field(unique=True, index=True)
    hashed_password: str
    role: UserRole = Field(default=UserRole.owner)
    created_at: datetime = Field(default_factory=datetime.utcnow)
