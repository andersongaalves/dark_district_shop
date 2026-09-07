import { ROUTES } from "../../utils/urls.js";

import { setupGallery } from "./produto_gallery.js";
import {
    setupOptions,
    updateAllOptionAvailability
} from "./produto_options.js";

import { updateProductAvailability } from "./produto_availability.js";

import { setupInterestButton } from "./produto_interest.js";

export function renderProduct(section, product) {
    const mainImage = product.images?.[0]?.url ?? null;

    const images = product.images?.length
        ? product.images
        : [];

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
                                        src="${mainImage}"
                                        alt="${product.title}"
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
                                                data-image="${image.url}"
                                            >
                                                <img
                                                    src="${image.url}"
                                                    alt="${product.title} - imagem ${index + 1}"
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
                        ${product.category}
                    </span>

                    <h1 class="produto__title">
                        ${product.title}
                    </h1>

                    <span class="produto__id">
                        ID: ${product.id}
                    </span>

                    <div class="produto__price">
                        R$ ${Number(product.price)
                            .toFixed(2)
                            .replace(".", ",")}
                    </div>

                    <p class="produto__description">
                        ${product.description}
                    </p>

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
                                                    data-value="${color}"
                                                >
                                                    ${color}
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
                                                    data-value="${size}"
                                                >
                                                    ${size}
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

    setupGallery(section);
    setupOptions(section, product);
    updateAllOptionAvailability(section, product);
    updateProductAvailability(section, product);
    setupInterestButton(section, product);
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