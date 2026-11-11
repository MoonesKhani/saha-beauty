from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

class ServiceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    code: str
    name: str
    description: str
    revision: int
    price_toman: int | None = None
    is_active: bool = True

class TeamOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    code: str
    name: str
    role: str
    bio: str
    revision: int = 1
    is_active: bool = True

class CatalogOut(BaseModel):
    services: list[ServiceOut]
    team: list[TeamOut]

class ServicePatch(BaseModel):
    model_config = ConfigDict(extra='forbid')
    revision: int = Field(ge=1)
    price_toman: int | None = Field(default=None, ge=0, le=2000000000)
    name: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = Field(default=None, min_length=1, max_length=2000)

    @field_validator('name', 'description')
    @classmethod
    def clean_text(cls, value):
        if value is None:
            return value
        value = value.strip()
        if not value or any(ord(c) < 32 and c not in '\n\t' for c in value):
            raise ValueError('متن معتبر وارد کنید.')
        return value

    @model_validator(mode='after')
    def require_change(self):
        if self.name is None and self.description is None and 'price_toman' not in self.model_fields_set:
            raise ValueError('دست‌کم یک متن باید مشخص شود.')
        return self
