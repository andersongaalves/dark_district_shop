import { writeFile } from "node:fs/promises";
import { fileURLToPath } from "node:url";

export const CANONICAL_ORIGIN = "https://darkdistrict.com.br";

const STATIC_PATHS = [
    "/",
    "/pages/catalogo/index.html",
    "/pages/brecho/index.html",
    "/pages/drops/index.html",
    "/pages/sobre/index.html",
    "/pages/faq/index.html",
    "/politica-de-privacidade"
];

function escapeXml(value) {
    return String(value).replace(/[<>&'\"]/g, (character) => ({
        "<": "&lt;", ">": "&gt;", "&": "&amp;", "'": "&apos;", "\"": "&quot;"
    })[character]);
}

export function isPubliclyAvailable(product) {
    if (!product?.available) return false;
    const variants = Array.isArray(product.variants) ? product.variants : [];
    return !variants.length || variants.some((variant) => Number(variant?.quantity) > 0);
}

export function getProductSitemapUrl(productId) {
    const url = new URL("/pages/produto/index.html", `${CANONICAL_ORIGIN}/`);
    url.searchParams.set("id", String(productId));
    return url.href;
}

function lastmod(value) {
    const date = new Date(value);
    return Number.isNaN(date.valueOf()) ? "" : `<lastmod>${date.toISOString().slice(0, 10)}</lastmod>`;
}

export function buildSitemap(products = []) {
    const urls = [
        ...STATIC_PATHS.map((path) => `<url><loc>${CANONICAL_ORIGIN}${path}</loc></url>`),
        ...products.filter(isPubliclyAvailable).map((product) =>
            `<url><loc>${escapeXml(getProductSitemapUrl(product.id))}</loc>${lastmod(product.updated_at)}</url>`)
    ];
    return `<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n${urls.join("\n")}\n</urlset>\n`;
}

export async function generateSitemap({ apiUrl = process.env.DARK_DISTRICT_API_URL ?? "https://dark-district-api.onrender.com", output = new URL("../sitemap.xml", import.meta.url) } = {}) {
    const response = await fetch(new URL("/produtos?available=true", apiUrl));
    if (!response.ok) throw new Error(`Não foi possível carregar o catálogo público (${response.status}).`);
    const products = await response.json();
    if (!Array.isArray(products)) throw new Error("A API pública retornou um catálogo inválido.");
    await writeFile(output, buildSitemap(products), "utf8");
}

if (process.argv[1] === fileURLToPath(import.meta.url)) {
    generateSitemap().catch((error) => {
        console.error(error.message);
        process.exitCode = 1;
    });
}
