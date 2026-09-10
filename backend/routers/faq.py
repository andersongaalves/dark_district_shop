from fastapi import APIRouter, Response

from schemas.faq import FAQItem
from services.faq import list_faq

router = APIRouter(prefix="/faq", tags=["FAQ"])


@router.get("", response_model=list[FAQItem])
def get_faq(response: Response):
    response.headers["Cache-Control"] = "no-cache"
    return list_faq()
