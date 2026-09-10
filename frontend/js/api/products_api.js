import { request } from "../core/api.js";

export function getProductsPath(filters = {}) {
    const query = new URLSearchParams();
    for (const key of ["product_type", "category_id", "collection_id", "featured", "is_offer", "available"]) {
        if (filters[key] !== undefined && filters[key] !== null) query.set(key, String(filters[key]));
    }
    return `/produtos${query.size ? `?${query}` : ""}`;
}

export function getProducts(filters = {}) {
    return request(getProductsPath(filters));
}

export async function getProduct(id) {
    try {
        return await request(`/produtos/${encodeURIComponent(id)}`, { cache: "no-store" });
    } catch (error) {
        if (error.status === 404) return null;
        throw error;
    }
}
