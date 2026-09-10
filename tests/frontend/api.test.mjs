import assert from "node:assert/strict";
import { test } from "node:test";
import { request, ApiError } from "../../frontend/js/core/api.js";
import { getProducts, getProduct } from "../../frontend/js/api/products_api.js";
import { get as adminGet } from "../../frontend/admin/api.js";
import { login } from "../../frontend/admin/auth.js";

test("public API never reads or forwards administrative credentials", async (t) => {
    t.mock.method(globalThis, "fetch", async (_url, options) => {
        assert.equal(new Headers(options.headers).has("Authorization"), false);
        return Response.json([]);
    });
    assert.deepEqual(await getProducts(), []);
});

test("404 becomes null only for product detail and IDs are encoded", async (t) => {
    t.mock.method(globalThis, "fetch", async (url, options) => {
        assert.equal(options.cache, "no-store");
        assert.ok(url.endsWith("/produtos/a%20%26%3F%23"));
        return Response.json({ detail: "Produto não encontrado." }, { status: 404 });
    });
    assert.equal(await getProduct("a &?#"), null);
});

test("validation and non-JSON server errors are predictable", async (t) => {
    const mocked = t.mock.method(globalThis, "fetch", async () =>
        Response.json({ detail: [{ loc: ["body", "price"], msg: "Invalid" }] }, { status: 422 }));
    await assert.rejects(request("/produtos"), { status: 422, message: "body.price: Invalid" });
    mocked.mock.mockImplementation(async () => new Response("<html>Bad gateway</html>", { status: 502 }));
    await assert.rejects(request("/produtos"), (error) => error instanceof ApiError && error.status === 502 && !error.message.includes("<html>"));
});

test("network failures, malformed successes and 204 are handled", async (t) => {
    const mocked = t.mock.method(globalThis, "fetch", async () => { throw new TypeError("Failed to fetch"); });
    await assert.rejects(request("/produtos"), { status: 0 });
    mocked.mock.mockImplementation(async () => new Response("bad JSON"));
    await assert.rejects(request("/produtos"), { status: 200, name: "ApiError" });
    mocked.mock.mockImplementation(async () => new Response(null, { status: 204 }));
    assert.equal(await request("/produtos/item", { method: "DELETE" }), null);
});

test("administrative 401 removes the token and redirects to login", async (t) => {
    const storage = new Map([["access_token", "test-token"]]);
    let redirect;
    const originalStorage = Object.getOwnPropertyDescriptor(globalThis, "localStorage");
    const originalWindow = globalThis.window;
    Object.defineProperty(globalThis, "localStorage", { configurable: true, value: {
        getItem: (key) => storage.get(key), removeItem: (key) => storage.delete(key)
    } });
    globalThis.window = { location: { assign: (url) => { redirect = url; } } };
    t.after(() => {
        if (originalStorage) Object.defineProperty(globalThis, "localStorage", originalStorage);
        else delete globalThis.localStorage;
        globalThis.window = originalWindow;
    });
    t.mock.method(globalThis, "fetch", async (_url, options) => {
        assert.equal(options.headers.get("Authorization"), "Bearer test-token");
        return Response.json({ detail: "Expired" }, { status: 401 });
    });
    await assert.rejects(adminGet("/produtos"), { status: 401 });
    assert.equal(storage.has("access_token"), false);
    assert.match(redirect, /admin\/login\/index.html$/);
});

test("login uses form encoding without an old bearer token", async (t) => {
    let saved;
    const originalStorage = Object.getOwnPropertyDescriptor(globalThis, "localStorage");
    Object.defineProperty(globalThis, "localStorage", { configurable: true, value: {
        setItem: (key, value) => { saved = [key, value]; }
    } });
    t.after(() => {
        if (originalStorage) Object.defineProperty(globalThis, "localStorage", originalStorage);
        else delete globalThis.localStorage;
    });
    t.mock.method(globalThis, "fetch", async (_url, options) => {
        assert.equal(options.headers.Authorization, undefined);
        assert.equal(options.body.get("username"), "test-admin");
        return Response.json({ access_token: "ephemeral-test-token", token_type: "bearer" });
    });
    await login("test-admin", "test-password");
    assert.deepEqual(saved, ["access_token", "ephemeral-test-token"]);
});
