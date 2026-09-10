# Dark District — catálogo, administração e carrinho

Implementação de 9 de setembro de 2026. Este documento descreve esta etapa; a
revisão arquitetural anterior permanece como histórico.

## Resultado e arquitetura

O frontend continua em HTML/CSS/JavaScript ES Modules, sem build ou dependências
de runtime. O backend mantém FastAPI, SQLAlchemy e Alembic, com PostgreSQL como
banco de produção. Categorias e coleções agora são entidades, e todos os tipos
de produto continuam no mesmo CRUD.

Antes desta etapa, categorias eram texto livre; o ADM tinha uma única listagem
sem filtros por tipo; Brechó e Drops exibiam “Em breve”; destaques não filtravam
disponibilidade; não havia ofertas funcionais nem carrinho. A edição de produtos
também recriava variantes e seus IDs, incompatível com um carrinho persistente.

As mudanças preservam o transporte HTTP compartilhado, os módulos de produto,
o card existente, autenticação, imagens, descrição, seleção de opções e contato
direto pelo WhatsApp. Nenhum banco existente ou credencial foi alterado.

```text
backend/
├── models/       produto.py, catalog.py
├── schemas/      produto.py, catalog.py
├── services/     produtos.py, catalog.py
├── routers/      produtos.py, catalog.py
├── alembic/versions/a72c901e4b31_product_catalog.py
└── tests/        testes anteriores + test_catalog.py
frontend/
├── admin/
│   ├── produtos/       CRUD, modal, formulário, imagens e variantes compartilhados
│   └── configuracoes/ configuracoes.js, configuracoes_ui.js
├── js/
│   ├── api/products_api.js
│   ├── core/products.js
│   ├── components/    header.js, footer.js, product_card.js
│   ├── sections/      catalogo.js, catalogo_render.js, featured.js, produto/
│   ├── utils/urls.js
│   └── cart/          cart.js, cart_state.js, cart_storage.js, cart_ui.js
├── css/components/    header.css, cart.css
└── pages/             catalogo/, brecho/, drops/, produto/
tests/frontend/
├── admin.test.mjs, storefront.test.mjs
├── cart.test.mjs, product_cart.test.mjs
└── helpers/dom.mjs
```

Categorias e coleções compartilham operações de serviço e UI onde as regras são
iguais, mas possuem tabelas, schemas e endpoints próprios. Os routers cuidam dos
contratos HTTP; os serviços cuidam de vínculos, conflitos e transações. Erros de
domínio são convertidos em respostas HTTP sem expor detalhes do banco.

O ADM usa hashes validados (`#produtos/catalogo`, `#produtos/brecho`,
`#produtos/drop`, `#configuracoes/categorias`, `#configuracoes/colecoes`). As páginas
públicas continuam sendo arquivos HTML nas URLs já publicadas. Não há necessidade
de fallback de SPA no servidor. A navegação descarta respostas de consultas de
uma seção administrativa que já tenha sido abandonada.

## Modelo e compatibilidade

- `product_type`: `catalogo`, `brecho` ou `drop`, validado no schema e por CHECK no banco.
- `category_id`: FK obrigatória, com exclusão restrita; `category` permanece como
  nome textual sincronizado para os clientes existentes.
- `collection_id`: uma coleção opcional. Omissão em PUT preserva o vínculo;
  `null` remove a coleção. `category_id: null` é rejeitado.
- `featured`, `is_offer` e `available`: booleanos independentes do tipo e dos vínculos.
- Categorias: ID, nome, slug único, estado ativo e datas. Coleções têm os mesmos
  campos mais descrição opcional. Nome e slug são únicos por entidade.
- Registros desativados não podem ser associados a novos produtos. Um produto
  já vinculado pode continuar sendo editado sem perder sua categoria/coleção.
- Exclusão de categoria/coleção em uso retorna 409 e não remove produtos.
- Variantes existentes mantêm o ID enviado pelo ADM. Escritas legadas sem IDs
  tentam preservar identidade por combinação exata e única de tamanho/cor.
  IDs de outro produto e combinações duplicadas são rejeitados.

O campo textual `category` ainda é aceito no contrato legado de escrita. O serviço
resolve/cria uma categoria real e sempre preenche a FK; o novo ADM usa somente
`category_id`. Quando nome e ID forem enviados juntos, precisam corresponder.
Esse suporte está marcado como legado no OpenAPI. Sua retirada futura exige
migrar os clientes antigos primeiro.

Não foram adicionados `original_price`, relação N:N de coleções, reservas de estoque,
pedidos, pré-venda ou agendamento de drops. Nenhum desses recursos é necessário
para a estrutura solicitada. Brechó aceita qualquer estoque válido, inclusive 1.

## Migration e publicação

Revision **`a72c901e4b31`**, sucessora de `fc910ce70e6d`:

