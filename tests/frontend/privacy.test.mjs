import assert from "node:assert/strict";
import { test } from "node:test";
import { readFile } from "node:fs/promises";
import { installDOM } from "./helpers/dom.mjs";
import { CONTACTS, ROUTES } from "../../frontend/js/utils/urls.js";

test("privacy policy is readable without JavaScript, authentication or API calls", async (t) => {
    const html = await readFile(new URL("../../frontend/politica-de-privacidade.html", import.meta.url), "utf8");
    await installDOM(t, html);
    assert.equal(document.documentElement.lang, "pt-BR");
    assert.equal(document.querySelectorAll("h1").length, 1);
    assert.match(document.title, /Política de Privacidade/);
    assert.ok(document.querySelector('meta[name="description"]').content);
    assert.equal(document.querySelector('link[rel="canonical"]').href, "https://darkdistrict.com.br/politica-de-privacidade");
    for (const link of document.querySelectorAll('a[href^="#"]')) {
        assert.ok(document.getElementById(link.hash.slice(1)), `Missing target ${link.hash}`);
    }
    const { renderPrivacyContacts } = await import("../../frontend/js/sections/privacidade.js");
    renderPrivacyContacts();
    for (const link of document.querySelectorAll("[data-privacy-contact]")) {
        assert.equal(link.href, `https://wa.me/${CONTACTS.whatsapp}`);
    }
    assert.match(document.querySelector("#whatsapp").textContent, /atendentes humanos/);
    assert.match(document.querySelector("#chat").textContent, /assistente de IA/);
    assert.equal(document.querySelectorAll("form, input[type=password]").length, 0);

    const { renderFooter } = await import("../../frontend/js/components/footer.js");
    renderFooter();
    const privacyLink = [...document.querySelectorAll("#footer a")].find((link) => link.textContent.includes("Política de Privacidade"));
    assert.equal(privacyLink.href, ROUTES.privacidade);
});
