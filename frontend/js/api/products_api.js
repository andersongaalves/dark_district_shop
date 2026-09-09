import { request } from "../core/api.js";

export function getProducts() {
    return request("/produtos");
}

export async function getProduct(id) {
    try {
        return await request(`/produtos/${encodeURIComponent(id)}`);
    } catch (error) {
        if (error.status === 404) return null;
        throw error;
    }
}
