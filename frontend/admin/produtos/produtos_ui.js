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
    const preco = Number(produto.price || 0)
        .toFixed(2)
        .replace(".", ",");

    return `
        <article
            class="admin-produto"
            data-id="${produto.id}"
        >
            <div>
                <strong>
                    ${produto.title}
                </strong>

                <span>
                    ID: ${produto.id}
                </span>
            </div>

            <span>
                R$ ${preco}
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
                    data-id="${produto.id}"
                >
                    Editar
                </button>

                <button
                    type="button"
                    data-action="delete"
                    data-id="${produto.id}"
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