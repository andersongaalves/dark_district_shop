import {
    get,
    post,
    put,
    deleteRequest
} from "../api.js";

import { renderProdutos } from "./produtos_ui.js";
import { openProductModal } from "./produtos_modal.js";

let produtos = [];

export async function carregarProdutos() {
    try {
        produtos = await get("/produtos");

        renderProdutos(produtos, {
            onNew: novoProduto,
            onEdit: editarProduto,
            onDelete: excluirProduto
        });
    } catch (error) {
        console.error(
            "Erro ao carregar produtos:",
            error
        );
    }
}

export function novoProduto() {
    openProductModal({
        onSubmit: criarProduto
    });
}

async function criarProduto(dados) {
    try {
        const produto = normalizarProduto(dados);

        await post(
            "/produtos",
            produto
        );

        await carregarProdutos();
    } catch (error) {
        console.error(
            "Erro ao criar produto:",
            error
        );

        alert(error.message);
    }
}

async function editarProduto(produto) {
    openProductModal({
        produto,
        onSubmit: async (dados) => {
            try {
                const produtoAtualizado =
                    normalizarProduto(dados);

                await put(
                    `/produtos/${produto.id}`,
                    produtoAtualizado
                );

                await carregarProdutos();
            } catch (error) {
                console.error(
                    "Erro ao atualizar produto:",
                    error
                );

                alert(error.message);
            }
        }
    });
}

async function excluirProduto(produto) {
    const confirmar = confirm(
        `Excluir o produto "${produto.title}"?`
    );

    if (!confirmar) return;

    try {
        await deleteRequest(
            `/produtos/${produto.id}`
        );

        await carregarProdutos();
    } catch (error) {
        console.error(
            "Erro ao excluir produto:",
            error
        );

        alert(error.message);
    }
}

function normalizarProduto(dados) {
    return {
        ...dados,

        images: (dados.images ?? [])
            .map((image, index) => {
                if (typeof image === "string") {
                    return {
                        url: image,
                        ordem: index
                    };
                }

                return {
                    url: image.url,
                    ordem: image.ordem ?? index
                };
            })
            .filter((image) => image.url),

        variants: (dados.variants ?? [])
            .map((variant) => ({
                size: variant.size ?? null,
                color: variant.color ?? null,
                quantity: Number(
                    variant.quantity ?? 0
                )
            }))
    };
}

document.addEventListener(
    "DOMContentLoaded",
    () => {
        carregarProdutos();
    }
);