import { isProductAvailable, getSelectedVariant } from "../../core/products.js";
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
    const available = isProductAvailable(product, selected);

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
    const cartButton = section.querySelector(".produto__cart");
    if (cartButton) cartButton.disabled = getSelectedVariant(product, selected) === undefined;
}
