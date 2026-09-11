"""Address-only geocoding: receiver, phone, complement and reference stay out of Maps."""
import json
import math
import re

import httpx

from core.config import settings
from services.customer_service import SupportError


def _json(client, method, url, **kwargs):
    try:
        with client.stream(method, url, **kwargs) as response:
            response.raise_for_status()
            body = bytearray()
            for chunk in response.iter_bytes():
                body.extend(chunk)
                if len(body) > 131072:
                    raise ValueError("oversized")
            result = json.loads(body)
            if not isinstance(result, dict):
                raise ValueError("invalid response")
            return result
    except (httpx.HTTPError, ValueError):
        raise SupportError("Não foi possível consultar o endereço agora. Tente novamente ou fale com a loja.", 503) from None


def lookup_cep(cep: str, *, client=None):
    if not re.fullmatch(r"\d{8}", cep):
        raise SupportError("Informe um CEP com 8 dígitos.", 422)
    if client is None:
        with httpx.Client(timeout=8) as session:
            return lookup_cep(cep, client=session)
    data = _json(client, "GET", f"https://viacep.com.br/ws/{cep}/json/")
    if data.get("erro"):
        raise SupportError("CEP não encontrado. Confira os números informados.", 404)
    if not isinstance(data.get("localidade"), str) or not re.fullmatch(r"[A-Z]{2}", str(data.get("uf", ""))):
        raise SupportError("Não foi possível consultar esse CEP.", 503)
    return {"cep": cep, "street": data.get("logradouro") or "", "neighborhood": data.get("bairro") or "",
            "city": data["localidade"], "state": data["uf"]}


def _geocode(client, address, *, expected=None):
    params = {"address": address, "key": settings.SHIPPING_GOOGLE_API_KEY.get_secret_value(),
              "language": "pt-BR", "components": "country:BR"}
    if expected:
        params["components"] += f"|postal_code:{expected.cep}"
    data = _json(client, "GET", "https://maps.googleapis.com/maps/api/geocode/json", params=params)
    if data.get("status") not in {"OK", "ZERO_RESULTS"}:
        raise SupportError("O cálculo de frete está indisponível. Fale com a loja.", 503)
    results = data.get("results", [])
    if not isinstance(results, list) or len(results) != 1:
        raise SupportError("Não localizamos um endereço único. Confira rua, número e CEP.", 422)
    try:
        result = results[0]
        if not isinstance(result, dict):
            raise ValueError("invalid result")
        geometry = result["geometry"]
        if result.get("partial_match") or geometry["location_type"] not in {"ROOFTOP", "RANGE_INTERPOLATED"}:
            raise ValueError("imprecise")
        components = {kind: component["short_name"] for component in result["address_components"] for kind in component["types"]}
        if components.get("country") != "BR":
            raise ValueError("country")
        if expected and (re.sub(r"\D", "", components.get("postal_code", "")) != expected.cep
            or components.get("administrative_area_level_1") != expected.state
            or components.get("street_number", "").replace(" ", "").casefold() != expected.number.replace(" ", "").casefold()):
            raise ValueError("address mismatch")
        lat, lng = float(geometry["location"]["lat"]), float(geometry["location"]["lng"])
        if not math.isfinite(lat) or not math.isfinite(lng) or not -90 <= lat <= 90 or not -180 <= lng <= 180:
            raise ValueError("invalid point")
        return lat, lng
    except (KeyError, TypeError, ValueError):
        raise SupportError("Não localizamos o número com precisão. Confira o endereço ou confirme o frete com a loja.", 422) from None


def radial_distance(origin, destination):
    lat1, lng1, lat2, lng2 = map(math.radians, (*origin, *destination))
    a = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lng2 - lng1) / 2) ** 2
    return math.ceil(6371000 * 2 * math.asin(min(1, math.sqrt(a))))


def delivery_distances(address, *, client=None):
    if not settings.SHIPPING_ORIGIN_ADDRESS.strip() or not settings.SHIPPING_GOOGLE_API_KEY.get_secret_value():
        raise SupportError("O frete automático ainda não está disponível. Você pode confirmar a entrega com a loja pelo WhatsApp.", 503)
    if client is None:
        with httpx.Client(timeout=10) as session:
            return delivery_distances(address, client=session)
    # Exact place coordinates, confirmed through the shop owner's Maps link.
    # The departure is a rural property without a street number or postal code.
    origin = (settings.SHIPPING_ORIGIN_LATITUDE, settings.SHIPPING_ORIGIN_LONGITUDE)
    destination = _geocode(client, f"{address.street}, {address.number}, {address.neighborhood}, {address.city} - {address.state}, {address.cep}, Brasil", expected=address)
    waypoint = lambda point: {"location": {"latLng": {"latitude": point[0], "longitude": point[1]}}}
    result = _json(client, "POST", "https://routes.googleapis.com/directions/v2:computeRoutes",
        headers={"X-Goog-Api-Key": settings.SHIPPING_GOOGLE_API_KEY.get_secret_value(),
                 "X-Goog-FieldMask": "routes.distanceMeters"},
        json={"origin": waypoint(origin), "destination": waypoint(destination), "travelMode": "DRIVE",
              "routingPreference": "TRAFFIC_UNAWARE", "computeAlternativeRoutes": False})
    try:
        distance = result["routes"][0]["distanceMeters"]
        if isinstance(distance, bool) or not isinstance(distance, int) or not 0 <= distance <= 1000000:
            raise ValueError("invalid distance")
    except (KeyError, IndexError, TypeError, ValueError):
        raise SupportError("Não foi possível traçar uma rota de entrega. Confirme com a loja.", 422) from None
    return radial_distance(origin, destination), distance
