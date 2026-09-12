import assert from "node:assert/strict";
import { test } from "node:test";
import { installDOM, eventually } from "./helpers/dom.mjs";
import { mountInbox } from "../../frontend/admin/atendimento/atendimento.js";

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
