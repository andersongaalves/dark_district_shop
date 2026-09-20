import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { test } from "node:test";
import { installDOM } from "./helpers/dom.mjs";
import {
    buildSitemap,
    getProductSitemapUrl,
    isPubliclyAvailable
} from "../../frontend/scripts/generate-sitemap.mjs";
import { getCanonicalProductUrl, setProductMetadata } from "../../frontend/js/core/seo.js";

const publicPages = [
    ["../../frontend/index.html", "https://darkdistrict.com.br/"],
    ["../../frontend/pages/catalogo/index.html", "https://darkdistrict.com.br/pages/catalogo/index.html"],
    ["../../frontend/pages/brecho/index.html", "https://darkdistrict.com.br/pages/brecho/index.html"],
    ["../../frontend/pages/drops/index.html", "https://darkdistrict.com.br/pages/drops/index.html"],
    ["../../frontend/pages/sobre/index.html", "https://darkdistrict.com.br/pages/sobre/index.html"],
    ["../../frontend/pages/faq/index.html", "https://darkdistrict.com.br/pages/faq/index.html"],
    ["../../frontend/politica-de-privacidade.html", "https://darkdistrict.com.br/politica-de-privacidade"]
];

test("public pages have unique canonical metadata and social previews", async (t) => {
    const titles = new Set();
    for (const [path, canonical] of publicPages) {
        const html = await readFile(new URL(path, import.meta.url), "utf8");
        assert.match(html, /<h1[\s>]/i, `${path} needs an H1 for its public content`);
        await installDOM(t, html, canonical);
        assert.ok(document.title, `${path} needs a title`);
        assert.ok(document.querySelector('meta[name="description"]')?.content, `${path} needs a description`);
        assert.equal(document.querySelector('link[rel="canonical"]')?.href, canonical);
        assert.equal(document.querySelector('meta[property="og:url"]')?.content, canonical);
        assert.ok(document.querySelector('meta[property="og:title"]')?.content);
        assert.ok(document.querySelector('meta[name="twitter:card"]')?.content);
        assert.ok(!document.head.innerHTML.includes("pages.dev"));
        assert.ok(!titles.has(document.title), `${path} repeats a title`);
        titles.add(document.title);
    }
});

test("robots and sitemap publish only canonical public routes", async () => {
    const [robots, sitemap] = await Promise.all([
        readFile(new URL("../../frontend/robots.txt", import.meta.url), "utf8"),
        readFile(new URL("../../frontend/sitemap.xml", import.meta.url), "utf8")
    ]);
    assert.match(robots, /^User-agent: \*$/m);
    assert.match(robots, /Sitemap: https:\/\/darkdistrict\.com\.br\/sitemap\.xml/);
    assert.match(robots, /Disallow: \/admin\//);
    assert.match(sitemap, /<urlset xmlns="http:\/\/www\.sitemaps\.org\/schemas\/sitemap\/0\.9">/);
    assert.match(sitemap, /https:\/\/darkdistrict\.com\.br\/<\/loc>/);
    assert.match(sitemap, /pages\/catalogo\/index\.html/);
    assert.doesNotMatch(sitemap, /\/admin|\/api|\/webhooks/);
    assert.doesNotMatch(sitemap, /pages\.dev|localhost/);
});

test("the sitemap generator includes only publicly available products and real lastmod values", () => {
    const available = { id: "peça 01", available: true, variants: [{ quantity: 2 }], updated_at: "2026-09-19T12:00:00Z" };
    const sold = { id: "sold", available: false, updated_at: "2026-09-19T12:00:00Z" };
    const emptyVariants = { id: "empty", available: true, variants: [{ quantity: 0 }] };
    assert.equal(isPubliclyAvailable(available), true);
    assert.equal(isPubliclyAvailable(sold), false);
    assert.equal(isPubliclyAvailable(emptyVariants), false);
    assert.equal(getProductSitemapUrl(available.id), "https://darkdistrict.com.br/pages/produto/index.html?id=pe%C3%A7a+01");
    const sitemap = buildSitemap([available, sold, emptyVariants]);
    assert.match(sitemap, /id=pe%C3%A7a\+01/);
    assert.match(sitemap, /<lastmod>2026-09-19<\/lastmod>/);
    assert.doesNotMatch(sitemap, /id=sold|id=empty/);
});

test("product SEO uses the stable ID URL and real product data only", async (t) => {
    await installDOM(t, "<head></head><body></body>", "https://darkdistrict.com.br/pages/produto/index.html?id=piece&utm_source=test");
    const product = {
        id: "piece & 1", title: "Camiseta preta", description: "Peça preta com detalhes reais.",
        price: 99.9, effective_price: 79.9, is_offer: true, offer_active: true, offer_price: 79.9,
        product_type: "catalogo", available: true, images: [{ url: "https://images.example/piece.jpg" }],
        variants: [{ quantity: 1 }]
    };
    setProductMetadata(product);
    const canonical = getCanonicalProductUrl(product.id);
    assert.equal(document.querySelector('link[rel="canonical"]').href, canonical);
    assert.equal(document.querySelector('meta[property="og:url"]').content, canonical);
    assert.equal(document.title, "Camiseta preta | Dark District");
    const schema = JSON.parse(document.querySelector("#seo-product").textContent);
    assert.equal(schema["@type"], "Product");
    assert.equal(schema.sku, product.id);
    assert.equal(schema.offers.priceCurrency, "BRL");
    assert.equal(schema.offers.price, "79.90");
    assert.equal(schema.offers.availability, "https://schema.org/InStock");
    assert.equal(Object.hasOwn(schema, "brand"), false);
    const breadcrumbs = JSON.parse(document.querySelector("#seo-breadcrumbs").textContent);
    assert.equal(breadcrumbs["@type"], "BreadcrumbList");
    assert.equal(breadcrumbs.itemListElement.at(-1).item, canonical);
});

test("admin surfaces stay out of search results", async () => {
    for (const path of ["../../frontend/admin/index.html", "../../frontend/admin/login/index.html"]) {
        const html = await readFile(new URL(path, import.meta.url), "utf8");
        assert.match(html, /<meta name="robots" content="noindex,nofollow,noarchive">/);
    }
});

test("the home structured data contains only verified public identity fields", async (t) => {
    const html = await readFile(new URL("../../frontend/index.html", import.meta.url), "utf8");
    await installDOM(t, html);
    const organization = JSON.parse(document.querySelector("#seo-organization").textContent);
    const website = JSON.parse(document.querySelector("#seo-website").textContent);
    assert.deepEqual(organization, {
        "@context": "https://schema.org", "@type": "Organization", name: "Dark District",
        url: "https://darkdistrict.com.br", logo: "https://darkdistrict.com.br/assets/images/logo/logo-full.png"
    });
    assert.deepEqual(website, { "@context": "https://schema.org", "@type": "WebSite", name: "Dark District", url: "https://darkdistrict.com.br" });
});
