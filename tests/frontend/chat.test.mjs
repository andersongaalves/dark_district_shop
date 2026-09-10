import assert from "node:assert/strict";
import { test } from "node:test";
import { installDOM, eventually } from "./helpers/dom.mjs";
import { createChatSession, getChatMessages, sendChatMessage, endChatSession } from "../../frontend/js/api/chat_api.js";
import { CHAT_STORAGE_KEY, loadChatSession, saveChatSession, clearChatSession } from "../../frontend/js/chat/chat_storage.js";
import { createChatController, normalizeChatMessage } from "../../frontend/js/chat/chat_state.js";
import { createChatView } from "../../frontend/js/chat/chat_ui.js";
import { initChat } from "../../frontend/js/chat/chat.js";

const token = "visitor_credential_only_1234567890";
const session = () => ({ session_id: token, conversation_id: "conversation-1", expires_at: new Date(Date.now() + 3600000).toISOString() });
const reply = (overrides = {}) => ({ conversation_id: "conversation-1", status: "AI", message_id: "reply-1", message: "Encontrei uma opção.", type: "message", products: [], actions: [], handoff: false, ...overrides });
const product = { id: "CR-001", title: "Cropped DD", category: "Cropped", price: 90, available: true,
    images: [{ url: "https://images.example.com/cropped.webp" }], variants: [{ size: "M", color: "Preto", stock: 1 }],
    is_offer: true, offer_active: true, offer_price: 70, offer_ends_at: null, effective_price: 70 };

function setupController(overrides = {}) {
    let stored = null, creates = 0, sends = [], messageCount = 0;
    const storage = {
        loadChatSession: () => stored, saveChatSession: (value) => { stored = value; return true; },
        clearChatSession: () => { stored = null; }
    };
    const api = {
        createChatSession: async () => { creates++; return session(); },
        getChatMessages: async () => ({ messages: [], status: "AI" }),
        sendChatMessage: async (credential, message) => { sends.push({ credential, ...message }); return reply(); },
        endChatSession: async () => {}, ...overrides
    };
    return { api, storage, create: () => createChatController({ api, storage, newId: () => `b59acf64-97cd-493c-a001-${String(++messageCount).padStart(12, "0")}` }),
        getStored: () => stored, getCreates: () => creates, sends };
}

test("chat API sends only its visitor bearer and keeps credentials out of URLs and request content", async (t) => {
    await installDOM(t, "<body></body>");
    localStorage.setItem("access_token", "administrative-secret");
    const calls = [];
    t.mock.method(globalThis, "fetch", async (url, options) => {
        calls.push({ url, options });
        if (options.method === "DELETE") return new Response(null, { status: 204 });
        return Response.json(session());
    });
    await createChatSession();
    await getChatMessages(token);
    await sendChatMessage(token, { message_id: "request-id", message: "Tem cropped?" });
    await endChatSession(token);
    assert.equal(calls[0].options.headers.has("Authorization"), false);
    for (const { url, options } of calls.slice(1)) {
        assert.equal(options.headers.get("Authorization"), `Bearer ${token}`);
        assert.equal(options.credentials, "omit");
        assert.equal(options.cache, "no-store");
        assert.equal(url.includes(token), false);
        assert.equal((options.body ?? "").includes(token), false);
    }
    assert.deepEqual(JSON.parse(calls[2].options.body), { message_id: "request-id", message: "Tem cropped?" });
    assert.match(calls[3].url, /\/api\/chat\/session$/);
    assert.equal(localStorage.getItem("access_token"), "administrative-secret");
});

test("session storage contains only visitor credential and expiry, validates expiry and survives disabled storage", async (t) => {
    const window = await installDOM(t, "<body></body>");
    assert.equal(saveChatSession({ ...session(), messages: ["private text"] }), true);
    assert.deepEqual(Object.keys(JSON.parse(window.sessionStorage.getItem(CHAT_STORAGE_KEY))), ["session_id", "expires_at"]);
    assert.equal(loadChatSession().session_id, token);
    window.sessionStorage.setItem(CHAT_STORAGE_KEY, JSON.stringify({ ...session(), expires_at: "2000-01-01T00:00:00Z" }));
    assert.equal(loadChatSession(), null);
    window.sessionStorage.setItem(CHAT_STORAGE_KEY, "not json");
    assert.equal(loadChatSession(), null);
    const blocked = { getItem() { throw new Error("blocked"); }, setItem() { throw new Error("blocked"); }, removeItem() { throw new Error("blocked"); } };
    assert.equal(loadChatSession(blocked), null);
    assert.equal(saveChatSession(session(), blocked), false);
    assert.equal(clearChatSession(blocked), false);
    Object.defineProperty(window, "sessionStorage", { configurable: true, get() { throw new Error("blocked"); } });
    assert.equal(loadChatSession(), null);
    assert.equal(saveChatSession(session()), false);
});

