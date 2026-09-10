import assert from "node:assert/strict";
import { test } from "node:test";
import { installDOM } from "./helpers/dom.mjs";
import { renderFeatured, renderOffers } from "../../frontend/js/sections/featured.js";

const product = { id: "piece", title: "Peça", category: "Camisetas", category_id: 1, price: 79.9, available: true,
    featured: true, is_offer: true, images: [], variants: [] };

test("public lists query each type and share category filtering and card rendering", async (t) => {
    await installDOM(t, '<section id="catalogo" data-product-type="catalogo"></section>');
    const { renderCatalogo } = await import("../../frontend/js/sections/catalogo.js");
    const queries = [];
    t.mock.method(globalThis, "fetch", async (url) => {
        queries.push(new URL(url).searchParams.get("product_type"));
        return Response.json([product, { ...product, id: "other", category_id: 2, category: "Calças" }]);
    });
    for (const type of ["catalogo", "brecho", "drop"]) {
        document.querySelector("section").dataset.productType = type;
        await renderCatalogo();
        assert.equal(document.querySelectorAll("article").length, 2);
        document.querySelector('[data-category="2"]').click();
        assert.equal(document.querySelectorAll("article").length, 1);
        assert.match(document.querySelector("article").textContent, /Calças/);
    }
    assert.deepEqual(queries, ["catalogo", "brecho", "drop"]);
    assert.match(document.querySelector("h1").textContent, /Drops/);
});

test("home selections request independent flags and never show unavailable products", async (t) => {
    await installDOM(t, '<section id="featured"></section><section id="offers"></section>');
    const queries = [];
    t.mock.method(globalThis, "fetch", async (url) => {
        queries.push(Object.fromEntries(new URL(url).searchParams));
        return Response.json([product, { ...product, id: "sold", available: false },
            { ...product, id: "plain", featured: false, is_offer: false }]);
    });
    await renderFeatured();
    await renderOffers();
    assert.deepEqual(queries, [{ featured: "true", available: "true" }, { is_offer: "true", offer_active: "true", available: "true" }]);
    assert.equal(document.querySelectorAll("#featured article").length, 1);
    assert.equal(document.querySelectorAll("#offers article").length, 1);
    assert.equal(document.querySelector("#ofertas").textContent, "Ofertas");
});
