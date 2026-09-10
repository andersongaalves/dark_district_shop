import { ROUTES } from "../js/utils/urls.js";
import { isAuthenticated } from "./auth.js";
import { carregarProdutos } from "./produtos/produtos.js";
import { carregarConfiguracoes } from "./configuracoes/configuracoes.js";

let navigationRevision = 0;

function renderAdminView() {
    const revision = ++navigationRevision;
    const isCurrent = () => revision === navigationRevision;
    const route = window.location.hash.slice(1);
    const configuration = /^configuracoes\/(categorias|colecoes)$/.exec(route);
    const type = /^produtos\/(catalogo|brecho|drop)$/.exec(route)?.[1] ?? "catalogo";
    document.querySelector("#admin-produtos").hidden = Boolean(configuration);
    document.querySelector("#admin-configuracoes").hidden = !configuration;
    document.querySelector(configuration ? "#admin-configuracoes" : "#admin-produtos").textContent = "Carregando…";
    const activeRoute = configuration ? route : `produtos/${type}`;
    document.querySelectorAll(".admin-nav a").forEach((link) => {
        if (link.getAttribute("href") === `#${activeRoute}`) link.setAttribute("aria-current", "page");
        else link.removeAttribute("aria-current");
    });
    if (configuration) carregarConfiguracoes({ resource: configuration[1], isCurrent });
    else carregarProdutos({ type, isCurrent });
}

function initAdmin() {
    if (!isAuthenticated()) {
        window.location.href = ROUTES.login;
        return;
    }

    window.addEventListener("hashchange", renderAdminView);
    renderAdminView();
}

document.addEventListener(
    "DOMContentLoaded",
    initAdmin
);
