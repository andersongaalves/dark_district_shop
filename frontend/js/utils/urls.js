const FRONTEND_URL = new URL("../../", import.meta.url);

export const CONTACTS = {
    whatsapp: "557481094041"
};

export const ROUTES = {
    home: new URL("index.html", FRONTEND_URL).href,
    catalogo: new URL("pages/catalogo/index.html", FRONTEND_URL).href,
    brecho: new URL("pages/brecho/index.html", FRONTEND_URL).href,
    drops: new URL("pages/brecho/index.html", FRONTEND_URL).href,
    sobre: new URL("pages/sobre/index.html", FRONTEND_URL).href

};

export function getProductUrl(productId) {
    const url = new URL(
        "pages/produto/index.html",
        FRONTEND_URL
    );

    url.searchParams.set("id", productId);

    return url.href;
}

export function getWhatsAppUrl(message) {
    const url = new URL(
        `https://wa.me/${CONTACTS.whatsapp}`
    );

    url.searchParams.set("text", message);

    return url.href;
}