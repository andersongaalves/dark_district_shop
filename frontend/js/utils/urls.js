const FRONTEND_URL = new URL("../../", import.meta.url);

export const CONTACTS = {
    whatsapp: "557488036775"
};

export const ROUTES = {
    home: new URL("index.html", FRONTEND_URL).href,
    catalogo: new URL("pages/catalogo/index.html", FRONTEND_URL).href,
    brecho: new URL("pages/brecho/index.html", FRONTEND_URL).href,
    drops: new URL("pages/drops/index.html", FRONTEND_URL).href,
    sobre: new URL("pages/sobre/index.html", FRONTEND_URL).href,
    faq: new URL("pages/faq/index.html", FRONTEND_URL).href,
    privacidade: new URL("politica-de-privacidade", FRONTEND_URL).href,
    destaques: new URL("index.html#destaques", FRONTEND_URL).href,
    admin: new URL("admin/index.html", FRONTEND_URL).href,
    login: new URL("admin/login/index.html", FRONTEND_URL).href

};

export function getProductUrl(productId) {
    const url = new URL(
        "pages/produto/index.html",
        FRONTEND_URL
    );

    url.searchParams.set("id", productId);

    return url.href;
}

export function getProductListUrl(type) {
    const routes = { catalogo: ROUTES.catalogo, brecho: ROUTES.brecho, drop: ROUTES.drops };
    return Object.hasOwn(routes, type) ? routes[type] : ROUTES.catalogo;
}

export function getWhatsAppUrl(message = "") {
    const url = new URL(
        `https://wa.me/${CONTACTS.whatsapp}`
    );

    if (message) url.searchParams.set("text", message);

    return url.href;
}

export function getImageUrl(value) {
    if (typeof value !== "string" || !value.trim()) return null;
    try {
        const url = new URL(value, FRONTEND_URL);
        return ["http:", "https:"].includes(url.protocol) ? url.href : null;
    } catch {
        return null;
    }
}
