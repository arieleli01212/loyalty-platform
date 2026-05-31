from typing import Optional
from pydantic import BaseModel
from app.models.customer import ContactType


class EnrollRequest(BaseModel):
    name: str
    contact: str
    contact_type: ContactType
    enrollment_channel: Optional[str] = "qr"


class EnrollResponse(BaseModel):
    customer_id: int
    card_id: int
    pass_serial: str
    pass_url: str
    current_stamps: int
    stamps_required: int
    reward_description: str
