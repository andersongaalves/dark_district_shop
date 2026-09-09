import { formatPrice } from "../../js/utils/format.js";
import { escapeHtml } from "../../js/utils/dom.js";

export function renderProdutosError(message, onRetry) {
    const container = document.querySelector("#admin-produtos");
    if (!container) return;
    container.innerHTML = `<p role="alert">${escapeHtml(message)}</p><button type="button">Tentar novamente</button>`;
    container.querySelector("button").addEventListener("click", onRetry);
}
export function renderProdutos(
    produtos,
    actions = {}
) {
    const container = document.querySelector(
        "#admin-produtos"
    );

    if (!container) return;

    container.innerHTML = `
        <div class="admin-produtos__header">
            <h1>Produtos</h1>

            <button
                type="button"
                id="novo-produto"
            >
                + Novo produto
            </button>
        </div>

        <div class="admin-produtos__list">
            ${
                produtos.length
                    ? produtos
                        .map((produto) =>
                            renderProduto(produto)
                        )
                        .join("")
                    : `
                        <p>
                            Nenhum produto cadastrado.
                        </p>
                    `
            }
        </div>
    `;

    setupActions(
        container,
        produtos,
        actions
    );
}

function renderProduto(produto) {

    return `
        <article
            class="admin-produto"
            data-id="${escapeHtml(produto.id)}"
        >
            <div>
                <strong>
                    ${escapeHtml(produto.title)}
                </strong>

                <span>
                    ID: ${escapeHtml(produto.id)}
                </span>
            </div>

            <span>
                ${formatPrice(produto.price)}
            </span>

            <span>
                ${produto.available
                    ? "Disponível"
                    : "Indisponível"}
            </span>

            <div>
                <button
                    type="button"
                    data-action="edit"
                    data-id="${escapeHtml(produto.id)}"
                >
                    Editar
                </button>

                <button
                    type="button"
                    data-action="delete"
                    data-id="${escapeHtml(produto.id)}"
                >
                    Excluir
                </button>
            </div>
        </article>
    `;
}

function setupActions(
    container,
    produtos,
    actions
) {
    const novoButton =
        container.querySelector(
            "#novo-produto"
        );

    novoButton?.addEventListener(
        "click",
        () => {
            actions.onNew?.();
        }
    );

    container
        .querySelectorAll("[data-action]")
        .forEach((button) => {
            button.addEventListener(
                "click",
                () => {
                    const produto =
                        produtos.find(
                            (item) =>
                                item.id ===
                                button.dataset.id
                        );

                    if (!produto) return;

                    if (
                        button.dataset.action ===
                        "edit"
                    ) {
                        actions.onEdit?.(
                            produto
                        );
                    }

                    if (
                        button.dataset.action ===
                        "delete"
                    ) {
                        actions.onDelete?.(
                            produto
                        );
                    }
                }
            );
        });
}
