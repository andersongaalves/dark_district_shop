import pytest
from pydantic import ValidationError

from schemas.produto import (
    ProdutoCreate,
    ProdutoUpdate,
    ProdutoImagemCreate,
    ProdutoVarianteCreate
)


def test_criar_produto_valido():
    produto = ProdutoCreate(
        id="prod-001",
        title="Camiseta Dark District",
        description="Camiseta preta",
        price=99.90,
        category="Camisetas",
        gender="Unissex"
    )

    assert produto.id == "prod-001"
    assert produto.price == 99.90
    assert produto.available is True
    assert produto.featured is False
    assert produto.images == []
    assert produto.variants == []


def test_produto_nao_aceita_preco_negativo():
    with pytest.raises(ValidationError):
        ProdutoCreate(
            id="prod-001",
            title="Produto",
            description="Descrição",
            price=-10,
            category="Categoria",
            gender="Unissex"
        )


def test_produto_aceita_imagens():
    produto = ProdutoCreate(
        id="prod-001",
        title="Produto",
        description="Descrição",
        price=50,
        category="Categoria",
        gender="Unissex",
        images=[
            ProdutoImagemCreate(
                url="https://exemplo.com/imagem1.jpg",
                ordem=0
            ),
            ProdutoImagemCreate(
                url="https://exemplo.com/imagem2.jpg",
                ordem=1
            )
        ]
    )

    assert len(produto.images) == 2
    assert produto.images[0].url == "https://exemplo.com/imagem1.jpg"
    assert produto.images[1].ordem == 1


def test_produto_aceita_variantes():
    produto = ProdutoCreate(
        id="prod-001",
        title="Produto",
        description="Descrição",
        price=50,
        category="Categoria",
        gender="Unissex",
        variants=[
            ProdutoVarianteCreate(
                size="M",
                color="Preto",
                quantity=5
            ),
            ProdutoVarianteCreate(
                size="G",
                color="Branco",
                quantity=3
            )
        ]
    )

    assert len(produto.variants) == 2
    assert produto.variants[0].size == "M"
    assert produto.variants[0].color == "Preto"
    assert produto.variants[0].quantity == 5


def test_variante_nao_aceita_quantidade_negativa():
    with pytest.raises(ValidationError):
        ProdutoVarianteCreate(
            size="M",
            color="Preto",
            quantity=-1
        )


def test_atualizacao_parcial():
    produto = ProdutoUpdate(
        title="Novo nome",
        price=120
    )

    assert produto.title == "Novo nome"
    assert produto.price == 120
    assert produto.description is None
    assert produto.category is None