import { renderHeader } from "../../components/header.js";
import { getProduct } from "./products_api.js";

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
    renderProduto();
});