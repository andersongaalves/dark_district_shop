// Availability is independent of category and featured status.
export function isProductAvailable(product, selection = {}) {
    if (!product.available) return false;
    const variants = product.variants ?? [];
    if (!variants.length) return true;
    return variants.some((variant) =>
        variant.quantity > 0 &&
        (!selection.color || variant.color === selection.color) &&
        (!selection.size || variant.size === selection.size)
    );
}
