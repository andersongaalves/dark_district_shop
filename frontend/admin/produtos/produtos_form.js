import { escapeHtml } from "../../js/utils/dom.js";
import { renderImages } from "./produtos_imagens.js";
import { renderVariants } from "./produtos_variantes.js";

export function renderProductForm(produto) {
    const images = produto?.images ?? [];
    const variants = produto?.variants ?? [];
    return `
        <div class="admin-modal__content">

            <div class="admin-modal__header">
                <h2>
                    ${produto ? "Editar produto" : "Novo produto"}
                </h2>

                <button
                    type="button"
                    class="admin-modal__close"
                    data-close
                >
                    ×
                </button>
            </div>

            <form
                id="produto-form"
                class="admin-modal__form"
            >

                <div class="admin-modal__field">
                    <label for="produto-id">
                        ID
                    </label>

                    <input
                        id="produto-id"
                        name="id"
                        value="${escapeHtml(produto?.id)}"
                        ${produto ? "readonly" : ""}
                        required
                    >
                </div>

                <div class="admin-modal__field">
                    <label for="produto-title">
                        Nome
                    </label>

                    <input
                        id="produto-title"
                        name="title"
                        value="${escapeHtml(produto?.title)}"
                        required
                    >
                </div>

                <div class="admin-modal__field">
                    <label for="produto-description">
                        Descrição
                    </label>

                    <textarea
                        id="produto-description"
                        name="description"
                        required
                    >${escapeHtml(produto?.description)}</textarea>
                </div>

                <div class="admin-modal__field">
                    <label for="produto-price">
                        Preço
                    </label>

                    <input
                        id="produto-price"
                        type="number"
                        name="price"
                        step="0.01"
                        min="0"
                        value="${escapeHtml(produto?.price)}"
                        required
                    >
                </div>

                <div class="admin-modal__field">
                    <label for="produto-category">
                        Categoria
                    </label>

                    <input
                        id="produto-category"
                        name="category"
                        value="${escapeHtml(produto?.category)}"
                        required
                    >
                </div>

                <div class="admin-modal__field">
                    <label for="produto-gender">
                        Gênero
                    </label>

                    <input
                        id="produto-gender"
                        name="gender"
                        value="${escapeHtml(produto?.gender)}"
                    >
                </div>

                <label>
                    <input
                        type="checkbox"
                        name="available"
                        ${produto?.available !== false
                            ? "checked"
                            : ""}
                    >
                    Disponível
                </label>

                <label>
                    <input
                        type="checkbox"
                        name="featured"
                        ${produto?.featured
                            ? "checked"
                            : ""}
                    >
                    Destaque
                </label>

                <div class="admin-modal__field">

                    <label>
                        Imagens
                    </label>

                    <div
                        id="produto-images"
                        class="admin-modal__images"
                    >
                        ${renderImages(images)}
                    </div>

                    <button
                        type="button"
                        id="add-image"
                    >
                        + Adicionar imagem
                    </button>

                </div>

                <div class="admin-modal__field">

                    <label>
                        Variações
                    </label>

                    <div
                        id="produto-variants"
                        class="admin-modal__variants"
                    >
                        ${renderVariants(variants)}
                    </div>

                    <button
                        type="button"
                        id="add-variant"
                    >
                        + Adicionar variação
                    </button>

                </div>

                <div class="admin-modal__actions">

                    <button
                        type="button"
                        data-close
                    >
                        Cancelar
                    </button>

                    <button type="submit">
                        Salvar
                    </button>

                </div>

            </form>

        </div>
    `;

}
