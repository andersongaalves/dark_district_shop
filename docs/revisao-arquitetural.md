# Revisão arquitetural — Dark District

## Diagnóstico anterior às alterações

Revisão de todos os módulos próprios de frontend/backend, HTML, CSS, configuração,
migration e testes. Arquivos locais `.env` e bancos existentes foram preservados;
seus valores não foram impressos. O repositório estava sem alterações locais.

| Grupo | Problemas encontrados |
| --- | --- |
| Arquitetura | Destaques dependia da API administrativa; API pública dentro da página de produto; catálogo e modal misturavam coordenação e templates; routers continham toda a persistência. |
| Duplicação | Configuração HTTP, formatação de preços, montagem de relações e consultas de produto; Admin buscava produtos duas vezes. |
| Inconsistências | Drops apontava para Brechó; footer criado fora do placeholder e ausente no catálogo/produto; WhatsApp incompleto; CSS de Sobre definia reset e tema global. |
| Bugs potenciais | Disponibilidade ignorava `available`, usava apenas a primeira variante compatível e não reagia à seleção; falha de gravação fechava modal; gênero vazio virava `null`, incompatível com schema; erros de rede/JSON inconsistentes. |
| Segurança | Interpolação sem escape de atributos, descrição, categorias e dados do Admin; testes de autenticação protegida substituíam a própria autenticação. |
| Código morto | Módulos JS/CSS vazios e dados estáticos de categorias sem referências; estado global desnecessário no Admin. |

## Plano, em ordem de risco

1. Centralizar HTTP público, URLs, escape e preços; corrigir links e footer.
2. Isolar regras puras de disponibilidade, conectar eventos e preservar descrição/galeria.
3. Separar renderização do catálogo e do modal; manter formulário aberto em falhas.
4. Extrair persistência para service, preservar contratos e melhorar cobertura real de auth.
5. Consolidar CSS sem mudar valores visuais; remover somente código comprovadamente sem uso.
6. Executar testes, verificar imports/recursos, navegar pelos fluxos locais e revisar diff.

## Limites deliberados

- Brechó e Drops são páginas “Em breve”. Não existe `type` nem `offer` no model,
  schema ou Admin. `featured` já é um booleano independente de `category`. Não
  inferir tipo por categoria/destaque e não introduzir campos/migration sem uma
  definição de classificação dos dados existentes. A home mantém o limite atual
  de quatro destaques, selecionados automaticamente por `featured`.
- FAQ não tem página nem conteúdo no repositório. Não inventar políticas comerciais.
- Manter FastAPI, SQLAlchemy, PostgreSQL, Alembic e ES Modules sem frameworks.
- Preservar rotas/status/payloads existentes, credenciais, migration inicial e bancos.
- Não substituir o armazenamento de autenticação por cookies: isso exige mudança
  coordenada de contrato e implantação. Restringir seu acesso à área administrativa.

## Validação inicial

26 testes passaram, executados em diretório temporário com chave efêmera de teste.
Os bancos locais existentes não foram utilizados. Há avisos de depreciação das
dependências e de `datetime.utcnow`.

## Decisões implementadas

- **HTTP:** `js/core/api.js` define ambiente e erros com `status`, interpreta 204,
  falhas de conexão, respostas inválidas e validações FastAPI. A API pública foi
  movida para `js/api/products_api.js`; somente `admin/api.js` acrescenta Bearer.
  Login usa o transporte sem token. Um 401 administrativo limpa a sessão e leva ao login.
- **URLs e segurança de UI:** rotas de Drops, Destaques e Admin são centralizadas;
  IDs são codificados nos caminhos HTTP. WhatsApp usa o contato existente. Dados
  dinâmicos são escapados em texto e atributos; imagens aceitam apenas HTTP/HTTPS.
  A descrição conserva títulos e listas, tratando seu conteúdo como texto.
- **Disponibilidade:** `js/core/products.js` concentra a regra: `available=false`
  bloqueia interesse; sem variantes vale o booleano; com variantes deve existir
  estoque em alguma combinação compatível. Seleções parciais consultam todas as
  variantes compatíveis, e mudanças de opção atualizam status e botão.
- **Controllers:** Produto coordena galeria, opções, disponibilidade e interesse;
  render não registra mais esses eventos. Catálogo e Sobre têm render separado.
  A seleção simples permanece local ao componente; não foi criado um store global.
- **Admin:** remoção da busca duplicada e do estado global de produtos. Lista,
  formulário, modal, imagens e variantes têm responsabilidades próprias. Templates
  de linhas são compartilhados entre render inicial e inserção. Falhas preservam
  o formulário e permitem tentar novamente; envio duplo é bloqueado. Gênero vazio
  permanece string, compatível com o schema, sem inventar um gênero padrão.
- **Backend:** routers mantêm endpoints/status e aplicam autenticação; service
  concentra consultas, relações e transações com rollback. PUT continua parcial:
  omitido/null preserva, `false`/zero atualiza e array vazio remove relações.
  Listagem carrega relações em lote (três SELECTs para o conjunto testado).
  Imagens respeitam `ordem`, com ID como desempate. Não houve alteração de schema.
