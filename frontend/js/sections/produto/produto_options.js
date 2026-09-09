import { isProductAvailable } from "../../core/products.js";

export function setupOptions(section, product, onChange) {
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

            if (onChange) {
                onChange();
            }
        });
    });
}

export function updateAllOptionAvailability(
    section,
    product
) {
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

        const hasStock = isProductAvailable(product, testSelection);

        button.disabled = !hasStock;

        button.classList.toggle(
            "is-disabled",
            !hasStock
        );
    });
}

export function getSelectedOptions(section) {
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