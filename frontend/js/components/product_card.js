import { getProductUrl } from "../utils/urls.js";

export function createProductCard(product) {
    const card = document.createElement("article");

    card.className = "product-card";
    card.dataset.productId = product.id;

    const availability = product.available
        ? "Disponível"
        : "Indisponível";

    const image = product.images?.[0]?.url ?? null;
    const productUrl = getProductUrl(product.id);

    const imageContent = image
        ? `
            <img
                src="${image}"
                alt="${product.title}"
                loading="lazy"
            >
        `
        : `
            <div class="product-card__image-placeholder">
                <span>Sem imagem</span>
            </div>
        `;

    card.innerHTML = `
        <a
            href="${productUrl}"
            class="product-card__image-link"
        >
            <div class="product-card__image">
                ${imageContent}
            </div>
        </a>

        <div class="product-card__content">

            <span class="product-card__category">
                ${product.category}
            </span>

            <h3 class="product-card__name">
                ${product.title}
            </h3>

            <div class="product-card__bottom">

                <span class="product-card__price">
                    R$ ${Number(product.price)
                        .toFixed(2)
                        .replace(".", ",")}
                </span>

                <span class="product-card__availability">
                    ${availability}
                </span>

            </div>

        </div>
    `;

    return card;
}