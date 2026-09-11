from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from core.config import settings
from database import get_db
from integrations.shipping_maps import lookup_cep
from schemas.shipping import CheckoutRequest, QuoteRequest, ShippingQuote
from services.shipping import checkout_message, create_quote
from services.shipping_policy import policy_description

router = APIRouter(prefix="/shipping", tags=["Frete"])


@router.get("/policy")
def policy():
    return {"description": policy_description(), "configured": bool(settings.SHIPPING_ORIGIN_ADDRESS.strip()
        and settings.SHIPPING_GOOGLE_API_KEY.get_secret_value())}


@router.get("/cep/{cep}")
def postal_code(cep: str):
    return lookup_cep(cep)


@router.post("/quote", response_model=ShippingQuote)
def quote(request: QuoteRequest, db: Session = Depends(get_db)):
    return create_quote(db, request)


@router.post("/checkout")
def checkout(request: CheckoutRequest, db: Session = Depends(get_db)):
    return checkout_message(db, request)
