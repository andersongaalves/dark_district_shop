import { getWhatsAppUrl } from "../../utils/urls.js";
import { getSelectedOptions } from "./produto_options.js";

export function setupInterestButton(
    section,
    product
) {
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
            `Preço: R$ ${Number(product.price)
                .toFixed(2)
                .replace(".", ",")}`
        ];

        if (selected.color) {
            message.push(
                `Cor: ${selected.color}`
            );
        }

        if (selected.size) {
            message.push(
                `Tamanho: ${selected.size}`
            );
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