1. Cria `categorias` e `colecoes`.
2. Adiciona tipo, oferta e FKs em produtos.
3. Converte cada nome textual distinto em categoria, mantendo acentos, diferenças
   de caixa e espaços. Gera slugs exclusivos `legacy-1`, `legacy-2`, etc.
4. Preenche `category_id` antes de torná-lo obrigatório; cria índices, FKs RESTRICT
   e CHECK de tipo. Corrige a sequência de IDs das categorias no PostgreSQL.
5. Produtos antigos recebem `catalogo`, `is_offer=false` e coleção nula. Imagens,
   variantes e seus IDs não são recriados no PostgreSQL.

A migration usa `ALTER TABLE` nativo no PostgreSQL; o modo batch é empregado
apenas pela compatibilidade dos testes com SQLite. Não usa `create_all` como
migração. Nomes legados vazios continuam recuperáveis e aparecem no ADM para edição.

Para publicação, faça backup e ensaie a migration em PostgreSQL de homologação.
Coordene uma janela para a migration e a troca do backend: a versão anterior do
backend não preenche a nova FK obrigatória. Depois publique o frontend. No ambiente
de implantação já configurado, a partir de `backend/`:

```powershell
python -m alembic upgrade head
```

Esse comando **não foi executado contra o banco do projeto ou produção** nesta
tarefa. Os testes de migration foram executados somente em arquivos temporários.

O downgrade até `fc910ce70e6d` preserva produtos, imagens, variantes e os nomes
atuais das categorias no campo textual, mas remove os metadados novos de tipo,
oferta, categorias/coleções e seus vínculos. Faça backup antes de reverter.

## Endpoints

| Operação | Contrato | Autenticação |
| --- | --- | --- |
| `GET /categorias`, `GET /colecoes` | Listar; filtro opcional `active` | Pública |
| `POST /categorias`, `POST /colecoes` | Criar | Bearer administrativo |
| `PATCH /categorias/{id}`, `PATCH /colecoes/{id}` | Editar ou ativar/desativar | Bearer administrativo |
| `DELETE /categorias/{id}`, `DELETE /colecoes/{id}` | Excluir se não houver vínculos | Bearer administrativo |
| `GET /produtos` | Filtros combináveis por AND | Pública |
| `GET /produtos/{produto_id}` | Detalhe com os novos campos | Pública |
| `POST /produtos`, `PUT /produtos/{produto_id}` | Mesmo CRUD, com tipo/vínculos/flags | Bearer administrativo |
| `DELETE /produtos/{produto_id}`, `PATCH /produtos/{produto_id}/vendido` | Operações existentes preservadas | Bearer administrativo |

Filtros de produtos: `product_type`, `category_id`, `collection_id`, `featured`,
`is_offer`, `available`. `false` é um filtro válido. IDs relacionais devem ser
inteiros positivos; os IDs de produto continuam sendo strings.

## Carrinho

- `cart_state.js`: identidade produto/variante, operações puras, contagem, subtotal,
  sanitização e reconciliação com os produtos atuais.
- `cart_storage.js`: único acesso ao localStorage do carrinho, com envelope versão 1
  na chave `darkDistrictCart:v1`. JSON inválido, esquema desconhecido e bloqueios
  de storage não derrubam o site. Falha ao salvar mantém o estado em memória e
  informa a limitação ao usuário.
- `cart.js`: coordena chamadas à API, persistência, assinaturas e fila de operações.
  A fila evita que cliques simultâneos ultrapassem o estoque dentro da mesma aba.
- `cart_ui.js`: drawer em `<dialog>`, contador, itens, quantidade, remoção, limpeza,
  subtotal, mensagens, foco e ação de WhatsApp, com escape de dados e imagens seguras.

O snapshot guarda apenas produto, variante, título, tamanho, cor, preço, quantidade
e imagem. Estoque e estado de validação nunca são recuperados do localStorage.
O detalhe é consultado com `cache: no-store`. Há revalidação ao carregar/abrir o
carrinho, adicionar, mudar quantidade, atualizar e continuar pelo WhatsApp.

Preços/opções alterados durante a validação final exigem revisão e novo clique.
Produtos vendidos, variantes removidas, quantidades superiores ao estoque e falhas
da API impedem a continuação. O carrinho não reserva unidades; disponibilidade,
entrega e pagamento ainda são confirmados pela loja.

Produtos sem variantes usam o booleano `available`, pois o modelo não contém
estoque numérico para eles. Há limites de tamanho do carrinho (100 itens e 999
unidades por item), independentes do estoque real. Valores são somados em centavos.
Eventos de storage atualizam outras abas; gravações simultâneas entre abas seguem
a semântica de última gravação do localStorage, sem reserva ou transação distribuída.
A persistência é por origem do navegador; domínios diferentes não compartilham o carrinho.

## Validação e revisão do diff

Baseline: 85 testes de backend e 20 de frontend. Resultado desta etapa:
**117 testes de backend e 40 de frontend**, com cobertura adicional de:

