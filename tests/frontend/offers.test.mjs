import assert from "node:assert/strict";
import { test } from "node:test";
import { installDOM, eventually } from "./helpers/dom.mjs";
import { isOfferActive, getProductPrice } from "../../frontend/js/core/products.js";
import { toDateTimeInput } from "../../frontend/js/utils/format.js";
import { renderProductPrice } from "../../frontend/js/components/product_price.js";
import { renderProduct } from "../../frontend/js/sections/produto/produto_render.js";
import { renderOffers } from "../../frontend/js/sections/featured.js";
import { renderProdutos } from "../../frontend/admin/produtos/produtos_ui.js";
import { openProductModal } from "../../frontend/admin/produtos/produtos_modal.js";
import { createCartController } from "../../frontend/js/cart/cart.js";

const now = Date.parse("2030-01-02T15:00:00Z");
const product = { id: "piece", title: "Peça", description: "Descrição", category: "Camisetas", category_id: 1,
    price: 100, offer_price: 70, is_offer: true, offer_active: true,
    offer_ends_at: "2030-01-02T16:00:00Z", effective_price: 70, available: true,
    images: [{ url: "https://example.com/photo.webp" }], variants: [] };

test("promotion respects exact expiration, original price and disabled offers", () => {
    assert.equal(getProductPrice(product, now), 70);
    assert.equal(getProductPrice(product, Date.parse(product.offer_ends_at)), 100);
    assert.equal(isOfferActive(product, Date.parse(product.offer_ends_at)), false);
    assert.equal(getProductPrice({ ...product, is_offer: false }, now), 100);
    assert.equal(getProductPrice({ ...product, offer_active: false }, now), 100);
    assert.equal(getProductPrice({ ...product, offer_price: 100 }, now), 100);
    assert.equal(getProductPrice({ ...product, offer_price: -1 }, now), 100);
    assert.equal(getProductPrice({ ...product, offer_price: 0 }, now), 0);
    assert.equal(getProductPrice({ ...product, offer_ends_at: null }, now), 70);
    assert.equal(getProductPrice({ ...product, offer_price: null }, now), 100);
});

test("admin date values round-trip between local inputs and UTC", () => {
    const original = "2030-01-02T13:15:30-03:00";
    assert.equal(new Date(toDateTimeInput(original)).toISOString(), "2030-01-02T16:15:30.000Z");
    assert.equal(toDateTimeInput(null), "");
    assert.equal(toDateTimeInput("invalid"), "");
});

test("admin shows thumbnail after title and before price with safe fallback", async (t) => {
    await installDOM(t, '<section id="admin-produtos"></section>');
    renderProdutos([product, { ...product, id: "unsafe", images: [{ url: "javascript:bad()" }] }]);
    const article = document.querySelector("article");
    assert.equal(article.children[0].className, "admin-produto__title");
    assert.equal(article.children[1].className, "admin-produto__preview");
    assert.equal(article.children[2].className, "admin-produto__price");
    assert.equal(article.querySelector("img").src, product.images[0].url);
    assert.equal(document.querySelector('article[data-id="unsafe"] img'), null);
    assert.match(article.querySelector("del").textContent, /100,00/);
    assert.match(article.querySelector(".price-offer").textContent, /70,00/);
});

test("offer form toggles inputs, validates discount, saves UTC and clears disabled values", async (t) => {
    const win = await installDOM(t, "<body></body>");
    const payloads = [];
    const open = () => openProductModal({ produto: product, categories: [{ id: 1, name: "Camisetas", active: true }],
        onSubmit: async (data) => { payloads.push(data); } });
    open();
    const price = document.querySelector('[name="offer_price"]');
    const end = document.querySelector('[name="offer_ends_at"]');
    assert.equal(price.required, true);
    assert.equal(price.value, "70");
    assert.equal(new Date(end.value).toISOString(), "2030-01-02T16:00:00.000Z");
    price.value = "100";
    price.dispatchEvent(new win.Event("input"));
    assert.equal(price.checkValidity(), false);
    price.value = "65";
    price.dispatchEvent(new win.Event("input"));
    document.querySelector("form").dispatchEvent(new win.Event("submit", { cancelable: true }));
    await eventually(() => assert.equal(payloads.length, 1));
    assert.equal(payloads[0].price, 100);
    assert.equal(payloads[0].offer_price, 65);
    assert.equal(payloads[0].offer_ends_at, "2030-01-02T16:00:00.000Z");
    open();
    document.querySelector('[name="is_offer"]').click();
    assert.equal(document.querySelector("#produto-offer-fields").hidden, true);
    assert.equal(document.querySelector('[name="offer_price"]').disabled, true);
    document.querySelector("form").dispatchEvent(new win.Event("submit", { cancelable: true }));
    await eventually(() => assert.equal(payloads.length, 2));
    assert.equal(payloads[1].is_offer, false);
    assert.equal(payloads[1].offer_price, null);
    assert.equal(payloads[1].offer_ends_at, null);
});

test("open product page switches back to original price without resetting user selection", async (t) => {
    await installDOM(t, '<section id="produto"></section>');
    t.mock.timers.enable({ apis: ["Date", "setTimeout"], now });
    const section = document.querySelector("section");
    renderProduct(section, product);
    const interestButton = section.querySelector(".produto__interest");
    assert.match(section.querySelector(".price-offer").textContent, /70,00/);
    t.mock.timers.tick(60 * 60 * 1000);
    assert.equal(section.querySelector(".price-offer"), null);
    assert.match(section.querySelector(".produto__price").textContent, /100,00/);
    assert.match(section.querySelector(".price-deadline").textContent, /encerrada/);
    assert.equal(section.querySelector(".produto__interest"), interestButton);
});

test("expired offers disappear from home while the page is open", async (t) => {
    await installDOM(t, '<section id="offers"></section>');
    t.mock.timers.enable({ apis: ["Date", "setTimeout"], now });
    t.mock.method(globalThis, "fetch", async () => Response.json([product]));
    await renderOffers();
    assert.equal(document.querySelectorAll("article").length, 1);
    t.mock.timers.tick(60 * 60 * 1000);
    assert.equal(document.querySelectorAll("article").length, 0);
    assert.match(document.querySelector(".featured__grid").textContent, /Nenhum produto disponível/);
});

test("cart honors server promotional price and requires review after expiration", async () => {
    let latest = product;
    const cart = createCartController({ fetchProduct: async () => latest,
        storage: { loadCart: () => [], saveCart: () => true, clearCart: () => true } });
    await cart.add(product.id);
    assert.equal(cart.getSnapshot().subtotal, 70);
    latest = { ...product, effective_price: 100, offer_active: false };
    await assert.rejects(cart.prepareCheckout(), /Preços ou opções mudaram/);
    assert.equal(cart.getSnapshot().subtotal, 100);
    const url = new URL(await cart.prepareCheckout());
    assert.match(url.searchParams.get("text"), /100,00/);
});

test("invalid deadline text cannot produce HTML in the price component", () => {
    const html = renderProductPrice({ ...product, offer_ends_at: '<img src=x onerror="bad()">' }, { showDeadline: true });
    assert.doesNotMatch(html, /<img/);
});
