from datetime import datetime
from typing import Optional
from sqlmodel import Field, SQLModel


class Business(SQLModel, table=True):
    __tablename__ = "business"

    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = Field(index=True)
    slug: str = Field(unique=True, index=True)
    owner_user_id: int = Field(foreign_key="merchantuser.id")
    logo_url: Optional[str] = None
    bg_color: str = Field(default="#FFFFFF")
    fg_color: str = Field(default="#000000")
    label_color: str = Field(default="#000000")
    created_at: datetime = Field(default_factory=datetime.utcnow)
