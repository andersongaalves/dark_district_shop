import { ROUTES } from "../js/utils/urls.js";
import { isAuthenticated } from "./auth.js";
import { carregarProdutos } from "./produtos/produtos.js";

function initAdmin() {
    if (!isAuthenticated()) {
        window.location.href = ROUTES.login;
        return;
    }

    carregarProdutos();
}

document.addEventListener(
    "DOMContentLoaded",
    initAdmin
);