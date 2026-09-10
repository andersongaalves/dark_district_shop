import { escapeHtml } from "../../js/utils/dom.js";
import { renderImages } from "./produtos_imagens.js";
import { renderVariants } from "./produtos_variantes.js";
import { PRODUCT_TYPES } from "../../js/core/products.js";
import { toDateTimeInput } from "../../js/utils/format.js";

function recordOptions(records, selectedId) {
    return records.filter((record) => record.active || record.id === selectedId)
        .map((record) => `<option value="${escapeHtml(record.id)}" ${record.id === selectedId ? "selected" : ""}>${escapeHtml(record.name) || "Sem nome"}${record.active ? "" : " (desativada)"}</option>`).join("");
}

export function renderProductForm(produto, { categories = [], collections = [], type = "catalogo" } = {}) {
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
                        Preço original
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
                    <label for="produto-type">Tipo</label>
                    <select id="produto-type" name="product_type" required>
                        ${Object.entries(PRODUCT_TYPES).map(([value, label]) => `<option value="${value}" ${value === (produto?.product_type ?? type) ? "selected" : ""}>${label}</option>`).join("")}
                    </select>
                </div>
                <div class="admin-modal__field">
                    <label for="produto-category">Categoria</label>
                    <select id="produto-category" name="category_id" required>
                        <option value="">Selecione uma categoria</option>
                        ${recordOptions(categories, produto?.category_id)}
                    </select>
                    ${categories.some((record) => record.active || record.id === produto?.category_id) ? "" : "<small>Cadastre uma categoria ativa em Configurações antes de salvar.</small>"}
                </div>
                <div class="admin-modal__field">
                    <label for="produto-collection">Coleção</label>
                    <select id="produto-collection" name="collection_id">
                        <option value="">Sem coleção</option>
                        ${recordOptions(collections, produto?.collection_id)}
                    </select>
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

                <label><input type="checkbox" name="is_offer" ${produto?.is_offer ? "checked" : ""}> Produto em oferta</label>

                <div id="produto-offer-fields" class="admin-modal__offer" ${produto?.is_offer ? "" : "hidden"}>
                    <div class="admin-modal__field">
                        <label for="produto-offer-price">Preço de oferta</label>
                        <input id="produto-offer-price" name="offer_price" type="number" min="0" step="0.01"
                            value="${escapeHtml(produto?.offer_price ?? "")}" ${produto?.is_offer ? "required" : "disabled"}>
                        <small>Informe um valor menor que o preço original.</small>
                    </div>
                    <div class="admin-modal__field">
                        <label for="produto-offer-end">Término da oferta (opcional)</label>
                        <input id="produto-offer-end" name="offer_ends_at" type="datetime-local" step="1"
                            value="${escapeHtml(toDateTimeInput(produto?.offer_ends_at))}" ${produto?.is_offer ? "" : "disabled"}>
                        <small>Horário local deste navegador. Deixe vazio para uma oferta sem prazo.</small>
                    </div>
                </div>

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