test("opening creates one session and reopening another page loads authorized history", async () => {
    const harness = setupController();
    const first = harness.create();
    assert.equal(harness.getCreates(), 0);
    assert.equal(await first.open(), true);
    assert.equal(await first.send("  Tem cropped preto?  "), true);
    assert.equal(harness.sends[0].credential, token);
    assert.equal(harness.sends[0].message, "Tem cropped preto?");
    assert.equal(first.getSnapshot().messages.length, 2);
    harness.api.getChatMessages = async (credential) => {
        assert.equal(credential, token);
        return { status: "AI", messages: [{ id: "saved-user", sender: "customer", content: "Tem cropped preto?" },
            { id: "saved-reply", sender: "assistant", content: "Encontrei uma opção.", response: reply({ type: "product_results", products: [product] }) }] };
    };
    const nextPage = harness.create();
    await nextPage.open();
    assert.equal(harness.getCreates(), 1);
    assert.equal(nextPage.getSnapshot().messages[1].products[0].id, "CR-001");
});

test("a timeout or processing conflict retries the same UUID without duplicating the customer message", async () => {
    const ids = [];
    const harness = setupController({ sendChatMessage: async (_credential, payload) => {
        ids.push(payload.message_id);
        if (ids.length === 1) throw Object.assign(new Error("network failed"), { status: 0 });
        if (ids.length === 2) throw Object.assign(new Error("processing"), { status: 409 });
        return reply();
    } });
    const controller = harness.create();
    assert.equal(await controller.send("Tem cropped?"), false);
    assert.equal(controller.getSnapshot().pending.message, "Tem cropped?");
    assert.equal(await controller.send("outra mensagem"), false);
    assert.equal(await controller.retry(), false);
    assert.match(controller.getSnapshot().error, /processada/);
    assert.equal(await controller.retry(), true);
    assert.equal(new Set(ids).size, 1);
    assert.equal(controller.getSnapshot().messages.filter((item) => item.sender === "customer").length, 1);
    assert.equal(controller.getSnapshot().pending, null);
});

test("double submission is blocked and empty or oversized text does not call the backend", async () => {
    let release;
    const harness = setupController({ sendChatMessage: () => new Promise((resolve) => { release = resolve; }) });
    const controller = harness.create();
    assert.equal(await controller.send("  "), false);
    assert.equal(await controller.send("a".repeat(2001)), false);
    assert.equal(harness.getCreates(), 0);
    const sending = controller.send("Olá");
    await Promise.resolve(); await Promise.resolve();
    assert.equal(await controller.send("Olá"), false);
    assert.equal(controller.getSnapshot().busy, true);
    release(reply());
    assert.equal(await sending, true);
});

test("reopening after an ambiguous delivery reconciles a replay with server history without duplicate bubbles", async () => {
    let attempts = 0;
    const external_id = "b59acf64-97cd-493c-a001-000000000001";
    const history = { status: "AI", messages: [
        { id: "database-user-id", external_id, sender: "customer", content: "Tem cropped?" },
        { id: "database-reply-id", external_id, sender: "assistant", content: "Encontrei uma opção.", response: reply() }
    ] };
    const harness = setupController({
        getChatMessages: async () => history,
        sendChatMessage: async () => {
            if (++attempts === 1) throw new Error("timeout after server committed");
            return reply();
        }
    });
    const controller = harness.create();
    await controller.send("Tem cropped?");
    await controller.open();
    await controller.retry();
    assert.equal(attempts, 1);
    assert.equal(controller.getSnapshot().messages.length, 2);
    assert.equal(controller.getSnapshot().pending, null);
});

test("reopening a still-processing message retains its UUID until retry and deduplicates server customer IDs", async () => {
    const external_id = "b59acf64-97cd-493c-a001-000000000001";
    let attempts = 0;
    const harness = setupController({
        getChatMessages: async () => ({ status: "AI", messages: [
            { id: "database-user-id", external_id, sender: "customer", content: "Tem cropped?" }
        ] }),
        sendChatMessage: async (_token, payload) => {
            assert.equal(payload.message_id, external_id);
            if (++attempts === 1) throw Object.assign(new Error("processing"), { status: 409 });
            return reply({ message_id: external_id });
        }
    });
    const controller = harness.create();
    await controller.send("Tem cropped?");
    await controller.open();
    assert.equal(controller.getSnapshot().pending.message_id, external_id);
    await controller.retry();
    assert.equal(attempts, 2);
    assert.equal(controller.getSnapshot().messages.length, 2);
});

