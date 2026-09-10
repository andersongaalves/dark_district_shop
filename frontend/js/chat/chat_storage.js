export const CHAT_STORAGE_KEY = "dd.webchat.session.v1";

export function validChatSession(value, now = Date.now()) {
    return value && typeof value.session_id === "string" && /^[A-Za-z0-9_-]{20,512}$/.test(value.session_id)
        && typeof value.expires_at === "string" && Date.parse(value.expires_at) > now;
}

// Only the short-lived visitor credential is persisted, never chat content.
export function loadChatSession(storage) {
    try {
        storage ??= globalThis.window?.sessionStorage;
        const value = JSON.parse(storage?.getItem(CHAT_STORAGE_KEY) ?? "null");
        if (validChatSession(value)) return { session_id: value.session_id, expires_at: value.expires_at };
        storage?.removeItem(CHAT_STORAGE_KEY);
    } catch { /* Storage can be disabled by the browser. */ }
    return null;
}

export function saveChatSession(value, storage) {
    try {
        storage ??= globalThis.window?.sessionStorage;
        if (!storage || !validChatSession(value)) return false;
        storage.setItem(CHAT_STORAGE_KEY, JSON.stringify({ session_id: value.session_id, expires_at: value.expires_at }));
        return true;
    } catch { return false; }
}

export function clearChatSession(storage) {
    try { (storage ?? globalThis.window?.sessionStorage)?.removeItem(CHAT_STORAGE_KEY); return true; }
    catch { return false; }
}
