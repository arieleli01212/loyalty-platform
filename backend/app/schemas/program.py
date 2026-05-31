from datetime import datetime
from typing import Optional
from pydantic import BaseModel
from app.models.program import ProgramType


class ProgramCreate(BaseModel):
    name: str
    type: ProgramType = ProgramType.stamp
    stamps_required: int
    reward_description: str
    active: bool = True


class ProgramRead(BaseModel):
    id: int
    business_id: int
    name: str
    type: ProgramType
    stamps_required: int
    reward_description: str
    active: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class ProgramUpdate(BaseModel):
    name: Optional[str] = None
    stamps_required: Optional[int] = None
    reward_description: Optional[str] = None
    active: Optional[bool] = None
