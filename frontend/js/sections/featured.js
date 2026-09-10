import { ROUTES } from "../utils/urls.js";
import { createProductCard } from "../components/product_card.js";
import { getProducts } from "../api/products_api.js";

async function renderSelection(selector, title, anchor, flag) {
    const section = document.querySelector(selector);
    if (!section) return;
    section.innerHTML = `
        <div class="container featured__container">
            <div class="featured__header">
                <div><span class="featured__eyebrow">Dark District</span>
                    <h2 id="${anchor}" class="featured__title">${title}</h2></div>
                <a href="${ROUTES.catalogo}" class="featured__link">Ver catálogo</a>
            </div>
            <div class="featured__grid" aria-live="polite">Carregando…</div>
        </div>`;
    const grid = section.querySelector(".featured__grid");
    try {
        const products = await getProducts({ [flag]: true, available: true });
        const selected = products.filter((product) => product[flag] && product.available).slice(0, 4);
        grid.replaceChildren(...selected.map(createProductCard));
        if (!selected.length) grid.textContent = "Nenhum produto disponível nesta seleção no momento.";
    } catch {
        grid.textContent = "Não foi possível carregar esta seleção de produtos.";
    }
}

export function renderFeatured() {
    return renderSelection("#featured", "Destaques", "destaques", "featured");
}

export function renderOffers() {
    return renderSelection("#offers", "Ofertas", "ofertas", "is_offer");
}
