import { escapeHtml } from "../utils/dom.js";
import { createProductCard } from "../components/product_card.js";
import { watchOfferExpiry } from "../components/product_price.js";

export function renderCatalogoLayout(section, title = "Catálogo") {
    section.innerHTML = `
        <div class="container catalogo__container">

            <div class="catalogo__header">
                <div>
                    <span class="catalogo__eyebrow">
                        Dark District
                    </span>

                    <h1 class="catalogo__title">
                        ${escapeHtml(title)}
                    </h1>

                    <p class="catalogo__description">
                        Explore nossa seleção de produtos.
                    </p>
                </div>
            </div>

            <div class="catalogo__toolbar">

                <div class="catalogo__categories">
                    <button
                        type="button"
                        class="catalogo__filter is-active"
                        data-category="all"
                    >
                        Todos
                    </button>
                </div>

                <span class="catalogo__count"></span>

            </div>

            <div class="catalogo__grid"></div>

            <div class="catalogo__empty">
                <span>Nenhum produto encontrado.</span>
            </div>

        </div>
    `;

}

export function renderCategoryFilters(section, products, onSelect) {
    const categories = [...new Map(products.map((product) => [product.category_id, product.category])).entries()];
    const container = section.querySelector(".catalogo__categories");
    container.innerHTML = `<button type="button" class="catalogo__filter is-active">Todos</button>` +
        categories.map(([id, name]) => `<button type="button" class="catalogo__filter" data-category="${escapeHtml(id)}">${escapeHtml(name)}</button>`).join("");
    container.querySelectorAll("button").forEach((button) => {
        button.addEventListener("click", () => {
            container.querySelectorAll("button").forEach((item) => item.classList.toggle("is-active", item === button));
            onSelect(button.dataset.category ?? null);
        });
    });
}

export function renderCatalogoProducts(section, products) {
    const grid = section.querySelector(".catalogo__grid");
    grid.replaceChildren(...products.map(createProductCard));
    section.querySelector(".catalogo__count").textContent = `${products.length} ${products.length === 1 ? "produto" : "produtos"}`;
    section.querySelector(".catalogo__empty").classList.toggle("is-visible", products.length === 0);
    watchOfferExpiry(section, products, () => renderCatalogoProducts(section, products));
}

export function renderCatalogoError(section) {
    renderCatalogoProducts(section, []);
    section.querySelector(".catalogo__empty span").textContent = "Não foi possível carregar os produtos.";
}
