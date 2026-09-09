import { isProductAvailable } from "../core/products.js";
import { formatPrice } from "../utils/format.js";
import { escapeHtml } from "../utils/dom.js";
import { getProductUrl, getImageUrl } from "../utils/urls.js";

export function createProductCard(product) {
    const card = document.createElement("article");

    card.className = "product-card";
    card.dataset.productId = product.id;

    const availability = isProductAvailable(product)
        ? "Disponível"
        : "Indisponível";

    const image = getImageUrl(product.images?.[0]?.url);
    const productUrl = getProductUrl(product.id);

    const imageContent = image
        ? `
            <img
                src="${escapeHtml(image)}"
                alt="${escapeHtml(product.title)}"
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
                ${escapeHtml(product.category)}
            </span>

            <h3 class="product-card__name">
                ${escapeHtml(product.title)}
            </h3>

            <div class="product-card__bottom">

                <span class="product-card__price">
                    ${formatPrice(product.price)}
                </span>

                <span class="product-card__availability">
                    ${availability}
                </span>

            </div>

        </div>
    `;

    return card;
}