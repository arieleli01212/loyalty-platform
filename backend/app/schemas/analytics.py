from typing import Dict
from pydantic import BaseModel


class AnalyticsSummary(BaseModel):
    total_customers: int
    total_cards: int
    total_installs: int
    stamps_issued: int
    rewards_redeemed: int
    active_customers: int
    drifting_customers: int
    channel_breakdown: Dict[str, int]
