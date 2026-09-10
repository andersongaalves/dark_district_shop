# Ofertas com preço próprio, vencimento e prévia no ADM

## Uso

Ao marcar **Produto em oferta** no formulário, informe um preço de oferta menor
que o preço original. O campo **Término da oferta** aceita data e hora locais do
navegador; deixar vazio mantém a oferta sem prazo. Desmarcar a opção no ADM limpa
preço promocional e vencimento no envio do formulário.

Na listagem administrativa, a ordem no desktop é **título → imagem → preço →
disponibilidade → ações**. A primeira imagem cadastrada é usada como miniatura;
quando não há uma URL válida, aparece “Sem imagem”. O layout se adapta a telas menores.

## Contrato e comportamento

| Campo | Uso |
| --- | --- |
| `price` | Preço original, preservado durante e após a oferta |
| `offer_price` | Preço promocional opcional, não negativo e menor que `price` |
| `offer_ends_at` | Vencimento opcional com fuso horário; normalizado para UTC |
| `is_offer` | Configuração administrativa existente |
| `offer_active` | Resposta calculada: oferta habilitada e ainda dentro do prazo |
| `effective_price` | Preço calculado pelo backend para o instante da consulta |

`GET /produtos?offer_active=true&available=true` retorna ofertas vigentes disponíveis.
O filtro `is_offer` continua mostrando a configuração salva, inclusive ofertas vencidas,
para permitir sua edição. A expiração usa o relógio do servidor e dispensa cron ou
alteração do preço original no banco. No limite exato do prazo, vale o preço original.

O backend aceita `offer_price: null` e `offer_ends_at: null` para limpar cada campo;
campos omitidos em PUT são preservados. Valida o desconto contra o preço final da
atualização, inclusive quando apenas `price` muda. Novos prazos e reativações exigem
data futura. Uma oferta vencida permite edição de outros dados sem obrigar renovação.

As ofertas antigas, que tinham somente o booleano, continuam válidas no contrato
legado e mantêm o preço original até receber um preço promocional pelo ADM.

## Site e carrinho

Cards, página do produto e ADM usam uma apresentação compartilhada: preço original
riscado e preço promocional quando houver desconto vigente. A página do produto
também informa o término. Temporizadores atualizam os preços no catálogo e detalhe
e retiram ofertas vencidas da home, preservando a seleção de tamanho/cor.

O carrinho consulta novamente a API para obter `effective_price`; o valor salvo
localmente e o relógio do navegador não decidem o valor final. Se a oferta vencer
antes de continuar pelo WhatsApp, o novo valor é exibido e exige revisão e novo
clique. O contato individual usa o preço vigente ao clicar.

## Migration e publicação

Arquivo: `backend/alembic/versions/b83d012f5c42_timed_offers.py`.
Revision anterior: `a72c901e4b31`.

A migration adiciona duas colunas anuláveis e a restrição de preço promocional.
Produtos, variantes, imagens, preços originais e configurações anteriores são
preservados. O downgrade remove apenas os campos novos e sua restrição.

Publique a migration e o backend atualizado antes do frontend. No ambiente do
backend configurado para o banco de destino, execute a partir de `backend/`:

```bash
python -m alembic upgrade head
```

A migration não foi aplicada ao banco real durante esta implementação. Faça backup
e ensaie em PostgreSQL de homologação antes da publicação. O teste local usa SQLite
temporário e também compila o SQL para PostgreSQL.

## Validação

130 testes de backend e 48 testes de frontend passaram, cobrindo também:

- desconto inválido, rollback e verificação da restrição no banco;
- expiração no instante exato, fuso horário, prazo opcional e renovação;
- migration com dados existentes e downgrade;
- envio do formulário em UTC e limpeza de campos ao desmarcar oferta;
- preço atualizado com a página aberta e remoção da home sem recarga;
- revalidação do valor no carrinho após vencer a oferta;
- posição da miniatura, URLs de imagem seguras, imports e caminhos.

A conferência de interface foi automatizada com jsdom; isso não substitui inspeção
visual em um navegador real. As credenciais e bancos existentes não foram alterados.
