import { ROUTES } from "../utils/urls.js";
import { initCart } from "../cart/cart.js";

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
                <a href="${ROUTES.brecho}">Brechó</a>
                <a href="${ROUTES.drops}">Drops</a>
                <a href="${ROUTES.sobre}">
                    Sobre
                </a>
            </nav>

            <button class="header-cart" type="button" aria-haspopup="dialog" aria-controls="cart-drawer">
                Carrinho (<span data-cart-count aria-live="polite">0</span>)
            </button>

        </div>
    `;
    initCart(header.querySelector(".header-cart"));
}
