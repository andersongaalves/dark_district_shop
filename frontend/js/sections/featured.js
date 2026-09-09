import { ROUTES } from "../utils/urls.js";
import { createProductCard } from "../components/product_card.js";
import { getProducts } from "../api/products_api.js";

export async function renderFeatured() {
    const section = document.querySelector("#featured");

    if (!section) return;

    section.innerHTML = `
        <div class="container featured__container">

            <div class="featured__header">

                <div>
                    <span class="featured__eyebrow">
                        Dark District
                    </span>

                    <h2 id="destaques" class="featured__title">
                        Destaques
                    </h2>
                </div>

                <a
                    href="${ROUTES.catalogo}"
                    class="featured__link"
                >
                    Ver catálogo
                </a>

            </div>

            <div class="featured__grid"></div>

        </div>
    `;

    const grid =
        section.querySelector(".featured__grid");

    try {
        const products = await getProducts();

        const featuredProducts = products
            .filter((product) => product.featured)
            .slice(0, 4);

        featuredProducts.forEach((product) => {
            grid.appendChild(
                createProductCard(product)
            );
        });
        if (!featuredProducts.length) {
            grid.textContent = "Nenhum destaque disponível no momento.";
        }
    } catch (error) {
        grid.textContent = "Não foi possível carregar os destaques.";
        console.error(
            "Erro ao carregar destaques:",
            error
        );
    }
}
