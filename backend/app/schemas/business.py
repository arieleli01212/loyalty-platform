from datetime import datetime
from typing import Optional
from pydantic import BaseModel, EmailStr


class BusinessRead(BaseModel):
    id: int
    name: str
    slug: str
    owner_user_id: int
    logo_url: Optional[str]
    bg_color: str
    fg_color: str
    label_color: str
    created_at: datetime

    model_config = {"from_attributes": True}


class BusinessUpdate(BaseModel):
    name: Optional[str] = None
    logo_url: Optional[str] = None
    bg_color: Optional[str] = None
    fg_color: Optional[str] = None
    label_color: Optional[str] = None


class StaffCreate(BaseModel):
    email: EmailStr
    password: str


class StaffOut(BaseModel):
    id: int
    email: str
    role: str
    created_at: datetime

    model_config = {"from_attributes": True}
