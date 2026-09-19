# Painel administrativo e inbox

Last verified against commit: `215910f2eb29c90a3fd8d2456d292fb470ae8a05`

## Entrada e autenticação

O admin está em `frontend/admin/index.html`; `admin.js` verifica `auth.js` e direciona
para o login quando não existe token local. `admin/login/login.js` chama
`POST /auth/login`. `admin/api.js` acrescenta o Bearer às chamadas e limpa/redireciona
após 401. A API confirma assinatura, expiração, usuário existente e `active=true`.

`create_admin.py` é uma operação explícita do backend com `ADMIN_USERNAME` e
`ADMIN_PASSWORD`; não existe cadastro público nem criação no startup.

## Navegação

O admin usa hashes, sem router externo:

- `#produtos/catalogo`, `#produtos/brecho`, `#produtos/drop`
- `#configuracoes/categorias`, `#configuracoes/colecoes`
- `#atendimento`

`frontend/admin/admin.js` desmonta a inbox anterior ao trocar de seção e usa uma revisão
para ignorar carregamentos atrasados.

## Produtos e configurações

`admin/produtos/produtos.js` coordena lista e modal. Formulário, imagens, variantes e
renderização ficam nos módulos vizinhos. A listagem usa a primeira imagem como preview.
Categorias/coleções compartilham controller em `admin/configuracoes/configuracoes.js` e
renderização em `configuracoes_ui.js`.

Escritas de `/produtos`, `/categorias` e `/colecoes` são protegidas no backend. Falha ao
salvar deve preservar os campos do modal. IDs existentes de variantes não devem mudar
sem necessidade.

## Inbox WhatsApp

`frontend/admin/atendimento/atendimento.js` monta a inbox e
`frontend/admin/atendimento/atendimento.css` define o layout. A lista usa polling de 5s,
filtros, paginação de 50 e ordenação do backend. O histórico pagina mensagens anteriores
por cursor e exibe estado de entrega.

Fluxos disponíveis:

- assumir: `POST /admin/conversations/{id}/claim`;
- encerrar: `POST /admin/conversations/{id}/close`;
- resposta humana: `POST /admin/conversations/{id}/messages`, com UUID do browser;
- modo: `PATCH /admin/conversations/{id}/ai-mode`;
- sugestão: `POST /admin/conversations/{id}/ai-suggestion`;
- retomar IA: `PATCH /admin/conversations/{id}` com status `AI`;
- histórico: `GET /admin/conversations/{id}/messages`;
- lista: `GET /admin/conversations?channel=whatsapp`.

Todas as rotas sob `/admin/conversations` exigem `get_current_user` e resposta sem cache.

## Estado da interface

Drafts e UUIDs de tentativas ficam em memória. Uma tentativa ambígua mantém texto/UUID
para reconciliação e impede editar silenciosamente a mesma operação. Polling é suspenso
enquanto há mutação e respostas atrasadas são ignoradas por revisão.

O painel lateral da IA mostra separadamente modo e status, última decisão com rótulo
amigável, tentativa de esclarecimento, motivo de handoff, produto em foco, quantidade de
produtos apresentados, preferências allowlisted e eventos operacionais recentes. Ele abre
no desktop e é colapsável no mobile. A API entrega esses dados no `ai_state` do histórico;
o `Conversation.context` bruto, prompts, payloads do provider e IDs internos não chegam ao
browser. IDs de produto são limitados pelo contexto V2 e resolvidos em uma consulta para
nome; o painel não funciona como catálogo.

As ações vêm no mesmo read model. “Retomar IA” aparece somente em `WAITING_HUMAN` ou
`HUMAN`, fica desabilitado durante a chamada e some após `AI`; nunca aparece em `CLOSED`.
Assumir e encerrar também respeitam o estado, e `HUMAN + ASSIST` mantém geração manual de
sugestão. Sugestão só é pedida por clique. Copiar/usar/enviar é habilitado em `HUMAN`;
“Enviar agora” preenche o composer e dispara o POST humano.

O polling de 5 segundos continua usando o endpoint de histórico e passa a atualizar também
todo o `ai_state`. Revisões descartam snapshots atrasados durante mutações, e o textarea não
é reconstruído nem substituído pelo polling, preservando o rascunho do atendente.

## Onde começar

| Mudança | Primeiro arquivo |
| --- | --- |
| Navegação/seção do admin | `frontend/admin/admin.js` |
| Login/token/401 | `frontend/admin/auth.js`, `frontend/admin/api.js` |
| Produto/lista/modal | `frontend/admin/produtos/` |
| Categoria/coleção | `frontend/admin/configuracoes/` |
| Inbox, polling ou sugestão | `frontend/admin/atendimento/atendimento.js` |
| Layout responsivo da inbox | `frontend/admin/atendimento/atendimento.css` |
| Contrato HTTP da inbox | `backend/routers/atendimento_admin.py` |
| Consulta/envio da inbox | `backend/services/whatsapp_inbox_service.py` |
| Modo/sugestão | `backend/services/whatsapp_ai_service.py` |
| Estado/handoff | `backend/services/conversation_service.py`, `whatsapp_hybrid_service.py` |

Testes principais: `tests/frontend/admin.test.mjs`, `inbox.test.mjs`,
`backend/tests/test_auth.py`, `test_whatsapp_inbox.py` e `test_whatsapp_hybrid.py`.
