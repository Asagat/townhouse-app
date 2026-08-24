from datetime import datetime
from typing import Optional

from pydantic import BaseModel


# ============ OWNER ============
class OwnerBase(BaseModel):
    full_name: str
    phone: Optional[str] = None

class OwnerCreate(OwnerBase):
    pass

class OwnerResponse(OwnerBase):
    id: int

    class Config:
        from_attributes = True


# ============ APARTMENT ============
class ApartmentBase(BaseModel):
    apartment_number: int
    address: str
    square: float = 0.0

class ApartmentCreate(ApartmentBase):
    owner_id: int

class ApartmentUpdate(ApartmentBase):
    owner_id: int

class ApartmentResponse(ApartmentBase):
    id: int
    owner_id: int
    owner: Optional[OwnerResponse] = None

    class Config:
        from_attributes = True


# ============ ACCOUNT ============
class AccountBase(BaseModel):
    account_number: str
    account_name: str
    is_active: bool = True

class AccountCreate(AccountBase):
    apartment_id: int

class AccountUpdate(AccountBase):
    apartment_id: int

class AccountResponse(AccountBase):
    id: int
    apartment_id: int
    apartment: Optional[ApartmentResponse] = None

    class Config:
        from_attributes = True


# ============ CASH POINT ============
class CashPointBase(BaseModel):
    name: str
    is_active: bool = True

class CashPointCreate(CashPointBase):
    pass

class CashPointUpdate(CashPointBase):
    pass

class CashPointResponse(CashPointBase):
    id: int

    class Config:
        from_attributes = True


# ============ SERVICE TYPE ============
class ServiceTypeBase(BaseModel):
    services_type: str

class ServiceTypeCreate(ServiceTypeBase):
    pass

class ServiceTypeUpdate(ServiceTypeBase):
    pass

class ServiceTypeResponse(ServiceTypeBase):
    id: int

    class Config:
        from_attributes = True


# ============ TARIFF TYPE ============
class TariffTypeBase(BaseModel):
    name: str

class TariffTypeCreate(TariffTypeBase):
    pass

class TariffTypeUpdate(TariffTypeBase):
    pass

class TariffTypeResponse(TariffTypeBase):
    id: int

    class Config:
        from_attributes = True


# ============ TARIFF ============
class TariffBase(BaseModel):
    price: float
    unit: Optional[str] = None
    valid_from: datetime

class TariffCreate(TariffBase):
    services_type_id: int
    tariff_type_id: int

class TariffUpdate(TariffBase):
    services_type_id: int
    tariff_type_id: int

class TariffResponse(TariffBase):
    id: int
    services_type_id: int
    tariff_type_id: int
    services_type: Optional[ServiceTypeResponse] = None
    tariff_type: Optional[TariffTypeResponse] = None

    class Config:
        from_attributes = True


# ============ METER ============
class MeterBase(BaseModel):
    serial_number: str
    installed_at: Optional[datetime] = None

class MeterCreate(MeterBase):
    apartment_id: int
    services_type_id: int

class MeterUpdate(MeterBase):
    apartment_id: int
    services_type_id: int

class MeterResponse(MeterBase):
    id: int
    apartment_id: int
    services_type_id: int
    apartment: Optional[ApartmentResponse] = None
    services_type: Optional[ServiceTypeResponse] = None

    class Config:
        from_attributes = True


# ============ METER READING ============
class MeterReadingBase(BaseModel):
    reading: float
    reading_date: datetime

class MeterReadingCreate(MeterReadingBase):
    meter_id: int
    services_type_id: int

class MeterReadingUpdate(MeterReadingBase):
    meter_id: int
    services_type_id: int

class MeterReadingResponse(MeterReadingBase):
    id: int
    meter_id: int
    services_type_id: int
    meter: Optional[MeterResponse] = None
    services_type: Optional[ServiceTypeResponse] = None

    class Config:
        from_attributes = True


# ============ TRANSACTION ============
class TransactionBase(BaseModel):
    transaction_date: Optional[datetime] = None
    transaction_type: str
    amount: float
    notes: Optional[str] = None

class TransactionCreate(TransactionBase):
    account_id: int
    cash_point_id: int

class TransactionUpdate(TransactionBase):
    account_id: int
    cash_point_id: int

class TransactionResponse(TransactionBase):
    id: int
    account_id: int
    cash_point_id: int
    account: Optional[AccountResponse] = None
    cash_point: Optional[CashPointResponse] = None
    apartment: Optional[ApartmentResponse] = None

    class Config:
        from_attributes = True


# ============ ACCRUALS REGISTER ============
class AccrualsRegisterBase(BaseModel):
    accrual_date: datetime
    past_reading_value: Optional[float] = None
    current_reading_value: Optional[float] = None
    consumption: float
    amount: float

class AccrualsRegisterCreate(AccrualsRegisterBase):
    account_id: int
    tariff_id: int
    services_type_id: int
    current_reading_id: Optional[int] = None

class AccrualsRegisterUpdate(AccrualsRegisterBase):
    account_id: int
    tariff_id: int
    services_type_id: int
    current_reading_id: Optional[int] = None

class AccrualsRegisterResponse(AccrualsRegisterBase):
    id: int
    account_id: int
    tariff_id: int
    services_type_id: int
    current_reading_id: Optional[int] = None
    account: Optional[AccountResponse] = None
    services_type: Optional[ServiceTypeResponse] = None
    tariff: Optional[TariffResponse] = None

    class Config:
        from_attributes = True


# ============ ACCOUNTS REGISTER ============
class AccountsRegisterBase(BaseModel):
    operation_date: Optional[datetime] = None
    income: float = 0.0
    expense: float = 0.0
    balance_after: float

class AccountsRegisterCreate(AccountsRegisterBase):
    account_id: int
    transaction_id: Optional[int] = None
    accrual_id: Optional[int] = None

class AccountsRegisterUpdate(AccountsRegisterBase):
    account_id: int
    transaction_id: Optional[int] = None
    accrual_id: Optional[int] = None

class AccountsRegisterResponse(AccountsRegisterBase):
    id: int
    account_id: int
    transaction_id: Optional[int] = None
    accrual_id: Optional[int] = None
    account: Optional[AccountResponse] = None

    class Config:
        from_attributes = True
