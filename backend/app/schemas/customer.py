from datetime import datetime
from typing import Optional
from pydantic import BaseModel

from app.models.customer import ContactType
from app.models.loyalty_card import CardStatus


class CustomerListItem(BaseModel):
    customer_id: int
    name: str
    contact: str
    contact_type: ContactType
    enrolled_at: datetime
    enrollment_channel: str
    # Card fields — null when no card exists
    current_stamps: Optional[int] = None
    rewards_available: Optional[int] = None
    lifetime_stamps: Optional[int] = None
    last_activity_at: Optional[datetime] = None
    status: Optional[CardStatus] = None

    model_config = {"from_attributes": True}
