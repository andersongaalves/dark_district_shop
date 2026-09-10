import assert from "node:assert/strict";
import { test } from "node:test";
import { installDOM, eventually } from "./helpers/dom.mjs";
import { openProductModal } from "../../frontend/admin/produtos/produtos_modal.js";
import { carregarConfiguracoes } from "../../frontend/admin/configuracoes/configuracoes.js";
import { carregarProdutos } from "../../frontend/admin/produtos/produtos.js";

test("product form submits relational fields, independent flags and stable variant IDs", async (t) => {
    const win = await installDOM(t, "<body></body>");
    let payload;
    openProductModal({
        produto: { id: "piece", title: "Peça", price: 80, category_id: 2, collection_id: 5, product_type: "drop",
            is_offer: true, featured: true, variants: [{ id: 8, size: "G", color: "Preto", quantity: 1 }] },
        categories: [{ id: 1, name: "Ativa", active: true }, { id: 2, name: "Antiga", active: false }, { id: 3, name: "Oculta", active: false }],
        collections: [{ id: 5, name: "Nocturne", active: false }, { id: 6, name: "Oculta", active: false }],
        onSubmit: async (data) => { payload = data; }
    });
    assert.equal(document.querySelector('[name="category_id"]').value, "2");
    assert.equal(document.querySelector('[name="product_type"]').value, "drop");
    assert.equal(document.querySelector('[name="category_id"] option[value="3"]'), null);
    assert.equal(document.querySelector('[name="collection_id"] option[value="6"]'), null);
    document.querySelector('[name="collection_id"]').value = "";
    document.querySelector("form").dispatchEvent(new win.Event("submit", { bubbles: true, cancelable: true }));
    await eventually(() => assert.ok(payload));
    assert.equal(payload.category_id, 2);
    assert.equal(payload.collection_id, null);
    assert.equal(payload.product_type, "drop");
    assert.equal(payload.is_offer, true);
    assert.equal(payload.featured, true);
    assert.deepEqual(payload.variants, [{ id: 8, size: "G", color: "Preto", quantity: 1 }]);
});

test("new products cannot select inactive taxonomy and configuration markup is escaped", async (t) => {
    await installDOM(t, "<body></body>");
    openProductModal({ type: "brecho", categories: [{ id: 1, name: '<img src=x onerror="bad()">', active: true },
        { id: 2, name: "Inativa", active: false }], collections: [{ id: 3, name: "Inativa", active: false }], onSubmit() {} });
    assert.equal(document.querySelector('[name="product_type"]').value, "brecho");
    assert.equal(document.querySelector('[name="category_id"]').options.length, 2);
    assert.equal(document.querySelector('[name="collection_id"]').options.length, 1);
    assert.equal(document.querySelector("img"), null);
    assert.equal(document.querySelector('[name="category_id"]').checkValidity(), false);
});

for (const resource of ["categorias", "colecoes"]) {
    test(`${resource} configuration creates, edits, deactivates and retains errors`, async (t) => {
        const win = await installDOM(t, '<section id="admin-configuracoes"></section>');
        const calls = [];
        let records = [];
        t.mock.method(globalThis, "fetch", async (url, options = {}) => {
            const method = options.method || "GET";
            const body = options.body ? JSON.parse(options.body) : null;
            calls.push({ path: new URL(url).pathname, method, body });
            if (method === "POST") records = [{ id: 1, ...body }];
            if (method === "PATCH") records = [{ ...records[0], ...body }];
            if (method === "DELETE") return Response.json({ detail: "Existem produtos vinculados." }, { status: 409 });
            return Response.json(method === "GET" ? records : records[0]);
        });
        await carregarConfiguracoes({ resource });
        document.querySelector('[name="name"]').value = "Nocturne";
        document.querySelector('[name="slug"]').value = "nocturne";
        document.querySelector("form").dispatchEvent(new win.Event("submit", { cancelable: true }));
        await eventually(() => assert.ok(document.querySelector('[data-action="edit"]')));
        assert.ok(calls.some((call) => call.method === "POST" && call.body.active));
        document.querySelector('[data-action="edit"]').click();
        document.querySelector('[name="name"]').value = "Novo nome";
        document.querySelector("form").dispatchEvent(new win.Event("submit", { cancelable: true }));
        await eventually(() => assert.match(document.querySelector("article").textContent, /Novo nome/));
        document.querySelector('[data-action="toggle"]').click();
        await eventually(() => assert.match(document.querySelector("article").textContent, /Desativada/));
        document.querySelector('[data-action="delete"]').click();
        await eventually(() => assert.match(document.querySelector('[data-config-status]').textContent, /vinculados/));
        assert.equal(document.querySelectorAll("article").length, 1);
    });
}

test("admin reuses one list and API filtered by each product type", async (t) => {
    await installDOM(t, '<section id="admin-produtos"></section>');
    const types = [];
    t.mock.method(globalThis, "fetch", async (url) => {
        types.push(new URL(url).searchParams.get("product_type"));
        return Response.json([]);
    });
    for (const type of ["catalogo", "brecho", "drop"]) await carregarProdutos({ type });
    assert.deepEqual(types, ["catalogo", "brecho", "drop"]);
    assert.equal(document.querySelector("h1").textContent, "Drops");
});
