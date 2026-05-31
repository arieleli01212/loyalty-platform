from pydantic import BaseModel
from app.models.scan_event import ScanType


class ScanRequest(BaseModel):
    barcode_token: str
    action: ScanType


class ScanResponse(BaseModel):
    card_id: int
    current_stamps: int
    rewards_available: int
    lifetime_stamps: int
    action: str
    message: str
