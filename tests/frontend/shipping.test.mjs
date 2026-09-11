import assert from "node:assert/strict";
import { test } from "node:test";
import { createCartController } from "../../frontend/js/cart/cart.js";
import { createShippingView } from "../../frontend/js/cart/shipping_ui.js";
import { cartItemKey } from "../../frontend/js/cart/cart_state.js";
import { installDOM, eventually } from "./helpers/dom.mjs";

const address = { recipient: "Cliente Teste", phone: "74999990000", cep: "48900000", street: "Rua Teste",
    number: "12", neighborhood: "Centro", city: "Juazeiro", state: "BA", complement: "Casa", reference: "Portão azul" };
const product = { id: "piece-001", title: "Camiseta", available: true, price: 100, images: [],
    variants: [{ id: 8, size: "M", color: "Preto", quantity: 3 }] };
const selection = { size: "M", color: "Preto" };
const quotation = () => ({ quote_token: "signed-token", expires_at: Math.floor(Date.now() / 1000) + 600,
    subtotal_cents: 10000, clothing_subtotal_cents: 10000, shipping_cents: 0, total_cents: 10000,
    radius_meters: 7000, route_meters: 8000, free_shipping: true, policy: "Política de frete" });

async function setup(overrides = {}) {
    const calls = [], saved = [];
    const cart = createCartController({ fetchProduct: async () => structuredClone(product),
        storage: { loadCart: () => [], saveCart: (items) => { saved.push(JSON.stringify(items)); return true; }, clearCart: () => true },
        shippingApi: { quoteShipping: async (data) => { calls.push(data); return quotation(); },
            checkoutShipping: async (data) => { calls.push(data); return { message: "Total confirmado: R$ 100,00" }; }, ...overrides } });
    await cart.add(product.id, selection);
    return { cart, calls, saved };
}

test("shipping sends item identities, verifies checkout server-side and never persists address or token", async () => {
    const { cart, calls, saved } = await setup();
    await cart.quoteShipping(address);
    assert.deepEqual(calls[0], { address, items: [{ product_id: product.id, variant_id: 8, quantity: 1 }] });
    const url = new URL(await cart.prepareCheckout(address));
    assert.equal(url.searchParams.get("text"), "Total confirmado: R$ 100,00");
    assert.equal(calls[1].quote_token, "signed-token");
    assert.doesNotMatch(saved.join(""), /Cliente Teste|Rua Teste|signed-token/);
});

test("quantity and address changes invalidate shipping and require a new quote", async () => {
    const { cart } = await setup();
    await cart.quoteShipping(address);
    await cart.setQuantity(cartItemKey(cart.getSnapshot().items[0]), 2);
    assert.equal(cart.getSnapshot().shippingQuote, null);
    await assert.rejects(cart.prepareCheckout(address), /Calcule o frete/);
    await cart.setQuantity(cartItemKey(cart.getSnapshot().items[0]), 1);
    await cart.quoteShipping(address);
    await assert.rejects(cart.prepareCheckout({ ...address, number: "99" }), /Calcule o frete/);
});

test("address edits during an in-flight lookup discard the stale quote", async () => {
    let resolve;
    const { cart } = await setup({ quoteShipping: () => new Promise((done) => { resolve = done; }) });
    const pending = cart.quoteShipping(address);
    await eventually(() => assert.equal(typeof resolve, "function"));
    cart.invalidateShipping();
    resolve(quotation());
    await assert.rejects(pending, /endereço mudou/);
    assert.equal(cart.getSnapshot().shippingQuote, null);
});

test("expired and server-rejected quotes cannot be reused", async () => {
    const { cart } = await setup({ quoteShipping: async () => ({ ...quotation(), expires_at: 1 }) });
    await cart.quoteShipping(address);
    await assert.rejects(cart.prepareCheckout(address), /Calcule o frete/);
    const second = await setup({ checkoutShipping: async () => { throw Object.assign(new Error("Preço mudou"), { status: 409 }); } });
    await second.cart.quoteShipping(address);
    await assert.rejects(second.cart.prepareCheckout(address), /Preço mudou/);
    assert.equal(second.cart.getSnapshot().shippingQuote, null);
});

