import { getSelectedOptions } from "./produto_options.js";

export function updateProductAvailability(
    section,
    product
) {
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