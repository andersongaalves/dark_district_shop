import assert from "node:assert/strict";
import { test } from "node:test";
import { readdir, readFile } from "node:fs/promises";
import { CONTACTS, getWhatsAppUrl } from "../../frontend/js/utils/urls.js";

test("WhatsApp uses the exact official number and encodes the complete message", () => {
    assert.equal(CONTACTS.whatsapp, "557488036775");
    assert.equal(getWhatsAppUrl(), "https://wa.me/557488036775");
    const message = "Olá! 🖤\nPeça: calça & saia + 10% #M\nhttps://darkdistrict.com.br/?id=1&cor=preto";
    const url = getWhatsAppUrl(message);
    assert.equal(url, `https://wa.me/557488036775?text=${encodeURIComponent(message)}`);
    assert.equal(new URL(url).searchParams.get("text"), message);
});

test("active frontend has one WhatsApp number source and no old contact numbers", async () => {
    const root = new URL("../../frontend/", import.meta.url);
    const files = await readdir(root, { recursive: true });
    const numberSources = [];
    for (const file of files.filter((name) => /\.(html|js|css|json|md)$/.test(name))) {
        const source = await readFile(new URL(file.replaceAll("\\", "/"), root), "utf8");
        assert.doesNotMatch(source, /5574988036775|98803[ -]?6775/, file);
        assert.doesNotMatch(source, /(?:api\.|web\.)whatsapp\.com/, file);
        if (source.includes("557488036775")) numberSources.push(file.replaceAll("\\", "/"));
    }
    assert.deepEqual(numberSources, ["js/utils/urls.js"]);
});
