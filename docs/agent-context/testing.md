# Testes e validação

Last verified against commit: `7ca1baf1cc64a488d1c9b2e3a25eb23d93713242`

## Ambientes

Backend usa pytest. `backend/tests/conftest.py` força SQLite em memória, segredo efêmero
e integrações externas desativadas antes de importar a aplicação. `client` substitui o
usuário administrativo apenas em testes de CRUD; `public_client` mantém auth real.

Frontend usa Node Test Runner e jsdom. Não há build. Os testes carregam os módulos ES e
simulam DOM/fetch/storage; eles não substituem conferência visual responsiva.

## Comandos

Na raiz:

```powershell
backend/venv/Scripts/python.exe -m pytest backend/tests -q
npm.cmd run test:frontend
```

Dentro de `backend/`:

```powershell
python -m pytest tests -q
python -m pytest tests/test_migrations.py -q
python -m alembic heads
python -m worker --hybrid --once
```

Em Windows com restrição no diretório temporário, passe um `--basetemp` novo e
`-p no:cacheprovider`. Não reutilize um caminho amplo para limpeza.

## PostgreSQL opcional

`backend/tests/test_delivery_postgres.py` só executa com `TEST_POSTGRES_URL`. O valor deve
apontar explicitamente para PostgreSQL dedicado a teste. Cada teste usa schema aleatório
e o remove ao terminar; nunca use a URL da aplicação/produção. A suíte cobre claims
concorrentes, ordem por identidade, idempotência de webhooks e envio humano.

## Matriz de seleção

| Área alterada | Testes mínimos relevantes |
| --- | --- |
| Models ou migration | `test_migrations.py`, schemas/domínio afetado, `alembic heads` |
| Produto/catálogo/oferta | `test_produtos.py`, `test_catalog.py`, `test_offers.py`, testes frontend correspondentes |
| Frete/carrinho | `test_shipping.py`, `shipping.test.mjs`, `cart.test.mjs` |
| Auth/segurança | `test_auth.py`, `test_security.py`, `test_security_hardening.py`, `admin.test.mjs` |
| AI Agent/tools | `test_ai_agent.py`, `test_agent_availability.py`, `test_agent_interaction.py`, `test_catalog_tools.py` |
| Web Chat | `test_webchat.py`, `test_conversations.py`, `chat.test.mjs` |
| Webhook/Meta | `test_whatsapp.py`, `test_whatsapp_human.py`, `test_whatsapp_hybrid.py` |
| Inbox/admin WhatsApp | `test_whatsapp_inbox.py`, `test_whatsapp_hybrid.py`, `inbox.test.mjs` |
| Worker/consumer | `test_worker.py`, `test_whatsapp_hybrid.py`; PostgreSQL opcional para concorrência |
| Layout/componentes públicos | arquivo `.test.mjs` correspondente + validação visual desktop/mobile |

Mudança compartilhada entre canais requer testar Web Chat e WhatsApp. Mudança em helper
de URL/API requer `architecture.test.mjs` e o teste funcional consumidor.

## Mocks e limites

Testes WhatsApp substituem Cloud API e notificações; testes de IA substituem o provider
ou usam o modo determinístico. Não fazem mensagem real, deploy, migration de produção ou
chamada paga. Migrações são exercitadas em SQLite temporário e compiladas offline para
PostgreSQL; isso não substitui homologação PostgreSQL antes de mudança arriscada.

Antes de commit, execute `git diff --check`, confira arquivos staged e faça busca por
credenciais. Documentação pura não exige suíte completa salvo regra nova que afete código.

## Integração e rollout WhatsApp V2

F2G consolida a matriz em `test_worker.py`, `test_whatsapp.py`,
`test_whatsapp_hybrid.py`, `test_whatsapp_inbox.py` e `test_webchat.py`. Os testes cobrem
validação de flags, consumer embutido ligado/desligado, worker `--hybrid --once`, fallback
humano sem LLM, falhas LLM/Meta, duplicatas, handoff, retomada, claim, ASSIST, CLOSED/novo
ciclo e independência do Web Chat. O cenário E2E simulado percorre descoberta, foco,
preço, intenção de compra, atendimento humano e reabertura sem APIs reais.

Antes de rollout, execute também `test_migrations.py`, `python -m alembic heads` e a suíte
frontend. Os testes PostgreSQL de concorrência continuam opcionais e exigem explicitamente
`TEST_POSTGRES_URL` dedicado; ausência dessa variável deve resultar em skip, nunca uso do
banco de produção.
