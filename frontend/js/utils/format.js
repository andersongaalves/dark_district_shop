export function formatPrice(value) {
    return `R$ ${Number(value ?? 0).toFixed(2).replace(".", ",")}`;
}

export function formatDateTime(value) {
    const date = new Date(value);
    if (!value || !Number.isFinite(date.getTime())) return "";
    return new Intl.DateTimeFormat("pt-BR", { dateStyle: "short", timeStyle: "short" }).format(date);
}

export function toDateTimeInput(value) {
    const date = new Date(value);
    if (!value || !Number.isFinite(date.getTime())) return "";
    const local = new Date(date.getTime() - date.getTimezoneOffset() * 60000);
    return local.toISOString().slice(0, 19);
}
