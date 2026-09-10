import { request, ApiError } from "../core/api.js";

async function chatRequest(path, { sessionId, body, method = "GET" } = {}) {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 45000);
    const headers = new Headers({ Accept: "application/json" });
    if (sessionId) headers.set("Authorization", `Bearer ${sessionId}`);
    if (body) headers.set("Content-Type", "application/json");
    try {
        return await request(`/api/chat/${path}`, {
            method, headers, credentials: "omit", cache: "no-store",
            signal: controller.signal, ...(body ? { body: JSON.stringify(body) } : {})
        });
    } catch (error) {
        if (error.name === "AbortError") throw new ApiError("O atendimento demorou a responder. Tente enviar novamente.");
        throw error;
    } finally {
        clearTimeout(timer);
    }
}

export const createChatSession = () => chatRequest("sessions", { method: "POST" });
export const getChatMessages = (sessionId) => chatRequest("messages", { sessionId });
export const sendChatMessage = (sessionId, message) => chatRequest("messages", { sessionId, method: "POST", body: message });
export const endChatSession = (sessionId) => chatRequest("session", { sessionId, method: "DELETE" });
