import { ROUTES } from "../utils/urls.js";

export function renderHeader() {
    const header = document.querySelector("#header");

    if (!header) return;

    const logoUrl = new URL(
        "../../assets/images/logo/logo-symbol.png",
        import.meta.url
    ).href;

    header.innerHTML = `
        <div class="header-container container">

            <a
                href="${ROUTES.home}"
                class="header-logo"
                aria-label="Dark District"
            >
                <img
                    src="${logoUrl}"
                    alt="Dark District"
                >
            </a>

            <nav
                class="header-nav"
                aria-label="Navegação principal"
            >
                <a href="${ROUTES.catalogo}">
                    Catálogo
                </a>

                <a href="${ROUTES.sobre}">
                    Sobre
                </a>
            </nav>

            <button
                class="header-menu"
                type="button"
                aria-label="Abrir menu"
                aria-expanded="false"
            >
                ☰
            </button>

        </div>
    `;
}