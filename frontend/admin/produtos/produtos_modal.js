import {
    renderVariants,
    addVariant,
    setupVariantRemoval,
    getVariants
} from "./produtos_variantes.js";

let modal;

export function openProductModal({
    produto = null,
    onSubmit
}) {
    createModal();

    const images = produto?.images ?? [];
    const variants = produto?.variants ?? [];

    modal.innerHTML = `
        <div class="admin-modal__content">

            <div class="admin-modal__header">
                <h2>
                    ${produto ? "Editar produto" : "Novo produto"}
                </h2>

                <button
                    type="button"
                    class="admin-modal__close"
                    data-close
                >
                    ×
                </button>
            </div>

            <form
                id="produto-form"
                class="admin-modal__form"
            >

                <div class="admin-modal__field">
                    <label for="produto-id">
                        ID
                    </label>

                    <input
                        id="produto-id"
                        name="id"
                        value="${produto?.id ?? ""}"
                        ${produto ? "readonly" : ""}
                        required
                    >
                </div>

                <div class="admin-modal__field">
                    <label for="produto-title">
                        Nome
                    </label>

                    <input
                        id="produto-title"
                        name="title"
                        value="${produto?.title ?? ""}"
                        required
                    >
                </div>

                <div class="admin-modal__field">
                    <label for="produto-description">
                        Descrição
                    </label>

                    <textarea
                        id="produto-description"
                        name="description"
                        required
                    >${produto?.description ?? ""}</textarea>
                </div>

                <div class="admin-modal__field">
                    <label for="produto-price">
                        Preço
                    </label>

                    <input
                        id="produto-price"
                        type="number"
                        name="price"
                        step="0.01"
                        min="0"
                        value="${produto?.price ?? ""}"
                        required
                    >
                </div>

                <div class="admin-modal__field">
                    <label for="produto-category">
                        Categoria
                    </label>

                    <input
                        id="produto-category"
                        name="category"
                        value="${produto?.category ?? ""}"
                        required
                    >
                </div>

                <div class="admin-modal__field">
                    <label for="produto-gender">
                        Gênero
                    </label>

                    <input
                        id="produto-gender"
                        name="gender"
                        value="${produto?.gender ?? ""}"
                    >
                </div>

                <label>
                    <input
                        type="checkbox"
                        name="available"
                        ${produto?.available !== false
                            ? "checked"
                            : ""}
                    >
                    Disponível
                </label>

                <label>
                    <input
                        type="checkbox"
                        name="featured"
                        ${produto?.featured
                            ? "checked"
                            : ""}
                    >
                    Destaque
                </label>

                <div class="admin-modal__field">

                    <label>
                        Imagens
                    </label>

                    <div
                        id="produto-images"
                        class="admin-modal__images"
                    >
                        ${renderImages(images)}
                    </div>

                    <button
                        type="button"
                        id="add-image"
                    >
                        + Adicionar imagem
                    </button>

                </div>

                <div class="admin-modal__field">

                    <label>
                        Variações
                    </label>

                    <div
                        id="produto-variants"
                        class="admin-modal__variants"
                    >
                        ${renderVariants(variants)}
                    </div>

                    <button
                        type="button"
                        id="add-variant"
                    >
                        + Adicionar variação
                    </button>

                </div>

                <div class="admin-modal__actions">

                    <button
                        type="button"
                        data-close
                    >
                        Cancelar
                    </button>

                    <button type="submit">
                        Salvar
                    </button>

                </div>

            </form>

        </div>
    `;

    document.body.appendChild(modal);

    setupModal(produto, onSubmit);
}

function renderImages(images) {
    if (!images.length) {
        return `
            <div class="admin-modal__empty">
                Nenhuma imagem adicionada.
            </div>
        `;
    }

    return images
        .map(
            (image, index) => `
                <div
                    class="admin-modal__image"
                    data-image-index="${index}"
                >
                    <input
                        type="url"
                        name="image"
                        value="${image.url ?? image}"
                        placeholder="https://..."
                    >

                    <button
                        type="button"
                        data-remove-image
                    >
                        ×
                    </button>
                </div>
            `
        )
        .join("");
}

function createModal() {
    modal?.remove();

    modal = document.createElement("div");
    modal.className = "admin-modal";
}

function setupModal(produto, onSubmit) {
    const form =
        modal.querySelector("#produto-form");

    const imagesContainer =
        modal.querySelector("#produto-images");

    const variantsContainer =
        modal.querySelector("#produto-variants");

    modal
        .querySelectorAll("[data-close]")
        .forEach((button) => {
            button.addEventListener(
                "click",
                closeModal
            );
        });

    modal
        .querySelector("#add-image")
        ?.addEventListener(
            "click",
            () => {
                addImage(imagesContainer);
            }
        );

    modal
        .querySelector("#add-variant")
        ?.addEventListener(
            "click",
            () => {
                addVariant(variantsContainer);
            }
        );

    setupImageRemoval(imagesContainer);
    setupVariantRemoval(variantsContainer);

    form.addEventListener(
        "submit",
        async (event) => {
            event.preventDefault();

            const formData =
                new FormData(form);

            const dados = {
                id: formData.get("id"),
                title: formData.get("title"),
                description:
                    formData.get("description"),
                price: Number(
                    formData.get("price")
                ),
                category:
                    formData.get("category"),
                gender:
                    formData.get("gender") || null,
                available:
                    formData.get("available") === "on",
                featured:
                    formData.get("featured") === "on",
                images:
                    getImages(imagesContainer),
                variants:
                    getVariants(variantsContainer)
            };

            await onSubmit(dados);

            closeModal();
        }
    );
}

function addImage(container) {
    const index =
        container.querySelectorAll(
            "[data-image-index]"
        ).length;

    const element =
        document.createElement("div");

    element.className =
        "admin-modal__image";

    element.dataset.imageIndex = index;

    element.innerHTML = `
        <input
            type="url"
            name="image"
            placeholder="https://..."
        >

        <button
            type="button"
            data-remove-image
        >
            ×
        </button>
    `;

    container
        .querySelector(
            ".admin-modal__empty"
        )
        ?.remove();

    container.appendChild(element);

    setupImageRemoval(container);

    element
        .querySelector("input")
        ?.focus();
}

function setupImageRemoval(container) {
    container
        .querySelectorAll(
            "[data-remove-image]"
        )
        .forEach((button) => {
            if (button.dataset.bound) return;

            button.dataset.bound = "true";

            button.addEventListener(
                "click",
                () => {
                    button
                        .closest(
                            "[data-image-index]"
                        )
                        ?.remove();

                    if (
                        !container.querySelector(
                            "[data-image-index]"
                        )
                    ) {
                        container.innerHTML = `
                            <div class="admin-modal__empty">
                                Nenhuma imagem adicionada.
                            </div>
                        `;
                    }
                }
            );
        });
}

function getImages(container) {
    return [
        ...container.querySelectorAll(
            'input[name="image"]'
        )
    ]
        .map((input, index) => ({
            url: input.value.trim(),
            ordem: index
        }))
        .filter((image) => image.url);
}

function closeModal() {
    modal?.remove();
    modal = null;
}