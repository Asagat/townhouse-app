from datetime import datetime
from typing import Optional

from pydantic import BaseModel

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

class TransactionOut(BaseModel):
    id: int
    amount: float
    transaction_type: str
    transaction_date: Optional[datetime] = None
    account_id: Optional[int] = None
    cash_point_id: Optional[int] = None
    notes: Optional[str] = None
    class Config:
        from_attributes = True
