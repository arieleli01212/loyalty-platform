from pydantic import BaseModel, EmailStr


class OtpRequestRequest(BaseModel):
    name: str
    email: EmailStr


class OtpRequestResponse(BaseModel):
    sent: bool = True


class OtpVerifyRequest(BaseModel):
    name: str
    email: EmailStr
    code: str


class GoogleEnrollRequest(BaseModel):
    id_token: str


class EnrollResponse(BaseModel):
    customer_id: int
    card_id: int
    pass_serial: str
    pass_url: str
    current_stamps: int
    stamps_required: int
    reward_description: str
    email: str
    email_verified: bool
