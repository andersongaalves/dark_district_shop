import { renderHeader } from "../components/header.js";
import { renderFooter } from "../components/footer.js";
import { getProducts } from "../api/products_api.js";
import {
    renderCatalogoLayout,
    renderCategoryFilters,
    renderCatalogoProducts,
    renderCatalogoError
} from "./catalogo_render.js";

export async function renderCatalogo() {
    const section = document.querySelector("#catalogo");
    if (!section) return;
    renderCatalogoLayout(section);
    try {
        const products = await getProducts();
        renderCategoryFilters(section, products, (category) => {
            renderCatalogoProducts(section, category === null
                ? products
                : products.filter((product) => product.category === category));
        });
        renderCatalogoProducts(section, products);
    } catch {
        renderCatalogoError(section);
    }
}

document.addEventListener("DOMContentLoaded", () => {
    renderHeader();
    renderFooter();
    renderCatalogo();
});
