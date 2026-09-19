import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { test } from "node:test";
import { installDOM, eventually } from "./helpers/dom.mjs";
import { DECISION_LABELS, HANDOFF_LABELS, mountInbox } from "../../frontend/admin/atendimento/atendimento.js";

const aiState = (changes = {}) => ({
    mode: "AUTO", status: "WAITING_HUMAN", last_decision: { action: "CLARIFY" },
    clarification: { attempts: 1, max_attempts: 2, kind: "PROCESS_TOPIC" },
    handoff: { reason: "LOW_CONFIDENCE", clarification_attempts: 2 },
    focus: { selected_product: { id: "p1", name: "Camiseta Gótica" }, presented_count: 3, products: [] },
    preferences: { garment: "camiseta", color: "preto", size: "M", max_price: 80, style_query: "gotico" },
    recent_events: [{ type: "AI_ACTIVATED", created_at: "2026-09-12T08:31:00Z" }],
    actions: { claim: true, close: true, change_mode: true, resume_ai: true, suggest: true, reply: false },
    ...changes
});

test("AI panel renders safe friendly observability fields", async (t) => {
    await installDOM(t, '<div id="inbox"></div>');
    Object.defineProperty(document, "hidden", { value: false, configurable: true });
    const root = document.querySelector("#inbox");
    const state = aiState();
    const view = mountInbox(root, { interval: 100000, api: {
        async get(url) { return url.includes("/messages") ? { status: state.status, ai_mode: state.mode, cycle: 1, ai_state: state, messages: [], has_more: false } :
            { items: [{ conversation_id: "c1", phone: "Contato", status: state.status, ai_mode: state.mode, updated_at: "2026-09-12T10:00:00Z" }], has_more: false }; }
    } });
    t.after(() => view.destroy());
    await view.ready; root.querySelector("[data-id]").click();
    await eventually(() => assert.match(root.querySelector(".inbox-ai").textContent, /Camiseta Gótica/));
    const text = root.querySelector(".inbox-ai").textContent;
    assert.match(text, /Automático/);
    assert.match(text, /Aguardando humano/);
    assert.match(text, /Pergunta de esclarecimento/);
    assert.match(text, /Tentativa: 1 de 2/);
    assert.match(text, /2 tentativas de esclarecimento/);
    assert.match(text, /Camiseta.*Preto.*M.*R\$\s*80,00.*Gótico/is);
    assert.match(text, /3 produtos apresentados/);
    assert.match(text, /Atendimento automático ativado/);
    assert.equal(root.querySelector("[data-ai-resume]").hidden, false);
});

test("AI panel uses friendly handoff labels and hides empty sections", async (t) => {
    await installDOM(t, '<div id="inbox"></div>');
    Object.defineProperty(document, "hidden", { value: false, configurable: true });
    let state = aiState({ mode: "OFF", status: "CLOSED", last_decision: { action: "HANDOFF" },
        clarification: null, handoff: { reason: "PURCHASE_INTENT", clarification_attempts: null },
        focus: { selected_product: null, presented_count: 0, products: [] }, preferences: {}, recent_events: [],
        actions: { claim: false, close: false, change_mode: false, resume_ai: false, suggest: false, reply: false } });
    const root = document.querySelector("#inbox");
    const view = mountInbox(root, { interval: 100000, api: {
        async get(url) { return url.includes("/messages") ? { status: state.status, ai_mode: state.mode, cycle: 1, ai_state: state, messages: [], has_more: false } :
            { items: [{ conversation_id: "c1", phone: "Contato", status: state.status, ai_mode: state.mode, updated_at: "2026-09-12T10:00:00Z" }], has_more: false }; }
    } });
    t.after(() => view.destroy());
    await view.ready; root.querySelector("[data-id]").click();
    await eventually(() => assert.match(root.querySelector(".inbox-ai").textContent, /Cliente quer finalizar compra/));
    assert.match(root.querySelector("[data-ai-summary]").textContent, /Atendimento encerrado/);
    assert.equal(root.querySelector("[data-ai-resume]").hidden, true);
    assert.equal(root.querySelector("[data-ai-clarification]").hidden, true);
    assert.equal(root.querySelector("[data-ai-focus]").hidden, true);
    assert.equal(root.querySelector("[data-ai-preferences]").hidden, true);
    assert.equal(root.querySelector("[data-claim]").hidden, true);
});

test("AI panel labels every decision and handoff reason without raw enums", () => {
    assert.deepEqual(Object.keys(DECISION_LABELS).sort(), ["ANSWER", "CLARIFY", "HANDOFF", "NO_ACTION"]);
    assert.deepEqual(Object.keys(HANDOFF_LABELS).sort(), ["AI_FAILURE", "COMPLAINT", "DELIVERY_ISSUE", "HUMAN_REQUESTED",
        "LOW_CONFIDENCE", "NEGOTIATION", "ORDER_SUPPORT", "PAYMENT", "PURCHASE_INTENT", "RETURN_EXCHANGE"]);
    for (const [code, label] of Object.entries({ ...DECISION_LABELS, ...HANDOFF_LABELS })) {
        assert.notEqual(label, code);
        assert.doesNotMatch(label, /^[A-Z_]+$/);
    }
});

