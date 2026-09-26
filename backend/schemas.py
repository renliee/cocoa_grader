"""Validated HTTP input for the persistent workflow."""
from pydantic import BaseModel, Field


class SignupIn(BaseModel):
    display_name: str = Field(min_length=2, max_length=80)
    login: str = Field(min_length=3, max_length=64)
    password: str = Field(min_length=10, max_length=128)
    password_confirmation: str


class LoginIn(BaseModel):
    login: str
    password: str


class ProfilePatch(BaseModel):
    display_name: str = Field(min_length=2, max_length=80)


class SupplierIn(BaseModel):
    name: str = Field(min_length=2, max_length=80)
    code: str = Field(min_length=2, max_length=8)
    contact: str = Field(default='', max_length=120)
    notes: str = Field(default='', max_length=1000)


class SupplierPatch(BaseModel):
    name: str = Field(min_length=2, max_length=80)
    contact: str = Field(default='', max_length=120)
    notes: str = Field(default='', max_length=1000)


class LotIn(BaseModel):
    supplier_id: str = Field(min_length=1)


class DraftPatch(BaseModel):
    expected_version: int = Field(ge=1)
    weight_kg: str | None = None
    notes: str = Field(default='', max_length=1000)
    wizard_step: str = 'lot'
    supplier_id: str | None = None


class PhotoReview(BaseModel):
    expected_input_version: int = Field(ge=0)
    review_state: str


class ExpectedInput(BaseModel):
    expected_input_version: int = Field(ge=0)


class AnalyzeIn(BaseModel):
    expected_input_version: int = Field(ge=0)
    confirm_small_sample: bool = False


class FinalizeIn(BaseModel):
    expected_version: int = Field(ge=1)


class LotVersionIn(BaseModel):
    expected_lot_version: int = Field(ge=1)
