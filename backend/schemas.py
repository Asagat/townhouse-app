from pydantic import BaseModel
from typing import Optional

class OwnerBase(BaseModel):
    full_name: str
    phone: Optional[str] = None

class OwnerCreate(OwnerBase):
    pass

class OwnerOut(OwnerBase):
    id: int
    class Config:
        from_attributes = True

class ApartmentBase(BaseModel):
    apartment_number: int
    address: str
    square: float = 0.0

class ApartmentCreate(ApartmentBase):
    owner_id: int

class ApartmentOut(ApartmentBase):
    id: int
    owner_id: int
    class Config:
        from_attributes = True
