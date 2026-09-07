import { renderHeader } from "../components/header.js";
import { getProducts } from "../sections/produto/products_api.js";
import { createProductCard } from "../components/product_card.js";

export async function renderCatalogo() {
    const section = document.querySelector("#catalogo");

    if (!section) return;

    section.innerHTML = `
        <div class="container catalogo__container">

            <div class="catalogo__header">
                <div>
                    <span class="catalogo__eyebrow">
                        Dark District
                    </span>

                    <h1 class="catalogo__title">
                        Catálogo
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

    const grid = section.querySelector(
        ".catalogo__grid"
    );

    const emptyState = section.querySelector(
        ".catalogo__empty"
    );

    const count = section.querySelector(
        ".catalogo__count"
    );

    const categoriesContainer = section.querySelector(
        ".catalogo__categories"
    );

    try {
        const products = await getProducts();

        const categories = [
            ...new Set(
                products
                    .map((product) => product.category)
                    .filter(Boolean)
            )
        ];

        categoriesContainer.innerHTML = `
            <button
                type="button"
                class="catalogo__filter is-active"
                data-category="all"
            >
                Todos
            </button>

            ${categories.map((category) => `
                <button
                    type="button"
                    class="catalogo__filter"
                    data-category="${category}"
                >
                    ${category}
                </button>
            `).join("")}
        `;

        const filters = section.querySelectorAll(
            ".catalogo__filter"
        );

        function renderProducts(category = "all") {
            const filteredProducts = category === "all"
                ? products
                : products.filter(
                    (product) =>
                        product.category === category
                );

            grid.innerHTML = "";

            filteredProducts.forEach((product) => {
                grid.appendChild(
                    createProductCard(product)
                );
            });

            count.textContent = `${filteredProducts.length} ${
                filteredProducts.length === 1
                    ? "produto"
                    : "produtos"
            }`;

            emptyState.classList.toggle(
                "is-visible",
                filteredProducts.length === 0
            );
        }

        filters.forEach((filter) => {
            filter.addEventListener("click", () => {
                filters.forEach((item) => {
                    item.classList.remove("is-active");
                });

                filter.classList.add("is-active");

                renderProducts(
                    filter.dataset.category
                );
            });
        });

        renderProducts();
    } catch (error) {
        console.error(
            "Erro ao carregar catálogo:",
            error
        );

        grid.innerHTML = "";

        count.textContent = "0 produtos";

        emptyState.classList.add("is-visible");

        emptyState.querySelector("span").textContent =
            "Não foi possível carregar os produtos.";
    }
}

document.addEventListener("DOMContentLoaded", () => {
    renderHeader();
    renderCatalogo();
});