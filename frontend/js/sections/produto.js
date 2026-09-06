import {
    ROUTES,
    getWhatsAppUrl
} from "../utils/urls.js";

import { getProduct } from "./products_api.js";
import { renderHeader } from "../components/header.js";

export async function renderProduto() {
    const section = document.querySelector("#produto");

    if (!section) return;

    const productId = getProductId();

    if (!productId) {
        renderNotFound(section);
        return;
    }

    try {
        const product = await getProduct(productId);

        if (!product) {
            renderNotFound(section);
            return;
        }

        renderProduct(section, product);
    } catch (error) {
        console.error(
            "Erro ao carregar produto:",
            error
        );

        renderError(section);
    }
}

function getProductId() {
    const params = new URLSearchParams(
        window.location.search
    );

    return params.get("id");
}

function renderProduct(section, product) {
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
    updateProductAvailability(section, product);
    setupInterestButton(section, product);
}

function setupGallery(section) {
    const mainImage = section.querySelector(
        ".produto__main-image img"
    );

    const thumbnails = section.querySelectorAll(
        ".produto__thumbnail"
    );

    if (!mainImage || !thumbnails.length) return;

    thumbnails.forEach((thumbnail) => {
        thumbnail.addEventListener("click", () => {
            mainImage.src = thumbnail.dataset.image;

            thumbnails.forEach((item) => {
                item.classList.remove("is-active");
            });

            thumbnail.classList.add("is-active");
        });
    });
}

function setupOptions(section, product) {
    const optionButtons = section.querySelectorAll(
        ".produto__option-button"
    );

    if (!optionButtons.length) return;

    optionButtons.forEach((button) => {
        button.addEventListener("click", () => {
            const group = button.parentElement;
            const isActive =
                button.classList.contains("is-active");

            group.querySelectorAll("button").forEach(
                (item) => {
                    item.classList.remove("is-active");
                }
            );

            if (!isActive) {
                button.classList.add("is-active");
            }

            updateAllOptionAvailability(
                section,
                product
            );

            updateProductAvailability(
                section,
                product
            );
        });
    });
}

function updateOptionAvailability(
    section,
    product,
    selectedOption,
    selectedValue
) {
    const selected = getSelectedOptions(section);

    selected[selectedOption] = selectedValue;

    const buttons = section.querySelectorAll(
        ".produto__option-button"
    );

    buttons.forEach((button) => {
        const option = button.dataset.option;
        const value = button.dataset.value;

        const testSelection = {
            ...selected,
            [option]: value
        };

        const hasStock = product.variants.some((variant) => {
            if (
                testSelection.color &&
                variant.color !== testSelection.color
            ) {
                return false;
            }

            if (
                testSelection.size &&
                variant.size !== testSelection.size
            ) {
                return false;
            }

            return variant.quantity > 0;
        });

        button.disabled = !hasStock;

        button.classList.toggle(
            "is-disabled",
            !hasStock
        );
    });
}

function updateProductAvailability(section, product) {
    const availability = section.querySelector(
        ".produto__availability"
    );

    const interestButton = section.querySelector(
        ".produto__interest"
    );

    if (!availability || !interestButton) return;

    const selected = getSelectedOptions(section);
    const variants = product.variants ?? [];

    let variant;

    if (Object.keys(selected).length === 0) {
        variant = variants.find(
            (item) => item.quantity > 0
        );
    } else {
        variant = variants.find((item) => {
            if (
                selected.color &&
                item.color !== selected.color
            ) {
                return false;
            }

            if (
                selected.size &&
                item.size !== selected.size
            ) {
                return false;
            }

            return true;
        });
    }

    const available = Boolean(
        variant && variant.quantity > 0
    );

    availability.classList.toggle(
        "is-available",
        available
    );

    availability.classList.toggle(
        "is-unavailable",
        !available
    );

    availability.textContent = available
        ? "Disponível"
        : "Indisponível";

    interestButton.disabled = !available;
}

function getSelectedOptions(section) {
    const selected = {};

    const activeButtons = section.querySelectorAll(
        ".produto__option-button.is-active"
    );

    activeButtons.forEach((button) => {
        selected[button.dataset.option] =
            button.dataset.value;
    });

    return selected;
}

function setupInterestButton(section, product) {
    const button = section.querySelector(
        ".produto__interest"
    );

    if (!button) return;

    button.addEventListener("click", () => {
        if (button.disabled) return;

        const selected = getSelectedOptions(section);

        const message = [
            "Olá! Tenho interesse neste produto:",
            "",
            `Produto: ${product.title}`,
            `ID: ${product.id}`,
            `Preço: R$ ${product.price
                .toFixed(2)
                .replace(".", ",")}`
        ];

        if (selected.color) {
            message.push(`Cor: ${selected.color}`);
        }

        if (selected.size) {
            message.push(`Tamanho: ${selected.size}`);
        }

        const url = getWhatsAppUrl(
            message.join("\n")
        );

        window.open(
            url,
            "_blank",
            "noopener,noreferrer"
        );
    });
}

function renderNotFound(section) {
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

function renderError(section) {
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

document.addEventListener("DOMContentLoaded", () => {
    renderHeader();
    renderProduto();
});

function updateAllOptionAvailability(section, product) {
    const selected = getSelectedOptions(section);

    const buttons = section.querySelectorAll(
        ".produto__option-button"
    );

    buttons.forEach((button) => {
        const option = button.dataset.option;
        const value = button.dataset.value;

        const testSelection = {
            ...selected,
            [option]: value
        };

        const hasStock = product.variants.some(
            (variant) => {
                if (
                    testSelection.color &&
                    variant.color !==
                        testSelection.color
                ) {
                    return false;
                }

                if (
                    testSelection.size &&
                    variant.size !==
                        testSelection.size
                ) {
                    return false;
                }

                return variant.quantity > 0;
            }
        );

        button.disabled = !hasStock;

        button.classList.toggle(
            "is-disabled",
            !hasStock
        );
    });
}