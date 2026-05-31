from dataclasses import dataclass
from typing import Protocol

from app.models.loyalty_card import LoyaltyCard


@dataclass
class PassArtifact:
    platform: str
    url: str  # for stub: URL to hosted pass page; for apple: .pkpass bytes


class WalletProvider(Protocol):
    def create_pass(self, card: LoyaltyCard) -> PassArtifact: ...
    def update_pass(self, card: LoyaltyCard) -> None: ...
    def revoke_pass(self, card: LoyaltyCard) -> None: ...
