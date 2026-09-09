import { formatPrice } from "../../utils/format.js";
import { escapeHtml } from "../../utils/dom.js";
import { ROUTES, getImageUrl } from "../../utils/urls.js";

import {
    renderDescription
} from "./produto_description.js";

export function renderProduct(section, product) {
    const mainImage = getImageUrl(product.images?.[0]?.url);

    const images = (product.images ?? [])
        .map((image) => ({ ...image, url: getImageUrl(image.url) }))
        .filter((image) => image.url);

    const variants = product.variants ?? [];

    const colors = [
        ...new Set(
            variants
                .map((variant) => variant.color)
                .filter(Boolean)
        )
    ];

    const sizes = [
        ...new Set(
            variants
                .map((variant) => variant.size)
                .filter(Boolean)
        )
    ];

    section.innerHTML = `
        <div class="container produto__container">

            <a
                href="${ROUTES.catalogo}"
                class="produto__back"
            >
                ← Voltar ao catálogo
            </a>

            <div class="produto__content">

                <div class="produto__gallery">

                    <div class="produto__main-image">
                        ${
                            mainImage
                                ? `
                                    <img
                                        src="${escapeHtml(mainImage)}"
                                        alt="${escapeHtml(product.title)}"
                                    >
                                `
                                : `
                                    <div class="produto__image-placeholder">
                                        Sem imagem
                                    </div>
                                `
                        }
                    </div>

                    ${
                        images.length > 1
                            ? `
                                <div class="produto__thumbnails">

                                    ${images.map(
                                        (image, index) => `
                                            <button
                                                type="button"
                                                class="produto__thumbnail ${
                                                    index === 0
                                                        ? "is-active"
                                                        : ""
                                                }"
                                                data-image="${escapeHtml(image.url)}"
                                            >
                                                <img
                                                    src="${escapeHtml(image.url)}"
                                                    alt="${escapeHtml(product.title)} - imagem ${index + 1}"
                                                >
                                            </button>
                                        `
                                    ).join("")}

                                </div>
                            `
                            : ""
                    }

                </div>

                <div class="produto__info">

                    <span class="produto__category">
                        ${escapeHtml(product.category)}
                    </span>

                    <h1 class="produto__title">
                        ${escapeHtml(product.title)}
                    </h1>

                    <span class="produto__id">
                        ID: ${escapeHtml(product.id)}
                    </span>

                    <div class="produto__price">
                        ${formatPrice(product.price)}
                    </div>

                    <details class="produto__description">
                        <summary>
                            Descrição
                            <span class="produto__description-icon">+</span>
                        </summary>

                        <div class="produto__description-content">
                            ${renderDescription(product.description)}
                        </div>
                    </details>

                    ${
                        colors.length
                            ? `
                                <div class="produto__option">

                                    <span class="produto__option-label">
                                        Cor
                                    </span>

                                    <div class="produto__options">

                                        ${colors.map(
                                            (color) => `
                                                <button
                                                    type="button"
                                                    class="produto__option-button"
                                                    data-option="color"
                                                    data-value="${escapeHtml(color)}"
                                                >
                                                    ${escapeHtml(color)}
                                                </button>
                                            `
                                        ).join("")}

                                    </div>

                                </div>
                            `
                            : ""
                    }

                    ${
                        sizes.length
                            ? `
                                <div class="produto__option">

                                    <span class="produto__option-label">
                                        Tamanho
                                    </span>

                                    <div class="produto__options">

                                        ${sizes.map(
                                            (size) => `
                                                <button
                                                    type="button"
                                                    class="produto__option-button"
                                                    data-option="size"
                                                    data-value="${escapeHtml(size)}"
                                                >
                                                    ${escapeHtml(size)}
                                                </button>
                                            `
                                        ).join("")}

                                    </div>

                                </div>
                            `
                            : ""
                    }

                    <div class="produto__availability is-unavailable">
                        Verificando disponibilidade...
                    </div>

                    <button
                        type="button"
                        class="produto__interest"
                        ${product.available ? "" : "disabled"}
                    >
                        Tenho interesse
                    </button>

                </div>

            </div>

        </div>
    `;


}

export function renderNotFound(section) {
    section.innerHTML = `
        <div class="container produto__not-found">

            <span>
                Produto não encontrado.
            </span>

            <a href="${ROUTES.catalogo}">
                Voltar ao catálogo
            </a>

        </div>
    `;
}

export function renderError(section) {
    section.innerHTML = `
        <div class="container produto__not-found">

            <span>
                Não foi possível carregar o produto.
            </span>

            <a href="${ROUTES.catalogo}">
                Voltar ao catálogo
            </a>

        </div>
    `;
}