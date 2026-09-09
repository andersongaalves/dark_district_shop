import { get, post, put, deleteRequest } from "../api.js";
import { renderProdutos, renderProdutosError } from "./produtos_ui.js";
import { openProductModal } from "./produtos_modal.js";

export async function carregarProdutos() {
    try {
        const produtos = await get("/produtos");
        renderProdutos(produtos, {
            onNew: () => openProductModal({ onSubmit: criarProduto }),
            onEdit: editarProduto,
            onDelete: excluirProduto
        });
    } catch (error) {
        renderProdutosError(error.message, carregarProdutos);
    }
}

async function criarProduto(dados) {
    await post("/produtos", dados);
    await carregarProdutos();
}

function editarProduto(produto) {
    openProductModal({
        produto,
        onSubmit: async (dados) => {
            await put(`/produtos/${encodeURIComponent(produto.id)}`, dados);
            await carregarProdutos();
        }
    });
}

async function excluirProduto(produto) {
    if (!confirm(`Excluir o produto "${produto.title}"?`)) return;
    try {
        await deleteRequest(`/produtos/${encodeURIComponent(produto.id)}`);
        await carregarProdutos();
    } catch (error) {
        alert(error.message);
    }
}