test("AI panel shows the second clarification attempt", async (t) => {
    await installDOM(t, '<div id="inbox"></div>');
    Object.defineProperty(document, "hidden", { value: false, configurable: true });
    const state = aiState({ clarification: { attempts: 2, max_attempts: 2, kind: "GENERAL" }, handoff: null });
    const root = document.querySelector("#inbox");
    const view = mountInbox(root, { interval: 100000, api: {
        async get(url) { return url.includes("/messages") ? { status: state.status, ai_mode: state.mode, cycle: 1, ai_state: state, messages: [], has_more: false } :
            { items: [{ conversation_id: "c1", phone: "Contato", status: state.status, ai_mode: state.mode, updated_at: "2026-09-12T10:00:00Z" }], has_more: false }; }
    } });
    t.after(() => view.destroy());
    await view.ready; root.querySelector("[data-id]").click();
    await eventually(() => assert.match(root.querySelector("[data-ai-clarification-text]").textContent, /Tentativa: 2 de 2/));
});

test("resume is disabled in flight and polling updates AI state without clearing draft", async (t) => {
    await installDOM(t, '<div id="inbox"></div>');
    Object.defineProperty(document, "hidden", { value: false, configurable: true });
    let state = aiState(), detailCalls = 0, release;
    const root = document.querySelector("#inbox");
    const view = mountInbox(root, { interval: 20, api: {
        async get(url) {
            if (!url.includes("/messages")) return { items: [{ conversation_id: "c1", phone: "Contato", status: state.status, ai_mode: state.mode, updated_at: "2026-09-12T10:00:00Z" }], has_more: false };
            detailCalls++;
            return { status: state.status, ai_mode: state.mode, cycle: 1, ai_state: state, messages: [], has_more: false };
        },
        async patch() {
            await new Promise((resolve) => { release = resolve; });
            state = aiState({ status: "AI", clarification: null, handoff: null,
                actions: { claim: true, close: true, change_mode: true, resume_ai: false, suggest: true, reply: false } });
            return { status: "AI", ai_mode: "AUTO" };
        }
    } });
    t.after(() => view.destroy());
    await view.ready; root.querySelector("[data-id]").click();
    await eventually(() => assert.equal(root.querySelector("[data-ai-resume]").hidden, false));
    const field = root.querySelector("textarea"); field.value = "Rascunho preservado";
    root.querySelector("[data-ai-resume]").click();
    assert.equal(root.querySelector("[data-ai-resume]").disabled, true);
    release();
    await eventually(() => assert.equal(root.querySelector("[data-ai-summary]").textContent, "Atendimento automático ativo"));
    assert.equal(root.querySelector("[data-ai-resume]").hidden, true);
    assert.equal(field.value, "Rascunho preservado");
    assert.ok(detailCalls >= 2);
});

test("mobile inbox prevents horizontal overflow and keeps the AI panel collapsible", async () => {
    const css = await readFile(new URL("../../frontend/admin/atendimento/atendimento.css", import.meta.url), "utf8");
    assert.match(css, /\.inbox\s*\{[^}]*max-width:\s*100%[^}]*overflow:\s*hidden/s);
    assert.match(css, /@media\s*\(max-width:\s*720px\)[\s\S]*\.inbox-ai details\s*\{[^}]*max-width:\s*100%/);
});

test("AI suggestion copy and send reuse the human message endpoint", async (t) => {
    await installDOM(t, '<div id="inbox"></div>');
    Object.defineProperty(document, "hidden", { value: false, configurable: true });
    let mode = "ASSIST";
    const calls = [], root = document.querySelector("#inbox");
    const answer = "Temos M preta no catálogo. 🖤";
    const view = mountInbox(root, { interval: 100000, api: {
        async get(url) { return url.includes("/messages") ? { status: "HUMAN", ai_mode: mode, cycle: 1, messages: [], has_more: false } :
            { items: [{ conversation_id: "c1", phone: "Contato", status: "HUMAN", ai_mode: mode, updated_at: "2026-09-12T10:00:00Z" }], has_more: false }; },
        async post(url, data) {
            calls.push({ url, data });
            if (url.endsWith("/ai-suggestion")) return { message: answer };
            return { id: "sent", sender: "human", content: data.message, created_at: "2026-09-12T11:00:00Z", delivery_status: "sent" };
        },
        async patch(url, data) { mode = data.ai_mode; return { ai_mode: mode, status: "HUMAN" }; }
    } });
    t.after(() => view.destroy());
    await view.ready; root.querySelector("[data-id]").click();
    await eventually(() => assert.equal(root.querySelector(".inbox-messages").textContent, ""));
    assert.equal(root.querySelector("[data-ai-summary]").textContent, "IA em modo assistido");
    root.querySelector("[data-ai-generate]").click();
    await eventually(() => assert.equal(root.querySelector("[data-ai-suggestion]").textContent, answer));
    assert.equal(calls.length, 1);
    root.querySelector("[data-ai-suggestion]").click();
    assert.equal(root.querySelector("textarea").value, answer);
    root.querySelector("[data-ai-send]").click();
    await eventually(() => assert.equal(root.querySelector("textarea").value, ""));
    assert.equal(calls[1].url, "/admin/conversations/c1/messages");
    assert.equal(calls[1].data.message, answer);
    const select = root.querySelector("[data-ai-mode]"); select.value = "OFF";
    select.dispatchEvent(new window.Event("change"));
    await eventually(() => assert.equal(select.value, "OFF"));
    assert.equal(root.querySelector("[data-ai-summary]").textContent, "IA desativada");
    assert.equal(root.querySelector("[data-ai-generate]").disabled, true);
});

