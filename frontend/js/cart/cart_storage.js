import { sanitizeCartItems } from "./cart_state.js";

export const CART_STORAGE_KEY = "darkDistrictCart:v1";

export function loadCart(storage) {
    try {
        const raw = (storage ?? globalThis.localStorage)?.getItem(CART_STORAGE_KEY);
        if (!raw || raw.length > 250000) return [];
        const data = JSON.parse(raw);
        return data?.version === 1 ? sanitizeCartItems(data.items) : [];
    } catch {
        return [];
    }
}

export function saveCart(items, storage) {
    try {
        const target = storage ?? globalThis.localStorage;
        if (!target) return false;
        target.setItem(CART_STORAGE_KEY, JSON.stringify({ version: 1, items: sanitizeCartItems(items) }));
        return true;
    } catch {
        return false;
    }
}

export function clearCart(storage) {
    try {
        const target = storage ?? globalThis.localStorage;
        if (!target) return false;
        target.removeItem(CART_STORAGE_KEY);
        return true;
    } catch {
        return false;
    }
}
