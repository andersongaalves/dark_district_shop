export function formatPrice(value) {
    return `R$ ${Number(value ?? 0).toFixed(2).replace(".", ",")}`;
}
