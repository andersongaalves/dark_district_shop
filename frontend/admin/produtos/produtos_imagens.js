import { escapeHtml } from "../../js/utils/dom.js";

export function renderImages(images) {
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
                        value="${escapeHtml(image.url ?? image)}"
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

export function addImage(container) {
    const index =
        container.querySelectorAll(
            "[data-image-index]"
        ).length;

    const element =
        document.createElement("div");

    element.innerHTML = renderImages([{ url: "" }]);
    const row = element.firstElementChild;
    row.dataset.imageIndex = index;

    container
        .querySelector(
            ".admin-modal__empty"
        )
        ?.remove();

    container.appendChild(row);

    setupImageRemoval(container);

    row
        .querySelector("input")
        ?.focus();
}

export function setupImageRemoval(container) {
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
                        container.innerHTML = renderImages([]);
                    }
                }
            );
        });
}

export function getImages(container) {
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

