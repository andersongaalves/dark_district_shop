import { getSelectedVariant } from "../core/products.js";

export const MAX_CART_ITEMS = 100;
export const MAX_CART_QUANTITY = 999;

export function cartItemKey(item) {
    return JSON.stringify([item.productId, item.variantId]);
}

export function validProductId(id) {
    return typeof id === "string" && id.length > 0 && id.length <= 50 && !/[/\\\u0000-\u001f\u007f]/.test(id);
}

function validPrice(price) {
    return typeof price === "number" && Number.isFinite(price) && price >= 0 &&
        Number.isSafeInteger(Math.round(price * 100) * MAX_CART_QUANTITY * MAX_CART_ITEMS);
}

export function validQuantity(quantity) {
    return Number.isInteger(quantity) && quantity >= 1 && quantity <= MAX_CART_QUANTITY;
}

export function sanitizeCartItems(value) {
    if (!Array.isArray(value) || value.length > MAX_CART_ITEMS) return [];
    const keys = new Set();
    return value.flatMap((item) => {
        if (!item || !validProductId(item.productId) || !validPrice(item.price) || !validQuantity(item.quantity)) return [];
        if (item.variantId !== null && (!Number.isSafeInteger(item.variantId) || item.variantId <= 0)) return [];
        for (const [field, limit] of [["title", 200], ["size", 50], ["color", 100], ["image", 1000]]) {
            if (typeof item[field] !== "string" || item[field].length > limit) return [];
        }
        const key = cartItemKey(item);
        if (keys.has(key)) return [];
        keys.add(key);
        // Explicit projection prevents persisted stock/validation/extra fields being trusted.
        return [{ productId: item.productId, variantId: item.variantId, title: item.title,
            size: item.size, color: item.color, price: item.price, quantity: item.quantity, image: item.image }];
    });
}

function snapshot(product, variant, quantity) {
    if (!validProductId(product.id) || !validPrice(product.price)) throw new Error("Dados de produto inválidos na API.");
    if (variant && (!Number.isSafeInteger(variant.id) || variant.id <= 0 ||
        !Number.isSafeInteger(variant.quantity) || variant.quantity < 0)) throw new Error("Dados de variante inválidos na API.");
    return { productId: product.id, variantId: variant?.id ?? null, title: product.title,
        size: variant?.size || "", color: variant?.color || "", price: product.price,
        quantity, image: product.images?.[0]?.url || "", stock: variant?.quantity ?? null, validated: true, issue: "" };
}

export function itemForSelection(product, selection, quantity = 1) {
    if (!product || !validQuantity(quantity)) throw new Error("Produto ou quantidade inválida.");
    const variant = getSelectedVariant(product, selection);
    if (variant === undefined) throw new Error("Selecione uma combinação disponível de tamanho e cor.");
    const item = snapshot(product, variant, quantity);
    if (item.stock !== null && quantity > item.stock) throw new Error(`Estoque insuficiente. Disponível: ${item.stock}.`);
    return item;
}

export function addCartItem(items, item) {
    const key = cartItemKey(item);
    const existing = items.find((entry) => cartItemKey(entry) === key);
    const quantity = item.quantity + (existing?.quantity ?? 0);
    if (!validQuantity(quantity)) throw new Error(`A quantidade máxima por item é ${MAX_CART_QUANTITY}.`);
    if (item.stock !== null && quantity > item.stock) throw new Error(`Estoque insuficiente. Disponível: ${item.stock}.`);
    if (!existing && items.length >= MAX_CART_ITEMS) throw new Error("O carrinho atingiu o limite de itens.");
    return existing ? items.map((entry) => cartItemKey(entry) === key ? { ...item, quantity } : entry) : [...items, item];
}

export function removeCartItem(items, key) {
    return items.filter((item) => cartItemKey(item) !== key);
}

export function cartCount(items) {
    return items.reduce((sum, item) => sum + item.quantity, 0);
}

export function cartSubtotal(items) {
    return items.reduce((cents, item) => cents + Math.round(item.price * 100) * item.quantity, 0) / 100;
}

export function reconcileCart(items, products) {
    let changed = false;
    const updated = items.map((item) => {
        const product = products.get(item.productId);
        if (product instanceof Error || product === undefined) return { ...item, validated: false, issue: "Não foi possível consultar este produto. Tente atualizar." };
        if (!product || product.id !== item.productId) return { ...item, validated: false, stock: 0, issue: "Produto não encontrado. Remova este item." };
        const variants = product.variants ?? [];
        const variant = item.variantId === null ? null : variants.find((entry) => entry.id === item.variantId);
        if ((item.variantId !== null && !variant) || (item.variantId === null && variants.length)) {
            return { ...item, validated: false, stock: 0, issue: "A variante mudou ou foi removida. Selecione novamente na página do produto." };
        }
        try {
            const fresh = snapshot(product, variant, item.quantity);
            if (fresh.price !== item.price || fresh.size !== item.size || fresh.color !== item.color) changed = true;
            if (!product.available) fresh.issue = "Produto indisponível. Remova este item.";
            else if (fresh.stock !== null && item.quantity > fresh.stock) fresh.issue = `Estoque disponível: ${fresh.stock}. Ajuste a quantidade ou remova.`;
            return fresh;
        } catch {
            return { ...item, validated: false, issue: "Dados de produto inválidos. Tente atualizar." };
        }
    });
    return { items: updated, changed };
}
