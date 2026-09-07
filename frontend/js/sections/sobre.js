import { renderHeader } from "../components/header.js";
import { renderFooter } from "../components/footer.js";

const sobre = document.getElementById("sobre");

document.addEventListener("DOMContentLoaded", () => {
    renderHeader();
    renderSobre();
    renderFooter();
});

function renderSobre() {
    if (!sobre) {
        return;
    }

    sobre.innerHTML = `
        <section class="about-hero">
            <div class="about-container">
                <div class="about-hero-content about-reveal">
                    <span class="about-label">Dark District</span>

                    <h1>
                        <span>Vista o seu lado</span>
                        <span>obscuro.</span>
                    </h1>

                    <p class="about-hero-description">
                        A Dark District nasceu para quem não vê a moda apenas
                        como uma forma de se vestir, mas como uma forma de
                        expressar quem é.
                    </p>

                    <span class="about-hero-mark">
                        Vale do São Francisco · Brasil
                    </span>
                </div>
            </div>
        </section>

        <section class="about-section about-reveal">
            <div class="about-container">
                <div class="about-section-grid">
                    <div class="about-section-heading">
                        <span class="about-section-number">
                            01 — NOSSA ESSÊNCIA
                        </span>

                        <h2>
                            Mais que roupas.
                            <br>
                            Uma identidade.
                        </h2>
                    </div>

                    <div class="about-section-content">
                        <p>
                            A Dark District é uma loja voltada para a estética
                            alternativa e para pessoas que encontram na roupa
                            uma maneira de representar sua personalidade.
                        </p>

                        <p>
                            Gótico, punk, grunge, streetwear e outras vertentes
                            alternativas fazem parte desse universo. Não
                            queremos limitar você a um único estilo.
                        </p>

                        <p>
                            Queremos oferecer peças para quem prefere fugir
                            do comum e construir o próprio visual.
                        </p>
                    </div>
                </div>
            </div>
        </section>

        <section class="about-origin about-reveal">
            <div class="about-container">
                <div class="about-origin-inner">
                    <span class="about-origin-label">
                        Nossa origem
                    </span>

                    <h2>
                        Do Vale do São Francisco
                        <em>para quem vive fora do comum.</em>
                    </h2>

                    <div class="about-origin-text">
                        <p>
                            A Dark District nasceu no Vale do São Francisco,
                            trazendo uma perspectiva alternativa para uma
                            região cheia de personalidade, contrastes e
                            histórias.
                        </p>

                        <p>
                            Nossa origem faz parte do que somos. Criamos a
                            Dark District para aproximar a estética alternativa
                            de quem vive aqui — e, ao mesmo tempo, levar essa
                            identidade para além do Vale.
                        </p>
                    </div>
                </div>
            </div>
        </section>

        <section class="about-section about-reveal">
            <div class="about-container">
                <div class="about-section-grid">
                    <div class="about-section-heading">
                        <span class="about-section-number">
                            02 — NOSSA PROPOSTA
                        </span>

                        <h2>
                            Encontre algo
                            <br>
                            que seja seu.
                        </h2>
                    </div>

                    <div class="about-section-content">
                        <p>
                            Nosso catálogo reúne peças escolhidas para
                            combinar com diferentes estilos dentro da cena
                            alternativa.
                        </p>

                        <p>
                            Além dos produtos tradicionais, a Dark District
                            também abre espaço para garimpos, peças únicas
                            e lançamentos especiais.
                        </p>

                        <p>
                            A ideia é simples: você não precisa se encaixar
                            em uma tendência. Pode encontrar referências,
                            misturar estilos e criar o seu próprio.
                        </p>
                    </div>
                </div>
            </div>
        </section>

        <section class="about-categories about-reveal">
            <div class="about-container">
                <div class="about-categories-header">
                    <span class="about-section-number">
                        03 — O QUE ENCONTRAR
                    </span>

                    <h2>
                        Três formas de
                        encontrar o seu estilo.
                    </h2>
                </div>

                <div class="about-category-grid">
                    <a
                        href="../../index.html#catalogo"
                        class="about-category"
                    >
                        <span class="about-category-number">01</span>

                        <h3>Catálogo</h3>

                        <p>
                            Peças selecionadas para fazer parte do dia a dia
                            de quem vive o estilo alternativo.
                        </p>

                        <span class="about-category-link">
                            Explorar catálogo →
                        </span>
                    </a>

                    <a
                        href="../../index.html#brecho"
                        class="about-category"
                    >
                        <span class="about-category-number">02</span>

                        <h3>Brechó</h3>

                        <p>
                            Garimpos, peças únicas e achados para quem gosta
                            de encontrar algo diferente.
                        </p>

                        <span class="about-category-link">
                            Explorar brechó →
                        </span>
                    </a>

                    <a
                        href="../../index.html#drops"
                        class="about-category"
                    >
                        <span class="about-category-number">03</span>

                        <h3>Drops</h3>

                        <p>
                            Lançamentos especiais e coleções limitadas para
                            quem quer algo ainda mais exclusivo.
                        </p>

                        <span class="about-category-link">
                            Explorar drops →
                        </span>
                    </a>
                </div>
            </div>
        </section>

        <section class="about-manifesto about-reveal">
            <div class="about-container">
                <div class="about-manifesto-inner">
                    <span class="about-manifesto-label">
                        Dark District
                    </span>

                    <h2>
                        Não siga tendências.
                        <br>
                        Crie a sua própria.
                    </h2>

                    <p>
                        Vista o seu lado obscuro.
                    </p>
                </div>
            </div>
        </section>
    `;

    initRevealAnimations();
}

function initRevealAnimations() {
    const elements = document.querySelectorAll(".about-reveal");

    if (!elements.length) {
        return;
    }

    if (!("IntersectionObserver" in window)) {
        elements.forEach((element) => {
            element.classList.add("is-visible");
        });

        return;
    }

    const observer = new IntersectionObserver(
        (entries, currentObserver) => {
            entries.forEach((entry) => {
                if (!entry.isIntersecting) {
                    return;
                }

                entry.target.classList.add("is-visible");
                currentObserver.unobserve(entry.target);
            });
        },
        {
            threshold: 0.1,
            rootMargin: "0px 0px -40px 0px"
        }
    );

    elements.forEach((element) => {
        observer.observe(element);
    });
}