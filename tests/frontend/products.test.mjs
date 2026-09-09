import assert from "node:assert/strict";
import { test } from "node:test";
import { isProductAvailable } from "../../frontend/js/core/products.js";
import { formatPrice } from "../../frontend/js/utils/format.js";
import { escapeHtml } from "../../frontend/js/utils/dom.js";
import { ROUTES, getProductUrl, getWhatsAppUrl, getImageUrl } from "../../frontend/js/utils/urls.js";
import { renderDescription } from "../../frontend/js/sections/produto/produto_description.js";
import { renderProduct } from "../../frontend/js/sections/produto/produto_render.js";
import { renderProductForm } from "../../frontend/admin/produtos/produtos_form.js";

test("availability honors sold status even when variants have stock", () => {
    assert.equal(isProductAvailable({ available: false, variants: [{ quantity: 5 }] }), false);
});

test("products without variants use the explicit availability flag", () => {
    assert.equal(isProductAvailable({ available: true }), true);
    assert.equal(isProductAvailable({ available: false }), false);
});

test("partial selection checks all matching variants and impossible combinations", () => {
    const product = { available: true, variants: [
        { color: "Preto", size: "M", quantity: 0 },
        { color: "Preto", size: "G", quantity: 3 },
        { color: "Branco", size: "M", quantity: 1 }
    ] };
    assert.equal(isProductAvailable(product, { color: "Preto" }), true);
    assert.equal(isProductAvailable(product, { color: "Preto", size: "M" }), false);
    assert.equal(isProductAvailable(product, { color: "Branco", size: "G" }), false);
    assert.equal(isProductAvailable(product, { color: "Preto", size: "G" }), true);
});

test("prices keep the existing BRL presentation", () => {
    assert.equal(formatPrice(99.9), "R$ 99,90");
    assert.equal(formatPrice(0), "R$ 0,00");
    assert.equal(formatPrice("1250.5"), "R$ 1250,50");
});

test("routes encode IDs and WhatsApp messages without losing their contents", () => {
    const id = 'id &?#"á';
    assert.equal(new URL(getProductUrl(id)).searchParams.get("id"), id);
    assert.match(ROUTES.drops, /pages\/drops\/index.html$/);
    assert.equal(new URL(ROUTES.destaques).hash, "#destaques");
    const message = "Olá!\nTamanho: G & GG";
    assert.equal(new URL(getWhatsAppUrl(message)).searchParams.get("text"), message);
    assert.notEqual(new URL(getWhatsAppUrl()).pathname, "/");
});

test("image URLs reject executable or embedded data schemes", () => {
    for (const value of ["javascript:alert(1)", "data:image/svg+xml,<svg/>", "file:///private", ""]) {
        assert.equal(getImageUrl(value), null);
    }
    assert.equal(getImageUrl("https://example.com/image.jpg"), "https://example.com/image.jpg");
});

test("description keeps headings and lists while escaping markup", () => {
    const html = renderDescription('Detalhes <img src=x onerror=alert(1)>\n- Tecido & algodão');
    assert.match(html, /<h3 /);
    assert.match(html, /<li>/);
    assert.match(html, /&lt;img/);
    assert.match(html, /Tecido &amp; algodão/);
    assert.doesNotMatch(html, /<img/);
});

test("product and admin templates cannot create markup from API fields", () => {
    const attack = '\"><script>alert(1)</script><img src=x onerror="alert(1)">';
    const product = {
        id: attack, title: attack, category: attack, gender: attack,
        description: "</textarea>" + attack, price: 10, available: true,
        images: [{ url: attack }], variants: [{ size: attack, color: attack, quantity: 1 }]
    };
    const section = { innerHTML: "" };
    renderProduct(section, product);
    const form = renderProductForm(product);
    for (const html of [section.innerHTML, form]) {
        assert.doesNotMatch(html, /<script>|<img src=x/);
        assert.ok(html.includes(escapeHtml(attack)));
    }
    assert.match(form, /&lt;\/textarea&gt;/);
});