- migration em banco vazio e preenchido, comparação com metadata e downgrade;
- compilação do SQL PostgreSQL, backfill e preservação de IDs;
- autenticação das novas escritas, CRUD, schemas, filtros e integridade referencial;
- bloqueio de exclusão/desativação, rollback de renomeação conflitante e variantes;
- formulários reais no jsdom, três listagens, ofertas e destaques;
- carrinho, alterações de preço/estoque, storage adulterado, rede indisponível;
- integração seleção → carrinho → contador → drawer, contato direto de WhatsApp;
- imports/exports, ausência de ciclos, assets e caminhos locais/produção, escape de HTML.

O diff foi revisado para duplicação, referências quebradas, funções antigas sem
uso, nomenclatura, caminhos e regressões. Os três tipos compartilham CRUD/API/card;
ofertas e destaques compartilham renderização; categorias/coleções compartilham UI.
O botão de menu inativo do header foi substituído pelo carrinho e seu CSS morto removido.
`git diff --check` não apontou problemas.

Execução na raiz:

```powershell
$testBase = Join-Path $env:TEMP ('dark-district-tests-' + [guid]::NewGuid().ToString('N'))
backend/venv/Scripts/python.exe -m pytest backend/tests -q -p no:cacheprovider --basetemp $testBase
npm ci
npm run test:frontend
```

O jsdom é apenas dependência de desenvolvimento, registrada no lockfile. A
instalação reportou zero vulnerabilidades. Permanecem avisos de depreciação de
dependências do backend e do uso anterior de `datetime.utcnow()`.

**Limites da validação:** o navegador integrado não disponibilizou uma sessão;
portanto, layout responsivo, comportamento visual e foco nativo do dialog precisam
de conferência em navegador. Não havia PostgreSQL/Docker disponível no ambiente;
a migration foi executada em SQLite temporário e compilada para PostgreSQL, sem
execução em PostgreSQL real. Não houve deploy, envio de mensagens, commit ou push.

## Commits sugeridos por etapa

1. `feat(db): adicionar categorias colecoes e classificacao de produtos`
2. `feat(api): gerenciar categorias colecoes e filtros de produtos`
3. `feat(admin): adicionar configuracoes de categorias e colecoes`
4. `feat(admin): unificar produtos por tipo e preservar variantes`
5. `feat(storefront): integrar catalogo brecho e drops com a API`
6. `feat(home): carregar ofertas e destaques disponiveis`
7. `feat(cart): adicionar carrinho persistente com validacao de estoque`
8. `test: validar migracao admin catalogo e carrinho`

Use seleção de hunks quando um arquivo participar de mais de uma etapa. As etapas
de banco e API precisam ser publicadas juntas; a documentação acompanha os commits
correspondentes. Nenhum commit foi criado automaticamente.

## Inventário de arquivos

### Criados (20)

```text
backend/alembic/versions/a72c901e4b31_product_catalog.py
backend/models/catalog.py
backend/routers/catalog.py
backend/schemas/catalog.py
backend/services/catalog.py
backend/tests/test_catalog.py
docs/catalogo-admin-carrinho.md
frontend/admin/configuracoes/configuracoes.js
frontend/admin/configuracoes/configuracoes_ui.js
frontend/css/components/cart.css
frontend/js/cart/cart.js
frontend/js/cart/cart_state.js
frontend/js/cart/cart_storage.js
frontend/js/cart/cart_ui.js
package-lock.json
tests/frontend/admin.test.mjs
tests/frontend/cart.test.mjs
tests/frontend/helpers/dom.mjs
tests/frontend/product_cart.test.mjs
tests/frontend/storefront.test.mjs
```

### Modificados (39)

```text
backend/README.md
backend/main.py
backend/models/__init__.py
backend/models/produto.py
backend/routers/produtos.py
backend/schemas/produto.py
backend/services/produtos.py
backend/tests/test_migrations.py
frontend/README.md
frontend/admin/admin.css
frontend/admin/admin.js
frontend/admin/api.js
frontend/admin/index.html
frontend/admin/produtos/produtos.js
frontend/admin/produtos/produtos_form.js
frontend/admin/produtos/produtos_modal.js
frontend/admin/produtos/produtos_ui.js
frontend/admin/produtos/produtos_variantes.js
frontend/css/components/header.css
frontend/css/main.css
frontend/index.html
frontend/js/api/products_api.js
frontend/js/components/header.js
frontend/js/core/products.js
frontend/js/main.js
frontend/js/sections/catalogo.js
frontend/js/sections/catalogo_render.js
frontend/js/sections/featured.js
frontend/js/sections/produto/produto.js
frontend/js/sections/produto/produto_availability.js
frontend/js/sections/produto/produto_render.js
frontend/js/utils/urls.js
frontend/pages/brecho/index.html
frontend/pages/catalogo/index.html
frontend/pages/drops/index.html
package.json
tests/frontend/api.test.mjs
tests/frontend/architecture.test.mjs
tests/frontend/modal.test.mjs
```

### Removidos (0)

Nenhum.
