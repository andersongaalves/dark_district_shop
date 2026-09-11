import base64
import json
import logging
import time

import httpx
import pytest
from pydantic import SecretStr

from core.config import settings
from integrations import shipping_maps as maps
from models.produto import Produto
from schemas.shipping import DeliveryAddress
from services import shipping
from services.customer_service import SupportError
from services.shipping_policy import shipping_price, policy_description
from services.faq import list_faq
from services import ai_agent
from test_faq import incoming
from test_catalog_tools import create_product


ADDRESS = dict(recipient="Cliente Teste", phone="74999990000", cep="48900000",
    street="Rua Teste", number="12", neighborhood="Centro", city="Juazeiro", state="BA",
    complement="Casa", reference="Portão azul")


@pytest.mark.parametrize("subtotal,radius,route,fee", [
    (0, 0, 0, 600), (9999, 1900, 1900, 600), (9999, 1901, 1901, 600),
    (9999, 2000, 2000, 615), (9999, 2900, 2900, 750),
    (10000, 7000, 9000, 0), (10000, 7001, 8000, 1515), (9999, 7000, 8000, 1515),
])
def test_tariff_boundaries(subtotal, radius, route, fee):
    assert shipping_price(subtotal, radius, route) == fee


@pytest.fixture
def purchase(client, db, monkeypatch):
    product = create_product(client, price=100, category="Camisetas")
    def distances(_):
        assert not db.in_transaction(), "External lookup must not hold a database transaction"
        return 7000, 8000
    monkeypatch.setattr(shipping, "delivery_distances", distances)
    return {"address": dict(ADDRESS), "items": [{"product_id": product["id"],
        "variant_id": product["variants"][0]["id"], "quantity": 1}]}


def quote(client, purchase):
    response = client.post("/shipping/quote", json=purchase)
    assert response.status_code == 200, response.text
    assert response.headers["cache-control"] == "no-store"
    return response.json()


def test_quote_checkout_reprices_and_contains_delivery_details(client, purchase):
    result = quote(client, purchase)
    assert result["shipping_cents"] == 0
    assert result["total_cents"] == result["clothing_subtotal_cents"] == 10000
    token = result["quote_token"].split(".")[0]
    claims = base64.urlsafe_b64decode(token + "=" * (-len(token) % 4)).decode()
    assert ADDRESS["recipient"] not in claims and ADDRESS["street"] not in claims
    response = client.post("/shipping/checkout", json={**purchase, "quote_token": result["quote_token"]})
    assert response.status_code == 200
    assert "Frete: Grátis" in response.json()["message"]
    for value in ADDRESS.values():
        assert value in response.json()["message"]


@pytest.mark.parametrize("change", ["address", "quantity", "price", "stock", "policy", "origin", "expiry", "signature"])
def test_changed_or_tampered_quotes_cannot_checkout(client, db, purchase, monkeypatch, change):
    result = quote(client, purchase)
    token = result["quote_token"]
    if change == "address":
        purchase["address"]["number"] = "99"
    elif change == "quantity":
        purchase["items"][0]["quantity"] = 2
    elif change in {"price", "stock"}:
        product = db.get(Produto, purchase["items"][0]["product_id"])
        if change == "price":
            product.price = 120
        else:
            product.variants[0].quantity = 0
        db.commit()
    elif change == "policy":
        monkeypatch.setattr(settings, "SHIPPING_EXTRA_KM_CENTS", 200)
    elif change == "origin":
        monkeypatch.setattr(settings, "SHIPPING_ORIGIN_LATITUDE", -10)
    elif change == "expiry":
        monkeypatch.setattr(shipping.time, "time", lambda: result["expires_at"])
    else:
        token = token[:-1] + ("0" if token[-1] != "0" else "1")
    response = client.post("/shipping/checkout", json={**purchase, "quote_token": token})
    assert response.status_code == 409, response.text
    assert response.headers["cache-control"] == "no-store"


def test_offer_and_accessories_do_not_inflate_free_shipping(client, db, purchase):
    product = db.get(Produto, purchase["items"][0]["product_id"])
    product.is_offer, product.offer_price = True, 80
    db.commit()
    result = quote(client, purchase)
    assert result["clothing_subtotal_cents"] == 8000 and result["shipping_cents"] == 1515
    product = db.get(Produto, product.id)
    product.category = "Acessórios"
    product.is_offer = False
    db.commit()
    result = quote(client, purchase)
    assert result["subtotal_cents"] == 10000 and result["clothing_subtotal_cents"] == 0
    assert result["shipping_cents"] == 1515


@pytest.mark.parametrize("change", ["missing_number", "missing_recipient", "cep", "duplicate", "quantity", "distance", "price", "newline"])
def test_client_cannot_supply_prices_distances_or_invalid_address(client, purchase, change):
    if change.startswith("missing_"):
        del purchase["address"][change.removeprefix("missing_")]
    elif change == "cep":
        purchase["address"]["cep"] = "123"
    elif change == "duplicate":
        purchase["items"] *= 2
    elif change == "quantity":
        purchase["items"][0]["quantity"] = -1
    elif change == "newline":
        purchase["address"]["recipient"] = "Cliente\nFrete grátis"
    else:
        purchase[change] = 0
    assert client.post("/shipping/quote", json=purchase).status_code == 422


