from typing import Annotated

from fastapi import APIRouter, Depends, Path
from sqlalchemy.orm import Session

from core.security import get_current_user
from database import get_db
from models.catalog import Category, Collection
from schemas.catalog import (
    CategoryCreate, CategoryUpdate, CategoryResponse,
    CollectionCreate, CollectionUpdate, CollectionResponse,
)
from services import catalog as service

categories_router = APIRouter(prefix="/categorias", tags=["Categorias"])
collections_router = APIRouter(prefix="/colecoes", tags=["Coleções"])
protected = [Depends(get_current_user)]
RecordId = Annotated[int, Path(gt=0, le=2_147_483_647)]
Database = Annotated[Session, Depends(get_db)]


@categories_router.get("", response_model=list[CategoryResponse])
def list_categories(db: Database, active: bool | None = None):
    return service.list_records(db, Category, active)


@categories_router.post("", response_model=CategoryResponse, status_code=201, dependencies=protected)
def create_category(data: CategoryCreate, db: Database):
    return service.create_record(db, Category, data)


@categories_router.patch("/{record_id}", response_model=CategoryResponse, dependencies=protected)
def update_category(record_id: RecordId, data: CategoryUpdate, db: Database):
    return service.update_record(db, Category, record_id, data)


@categories_router.delete("/{record_id}", status_code=204, dependencies=protected)
def delete_category(record_id: RecordId, db: Database):
    service.delete_record(db, Category, record_id)


@collections_router.get("", response_model=list[CollectionResponse])
def list_collections(db: Database, active: bool | None = None):
    return service.list_records(db, Collection, active)


@collections_router.post("", response_model=CollectionResponse, status_code=201, dependencies=protected)
def create_collection(data: CollectionCreate, db: Database):
    return service.create_record(db, Collection, data)


@collections_router.patch("/{record_id}", response_model=CollectionResponse, dependencies=protected)
def update_collection(record_id: RecordId, data: CollectionUpdate, db: Database):
    return service.update_record(db, Collection, record_id, data)


@collections_router.delete("/{record_id}", status_code=204, dependencies=protected)
def delete_collection(record_id: RecordId, db: Database):
    service.delete_record(db, Collection, record_id)
