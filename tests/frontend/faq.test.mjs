import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { test } from "node:test";
import { installDOM, eventually } from "./helpers/dom.mjs";
import { getFAQ } from "../../frontend/js/api/faq_api.js";
import { renderFAQ } from "../../frontend/js/sections/faq_render.js";
import { renderFooter } from "../../frontend/js/components/footer.js";
import { ROUTES } from "../../frontend/js/utils/urls.js";

const published = JSON.parse(await readFile(new URL("../../backend/content/faq.json", import.meta.url), "utf8"));

test("FAQ loads public answers without administrative credentials", async (t) => {
    await installDOM(t, "<body></body>");
    localStorage.setItem("access_token", "admin-only");
    t.mock.method(globalThis, "fetch", async (url, options) => {
        assert.match(url, /\/faq$/);
        assert.equal(options.credentials, "omit");
        assert.equal(options.cache, "no-cache");
        assert.equal(new Headers(options.headers).has("Authorization"), false);
        return Response.json(published);
    });
    assert.deepEqual(await getFAQ(), published);
});

test("FAQ shows all published questions with native expandable answers", async (t) => {
    await installDOM(t, '<body><section id="faq"></section></body>');
    t.mock.method(globalThis, "fetch", async () => Response.json(published));
    await renderFAQ(document.querySelector("#faq"));
    const items = [...document.querySelectorAll("details")];
    assert.equal(items.length, 4);
    for (const [index, item] of items.entries()) {
        assert.equal(item.querySelector("summary").textContent, published[index].question);
        assert.equal(item.querySelector(".faq-answer").textContent, published[index].answer);
    }
    assert.equal(items[0].open, true);
    assert.equal(items[1].open, false);
    items[1].querySelector("summary").click();
    assert.equal(items[1].open, true);
    assert.equal(document.querySelector(".faq-list").getAttribute("aria-busy"), "false");
    assert.match(document.querySelector(".faq-contact a").href, /^https:\/\/wa.me\/\d+$/);
});

test("FAQ handles failed loading and keyboard focus after a successful retry", async (t) => {
    await installDOM(t, '<body><section id="faq"></section></body>');
    let attempts = 0;
    t.mock.method(globalThis, "fetch", async () => ++attempts === 1
        ? new Response("Unavailable", { status: 503 }) : Response.json(published));
    const container = document.querySelector("#faq");
    await renderFAQ(container);
    assert.ok(container.querySelector('[role="alert"]'));
    assert.equal(container.querySelectorAll("details").length, 0);
    container.querySelector("button").click();
    await eventually(() => assert.equal(container.querySelectorAll("details").length, 4));
    assert.equal(document.activeElement, container.querySelector("summary"));
    assert.equal(container.querySelector('[role="alert"]'), null);
});

test("FAQ treats published text as text and rejects malformed responses", async (t) => {
    await installDOM(t, '<body><section id="faq"></section></body>');
    let body = [{ id: "compra", question: '<img src=x onerror="alert(1)">', answer: '<script>alert(1)</script>' }];
    t.mock.method(globalThis, "fetch", async () => Response.json(body));
    await renderFAQ(document.querySelector("#faq"));
    assert.equal(document.querySelector("#faq img, #faq script"), null);
    assert.equal(document.querySelector("summary").textContent, body[0].question);
    for (const invalid of [null, [], {}, [{ id: "compra", question: "Compra?" }]]) {
        body = invalid;
        await assert.rejects(getFAQ(), /perguntas frequentes/);
    }
});

test("footer FAQ points to the public page", async (t) => {
    await installDOM(t, '<body><footer id="footer"></footer></body>');
    renderFooter();
    const link = [...document.querySelectorAll("#footer a")].find((anchor) => anchor.textContent === "FAQ");
    assert.equal(link.href, ROUTES.faq);
    assert.match(link.href, /\/pages\/faq\/index.html$/);
});
