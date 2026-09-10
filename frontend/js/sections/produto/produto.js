import { setupGallery } from "./produto_gallery.js";
import { setupOptions, updateAllOptionAvailability, getSelectedOptions } from "./produto_options.js";
import { updateProductAvailability } from "./produto_availability.js";
import { setupInterestButton } from "./produto_interest.js";
import { renderFooter } from "../../components/footer.js";
import { renderHeader } from "../../components/header.js";
import { getProduct } from "../../api/products_api.js";
import { getCart } from "../../cart/cart.js";

import {
    renderProduct,
    renderNotFound,
    renderError
} from "./produto_render.js";

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
        setupGallery(section);
        setupOptions(section, product, () => updateProductAvailability(section, product));
        updateAllOptionAvailability(section, product);
        updateProductAvailability(section, product);
        setupInterestButton(section, product);
        const button = section.querySelector(".produto__cart");
        const message = section.querySelector(".produto__cart-status");
        let adding = false;
        button.addEventListener("click", async () => {
            if (adding) return;
            adding = true;
            button.disabled = true;
            message.textContent = "Verificando preço e estoque…";
            try {
                await getCart().add(product.id, getSelectedOptions(section));
                message.textContent = "Adicionado. Acesse seus itens pelo ícone no topo da página.";
            } catch (error) {
                message.textContent = error.message;
            } finally {
                adding = false;
                updateProductAvailability(section, product);
            }
        });
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

document.addEventListener("DOMContentLoaded", () => {
    renderHeader();
    renderFooter();
    renderProduto();
});
