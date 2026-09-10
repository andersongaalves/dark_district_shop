import { get, post, put, deleteRequest } from "../api.js";
import { getProductsPath } from "../../js/api/products_api.js";
import { PRODUCT_TYPES } from "../../js/core/products.js";
import { renderProdutos, renderProdutosError } from "./produtos_ui.js";
import { openProductModal } from "./produtos_modal.js";

export async function carregarProdutos({ type = "catalogo", isCurrent = () => true } = {}) {
    if (!Object.hasOwn(PRODUCT_TYPES, type)) type = "catalogo";
    const reload = () => carregarProdutos({ type, isCurrent });
    let opening = false;
    const open = async (produto = null) => {
        if (opening || !isCurrent()) return;
        opening = true;
        try {
            const [categories, collections] = await Promise.all([get("/categorias"), get("/colecoes")]);
            if (!isCurrent()) return;
            openProductModal({
                produto, categories, collections, type,
                onSubmit: async (data) => {
                    if (produto) await put(`/produtos/${encodeURIComponent(produto.id)}`, data);
                    else await post("/produtos", data);
                    if (isCurrent()) await reload();
                }
            });
        } catch (error) {
            if (isCurrent()) alert(error.message);
        } finally {
            opening = false;
        }
    };
    try {
        const products = await get(getProductsPath({ product_type: type }));
        if (!isCurrent()) return;
        renderProdutos(products, {
            title: PRODUCT_TYPES[type], onNew: () => open(), onEdit: open,
            onDelete: async (product) => {
                if (!confirm(`Excluir o produto "${product.title}"?`)) return;
                try {
                    await deleteRequest(`/produtos/${encodeURIComponent(product.id)}`);
                    if (isCurrent()) await reload();
                } catch (error) {
                    if (isCurrent()) alert(error.message);
                }
            }
        });
    } catch (error) {
        if (isCurrent()) renderProdutosError(error.message, reload);
    }
}
