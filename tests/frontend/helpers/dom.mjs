import { JSDOM } from "jsdom";

export async function installDOM(t, html, url = "https://darkdistrict.com.br/") {
    const dom = new JSDOM(html, { url });
    const keys = ["window", "document", "FormData", "localStorage", "location", "confirm", "alert"];
    const original = new Map(keys.map((key) => [key, Object.getOwnPropertyDescriptor(globalThis, key)]));
    for (const key of keys) Object.defineProperty(globalThis, key, { value: dom.window[key], configurable: true, writable: true });
    globalThis.confirm = () => true;
    globalThis.alert = (message) => { throw new Error(message); };
    t.after(() => {
        dom.window.close();
        for (const [key, descriptor] of original) {
            if (descriptor) Object.defineProperty(globalThis, key, descriptor);
            else delete globalThis[key];
        }
    });
    if (dom.window.document.readyState === "loading") {
        await new Promise((resolve) => dom.window.document.addEventListener("DOMContentLoaded", resolve, { once: true }));
    }
    return dom.window;
}

export async function eventually(assertion) {
    for (let attempt = 0; attempt < 50; attempt++) {
        try { assertion(); return; } catch (error) {
            if (attempt === 49) throw error;
            await new Promise((resolve) => setTimeout(resolve, 5));
        }
    }
}
