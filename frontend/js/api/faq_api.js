import { ApiError, request } from "../core/api.js";

export async function getFAQ() {
    const items = await request("/faq", { credentials: "omit", cache: "no-cache" });
    if (!Array.isArray(items) || !items.length || items.some((item) =>
        !item || typeof item.id !== "string" ||
        typeof item.question !== "string" || !item.question.trim() ||
        typeof item.answer !== "string" || !item.answer.trim()
    )) {
        throw new ApiError("Não foi possível carregar as perguntas frequentes.");
    }
    return items;
}
