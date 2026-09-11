import assert from "node:assert/strict";
import { test } from "node:test";
import { installDOM, eventually } from "./helpers/dom.mjs";
import { CART_STORAGE_KEY } from "../../frontend/js/cart/cart_storage.js";

test("product selection adds to persistent cart, updates header/drawer and retains WhatsApp interest", async (t) => {
    const win = await installDOM(t, '<header id="header"></header><section id="produto"></section>',
        'https://darkdistrict.com.br/pages/produto/index.html?id=piece-001');
    // Exercise DOM wiring; these two methods do not simulate browser layout/focus trapping.
    win.HTMLDialogElement.prototype.showModal = function () { this.open = true; };
    win.HTMLDialogElement.prototype.close = function () { this.open = false; };
    let interestUrl;
    win.open = (url) => { interestUrl = url; };
    const product = { id: "piece-001", title: "Peça", description: "Descrição", price: 79.9,
        category: "Camisetas", category_id: 1, available: true, product_type: "brecho", images: [],
        variants: [{ id: 8, size: "G", color: "Preto", quantity: 3 }] };
    t.mock.method(globalThis, "fetch", async () => Response.json(product));
    const { renderHeader } = await import("../../frontend/js/components/header.js");
    const { renderProduto } = await import("../../frontend/js/sections/produto/produto.js");
    const { getCart } = await import("../../frontend/js/cart/cart.js");
    renderHeader();
    await renderProduto();
    const add = document.querySelector(".produto__cart");
    assert.equal(add.disabled, true);
    document.querySelector('[data-option="color"]').click();
    assert.equal(add.disabled, true);
    document.querySelector('[data-option="size"]').click();
    assert.equal(add.disabled, false);
    add.click();
    await eventually(() => assert.equal(document.querySelector('[data-cart-count]').textContent, "1"));
    assert.equal(JSON.parse(localStorage.getItem(CART_STORAGE_KEY)).items[0].variantId, 8);
    assert.match(document.querySelector(".produto__cart-status").textContent, /Adicionado/);
    document.querySelector(".produto__interest").click();
    assert.equal(new URL(interestUrl).hostname, "wa.me");
    assert.equal(new URL(interestUrl).pathname, "/557488036775");
    assert.equal(new URL(interestUrl).searchParams.get("text"),
        "Olá! Tenho interesse neste produto:\n\nProduto: Peça\nID: piece-001\nPreço: R$ 79,90\nCor: Preto\nTamanho: G");
    document.querySelector(".header-cart").click();
    assert.equal(document.querySelector("dialog").open, true);
    await eventually(() => assert.equal(getCart().getSnapshot().busy, false));
    assert.match(document.querySelector("dialog article").textContent, /Tamanho: G · Cor: Preto/);
    assert.match(document.querySelector(".cart-drawer__subtotal").textContent, /79,90/);
    renderHeader();
    assert.equal(document.querySelectorAll("dialog").length, 1);
    assert.equal(document.querySelector('[data-cart-count]').textContent, "1");

    // A storage event from a second tab replaces the snapshot and revalidates it.
    const external = JSON.parse(localStorage.getItem(CART_STORAGE_KEY));
    external.items[0].quantity = 2;
    external.items[0].price = 0.01;
    localStorage.setItem(CART_STORAGE_KEY, JSON.stringify(external));
    win.dispatchEvent(new win.StorageEvent("storage", { key: CART_STORAGE_KEY }));
    await eventually(() => assert.equal(getCart().getSnapshot().count, 2));
    await eventually(() => assert.equal(getCart().getSnapshot().busy, false));
    assert.equal(getCart().getSnapshot().subtotal, 159.8);
    assert.equal(document.querySelector('[data-cart-count]').textContent, "2");
    document.querySelector('[data-clear]').click();
    await eventually(() => assert.equal(document.querySelector('[data-cart-count]').textContent, "0"));
    assert.equal(localStorage.getItem(CART_STORAGE_KEY), null);
});
