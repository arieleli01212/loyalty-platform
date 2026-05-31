from app.models.loyalty_card import LoyaltyCard
from app.services.wallet.provider import PassArtifact


class StubWalletProvider:
    def create_pass(self, card: LoyaltyCard) -> PassArtifact:
        return PassArtifact(
            platform="stub",
            url=f"/stub-pass/{card.pass_serial}",
        )

    def update_pass(self, card: LoyaltyCard) -> None:
        return None

    def revoke_pass(self, card: LoyaltyCard) -> None:
        return None
