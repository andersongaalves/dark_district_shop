import { ROUTES } from "../utils/urls.js";

export function renderHero() {
    const hero = document.querySelector("#hero");

    if (!hero) return;

    hero.innerHTML = `
        <div class="container hero__inner">

            <div class="hero__content">

                <p class="hero__eyebrow">
                    DARK DISTRICT
                </p>

                <h1 class="hero__title">
                    <span>ENCONTRE O</span>
                    <span>SEU ESTILO.</span>
                </h1>

                <p class="hero__description">
                    Produtos selecionados para quem busca algo
                    diferente. Disponíveis para pronta entrega.
                </p>

                <div class="hero__actions">
                    <a
                        href="${ROUTES.catalogo}"
                        class="hero__button"
                    >
                        Explorar catálogo
                    </a>
                </div>

            </div>

        </div>
    `;
}