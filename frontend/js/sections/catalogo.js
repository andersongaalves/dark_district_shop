import { renderHeader } from "../components/header.js";
import { renderFooter } from "../components/footer.js";
import { getProducts } from "../api/products_api.js";
import { PRODUCT_TYPES } from "../core/products.js";
import { initChat } from "../chat/chat.js";
import {
    renderCatalogoLayout,
    renderCategoryFilters,
    renderCatalogoProducts,
    renderCatalogoError
} from "./catalogo_render.js";

export async function renderCatalogo() {
    const section = document.querySelector("#catalogo");
    if (!section) return;
    const type = Object.hasOwn(PRODUCT_TYPES, section.dataset.productType) ? section.dataset.productType : "catalogo";
    renderCatalogoLayout(section, PRODUCT_TYPES[type]);
    try {
        const products = await getProducts({ product_type: type });
        renderCategoryFilters(section, products, (category) => {
            renderCatalogoProducts(section, category === null
                ? products
                : products.filter((product) => String(product.category_id) === category));
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
    initChat();
});
