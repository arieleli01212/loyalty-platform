from datetime import datetime
from typing import Optional
from sqlmodel import Field, SQLModel, UniqueConstraint


class EnrollmentOTP(SQLModel, table=True):
    __tablename__ = "enrollmentotp"
    __table_args__ = (UniqueConstraint("business_id", "email", name="uq_otp_business_email"),)

    id: Optional[int] = Field(default=None, primary_key=True)
    business_id: int = Field(foreign_key="business.id", index=True)
    email: str = Field(index=True)
    code_hash: str
    expires_at: datetime
    attempts: int = Field(default=0)
    created_at: datetime = Field(default_factory=datetime.utcnow)
