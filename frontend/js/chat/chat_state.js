import { createChatSession, getChatMessages, sendChatMessage, endChatSession } from "../api/chat_api.js";
import { loadChatSession, saveChatSession, clearChatSession, validChatSession } from "./chat_storage.js";

export const MAX_CHAT_MESSAGE_LENGTH = 2000;
const STATUSES = new Set(["AI", "WAITING_HUMAN", "HUMAN"]);

export function normalizeChatMessage(value) {
    if (!value || typeof value !== "object") return null;
    if (value.sender === "system") return null;
    const response = value.response ?? value.metadata?.response ?? value;
    const sender = ["customer", "user"].includes(value.sender) ? "customer"
        : value.sender === "human" ? "human" : "assistant";
    const message = typeof value.content === "string" ? value.content : response.message;
    if (response.type === "silent" || (typeof message !== "string" && !response.products?.length)) return null;
    return {
        id: String(value.external_id ?? value.id ?? value.message_id ?? ""), sender,
        message: typeof message === "string" ? message.slice(0, 12000) : "",
        products: Array.isArray(response.products) ? response.products.slice(0, 12).filter((product) =>
            product && typeof product.id === "string" && typeof product.title === "string" && Number.isFinite(product.price)) : []
    };
}

export function createChatController({
    api = { createChatSession, getChatMessages, sendChatMessage, endChatSession },
    storage = { loadChatSession, saveChatSession, clearChatSession },
    newId = () => globalThis.crypto.randomUUID()
} = {}) {
    let session = storage.loadChatSession(), messages = [], status = "AI";
    let busy = false, error = "", persisted = true, pending = null;
    const listeners = new Set();
    const snapshot = () => ({ messages: messages.map((item) => ({ ...item })), status, busy, error, persisted,
        pending: pending ? { ...pending } : null, hasSession: Boolean(session) });
    const emit = () => listeners.forEach((listener) => listener(snapshot()));
    const readStatus = (value) => { if (STATUSES.has(value?.status)) status = value.status; };
    const ensureSession = async () => {
        if (session && validChatSession(session)) return;
        const value = await api.createChatSession();
        if (!validChatSession(value)) throw new Error("Não foi possível iniciar o atendimento. Tente novamente.");
        session = { session_id: value.session_id, expires_at: value.expires_at };
        messages = []; status = "AI";
        persisted = storage.saveChatSession(session);
    };
    const expireSession = () => {
        session = null; messages = []; status = "AI"; storage.clearChatSession();
    };
    const run = async (operation) => {
        if (busy) return false;
        busy = true; error = ""; emit();
        try { await operation(); return true; }
        catch (failure) {
            if ([401, 403].includes(failure.status)) {
                expireSession();
                error = "Sua sessão expirou. Tente novamente para iniciar outra conversa.";
            } else error = failure.status === 429
                ? "Muitas mensagens em pouco tempo. Aguarde um pouco e tente novamente."
                : failure.status === 409 ? "Sua mensagem ainda está sendo processada. Aguarde um pouco e tente novamente."
                : failure.message || "Não foi possível continuar. Tente novamente.";
            return false;
        } finally { busy = false; emit(); }
    };
    const deliverPending = async () => {
        await ensureSession();
        if (!messages.some((item) => item.sender === "customer" && item.id === pending.message_id)) {
            messages.push({ id: pending.message_id, sender: "customer", message: pending.message, products: [] });
            emit();
        }
        const reply = await api.sendChatMessage(session.session_id, { ...pending });
        const message = normalizeChatMessage(reply);
        if (message && !messages.some((item) => item.sender === message.sender && item.id === message.id)) messages.push(message);
        readStatus(reply);
        messages = messages.slice(-100);
        pending = null;
    };
    return {
        getSnapshot: snapshot,
        subscribe(listener) { listeners.add(listener); listener(snapshot()); return () => listeners.delete(listener); },
        open() {
            return run(async () => {
                await ensureSession();
                try {
                    const history = await api.getChatMessages(session.session_id);
                    messages = (Array.isArray(history?.messages) ? history.messages : []).slice(-100).map(normalizeChatMessage).filter(Boolean);
                    readStatus(history);
                    // A reply persisted after a lost HTTP response acknowledges
                    // the UUID, even when the browser has not retried yet.
                    if (pending && messages.some((item) => item.sender === "assistant" && item.id === pending.message_id)) pending = null;
                } catch (failure) {
                    if (![401, 403].includes(failure.status)) throw failure;
                    expireSession();
                    await ensureSession();
                }
            });
        },
        send(value) {
            const message = typeof value === "string" ? value.trim() : "";
            if (busy || pending || !message) return Promise.resolve(false);
            if (message.length > MAX_CHAT_MESSAGE_LENGTH) {
                error = `Use até ${MAX_CHAT_MESSAGE_LENGTH} caracteres por mensagem.`; emit();
                return Promise.resolve(false);
            }
            pending = { message_id: newId(), message };
            return run(deliverPending);
        },
        retry() { return pending ? run(deliverPending) : this.open(); },
        discard() {
            if (busy || !pending) return;
            pending = null; error = ""; emit();
        },
        end() {
            return run(async () => {
                if (session) await api.endChatSession(session.session_id);
                expireSession(); pending = null; persisted = true;
            });
        }
    };
}