- **Configuração e Alembic:** `.env` é resolvido a partir de `backend/`, CORS aceita
  configuração de ambiente mantendo origens existentes, e Alembic usa todos os
  models e o caminho de configuração, sem URL SQLite redundante no INI.
- **CSS:** reset/tema efetivamente exibido ficam em base; as variáveis de Sobre
  ficam no escopo `.sobre`. Cores e fontes repetidas usam tokens com os mesmos
  valores; três containers duplicados usam `.container`. Identidade e breakpoints
  foram preservados. Nenhuma comparação visual foi possível nesta sessão.
- **Nomes:** mantidos nomes portugueses de páginas/Admin e helpers ingleses já
  estabelecidos. A movimentação de `products_api.js` corrige responsabilidade;
  não houve tradução ou renomeação em massa de classes e contratos.

## Estrutura resultante

```text
backend/
  core/                 configuração e segurança
  models/               mapeamento SQLAlchemy
  schemas/              entrada e saída
  routers/              contratos HTTP
  services/produtos.py   persistência e transações
  alembic/              migration inicial preservada
  tests/                API, auth, schemas, regressões e migrations
  database.py, main.py, create_admin.py
  requirements.txt, requirements-dev.txt, README.md
frontend/
  pages/                catálogo, produto, sobre, brechó e drops
  js/
    api/products_api.js
    core/api.js, products.js
    utils/urls.js, dom.js, format.js
    components/         header, footer, product_card
    sections/           hero, featured, controllers/render de catálogo e sobre
      produto/          controller, render, description, gallery, options,
                        availability, interest
  admin/
    api.js, auth.js, admin.js
    login/
    produtos/           controller, UI, modal, form, imagens, variantes
  css/base/, css/components/, css/sections/, css/main.css
  assets/, index.html, wrangler.jsonc, README.md
tests/frontend/         testes Node sem dependências
docs/revisao-arquitetural.md
package.json            ES Modules e comando de testes, sem build
```

## Código morto removido

- JS vazio: `core/state.js`, `core/router.js`, `components/category_card.js`,
  `sections/categories.js`, `sections/offers.js`.
- `js/data/categories.js`: lista estática sem consumidores; filtros usam categorias da API.
- CSS vazio: `components/buttons.css`, `components/category-card.css`,
  `sections/categories.css`, `sections/offers.css`.
- API antiga dentro de `sections/produto/`: substituída pelo módulo público compartilhado.
- `normalizarProduto` redundante com o payload do formulário, `postForm` substituído
  pelo login sem Bearer, imports redundantes de testes e listener duplicado do Admin.

## Validação final

| Verificação | Resultado |
| --- | --- |
| `backend/venv/Scripts/python.exe -m pytest backend/tests -q` | 48 testes passaram. |
| `npm.cmd run test:frontend` | 20 testes passaram, sem dependências npm. |
| Migrations | Upgrade em SQLite temporário corresponde aos models; SQL PostgreSQL compilado offline. |
| API protegida | CRUD com login real; sem token, inválido, expirado, usuário inexistente/inativo e sem subject rejeitados. |
| Relações e contratos | PUT parcial, false/zero, arrays vazios, órfãos, 404, imagens ordenadas e DELETE 204 cobertos. |
| Frontend | Disponibilidade, seleções parciais, escape/XSS nos templates, HTTP, login, 401, URLs e retenção do modal em falhas cobertos. |
| Arquitetura estática | Imports/exports reais vinculados, nenhum ciclo encontrado, API pública sem dependência de Admin, recursos locais existentes e variáveis CSS definidas. |
| Caminhos | URLs testadas na raiz de hospedagem e sob `/frontend/`, além da seleção de ambiente local IPv4/IPv6. |

Os testes de frontend usam mocks de rede e, no teste do modal, um objeto que
implementa os contratos necessários do DOM. Eles não comprovam navegação ou aparência.
O Browser integrado retornou indisponível e a descoberta de navegadores retornou
lista vazia. Portanto **os fluxos manuais de Home, catálogo, produto, galeria,
filtros, header/footer, WhatsApp e Admin não foram executados no navegador**.
Também não houve execução online contra PostgreSQL, Render ou Cloudflare.

Os testes de backend ainda emitem avisos de depreciação de Starlette/httpx/anyio
e `datetime.utcnow`. Não foram atualizadas dependências nem alterados tipos de
timestamp para silenciar avisos. Os arquivos versionados revisados não apresentaram
credenciais reais embutidas; `.env` e bancos locais continuam ignorados e intactos.
Essa verificação não equivale a auditoria do histórico Git ou dos serviços hospedados.

## Pendências deliberadas e próximos passos relevantes

1. Executar a verificação visual e os fluxos completos em homologação, incluindo
   CRUD real no Admin, imagens, variantes e WhatsApp, com PostgreSQL e migrations.
