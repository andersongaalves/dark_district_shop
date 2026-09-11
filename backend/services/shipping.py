"""Short-lived signed quotes. No delivery address is persisted in the database."""
import base64
from decimal import Decimal, ROUND_HALF_UP
import hashlib
import hmac
import json
import re
import time
import unicodedata
from typing import get_args

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from core.config import settings
from integrations.shipping_maps import delivery_distances
from models.produto import Produto
from schemas.produto import Garment, ProdutoResponse
from schemas.shipping import ShippingQuote
from services.customer_service import SupportError
from services.shipping_policy import money, policy_description, policy_values, shipping_price


def _digest(data):
    return hashlib.sha256(json.dumps(data, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()


def _policy_digest():
    return _digest({**policy_values(), "origin": settings.SHIPPING_ORIGIN_ADDRESS,
        "lat": settings.SHIPPING_ORIGIN_LATITUDE, "lng": settings.SHIPPING_ORIGIN_LONGITUDE})


def _clothing(category):
    name = "".join(c for c in unicodedata.normalize("NFKD", (category or "").lower()) if not unicodedata.combining(c))
    words = (*get_args(Garment), "roupa", "vestuario", "conjunto", "casaco", "body", "moleton")
    return bool(re.search(r"\b(?:" + "|".join(words) + r")s?\b", name))


def basket(db, requested):
    products = db.scalars(select(Produto).where(Produto.id.in_({item.product_id for item in requested}))
        .options(selectinload(Produto.variants), selectinload(Produto.images))).all()
    by_id = {product.id: product for product in products}
    lines = []
    for item in requested:
        product = by_id.get(item.product_id)
        if not product or not product.available:
            raise SupportError("Um produto não está mais disponível. Atualize seus itens.", 409)
        variant = next((entry for entry in product.variants if entry.id == item.variant_id), None)
        if (product.variants and variant is None) or (not product.variants and item.variant_id is not None):
            raise SupportError("Uma variante mudou. Selecione novamente o tamanho e a cor.", 409)
        if variant and variant.quantity < item.quantity:
            raise SupportError("Estoque insuficiente. Revise as quantidades antes de continuar.", 409)
        price = ProdutoResponse.model_validate(product).effective_price
        unit_cents = int((Decimal(str(price)) * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
        lines.append({"product_id": item.product_id, "variant_id": item.variant_id, "quantity": item.quantity,
            "title": product.title, "size": variant.size or "" if variant else "", "color": variant.color or "" if variant else "",
            "unit_cents": unit_cents, "line_cents": unit_cents * item.quantity, "clothing": _clothing(product.category)})
    return sorted(lines, key=lambda line: (line["product_id"], line["variant_id"] or 0))


def _sign(payload):
    data = base64.urlsafe_b64encode(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).rstrip(b"=")
    signature = hmac.new(settings.SECRET_KEY.get_secret_value().encode(), b"dd-shipping-v1:" + data, hashlib.sha256).hexdigest()
    return data.decode() + "." + signature


def _verify(token):
    try:
        data, signature = token.split(".")
        expected = hmac.new(settings.SECRET_KEY.get_secret_value().encode(), b"dd-shipping-v1:" + data.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected, signature):
            raise ValueError("signature")
        payload = json.loads(base64.b64decode(data + "=" * (-len(data) % 4), altchars=b"-_", validate=True))
        if payload["v"] != 1 or payload["exp"] <= int(time.time()) or payload["policy"] != _policy_digest():
            raise ValueError("expired")
        return payload
    except (ValueError, KeyError, TypeError):
        raise SupportError("A cotação expirou ou mudou. Calcule o frete novamente.", 409) from None


def create_quote(db, request):
    # Avoid spending a Maps request on an already invalid basket; release SQL
    # before external IO, then reprice after the route lookup.
    basket(db, request.items)
    db.rollback()
    radius, route = delivery_distances(request.address)
    lines = basket(db, request.items)
    db.rollback()
    subtotal = sum(line["line_cents"] for line in lines)
    clothing = sum(line["line_cents"] for line in lines if line["clothing"])
    fee = shipping_price(clothing, radius, route)
    expires = int(time.time()) + settings.SHIPPING_QUOTE_SECONDS
    payload = {"v": 1, "exp": expires, "policy": _policy_digest(), "basket": _digest(lines),
        "address": _digest(request.address.model_dump()), "radius": radius, "route": route, "fee": fee}
    return ShippingQuote(quote_token=_sign(payload), expires_at=expires, subtotal_cents=subtotal,
        clothing_subtotal_cents=clothing, shipping_cents=fee, total_cents=subtotal + fee,
        radius_meters=radius, route_meters=route, free_shipping=fee == 0, policy=policy_description())


def checkout_message(db, request):
    quoted = _verify(request.quote_token)
    lines = basket(db, request.items)
    if _digest(lines) != quoted["basket"] or _digest(request.address.model_dump()) != quoted["address"]:
        raise SupportError("Os itens, preços ou endereço mudaram. Revise e calcule o frete novamente.", 409)
    clothing = sum(line["line_cents"] for line in lines if line["clothing"])
    fee = shipping_price(clothing, quoted["radius"], quoted["route"])
    if fee != quoted["fee"]:
        raise SupportError("O frete mudou. Calcule novamente.", 409)
    subtotal = sum(line["line_cents"] for line in lines)
    address = request.address
    message = ["Olá! Gostaria de confirmar a compra:"]
    for line in lines:
        selection = " / ".join(filter(None, [line["size"], line["color"]]))
        message.append(f"{line['quantity']} × {line['title']} (ID: {line['product_id']}, variante: {line['variant_id'] or 'sem variante'})"
                       f"{' — ' + selection if selection else ''}: {money(line['line_cents'])}")
    message += [f"Subtotal: {money(subtotal)}", f"Frete: {'Grátis' if fee == 0 else money(fee)}", f"Total: {money(subtotal + fee)}",
        f"Trajeto: {quoted['route'] / 1000:.3f} km; distância em linha reta: {quoted['radius'] / 1000:.3f} km",
        f"Recebedor: {address.recipient}", f"Telefone: {address.phone}",
        f"Entrega: {address.street}, {address.number} — {address.neighborhood}, {address.city}/{address.state}, CEP {address.cep}"]
    if address.complement:
        message.append(f"Complemento: {address.complement}")
    if address.reference:
        message.append(f"Referência: {address.reference}")
    message.append("A cotação não reserva estoque nem confirma pagamento. Aguardo a confirmação da loja.")
    return {"message": "\n".join(message)}
