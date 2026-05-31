from datetime import datetime
from typing import Optional
from sqlmodel import Field, SQLModel, UniqueConstraint


class Customer(SQLModel, table=True):
    __tablename__ = "customer"
    __table_args__ = (UniqueConstraint("business_id", "email", name="uq_customer_business_email"),)

    id: Optional[int] = Field(default=None, primary_key=True)
    business_id: int = Field(foreign_key="business.id", index=True)
    name: str
    email: str = Field(index=True)
    email_verified: bool = Field(default=False)
    google_sub: Optional[str] = Field(default=None, index=True)
    enrolled_at: datetime = Field(default_factory=datetime.utcnow)
    enrollment_channel: str