test("expired authorization renews on open and never mixes old and new conversation messages", async () => {
    const harness = setupController();
    const controller = harness.create();
    await controller.send("Minha conversa anterior");
    harness.api.getChatMessages = async () => { throw Object.assign(new Error("expired"), { status: 401 }); };
    assert.equal(await controller.open(), true);
    assert.equal(harness.getCreates(), 2);
    assert.deepEqual(controller.getSnapshot().messages, []);
    await controller.end();
    assert.equal(harness.getStored(), null);
    assert.equal(controller.getSnapshot().hasSession, false);
});

test("human handoff preserves state and silent replies add no automated message", async () => {
    let handoff = true;
    const harness = setupController({ sendChatMessage: async () => {
        if (handoff) { handoff = false; return reply({ type: "handoff", status: "WAITING_HUMAN", message: "Solicitei atendimento da equipe.", handoff: true }); }
        return reply({ type: "silent", status: "HUMAN", message: "", products: [] });
    } });
    const controller = harness.create();
    await controller.send("Quero falar com uma pessoa");
    assert.equal(controller.getSnapshot().status, "WAITING_HUMAN");
    await controller.send("Meu nome é Cliente");
    assert.equal(controller.getSnapshot().status, "HUMAN");
    assert.equal(controller.getSnapshot().messages.length, 3);
    assert.equal(controller.getSnapshot().messages.filter((item) => item.sender === "assistant").length, 1);
    assert.equal(normalizeChatMessage({ sender: "system", content: "Atendimento: HUMAN." }), null);
});

test("chat view treats text as text, reuses safe product links and shows original and promotional prices", async (t) => {
    await installDOM(t, "<body></body>");
    const view = createChatView({});
    t.after(() => view.destroy());
    const hostile = { ...product, title: '<img src=x onerror="alert(1)">', images: [{ url: "javascript:alert(1)" }], url: "javascript:alert(1)" };
    const message = normalizeChatMessage(reply({ message: '<script>alert("bad")</script>', products: [hostile], type: "product_results" }));
    view.render({ messages: [message], status: "AI", busy: false, error: "", pending: null, persisted: true, hasSession: true });
    assert.equal(document.querySelector("#dd-chat script"), null);
    assert.equal(document.querySelector("#dd-chat [onerror]"), null);
    assert.match(document.querySelector("[data-messages]").textContent, /<script>/);
    assert.equal(document.querySelector(".product-card img"), null);
    for (const link of document.querySelectorAll("#dd-chat a")) assert.equal(link.href.startsWith("javascript:"), false);
    assert.match(document.querySelector(".dd-chat__product-link").href, /id=CR-001$/);
    assert.match(document.querySelector(".price-original").textContent, /90,00/);
    assert.match(document.querySelector(".price-offer").textContent, /70,00/);
});

test("widget opens on demand, keeps composer focus, cycles Tab, restores focus and coexists with cart", async (t) => {
    const window = await installDOM(t, '<body><button id="outside">Outside</button><dialog id="cart-drawer"></dialog></body>');
    window.HTMLDialogElement.prototype.showModal = function () { this.open = true; };
    window.HTMLDialogElement.prototype.close = function () { this.open = false; this.dispatchEvent(new window.Event("close")); };
    let requests = 0;
    t.mock.method(globalThis, "fetch", async (url, options) => {
        requests++;
        if (url.endsWith("/sessions")) return Response.json(session());
        if (options.method === "POST") return Response.json(reply());
        return Response.json({ messages: [], status: "AI" });
    });
    const widget = initChat();
    t.after(() => widget.destroy());
    assert.equal(initChat(), widget);
    assert.equal(requests, 0);
    const launcher = document.querySelector(".dd-chat-launcher");
    document.querySelector("#cart-drawer").open = true;
    launcher.click();
    assert.equal(widget.view.isOpen(), false);
    document.querySelector("#cart-drawer").open = false;
    launcher.focus(); launcher.click();
    await eventually(() => assert.equal(requests, 2));
    await eventually(() => assert.equal(widget.controller.getSnapshot().busy, false));
    assert.equal(widget.view.isOpen(), true);
    assert.equal(launcher.getAttribute("aria-expanded"), "true");
    const input = document.querySelector("#dd-chat-message");
    assert.equal(document.activeElement, input);
    input.value = "Olá";
    input.dispatchEvent(new window.KeyboardEvent("keydown", { key: "Enter", bubbles: true, cancelable: true }));
    await eventually(() => assert.equal(widget.controller.getSnapshot().messages.length, 2));
    assert.equal(document.activeElement, input);
    const end = document.querySelector("[data-end]");
    end.focus();
    end.dispatchEvent(new window.KeyboardEvent("keydown", { key: "Tab", bubbles: true, cancelable: true }));
    assert.equal(document.activeElement, document.querySelector("[data-close]"));
    document.querySelector("[data-close]").click();
    assert.equal(widget.view.isOpen(), false);
    assert.equal(document.activeElement, launcher);
    assert.equal(launcher.getAttribute("aria-expanded"), "false");
});