test("manual delivery remains explicit and never claims free shipping", async () => {
    const { cart, calls } = await setup();
    const message = new URL(await cart.prepareCheckout(address, { manual: true })).searchParams.get("text");
    assert.match(message, /Frete a confirmar com a loja/);
    assert.match(message, /Cliente Teste/);
    assert.match(message, /48900000/);
    assert.doesNotMatch(message, /Frete: Grátis/);
    assert.equal(calls.length, 0);
});

test("delivery form validates fields, preserves input on render and enables quoted checkout", async (t) => {
    const win = await installDOM(t, "<body></body>");
    const calls = [];
    const view = createShippingView({ onQuote: (data) => calls.push(["quote", data]),
        onAddressChange: () => calls.push(["edit"]), onCheckout: (...args) => calls.push(["checkout", ...args]) });
    t.after(() => view.destroy());
    document.body.append(view.element);
    const state = { items: [product], busy: false, shippingQuote: null };
    view.render(state);
    view.element.dispatchEvent(new win.Event("submit", { bubbles: true, cancelable: true }));
    assert.equal(calls.length, 0);
    for (const [name, value] of Object.entries(address)) view.element.elements.namedItem(name).value = value;
    view.render({ ...state, busy: true });
    assert.equal(view.element.querySelector("fieldset").disabled, true);
    view.render(state);
    assert.equal(view.element.elements.namedItem("recipient").value, address.recipient);
    view.element.dispatchEvent(new win.Event("submit", { bubbles: true, cancelable: true }));
    await eventually(() => assert.equal(calls.length, 1));
    assert.deepEqual(calls[0], ["quote", address]);
    assert.equal(view.element.querySelector("[data-checkout]").disabled, true);
    view.render({ ...state, shippingQuote: quotation() });
    view.element.querySelector("[data-checkout]").click();
    await eventually(() => assert.equal(calls.length, 2));
    assert.deepEqual(calls[1], ["checkout", address, { manual: false }]);
    view.render({ ...state, shippingQuote: { ...quotation(), quote_token: "expired", expires_at: 1 } });
    assert.equal(view.element.querySelector("[data-checkout]").disabled, true);
    assert.match(view.element.textContent, /cotação expirou/);
    view.element.querySelector("[data-manual]").click();
    await eventually(() => assert.equal(calls.length, 3));
    assert.deepEqual(calls[2], ["checkout", address, { manual: true }]);
});

test("CEP lookup fills address only and ignores a response after CEP changes", async (t) => {
    await installDOM(t, "<body></body>");
    let resolve;
    const view = createShippingView({ onAddressChange() {} }, { cep: () => new Promise((done) => { resolve = done; }),
        policy: async () => ({ configured: false, description: '<img src=x onerror="bad()">' }) });
    t.after(() => view.destroy());
    document.body.append(view.element);
    view.render({ items: [product], busy: false });
    await view.loadPolicy();
    assert.equal(view.element.querySelector("img"), null);
    const field = (name) => view.element.elements.namedItem(name);
    field("cep").value = address.cep;
    field("recipient").value = address.recipient;
    view.element.querySelector("[data-cep]").click();
    await eventually(() => assert.equal(typeof resolve, "function"));
    field("cep").value = "11111111";
    resolve(address);
    await eventually(() => assert.equal(view.element.querySelector("[data-cep]").disabled, false));
    assert.equal(field("street").value, "");
    resolve = null;
    view.element.querySelector("[data-cep]").click();
    await eventually(() => assert.equal(typeof resolve, "function"));
    resolve(address);
    await eventually(() => assert.equal(field("street").value, address.street));
    assert.equal(field("recipient").value, address.recipient);
});
