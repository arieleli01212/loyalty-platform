from typing import Protocol, runtime_checkable


@runtime_checkable
class EmailProvider(Protocol):
    async def send_otp(self, to_email: str, code: str, business_name: str) -> None:
        ...
