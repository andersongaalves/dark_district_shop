from decimal import Decimal, ROUND_HALF_UP

from core.config import settings


def money(cents):
    return "R$ " + f"{Decimal(cents) / 100:.2f}".replace(".", ",")


def policy_values():
    return {name: getattr(settings, name) for name in (
        "SHIPPING_BASE_METERS", "SHIPPING_BASE_CENTS", "SHIPPING_EXTRA_KM_CENTS",
        "SHIPPING_FREE_MIN_CENTS", "SHIPPING_FREE_RADIUS_METERS")}


def shipping_price(clothing_subtotal_cents: int, radius_meters: int, route_meters: int) -> int:
    if min(clothing_subtotal_cents, radius_meters, route_meters) < 0:
        raise ValueError("Valores de frete não podem ser negativos.")
    if clothing_subtotal_cents >= settings.SHIPPING_FREE_MIN_CENTS and radius_meters <= settings.SHIPPING_FREE_RADIUS_METERS:
        return 0
    extra = Decimal(max(0, route_meters - settings.SHIPPING_BASE_METERS)) * settings.SHIPPING_EXTRA_KM_CENTS / 1000
    return settings.SHIPPING_BASE_CENTS + int(extra.quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def policy_description():
    base_km = str(Decimal(settings.SHIPPING_BASE_METERS) / 1000).replace(".", ",")
    radius_km = str(Decimal(settings.SHIPPING_FREE_RADIUS_METERS) / 1000).replace(".", ",")
    return (f"Frete grátis em compras a partir de {money(settings.SHIPPING_FREE_MIN_CENTS)} em roupas, "
        f"dentro de um raio de {radius_km} km do ponto de saída (distância em linha reta). "
        f"Nos demais casos, o frete custa {money(settings.SHIPPING_BASE_CENTS)} até {base_km} km de trajeto "
        f"e {money(settings.SHIPPING_EXTRA_KM_CENTS)} por km adicional, proporcional à distância. "
        "Fora do raio gratuito, aplica-se a tarifa normal completa. Informe o endereço na seleção de itens para calcular.")
