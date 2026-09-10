from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from models.catalog import Category, Collection
from models.produto import Produto


class CatalogError(Exception):
    def __init__(self, message: str, status_code: int = 422):
        super().__init__(message)
        self.status_code = status_code


def list_records(db: Session, model, active: bool | None = None):
    query = select(model).order_by(model.name, model.id)
    if active is not None:
        query = query.where(model.active == active)
    return db.scalars(query).all()


def get_record(db: Session, model, record_id: int):
    record = db.scalar(select(model).where(model.id == record_id).with_for_update())
    if record is None:
        raise CatalogError("Categoria ou coleção não encontrada.", 404)
    return record


def resolve_reference(db: Session, model, record_id: int, current_id: int | None):
    record = get_record(db, model, record_id)
    if not record.active and record.id != current_id:
        raise CatalogError("Categoria ou coleção desativada. Selecione uma opção ativa.")
    return record


def _save(db: Session, record):
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise CatalogError("Já existe um registro com este nome ou slug.", 409) from None
    db.refresh(record)
    return record


def create_record(db: Session, model, data):
    record = model(**data.model_dump())
    db.add(record)
    return _save(db, record)


def update_record(db: Session, model, record_id: int, data):
    record = get_record(db, model, record_id)
    fields = data.model_dump(exclude_unset=True)
    for name, value in fields.items():
        setattr(record, name, value)
    if model is Category and "name" in fields:
        # Keep the legacy text response synchronized with its relational category.
        db.execute(update(Produto).where(Produto.category_id == record.id).values(category=record.name))
    return _save(db, record)


def delete_record(db: Session, model, record_id: int):
    record = get_record(db, model, record_id)
    reference = Produto.category_id if model is Category else Produto.collection_id
    if db.scalar(select(Produto.id).where(reference == record.id).limit(1)) is not None:
        raise CatalogError("Existem produtos vinculados. Desative o registro ou altere os vínculos antes de excluir.", 409)
    try:
        db.delete(record)
        db.commit()
    except IntegrityError:
        db.rollback()
        raise CatalogError("Existem produtos vinculados. O registro não pode ser excluído.", 409) from None
