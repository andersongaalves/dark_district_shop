import assert from "node:assert/strict";
import { test } from "node:test";
import { createCartController } from "../../frontend/js/cart/cart.js";
import { cartItemKey, cartCount, cartSubtotal, itemForSelection, sanitizeCartItems } from "../../frontend/js/cart/cart_state.js";
import { loadCart, saveCart, clearCart, CART_STORAGE_KEY } from "../../frontend/js/cart/cart_storage.js";
import { createCartView } from "../../frontend/js/cart/cart_ui.js";
import { getSelectedVariant } from "../../frontend/js/core/products.js";
import { installDOM, eventually } from "./helpers/dom.mjs";

const product = { id: "piece-001", title: "Camiseta", available: true, price: 79.9,
    images: [{ url: "https://example.com/piece.webp" }], variants: [
        { id: 8, size: "G", color: "Preto", quantity: 3 },
        { id: 9, size: "M", color: "Preto", quantity: 1 }
    ] };
const selection = { size: "G", color: "Preto" };

function memoryStorage() {
    const values = new Map();
    return { getItem: (key) => values.get(key) ?? null,
        setItem: (key, value) => values.set(key, value), removeItem: (key) => values.delete(key) };
}

function controllerWith(fetchProduct = async () => structuredClone(product), raw = memoryStorage()) {
    return createCartController({ fetchProduct, storage: {
        loadCart: () => loadCart(raw), saveCart: (items) => saveCart(items, raw), clearCart: () => clearCart(raw)
    } });
}

test("cart requires a complete valid variant, including explicit mixed empty options", () => {
    assert.equal(getSelectedVariant(product), undefined);
    assert.equal(getSelectedVariant(product, { color: "Preto" }), undefined);
    assert.equal(getSelectedVariant(product, { size: "GG", color: "Preto" }), undefined);
    assert.equal(getSelectedVariant(product, selection).id, 8);
    assert.equal(getSelectedVariant({ available: true, variants: [] }), null);
    const mixed = { ...product, variants: [...product.variants, { id: 10, size: null, color: null, quantity: 1 }] };
    assert.equal(getSelectedVariant(mixed, { size: "", color: "" }).id, 10);
    assert.equal(getSelectedVariant({ ...product, available: false }, selection), undefined);
});

test("same variant increments; other variants stay separate; remove and clear update totals", async () => {
    const cart = controllerWith();
    await cart.add(product.id, selection);
    await cart.add(product.id, selection);
    await cart.add(product.id, { size: "M", color: "Preto" });
    const state = cart.getSnapshot();
    assert.equal(state.items.length, 2);
    assert.equal(state.count, 3);
    assert.equal(state.subtotal, 239.7);
    await cart.remove(cartItemKey(state.items[1]));
    assert.equal(cart.getSnapshot().count, 2);
    await cart.clear();
    assert.equal(cart.getSnapshot().count, 0);
    assert.equal(cart.getSnapshot().subtotal, 0);
});

test("concurrent additions serialize stock checks and do not exceed the last unit", async () => {
    let calls = 0;
    const cart = controllerWith(async () => { calls++; return product; });
    const result = await Promise.allSettled([cart.add(product.id, { size: "M", color: "Preto" }),
        cart.add(product.id, { size: "M", color: "Preto" })]);
    assert.deepEqual(result.map((item) => item.status), ["fulfilled", "rejected"]);
    assert.equal(cart.getSnapshot().count, 1);
    assert.equal(calls, 2);
    assert.equal(cart.getSnapshot().busy, false);
});

test("quantity changes revalidate current stock and reject invalid user values", async () => {
    let latest = structuredClone(product);
    const cart = controllerWith(async () => latest);
    await cart.add(product.id, selection);
    const key = cartItemKey(cart.getSnapshot().items[0]);
    await cart.setQuantity(key, 3);
    assert.equal(cart.getSnapshot().count, 3);
    latest.variants[0].quantity = 1;
    await assert.rejects(cart.setQuantity(key, 2), /Estoque disponível: 1/);
    await assert.rejects(cart.prepareCheckout(), /sinalizados/);
    await cart.setQuantity(key, 1);
    assert.equal(cart.getSnapshot().count, 1);
    assert.equal(cart.getSnapshot().items[0].issue, "");
    for (const quantity of [0, -1, 1.5, NaN, Infinity, 1000, "2"]) {
        await assert.rejects(cart.setQuantity(key, quantity), /quantidade inteira/);
    }
});

test("storage survives new page/controller instances but prices are revalidated", async () => {
    const raw = memoryStorage();
    const first = controllerWith(undefined, raw);
    await first.add(product.id, selection);
    const second = controllerWith(async () => ({ ...product, price: 99.9 }), raw);
    assert.equal(second.getSnapshot().count, 1);
    assert.equal(second.getSnapshot().items[0].validated, false);
    await second.refresh();
    assert.equal(second.getSnapshot().subtotal, 99.9);
    assert.equal(second.getSnapshot().items[0].validated, true);
    const stored = JSON.parse(raw.getItem(CART_STORAGE_KEY));
    assert.equal(stored.version, 1);
    assert.equal("stock" in stored.items[0], false);
    assert.equal("validated" in stored.items[0], false);
    await second.clear();
    assert.equal(raw.getItem(CART_STORAGE_KEY), null);
    assert.equal(controllerWith(undefined, raw).getSnapshot().count, 0);
});

