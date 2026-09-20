import { getProductPrice, isProductAvailable, PRODUCT_TYPES } from "./products.js";

export const CANONICAL_ORIGIN = "https://darkdistrict.com.br";
export const DEFAULT_SOCIAL_IMAGE = `${CANONICAL_ORIGIN}/assets/images/logo/logo-full.png`;

function publicUrl(pathname = "/") {
    return new URL(pathname, `${CANONICAL_ORIGIN}/`).href;
}

export function getCanonicalProductUrl(productId) {
    const url = new URL("/pages/produto/index.html", `${CANONICAL_ORIGIN}/`);
    url.searchParams.set("id", String(productId));
    return url.href;
}

function cleanText(value, fallback = "") {
    const text = typeof value === "string" ? value.replace(/\s+/g, " ").trim() : "";
    return text || fallback;
}

function truncate(value, limit = 160) {
    const text = cleanText(value);
    return text.length > limit ? `${text.slice(0, limit - 1).trimEnd()}…` : text;
}

function setMeta(selector, attributes, content) {
    let element = document.head.querySelector(selector);
    if (!element) {
        element = document.createElement("meta");
        Object.entries(attributes).forEach(([name, value]) => element.setAttribute(name, value));
        document.head.append(element);
    }
    element.setAttribute("content", content);
}

function setCanonical(url) {
    let element = document.head.querySelector('link[rel="canonical"]');
    if (!element) {
        element = document.createElement("link");
        element.rel = "canonical";
        document.head.append(element);
    }
    element.href = url;
}

export function setStructuredData(id, value) {
    let element = document.getElementById(id);
    if (!element) {
        element = document.createElement("script");
        element.id = id;
        element.type = "application/ld+json";
        document.head.append(element);
    }
    element.textContent = JSON.stringify(value);
}

export function removeStructuredData(id) {
    document.getElementById(id)?.remove();
}

export function setNoIndex() {
    setMeta('meta[name="robots"]', { name: "robots" }, "noindex,follow");
}

export function clearNoIndex() {
    document.head.querySelector('meta[name="robots"]')?.remove();
}

export function setPageMetadata({ title, description, canonical, image = DEFAULT_SOCIAL_IMAGE, type = "website" }) {
    document.title = title;
    setCanonical(canonical);
    setMeta('meta[name="description"]', { name: "description" }, description);
    setMeta('meta[property="og:title"]', { property: "og:title" }, title);
    setMeta('meta[property="og:description"]', { property: "og:description" }, description);
    setMeta('meta[property="og:url"]', { property: "og:url" }, canonical);
    setMeta('meta[property="og:image"]', { property: "og:image" }, image);
    setMeta('meta[property="og:type"]', { property: "og:type" }, type);
    setMeta('meta[name="twitter:card"]', { name: "twitter:card" }, "summary_large_image");
    setMeta('meta[name="twitter:title"]', { name: "twitter:title" }, title);
    setMeta('meta[name="twitter:description"]', { name: "twitter:description" }, description);
    setMeta('meta[name="twitter:image"]', { name: "twitter:image" }, image);
}

function getProductImage(product) {
    const source = product.images?.[0]?.url;
    if (typeof source !== "string" || !source.trim()) return DEFAULT_SOCIAL_IMAGE;
    try {
        const url = new URL(source, `${CANONICAL_ORIGIN}/`);
        return ["http:", "https:"].includes(url.protocol) ? url.href : DEFAULT_SOCIAL_IMAGE;
    } catch {
        return DEFAULT_SOCIAL_IMAGE;
    }
}

function getProductImages(product) {
    return (product.images ?? []).map((image) => {
        try {
            const url = new URL(image?.url, `${CANONICAL_ORIGIN}/`);
            return ["http:", "https:"].includes(url.protocol) ? url.href : null;
        } catch {
            return null;
        }
    }).filter(Boolean);
}

function productDescription(product) {
    return truncate(product.description, 160) || `${cleanText(product.title, "Produto")} disponível na Dark District.`;
}

export function setProductMetadata(product) {
    const title = `${cleanText(product.title, "Produto")} | Dark District`;
    const description = productDescription(product);
    const canonical = getCanonicalProductUrl(product.id);
    const image = getProductImage(product);
    const productType = PRODUCT_TYPES[product.product_type] ?? "Catálogo";
    const price = Number(getProductPrice(product));
    const available = isProductAvailable(product);

    setPageMetadata({ title, description, canonical, image, type: "product" });
    setStructuredData("seo-product", {
        "@context": "https://schema.org",
        "@type": "Product",
        name: cleanText(product.title, "Produto"),
        ...(getProductImages(product).length ? { image: getProductImages(product) } : {}),
        description,
        sku: String(product.id),
        offers: {
            "@type": "Offer",
            priceCurrency: "BRL",
            price: Number.isFinite(price) ? price.toFixed(2) : "0.00",
            availability: `https://schema.org/${available ? "InStock" : "OutOfStock"}`,
            url: canonical
        }
    });
    setStructuredData("seo-breadcrumbs", {
        "@context": "https://schema.org",
        "@type": "BreadcrumbList",
        itemListElement: [
            { "@type": "ListItem", position: 1, name: "Início", item: publicUrl("/") },
            { "@type": "ListItem", position: 2, name: productType, item: publicUrl(`/pages/${product.product_type === "drop" ? "drops" : product.product_type}/index.html`) },
            { "@type": "ListItem", position: 3, name: cleanText(product.title, "Produto"), item: canonical }
        ]
    });
}

export function clearProductMetadata() {
    removeStructuredData("seo-product");
    removeStructuredData("seo-breadcrumbs");
}
