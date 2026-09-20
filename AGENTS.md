# Dark District

Loja de moda alternativa/streetwear com vitrine pública, carrinho, frete, Web Chat,
painel administrativo e atendimento WhatsApp pela Cloud API oficial da Meta.

## Regra principal para agentes

Antes de fazer reconhecimento amplo do repositório, leia os documentos relevantes em
`docs/agent-context/`. Só faça nova exploração ampla quando a documentação estiver
ausente, inconsistente ou quando a tarefa envolver uma área ainda não documentada.

O campo `Last verified against commit` registra o commit usado na última conferência.
Um hash antigo não invalida automaticamente o documento: primeiro compare os arquivos
e subsistemas afetados pelos commits posteriores.

## Stack

- Frontend: HTML, CSS e JavaScript vanilla com ES Modules, sem build de produção.
- Backend: Python, FastAPI, Pydantic, SQLAlchemy e Alembic.
- Banco: PostgreSQL em produção; SQLite isolado em grande parte dos testes.
- Hospedagem: frontend estático via configuração Wrangler/Cloudflare; API no Render.
- Integrações: WhatsApp Cloud API, provider LLM compatível com OpenAI e Google Maps.
- Testes: pytest no backend e Node Test Runner + jsdom no frontend.

## Estrutura

- `backend/`: API, domínio, banco, migrations, integrações e testes Python.
- `frontend/`: site e admin estáticos, organizados em módulos e CSS por escopo.
- `tests/frontend/`: testes dos módulos e da interface em jsdom.
- `docs/`: documentação funcional e registros de entregas anteriores.
- `docs/agent-context/`: mapa arquitetural durável para futuras sessões.
- `compose.yaml`: PostgreSQL local opcional.
- `package.json`: dependências e comando dos testes do frontend.

Regras específicas existem em `backend/AGENTS.md` e `frontend/AGENTS.md`.

## Arquitetura

- O browser carrega o frontend estático e chama a API FastAPI.
- Routers validam HTTP e delegam regras aos services.
- Services concentram consultas, transações e integrações.
- Models SQLAlchemy e migrations Alembic definem o schema PostgreSQL.
- O catálogo atende vitrine, admin, carrinho e ferramentas de IA.
- O Web Chat processa o AI Agent no fluxo da requisição.
- O WhatsApp persiste primeiro; no modo híbrido, `DeliveryJob` desacopla IA e envio.
- A inbox em `/admin/#atendimento` centraliza o atendimento humano.

Detalhes e caminhos estão em [arquitetura](docs/agent-context/architecture.md).

## Documentação para agentes

| Assunto | Leia primeiro |
| --- | --- |
| Arquitetura geral e localização de código | [architecture.md](docs/agent-context/architecture.md) |
| WhatsApp, IA, fila, modos e handoff | [whatsapp-ai.md](docs/agent-context/whatsapp-ai.md) |
| Admin, autenticação e inbox | [admin.md](docs/agent-context/admin.md) |
| Models, relações e migrations | [data-model.md](docs/agent-context/data-model.md) |
| Testes e seleção de suítes | [testing.md](docs/agent-context/testing.md) |
| Render, Cloudflare e configuração | [deployment.md](docs/agent-context/deployment.md) |
| SEO técnico, sitemap e Search Console | [seo.md](docs/agent-context/seo.md) |
| Decisões arquiteturais duráveis | [decisions.md](docs/agent-context/decisions.md) |

Os documentos funcionais em `docs/` continuam úteis para detalhes de uma entrega.
Use `docs/agent-context/` como índice inicial e siga os links ali indicados.
`AGENTS.md` é o mapa curto, `docs/agent-context/` é a documentação operacional atual e
guias legados em `docs/` são referência histórica quando identificados como tal.

## Efficient context loading

1. Leia este `AGENTS.md`.
2. Identifique a área afetada pela tarefa.
3. Leia apenas os documentos relevantes em `docs/agent-context/`.
4. Leia os arquivos de código indicados nesses documentos.
5. Só faça exploração ampla se encontrar inconsistência ou informação faltante.
6. Não reanalise subsistemas sem relação com a tarefa.
7. Após mudanças arquiteturais, atualize a documentação afetada.

## Regras permanentes

- Nunca versione `.env`, tokens, chaves, passwords, URLs de banco com credenciais ou
  dados pessoais de clientes. Configuração secreta pertence ao backend/ambiente.
- Preserve o frontend vanilla e os ES Modules; só migre de framework sob pedido explícito.
- Reutilize models, services e componentes existentes; não crie domínios paralelos de
  produto, cliente, identidade, conversa, mensagem ou fila.
- Alterações de schema são feitas por migration Alembic. A aplicação não cria tabelas
  automaticamente em produção.
- Routers não devem concentrar regras de negócio; services controlam transações.
- Operações administrativas exigem o Bearer token administrativo existente.
- O WhatsApp usa somente a Cloud API oficial e preserva verificação GET, HMAC do POST,
  validação da conta, idempotência por evento e proteção contra mensagens próprias.
- O AI Agent não fecha vendas, recebe pagamentos, reserva peças nem altera estoque.
- Ferramentas de atendimento da IA permanecem somente leitura.
- `AUTO`, `ASSIST` e `OFF` são modos; `AI`, `WAITING_HUMAN`, `HUMAN` e `CLOSED` são
  estados independentes. Não misture os dois conceitos.
- `HUMAN` e `WAITING_HUMAN` não recebem respostas automáticas do WhatsApp.
- Checkout, preço, estoque e frete são revalidados no backend; dados do browser não são
  autoridade comercial.
- Preserve IDs de idempotência e o tratamento de envios Meta `uncertain`; não reenvie
  automaticamente uma operação externa cuja aceitação seja desconhecida.

## Comandos essenciais

Execute na raiz, salvo quando indicado:

```powershell
backend/venv/Scripts/python.exe -m pytest backend/tests -q
npm.cmd run test:frontend
backend/venv/Scripts/python.exe -m http.server 5500 --directory frontend
```

Execute dentro de `backend/` com o ambiente virtual ativo:

```powershell
python -m uvicorn main:app --host 127.0.0.1 --port 8000 --log-config logging.json
python -m alembic heads
python -m alembic upgrade head
python -m worker --hybrid
python -m worker --hybrid --once
python -m worker --purge-expired
```

Use `TEST_POSTGRES_URL` somente com um banco de teste dedicado para ativar os testes
de concorrência PostgreSQL. Eles nunca devem apontar para produção.

## Política de atualização da documentação

Se uma mudança alterar arquitetura, fluxo, modelo de dados, endpoint, configuração,
deploy ou invariantes descritas em `docs/agent-context`, atualize o documento
correspondente no mesmo trabalho.

Se código e documentação entrarem em conflito, o código é a fonte de verdade. Corrija
a documentação e registre um novo commit verificado quando a revisão for abrangente.
