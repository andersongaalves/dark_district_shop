import { ApiError, request } from "../core/api.js";

const options = { credentials: "omit", cache: "no-store" };
const post = (path, data) => request(path, { ...options, method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(data) });

export const getShippingPolicy = () => request("/shipping/policy", options);
export const lookupCEP = (cep) => {
    const digits = String(cep).replace(/\D/g, "");
    if (!/^\d{8}$/.test(digits)) return Promise.reject(new Error("Informe um CEP com 8 dígitos."));
    return request(`/shipping/cep/${digits}`, options);
};

export async function quoteShipping(data) {
    const quote = await post("/shipping/quote", data);
    if (!quote || typeof quote.quote_token !== "string" || !quote.quote_token ||
        !["subtotal_cents", "clothing_subtotal_cents", "shipping_cents", "total_cents", "radius_meters", "route_meters", "expires_at"]
            .every((field) => Number.isSafeInteger(quote[field]) && quote[field] >= 0) ||
        quote.total_cents !== quote.subtotal_cents + quote.shipping_cents || typeof quote.policy !== "string") {
        throw new ApiError("A cotação retornada é inválida. Tente novamente.");
    }
    return quote;
}

export async function checkoutShipping(data) {
    const response = await post("/shipping/checkout", data);
    if (typeof response?.message !== "string" || !response.message) throw new ApiError("Não foi possível preparar a compra.");
    return response;
}