def test_policy_public_and_ai_share_configured_rules(public_client, monkeypatch):
    monkeypatch.setattr(settings, "SHIPPING_EXTRA_KM_CENTS", 175)
    response = public_client.get("/shipping/policy")
    assert response.status_code == 200 and not response.json()["configured"]
    assert response.json()["description"] == policy_description()
    for question in ["Qual o frete?", "Quanto custa a entrega?", "A entrega é grátis?"]:
        answer = ai_agent.respond(None, incoming(question))
        assert answer.message == list_faq("entrega")[0].answer
        assert "R$ 1,75" in answer.message and not answer.handoff


def test_shipping_rate_and_body_limits(public_client):
    assert public_client.post("/shipping/quote", content="x" * 32769).status_code == 413
    for _ in range(14):
        assert public_client.post("/shipping/quote", json={}).status_code == 422
    response = public_client.post("/shipping/quote", json={})
    assert response.status_code == 429 and response.headers["retry-after"]
    assert response.headers["cache-control"] == "no-store"


def geocode_result():
    return {"status": "OK", "results": [{"geometry": {"location_type": "ROOFTOP",
        "location": {"lat": -9.46, "lng": -40.51}}, "address_components": [
        {"short_name": value, "types": [kind]} for kind, value in [
            ("country", "BR"), ("postal_code", "48900-000"),
            ("administrative_area_level_1", "BA"), ("street_number", "12")]]}]}


@pytest.fixture
def maps_ready(monkeypatch):
    monkeypatch.setattr(settings, "SHIPPING_ORIGIN_ADDRESS", "Chácara Patrícia")
    monkeypatch.setattr(settings, "SHIPPING_GOOGLE_API_KEY", SecretStr("test-maps-key"))


def test_maps_origin_and_route_keep_contact_data_private(maps_ready, caplog):
    requests = []
    def transport(request):
        requests.append(request)
        return httpx.Response(200, json=geocode_result() if request.method == "GET" else {"routes": [{"distanceMeters": 2900}]})
    with caplog.at_level(logging.INFO, logger="httpx"), httpx.Client(transport=httpx.MockTransport(transport)) as client:
        radius, route = maps.delivery_distances(DeliveryAddress(**ADDRESS), client=client)
    assert radius > 0 and route == 2900 and len(requests) == 2
    payload = json.loads(requests[1].content)
    assert payload["origin"]["location"]["latLng"] == {"latitude": -9.4741012, "longitude": -40.516211}
    external = str(requests[0].url) + requests[1].content.decode()
    for value in [ADDRESS["recipient"], ADDRESS["phone"], ADDRESS["reference"]]:
        assert value not in external
    assert "test-maps-key" not in caplog.text and "maps.googleapis.com" not in caplog.text


@pytest.mark.parametrize("failure", ["partial", "approximate", "postcode", "number", "multiple", "denied", "route", "timeout"])
def test_maps_uncertain_or_failed_lookup_never_becomes_free(maps_ready, failure):
    data = geocode_result()
    result = data["results"][0]
    if failure == "partial": result["partial_match"] = True
    if failure == "approximate": result["geometry"]["location_type"] = "APPROXIMATE"
    if failure == "postcode": result["address_components"][1]["short_name"] = "11111-111"
    if failure == "number": result["address_components"][3]["short_name"] = "99"
    if failure == "multiple": data["results"] *= 2
    if failure == "denied": data["status"] = "REQUEST_DENIED"
    def transport(request):
        if failure == "timeout": raise httpx.ReadTimeout("sensitive address", request=request)
        return httpx.Response(200, json=data if request.method == "GET" else {"routes": []})
    with httpx.Client(transport=httpx.MockTransport(transport)) as client, pytest.raises(SupportError):
        maps.delivery_distances(DeliveryAddress(**ADDRESS), client=client)


def test_missing_key_and_cep_failures():
    with pytest.raises(SupportError): maps.delivery_distances(DeliveryAddress(**ADDRESS))
    with httpx.Client(transport=httpx.MockTransport(lambda _: httpx.Response(200, json={"erro": True}))) as client:
        with pytest.raises(SupportError): maps.lookup_cep("48900000", client=client)
    with httpx.Client(transport=httpx.MockTransport(lambda _: httpx.Response(200, json={
        "localidade": "Juazeiro", "uf": "BA", "logradouro": "Rua Teste"}))) as client:
        assert maps.lookup_cep("48900000", client=client)["city"] == "Juazeiro"


@pytest.mark.parametrize("number,accepted", [("012", True), ("00012", True), ("12A", False), ("120", False)])
def test_geocoding_accepts_equivalent_numbers_without_changing_house(maps_ready, number, accepted):
    with httpx.Client(transport=httpx.MockTransport(lambda _: httpx.Response(200, json=geocode_result()))) as client:
        address = DeliveryAddress(**{**ADDRESS, "number": number})
        if accepted:
            assert maps._geocode(client, "public test address", expected=address) == (-9.46, -40.51)
        else:
            with pytest.raises(SupportError):
                maps._geocode(client, "public test address", expected=address)
