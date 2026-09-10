import { ROUTES, getWhatsAppUrl } from "../utils/urls.js";

export function renderFooter() {
    const footer = document.querySelector("#footer") || document.createElement("footer");
    footer.id = "footer";
    footer.className = "site-footer";

    const logoUrl = new URL(
        "../../assets/images/logo/logo-symbol.png",
        import.meta.url
    ).href;

    footer.innerHTML = `
        <div class="footer-container">
            <div class="footer-main">
                <div class="footer-brand">
                    <img
                        class="footer-logo"
                        src="${logoUrl}"
                        alt="Dark District"
                    >

                    <p class="footer-description">
                        Vista o seu lado obscuro.
                    </p>
                </div>

                <div class="footer-column">
                    <h3 class="footer-title">Navegação</h3>

                    <ul class="footer-links">
                        <li><a href="${ROUTES.catalogo}">Catálogo</a></li>
                        <li><a href="${ROUTES.destaques}">Destaques</a></li>
                    </ul>
                </div>

                <div class="footer-column">
                    <h3 class="footer-title">Ajuda</h3>

                    <ul class="footer-links">
                        <li>
                            <a href="${getWhatsAppUrl()}" target="_blank" rel="noopener noreferrer">
                                WhatsApp
                            </a>
                        </li>
                        <li><a href="${ROUTES.faq}">FAQ</a></li>
                    </ul>
                </div>

                <div class="footer-column">
                    <h3 class="footer-title">Redes</h3>

                    <div class="footer-socials">
                        <a href="https://www.instagram.com/dark.district.shop" target="_blank" rel="noopener noreferrer">
                            Instagram
                        </a>

                        <a href="https://br.pinterest.com/Dark_District/" target="_blank" rel="noopener noreferrer">
                            Pinterest
                        </a>
                    </div>
                </div>
            </div>

            <div class="footer-bottom">
                <p class="footer-copyright">
                    © 2026 Dark District. Todos os direitos reservados.
                </p>

                <p class="footer-credit">
                    Feito por quem veste a própria identidade.
                </p>
            </div>
        </div>
    `;

    if (!footer.isConnected) document.body.appendChild(footer);
}
