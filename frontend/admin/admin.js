import { isAuthenticated } from "./auth.js";
import { carregarProdutos } from "./produtos/produtos.js";

function initAdmin() {
    if (!isAuthenticated()) {
        window.location.href = "./login/index.html";
        return;
    }

    carregarProdutos();
}

document.addEventListener(
    "DOMContentLoaded",
    initAdmin
);