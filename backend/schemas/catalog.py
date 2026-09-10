from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, StringConstraints, model_validator

Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]
Slug = Annotated[str, StringConstraints(min_length=1, max_length=120, pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")]


class CategoryCreate(BaseModel):
    name: Name
    slug: Slug
    active: bool = True


class CategoryUpdate(BaseModel):
    name: Name | None = None
    slug: Slug | None = None
    active: bool | None = None

    @model_validator(mode="after")
    def reject_null_fields(self):
        for field in ("name", "slug", "active"):
            if field in self.model_fields_set and getattr(self, field) is None:
                raise ValueError(f"{field} não pode ser nulo.")
        return self


class CategoryResponse(BaseModel):
    id: int
    name: str
    slug: str
    active: bool
    created_at: datetime
    updated_at: datetime
    model_config = ConfigDict(from_attributes=True)


class CollectionCreate(CategoryCreate):
    description: Annotated[str, StringConstraints(max_length=10000)] | None = None


class CollectionUpdate(CategoryUpdate):
    description: Annotated[str, StringConstraints(max_length=10000)] | None = None


class CollectionResponse(CategoryResponse):
    description: str | None