test("invalid/old JSON and tampered storage are harmless and cannot supply stock or price authority", async () => {
    const raw = memoryStorage();
    for (const data of ["broken", "null", "{}", "[]", '{"version":0,"items":[]}', '{"version":1,"items":{}}']) {
        raw.setItem(CART_STORAGE_KEY, data);
        assert.deepEqual(loadCart(raw), []);
    }
    const item = { ...itemForSelection(product, selection), price: 0.01, stock: 9999, validated: true };
    saveCart([item], raw);
    const saved = loadCart(raw)[0];
    assert.equal(saved.stock, undefined);
    assert.equal(saved.validated, undefined);
    const cart = controllerWith(undefined, raw);
    await assert.rejects(cart.prepareCheckout(), /Preços ou opções mudaram/);
    assert.equal(cart.getSnapshot().subtotal, 79.9);
    const url = new URL(await cart.prepareCheckout());
    assert.equal(url.hostname, "wa.me");
    assert.match(url.searchParams.get("text"), /R\$ 79,90/);
    assert.doesNotMatch(url.searchParams.get("text"), /0,01/);
    for (const bad of [{ quantity: -2 }, { quantity: 1.5 }, { productId: "../secret" }, { variantId: -1 }, { price: NaN }]) {
        assert.deepEqual(sanitizeCartItems([{ ...item, ...bad }]), []);
    }
});

test("unavailable storage does not prevent using the cart in memory", async () => {
    const blocked = { getItem() { throw Error("blocked"); }, setItem() { throw Error("blocked"); }, removeItem() { throw Error("blocked"); } };
    assert.deepEqual(loadCart(blocked), []);
    const cart = controllerWith(undefined, blocked);
    await cart.add(product.id, selection);
    assert.equal(cart.getSnapshot().count, 1);
    assert.equal(cart.getSnapshot().persisted, false);
    await cart.clear();
    assert.equal(cart.getSnapshot().count, 0);
});

test("checkout blocks sold/deleted products, removed variants and network failures", async () => {
    let latest = product;
    const cart = controllerWith(async () => { if (latest instanceof Error) throw latest; return latest; });
    await cart.add(product.id, selection);
    for (const value of [{ ...product, available: false }, null, { ...product, variants: [] }, new Error("offline")]) {
        latest = value;
        await assert.rejects(cart.prepareCheckout(), /sinalizados/);
        assert.ok(cart.getSnapshot().items[0].issue);
    }
    latest = product;
    assert.match(await cart.prepareCheckout(), /^https:\/\/wa.me\//);
});

test("new product options and price changes require a fresh review before checkout", async () => {
    let latest = structuredClone(product);
    const cart = controllerWith(async () => latest);
    await cart.add(product.id, selection);
    latest.price = 89.9;
    latest.variants[0].color = "Branco";
    await assert.rejects(cart.prepareCheckout(), /Revise os valores/);
    const url = new URL(await cart.prepareCheckout());
    assert.match(url.searchParams.get("text"), /Branco/);
    assert.match(url.searchParams.get("text"), /89,90/);
});

test("products without variants use availability, without inventing a single-unit stock rule", async () => {
    const cart = controllerWith(async () => ({ ...product, variants: [] }));
    await cart.add(product.id, {}, 3);
    assert.equal(cart.getSnapshot().count, 3);
    assert.equal(cart.getSnapshot().items[0].variantId, null);
    assert.equal(cart.getSnapshot().items[0].stock, null);
});

test("cart totals use cents to avoid accumulated floating-point errors", () => {
    const items = [{ quantity: 3, price: 0.1 }, { quantity: 1, price: 0.2 }];
    assert.equal(cartCount(items), 4);
    assert.equal(cartSubtotal(items), 0.5);
});

test("cart DOM escapes stored data and connects quantity, removal and clear actions", async (t) => {
    const win = await installDOM(t, "<body></body>");
    const calls = [];
    const view = createCartView({ onQuantity: (...args) => calls.push(["quantity", ...args]),
        onRemove: (...args) => calls.push(["remove", ...args]), onClear: () => calls.push(["clear"]),
        onRefresh() {}, onCheckout() {} });
    const item = { ...itemForSelection(product, selection), title: '<img src=x onerror="bad()">',
        image: "javascript:bad()", size: '<script>bad()</script>' };
    view.render({ items: [item], count: 1, subtotal: 79.9, busy: false, message: "<script>bad()</script>", persisted: true });
    assert.equal(document.querySelector("script, img"), null);
    assert.match(document.querySelector("article").textContent, /<img/);
    const input = document.querySelector("[data-quantity]");
    input.value = "2";
    input.dispatchEvent(new win.Event("change", { bubbles: true }));
    document.querySelector("[data-remove]").click();
    document.querySelector("[data-clear]").click();
    await eventually(() => assert.equal(calls.length, 3));
    assert.deepEqual(calls[0], ["quantity", cartItemKey(item), 2]);
    assert.deepEqual(calls[1], ["remove", cartItemKey(item)]);
    assert.deepEqual(calls[2], ["clear"]);
});
