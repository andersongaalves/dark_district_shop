export const PRODUCT_TYPES = Object.freeze({ catalogo: "Catálogo", brecho: "Brechó", drop: "Drops" });

export function isOfferActive(product, now = Date.now()) {
    if (!product.is_offer || product.offer_active === false) return false;
    if (!product.offer_ends_at) return true;
    const end = Date.parse(product.offer_ends_at);
    return Number.isFinite(end) && end > now;
}

export function getProductPrice(product, now = Date.now()) {
    return isOfferActive(product, now) && Number.isFinite(product.offer_price) &&
        product.offer_price >= 0 && product.offer_price < product.price ? product.offer_price : product.price;
}

// Availability is independent of category and featured status.
export function isProductAvailable(product, selection = {}) {
    if (!product.available) return false;
    const variants = product.variants ?? [];
    if (!variants.length) return true;
    return variants.some((variant) =>
        variant.quantity > 0 &&
        (!Object.hasOwn(selection, "color") || (variant.color || "") === selection.color) &&
        (!Object.hasOwn(selection, "size") || (variant.size || "") === selection.size)
    );
}

export function getVariantOptions(product) {
    return Object.fromEntries(["color", "size"].map((field) => {
        const values = [...new Set((product.variants ?? []).map((variant) => variant[field] || ""))];
        return [field, values.some(Boolean) ? values : []];
    }));
}

// null means a product without variants; undefined means incomplete/invalid selection.
export function getSelectedVariant(product, selection = {}) {
    if (!isProductAvailable(product, selection)) return undefined;
    const variants = product.variants ?? [];
    if (!variants.length) return null;
    const options = getVariantOptions(product);
    if (["color", "size"].some((field) => options[field].length && !Object.hasOwn(selection, field))) return undefined;
    const matches = variants.filter((variant) => variant.quantity > 0 &&
        ["color", "size"].every((field) => (variant[field] || "") === (selection[field] || "")));
    return matches.length === 1 ? matches[0] : undefined;
}
