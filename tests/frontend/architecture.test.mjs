import assert from "node:assert/strict";
import { test } from "node:test";
import { readdir, readFile, stat } from "node:fs/promises";
import { fileURLToPath, pathToFileURL } from "node:url";
import path from "node:path";

const root = fileURLToPath(new URL("../../frontend/", import.meta.url));

async function filesAt(directory) {
    const entries = await readdir(directory, { withFileTypes: true });
    const files = await Promise.all(entries.map((entry) => entry.isDirectory()
        ? filesAt(path.join(directory, entry.name))
        : path.join(directory, entry.name)));
    return files.flat();
}

test("all module imports resolve, exports link, and dependencies have no cycles", async (t) => {
    const files = (await filesAt(root)).filter((file) => file.endsWith(".js"));
    const graph = new Map();
    for (const file of files) {
        const source = await readFile(file, "utf8");
        const dependencies = [...source.matchAll(/(?:from\s*|import\s*)["']([^"']+)["']/g)]
            .map((match) => path.resolve(path.dirname(file), match[1]));
        for (const dependency of dependencies) {
            assert.ok(files.includes(dependency), `Missing import from ${file}: ${dependency}`);
            if (file.includes(`${path.sep}js${path.sep}`)) {
                assert.ok(!dependency.includes(`${path.sep}admin${path.sep}`), "Public modules must not depend on Admin");
            }
        }
        graph.set(file, dependencies);
    }
    const visited = new Set();
    function visit(file, ancestors = []) {
        assert.ok(!ancestors.includes(file), `Circular dependency: ${[...ancestors, file].join(" -> ")}`);
        if (visited.has(file)) return;
        graph.get(file).forEach((dependency) => visit(dependency, [...ancestors, file]));
        visited.add(file);
    }
    files.forEach((file) => visit(file));

    // Link actual modules without starting page controllers or touching the network.
    const originalDocument = globalThis.document;
    globalThis.document = { addEventListener() {}, querySelector() { return null; } };
    t.after(() => { globalThis.document = originalDocument; });
    for (const file of files) await import(pathToFileURL(file).href);
});

test("HTML, CSS and module-local assets reference existing files", async () => {
    const files = await filesAt(root);
    for (const file of files.filter((item) => /\.(html|css|js)$/.test(item))) {
        const source = await readFile(file, "utf8");
        const expressions = file.endsWith(".html")
            ? [/\b(?:src|href)\s*=\s*["']([^"']+)["']/g]
            : file.endsWith(".css")
                ? [/url\(\s*["']?([^"')\s]+)["']?\s*\)/g]
                : [/new URL\(\s*["']([^"']+)["']\s*,\s*import.meta.url\s*\)/g];
        for (const expression of expressions) {
            for (const [, reference] of source.matchAll(expression)) {
                if (/^(?:https?:|data:|#)/.test(reference)) continue;
                const target = fileURLToPath(new URL(reference, pathToFileURL(file)));
                assert.ok(await stat(target), `${file} references missing resource ${reference}`);
            }
        }
    }
});

test("CSS custom properties have definitions", async () => {
    const files = (await filesAt(root)).filter((file) => file.endsWith(".css"));
    const css = (await Promise.all(files.map((file) => readFile(file, "utf8")))).join("\n");
    const defined = new Set([...css.matchAll(/(--[\w-]+)\s*:/g)].map((match) => match[1]));
    for (const [, variable] of css.matchAll(/var\(\s*(--[\w-]+)/g)) {
        assert.ok(defined.has(variable), `Undefined CSS property: ${variable}`);
    }
});

test("URLs work at a hosting root and under a local frontend subdirectory", async () => {
    const source = await readFile(path.join(root, "js/utils/urls.js"), "utf8");
    for (const base of ["https://darkdistrict.com.br/", "http://localhost:5500/", "http://localhost:5500/frontend/"]) {
        const moduleUrl = `${base}js/utils/urls.js`;
        const simulated = source.replaceAll("import.meta.url", JSON.stringify(moduleUrl));
        const urls = await import(`data:text/javascript;base64,${Buffer.from(simulated).toString("base64")}`);
        assert.equal(urls.ROUTES.catalogo, `${base}pages/catalogo/index.html`);
        assert.equal(urls.ROUTES.drops, `${base}pages/drops/index.html`);
        assert.equal(urls.ROUTES.faq, `${base}pages/faq/index.html`);
        assert.equal(urls.getProductListUrl("brecho"), `${base}pages/brecho/index.html`);
        assert.equal(urls.getProductListUrl("drop"), `${base}pages/drops/index.html`);
        assert.equal(urls.ROUTES.destaques, `${base}index.html#destaques`);
        assert.equal(urls.getImageUrl("assets/images/products/image.webp"), `${base}assets/images/products/image.webp`);
    }
});

test("API environment selection recognizes local IPv4, hostname and IPv6", async (t) => {
    const original = globalThis.location;
    t.after(() => { globalThis.location = original; });
    for (const hostname of ["localhost", "127.0.0.1", "[::1]", "shop.example.com"]) {
        globalThis.location = { hostname };
        const { API_URL } = await import(`../../frontend/js/core/api.js?host=${hostname}`);
        assert.equal(new URL(API_URL).hostname === "127.0.0.1", hostname !== "shop.example.com");
    }
});
