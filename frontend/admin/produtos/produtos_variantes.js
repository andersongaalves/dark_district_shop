export function renderVariants(variants = []) {
    if (!variants.length) {
        return `
            <div class="admin-modal__empty">
                Nenhuma variação adicionada.
            </div>
        `;
    }

    return variants
        .map(
            (variant, index) => `
                <div
                    class="admin-modal__variant"
                    data-variant-index="${index}"
                >
                    <input
                        type="text"
                        name="variant-size"
                        value="${variant.size ?? ""}"
                        placeholder="Tamanho"
                    >

                    <input
                        type="text"
                        name="variant-color"
                        value="${variant.color ?? ""}"
                        placeholder="Cor"
                    >

                    <input
                        type="number"
                        name="variant-quantity"
                        value="${variant.quantity ?? 0}"
                        min="0"
                        placeholder="Quantidade"
                    >

                    <button
                        type="button"
                        data-remove-variant
                    >
                        ×
                    </button>
                </div>
            `
        )
        .join("");
}

export function addVariant(container) {
    const index =
        container.querySelectorAll(
            "[data-variant-index]"
        ).length;

    const element =
        document.createElement("div");

    element.className =
        "admin-modal__variant";

    element.dataset.variantIndex = index;

    element.innerHTML = `
        <input
            type="text"
            name="variant-size"
            placeholder="Tamanho"
        >

        <input
            type="text"
            name="variant-color"
            placeholder="Cor"
        >

        <input
            type="number"
            name="variant-quantity"
            min="0"
            value="0"
            placeholder="Quantidade"
        >

        <button
            type="button"
            data-remove-variant
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

    setupVariantRemoval(container);

    element
        .querySelector('[name="variant-size"]')
        ?.focus();
}

export function setupVariantRemoval(container) {
    container
        .querySelectorAll(
            "[data-remove-variant]"
        )
        .forEach((button) => {
            if (button.dataset.bound) return;

            button.dataset.bound = "true";

            button.addEventListener(
                "click",
                () => {
                    button
                        .closest(
                            "[data-variant-index]"
                        )
                        ?.remove();

                    if (
                        !container.querySelector(
                            "[data-variant-index]"
                        )
                    ) {
                        container.innerHTML = `
                            <div class="admin-modal__empty">
                                Nenhuma variação adicionada.
                            </div>
                        `;
                    }
                }
            );
        });
}

export function getVariants(container) {
    return [
        ...container.querySelectorAll(
            "[data-variant-index]"
        )
    ].map((variant) => ({
        size:
            variant
                .querySelector(
                    '[name="variant-size"]'
                )
                ?.value
                .trim() || null,

        color:
            variant
                .querySelector(
                    '[name="variant-color"]'
                )
                ?.value
                .trim() || null,

        quantity:
            Number(
                variant
                    .querySelector(
                        '[name="variant-quantity"]'
                    )
                    ?.value
            ) || 0
    }));
}