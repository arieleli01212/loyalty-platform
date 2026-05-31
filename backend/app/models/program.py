from datetime import datetime
from enum import Enum
from typing import Optional
from sqlmodel import Field, SQLModel


class ProgramType(str, Enum):
    stamp = "stamp"


class RewardProgram(SQLModel, table=True):
    __tablename__ = "rewardprogram"

    id: Optional[int] = Field(default=None, primary_key=True)
    business_id: int = Field(foreign_key="business.id", index=True)
    name: str
    type: ProgramType = Field(default=ProgramType.stamp)
    stamps_required: int
    reward_description: str
    active: bool = Field(default=True)
    created_at: datetime = Field(default_factory=datetime.utcnow)