2. Definir a classificação de produtos antes de adicionar `type`/`offer` e ativar
   Brechó/Drops; `featured` deve continuar independente. FAQ aguarda conteúdo real.
3. Planejar atualização compatível das dependências com avisos. Manter por ora
   Float de preço, timestamps existentes e token em localStorage evita mudanças
   de contrato/dados/autenticação fora desta refatoração. localStorage permanece
   acessível a JavaScript; a correção de escape reduz os vetores encontrados,
   mas uma migração para cookies exige desenho próprio.

Sugestão de commit:

```text
refactor: modularize storefront and admin and centralize product services
```

## Arquivos alterados

| Arquivo | Status |
| --- | --- |
| `backend/README.md` | Adicionado |
| `backend/alembic.ini` | Alterado |
| `backend/alembic/env.py` | Alterado |
| `backend/core/config.py` | Alterado |
| `backend/main.py` | Alterado |
| `backend/models/produto.py` | Alterado |
| `backend/requirements-dev.txt` | Adicionado |
| `backend/routers/produtos.py` | Alterado |
| `backend/schemas/produto.py` | Alterado |
| `backend/services/__init__.py` | Adicionado |
| `backend/services/produtos.py` | Adicionado |
| `backend/tests/conftest.py` | Alterado |
| `backend/tests/test_auth.py` | Alterado |
| `backend/tests/test_migrations.py` | Adicionado |
| `backend/tests/test_regressions.py` | Adicionado |
| `backend/tests/test_security.py` | Alterado |
| `docs/revisao-arquitetural.md` | Adicionado |
| `frontend/README.md` | Alterado |
| `frontend/admin/admin.js` | Alterado |
| `frontend/admin/api.js` | Alterado |
| `frontend/admin/auth.js` | Alterado |
| `frontend/admin/login/login.js` | Alterado |
| `frontend/admin/produtos/produtos.js` | Alterado |
| `frontend/admin/produtos/produtos_form.js` | Adicionado |
| `frontend/admin/produtos/produtos_imagens.js` | Adicionado |
| `frontend/admin/produtos/produtos_modal.js` | Alterado |
| `frontend/admin/produtos/produtos_ui.js` | Alterado |
| `frontend/admin/produtos/produtos_variantes.js` | Alterado |
| `frontend/css/base/reset.css` | Alterado |
| `frontend/css/base/variables.css` | Alterado |
| `frontend/css/components/buttons.css` | Removido |
| `frontend/css/components/cards.css` | Alterado |
| `frontend/css/components/category-card.css` | Removido |
| `frontend/css/components/footer.css` | Alterado |
| `frontend/css/main.css` | Alterado |
| `frontend/css/sections/catalogo.css` | Alterado |
| `frontend/css/sections/categories.css` | Removido |
| `frontend/css/sections/featured.css` | Alterado |
| `frontend/css/sections/hero.css` | Alterado |
| `frontend/css/sections/offers.css` | Removido |
| `frontend/css/sections/produto.css` | Alterado |
| `frontend/css/sections/sobre.css` | Alterado |
| `frontend/js/api/products_api.js` | Adicionado |
| `frontend/js/components/category_card.js` | Removido |
| `frontend/js/components/footer.js` | Alterado |
| `frontend/js/components/product_card.js` | Alterado |
| `frontend/js/core/api.js` | Adicionado |
| `frontend/js/core/products.js` | Adicionado |
| `frontend/js/core/router.js` | Removido |
| `frontend/js/core/state.js` | Removido |
| `frontend/js/data/categories.js` | Removido |
| `frontend/js/sections/catalogo.js` | Alterado |
| `frontend/js/sections/catalogo_render.js` | Adicionado |
| `frontend/js/sections/categories.js` | Removido |
| `frontend/js/sections/featured.js` | Alterado |
| `frontend/js/sections/offers.js` | Removido |
| `frontend/js/sections/produto/products_api.js` | Removido |
| `frontend/js/sections/produto/produto.js` | Alterado |
| `frontend/js/sections/produto/produto_availability.js` | Alterado |
| `frontend/js/sections/produto/produto_description.js` | Alterado |
| `frontend/js/sections/produto/produto_interest.js` | Alterado |
| `frontend/js/sections/produto/produto_options.js` | Alterado |
| `frontend/js/sections/produto/produto_render.js` | Alterado |
| `frontend/js/sections/sobre.js` | Alterado |
| `frontend/js/sections/sobre_render.js` | Adicionado |
| `frontend/js/utils/dom.js` | Alterado |
| `frontend/js/utils/format.js` | Alterado |
| `frontend/js/utils/urls.js` | Alterado |
| `frontend/pages/brecho/index.html` | Alterado |
| `frontend/pages/drops/index.html` | Alterado |
| `package.json` | Adicionado |
| `tests/frontend/api.test.mjs` | Adicionado |
| `tests/frontend/architecture.test.mjs` | Adicionado |
| `tests/frontend/modal.test.mjs` | Adicionado |
| `tests/frontend/products.test.mjs` | Adicionado |
