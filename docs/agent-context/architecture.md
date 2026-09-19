# Arquitetura do projeto

Last verified against commit: `215910f2eb29c90a3fd8d2456d292fb470ae8a05`

## Visão geral

Dark District é uma loja de moda alternativa com frontend estático, API FastAPI e
PostgreSQL. A vitrine, o carrinho, o Web Chat e o admin usam a mesma API. O catálogo é
a fonte dos produtos apresentados ao usuário e das respostas factuais da IA.

```text
Browser
  ├─ site público ───────────────┐
  └─ admin (Bearer JWT) ─────────┤
                                 v
                         FastAPI / routers
                                 v
                    services / tools / integrations
                                 v
                             PostgreSQL

Meta WhatsApp -> webhook HMAC -> persistência -> DeliveryJob -> consumer ->
decision layer -> AI ou handoff -> WhatsApp Cloud API
```

## Stack e entrypoints

- Frontend: HTML/CSS/JavaScript vanilla, ES Modules, entrada pública em
  `frontend/js/main.js` e páginas em `frontend/pages/`.
- Admin: `frontend/admin/index.html` + `frontend/admin/admin.js`; navegação por hash.
- Backend: `backend/main.py`, executado como `uvicorn main:app` a partir de `backend/`.
- Configuração: `backend/core/config.py`, com ambiente acima de `backend/.env`.
- Banco: `backend/database.py`; schema por `backend/alembic/versions/`.
- WhatsApp V2: `backend/services/whatsapp_hybrid_service.py`; consumer embutido no
  lifespan da API ou worker externo opcional em `backend/worker.py --hybrid`.

## Backend

`main.py` configura middleware de tamanho/rate limit, CORS, respostas privadas sem cache,
handlers de domínio e estes grupos de rotas:

| Prefixo | Router | Responsabilidade |
| --- | --- | --- |
| `/auth` | `routers/auth.py` | login administrativo |
| `/produtos` | `routers/produtos.py` | listagem pública e CRUD protegido |
| `/categorias`, `/colecoes` | `routers/catalog.py` | taxonomia e coleções |
| `/faq` | `routers/faq.py` | FAQ público |
| `/shipping` | `routers/shipping.py` | política, CEP, cotação e checkout textual |
| `/api/chat` | `routers/webchat.py` | sessão e mensagens do Web Chat |
| `/webhooks/whatsapp` | `routers/whatsapp.py` | verificação e eventos Meta |
| `/admin/conversations` | `routers/atendimento_admin.py` | inbox e controle humano/IA |

Routers devem permanecer finos. `services/` contém transações e regras; `models/`
contém persistência; `schemas/` valida entrada/saída; `integrations/` limita IO externo.

## Frontend

`frontend/js/core/api.js` escolhe a API local para loopback e a API de produção para
outros hosts. `js/utils/urls.js` resolve caminhos tanto na raiz hospedada quanto sob
`/frontend/`. Header, footer, cards e preço são componentes compartilhados.

Catálogo, Brechó e Drops reutilizam `sections/catalogo.js` com `data-product-type`.
Produto é dividido em galeria, descrição, opções, disponibilidade e interesse. Carrinho
separa estado, persistência e UI; o `localStorage` não é autoridade para preço/estoque.
O chat separa API, estado, `sessionStorage` e apresentação.

O admin verifica um token no `localStorage`, navega por hash e carrega produtos,
categorias, coleções ou inbox. A API ainda valida todo acesso; a checagem do browser não
substitui autenticação.

## Autenticação e segurança

Admin usa username/password com bcrypt e JWT assinado. `get_current_user` exige `sub`,
`exp`, algoritmo configurado e usuário ativo. `create_admin.py` cria administrador apenas
quando executado explicitamente com variáveis próprias.

Web Chat usa credencial aleatória por sessão; apenas SHA-256 é persistido. WhatsApp usa
a identidade verificada `phone_number_id:sender`, sem aceitar alegações do cliente para
mesclar identidades. Rotas privadas recebem `no-store`; corpos e tentativas são limitados
por middleware process-local.

## Catálogo, compra e frete

`Produto` relaciona categoria obrigatória, coleção opcional, imagens e variantes.
Preço efetivo considera oferta ativa e prazo. CRUD fica em `services/produtos.py`;
taxonomia em `services/catalog.py`.

O frontend reconsulta a API ao operar o carrinho. `services/shipping.py` reconstrói a
cesta no banco, calcula a rota por `integrations/shipping_maps.py`, aplica
`shipping_policy.py` e assina uma cotação curta. O checkout valida novamente a cotação e
gera a mensagem; não há model de pedido ou pagamento.

## Web Chat, WhatsApp e admin

O Web Chat chama `conversation_service.receive`, que persiste a entrada, libera a conexão
antes do LLM, usa `ai_agent` e finaliza sob lock/versionamento. O WhatsApp V2 valida o
webhook, persiste `Customer`, `ChannelIdentity`, `Conversation`, `Message` e
`DeliveryJob`, e deixa o consumer decidir entre resposta automática e handoff. A mesma
fila usa PostgreSQL para leases/ownership e pode ser consumida pelo lifespan ou pelo worker
externo. O fluxo humano continua disponível quando a IA do WhatsApp está desligada.
Detalhes estão em [whatsapp-ai.md](whatsapp-ai.md).

O admin protege todas as rotas com JWT. A inbox lista/pagina conversas WhatsApp, carrega
histórico, assume, encerra, envia mensagens humanas, altera modo e pede sugestões.
Detalhes estão em [admin.md](admin.md).

## Where to look

| Para alterar | Comece por |
| --- | --- |
| Produto, oferta, imagem ou variante | `models/produto.py`, `schemas/produto.py`, `services/produtos.py` |
| Categoria ou coleção | `models/catalog.py`, `routers/catalog.py`, `services/catalog.py` |
| Carrinho e produto público | `frontend/js/cart/`, `frontend/js/sections/produto/` |
| Frete | `routers/shipping.py`, `services/shipping.py`, `services/shipping_policy.py` |
| Auth/admin | `core/security.py`, `routers/auth.py`, `frontend/admin/` |
| Web Chat | `routers/webchat.py`, `services/conversation_service.py`, `services/ai_agent.py` |
| Ferramentas da IA | `tools/registry.py`, `tools/catalog_tools.py`, `tools/faq_tools.py` |
| WhatsApp/AI | [whatsapp-ai.md](whatsapp-ai.md) |
| Inbox | [admin.md](admin.md) |
| Banco/migrations | [data-model.md](data-model.md) |
| Deploy/config | [deployment.md](deployment.md) |
