import assert from "node:assert/strict";
import { test } from "node:test";
import { openProductModal } from "../../frontend/admin/produtos/produtos_modal.js";

test("failed saves retain form data, prevent duplicate requests, and allow retry", async (t) => {
    // Small DOM contract double for the async controller; browser rendering is not simulated.
    let submitHandler;
    let removed = false;
    const submit = { disabled: false };
    const alert = { textContent: "", setAttribute() {} };
    const emptyCollection = { querySelectorAll: () => [] };
    const fieldValues = new Map([
        ["id", "item"], ["title", "Produto"], ["description", "Descrição"],
        ["price", "10"], ["category", "Teste"], ["gender", ""],
        ["available", "on"], ["featured", "on"]
    ]);
    const form = {
        querySelector: () => submit,
        appendChild() {},
        addEventListener: (_event, callback) => { submitHandler = callback; }
    };
    const modal = {
        setAttribute() {},
        remove() { removed = true; },
        querySelectorAll: () => [],
        querySelector(selector) {
            if (selector === "#produto-form") return form;
            if (["#produto-images", "#produto-variants"].includes(selector)) return emptyCollection;
            return { addEventListener() {} };
        }
    };
    const originalDocument = globalThis.document;
    const originalFormData = globalThis.FormData;
    globalThis.document = {
        createElement: (tag) => tag === "p" ? alert : modal,
        body: { appendChild() {} }
    };
    globalThis.FormData = class { get(name) { return fieldValues.get(name) ?? null; } };
    t.after(() => { globalThis.document = originalDocument; globalThis.FormData = originalFormData; });

    let rejectSave;
    let attempts = 0;
    openProductModal({ onSubmit: (payload) => {
        attempts += 1;
        assert.equal(payload.gender, "");
        assert.equal(payload.price, 10);
        assert.equal(payload.featured, true);
        if (attempts === 1) return new Promise((_resolve, reject) => { rejectSave = reject; });
    } });
    const event = { preventDefault() {} };
    const first = submitHandler(event);
    assert.equal(submit.disabled, true);
    await submitHandler(event);
    assert.equal(attempts, 1);
    rejectSave(new Error("Falha temporária"));
    await first;
    assert.equal(removed, false);
    assert.equal(alert.textContent, "Falha temporária");
    assert.equal(submit.disabled, false);
    assert.equal(fieldValues.get("title"), "Produto");
    await submitHandler(event);
    assert.equal(attempts, 2);
    assert.equal(removed, true);
});