test("inbox filters, claims, displays safe history, sends once and closes", async (t) => {
    await installDOM(t, '<div id="inbox"></div>');
    Object.defineProperty(document, "hidden", { value: false, configurable: true });
    let state = "WAITING_HUMAN", pending, calls = [];
    const initial = { id: "first", content: '<img src=x onerror=alert(1)>', sender: "customer", created_at: "2026-09-12T10:00:00Z" };
    const api = {
        async get(url) {
            calls.push(url);
            return url.includes("/messages") ? { status: state, messages: [initial], has_more: false }
                : { items: [{ conversation_id: "c1", phone: "5599999999", status: state, last_message: initial }], has_more: false };
        },
        async post(url, data) {
            calls.push({ url, data });
            if (url.endsWith("/claim")) return { status: state = "HUMAN" };
            if (url.endsWith("/close")) return { status: state = "CLOSED" };
            await new Promise((resolve) => { pending = resolve; });
            return { id: "reply", sender: "human", content: data.message, created_at: "2026-09-12T11:00:00Z", delivery_status: "sent" };
        }
    };
    const root = document.querySelector("#inbox");
    const view = mountInbox(root, { api, interval: 100000 });
    t.after(() => view.destroy());
    await view.ready;
    assert.equal(root.querySelector("img"), null);
    root.querySelector("[data-id]").click();
    await eventually(() => assert.equal(root.querySelector(".inbox-message p").textContent, initial.content));
    assert.equal(root.querySelector("textarea").disabled, true);
    root.querySelector("[data-claim]").click();
    await eventually(() => assert.equal(root.querySelector("textarea").disabled, false));
    const field = root.querySelector("textarea"), form = root.querySelector("form");
    field.value = " "; form.dispatchEvent(new window.Event("submit", { cancelable: true }));
    assert.equal(calls.filter((c) => c.url?.endsWith("/messages")).length, 0);
    field.value = "Resposta"; field.dispatchEvent(new window.Event("input"));
    form.dispatchEvent(new window.Event("submit", { cancelable: true }));
    form.dispatchEvent(new window.Event("submit", { cancelable: true }));
    assert.equal(calls.filter((c) => c.url?.endsWith("/messages")).length, 1);
    assert.equal(field.disabled, true);
    pending();
    await eventually(() => assert.equal(field.value, ""));
    await eventually(() => assert.equal(root.querySelector("[data-close]").disabled, false));
    root.querySelector("[data-close]").click();
    await eventually(() => assert.equal(root.querySelector("[data-status]").textContent, "Encerrada"));
    await eventually(() => assert.equal(root.querySelector("[data-claim]").disabled, false));
    const filter = root.querySelector("[data-filter]"); filter.value = "CLOSED";
    filter.dispatchEvent(new window.Event("change"));
    await eventually(() => assert.ok(calls.some((c) => typeof c === "string" && c.includes("status=CLOSED"))));
    assert.equal(root.querySelector("img"), null);
});

test("network retry retains draft and UUID; navigation cleanup ignores late responses", async (t) => {
    await installDOM(t, '<div id="inbox"></div>');
    Object.defineProperty(document, "hidden", { value: false, configurable: true });
    const attempts = [];
    const root = document.querySelector("#inbox");
    const view = mountInbox(root, { interval: 100000, api: {
        async get(url) { return url.includes("/messages") ? { status: "HUMAN", messages: [], has_more: false } :
            { items: [{ conversation_id: "c1", phone: "5599999999", status: "HUMAN", updated_at: "2026-09-12T10:00:00Z" }], has_more: false }; },
        async post(url, data) { attempts.push(data); throw new Error("Sem conexão"); }
    } });
    t.after(() => view.destroy());
    await view.ready; root.querySelector("[data-id]").click();
    await eventually(() => assert.equal(root.querySelector(".inbox-messages").textContent, ""));
    const field = root.querySelector("textarea"), form = root.querySelector("form");
    field.value = "Olá";
    form.dispatchEvent(new window.Event("submit", { cancelable: true }));
    await eventually(() => assert.equal(field.disabled, false));
    assert.equal(field.value, "Olá");
    form.dispatchEvent(new window.Event("submit", { cancelable: true }));
    await eventually(() => assert.equal(attempts.length, 2));
    assert.equal(attempts[0].message_id, attempts[1].message_id);
    view.destroy();
    await new Promise((resolve) => setTimeout(resolve, 10));
    assert.equal(root.textContent, "");
});
