# Deploy e configuração

Last verified against commit: `215910f2eb29c90a3fd8d2456d292fb470ae8a05`

Este arquivo documenta nomes e finalidade das variáveis, nunca valores. Credenciais e
dados pessoais pertencem ao gerenciador de ambiente, não ao Git, frontend ou logs.

## Frontend

O conteúdo de `frontend/` é estático e não possui etapa de build. `wrangler.jsonc` aponta
assets para o próprio diretório. A configuração existente publica o domínio da loja via
Cloudflare/Wrangler. `js/core/api.js` aponta browsers públicos para a API Render e usa
loopback no desenvolvimento. Preserve funcionamento na raiz e sob `/frontend/`.

Teste local a partir da raiz:

```powershell
backend/venv/Scripts/python.exe -m http.server 5500 --directory frontend
```

Para validar rotas sem extensão com o runtime Cloudflare, o projeto já documenta
`npx.cmd wrangler@4 dev --local --port 8788` executado em `frontend/`. Não há segredo no
bundle; qualquer chave operacional fica no backend.

## API no Render

Configuração atual documentada:

| Campo | Configuração |
| --- | --- |
| Serviço | Web Service Python existente |
| Root Directory | `backend` |
| Build Command | `python -m pip install -r requirements.txt` |
| Pre-Deploy Command | `python -m alembic upgrade head` |
| Start Command | `python -m uvicorn main:app --host 0.0.0.0 --port $PORT --log-config logging.json` |

Use Pre-Deploy para migrations. Se o plano não oferecer esse campo, aplique `alembic
upgrade head` manualmente no banco correto antes de iniciar código que depende do schema.
Não use `stamp` para pular alterações e não rode `create_all` em produção.

## Grupos de variáveis

Obrigatórias da API:

- `DATABASE_URL`: PostgreSQL da aplicação; contém segredo e não deve ser exibida.
- `SECRET_KEY`: assinatura JWT; preserve/rotacione deliberadamente.
- `ALGORITHM`, `ACCESS_TOKEN_EXPIRE_MINUTES`: parâmetros do JWT.
- `CORS_ORIGINS`: origens públicas permitidas.

Segurança e limites:

- `LOGIN_ATTEMPTS`, `LOGIN_WINDOW_SECONDS`
- `MAX_REQUEST_BODY_BYTES`, `MAX_LOGIN_BODY_BYTES`
- `CHAT_REQUESTS_PER_MINUTE`, `CHAT_GLOBAL_REQUESTS_PER_MINUTE`
- `CHAT_SESSIONS_PER_HOUR`, `CHAT_MAX_MESSAGES_PER_SESSION`

Web Chat/AI compartilhada:

- `CHAT_ENABLED`, `CHAT_SESSION_HOURS`, `CHAT_MAX_MESSAGE_LENGTH`
- `CHAT_HISTORY_MESSAGES`, `CHAT_MAX_PRODUCTS`, `CHAT_PROCESSING_LEASE_SECONDS`
- `CHAT_RETENTION_DAYS`, `STOREFRONT_URL`
- `LLM_PROVIDER`, `LLM_MODEL`, `LLM_API_KEY`, `LLM_BASE_URL`
- `LLM_TIMEOUT_SECONDS`, `LLM_MAX_OUTPUT_TOKENS`, `LLM_MAX_TOOL_CALLS`

WhatsApp Cloud API:

- `WHATSAPP_ENABLED`, `WHATSAPP_VERIFY_TOKEN`, `META_APP_SECRET`
- `WHATSAPP_ACCESS_TOKEN`, `WHATSAPP_PHONE_NUMBER_ID`, `WHATSAPP_WABA_ID`
- `WHATSAPP_BUSINESS_PHONE_NUMBER`, `WHATSAPP_GRAPH_VERSION`
- `WHATSAPP_HTTP_TIMEOUT_SECONDS`

WhatsApp híbrido/notificação:

- `AI_WHATSAPP_ENABLED`, `WHATSAPP_AI_DEFAULT_MODE`
- `WHATSAPP_EMBEDDED_CONSUMER`
- `WHATSAPP_ATTENDANT_NUMBER`
- `WHATSAPP_ATTENDANT_TEMPLATE`, `WHATSAPP_ATTENDANT_TEMPLATE_LANGUAGE`
- `DELIVERY_LEASE_SECONDS`, `DELIVERY_MAX_ATTEMPTS`, `WORKER_POLL_SECONDS`

Frete:

- `SHIPPING_GOOGLE_API_KEY`
- `SHIPPING_ORIGIN_ADDRESS`, `SHIPPING_ORIGIN_LATITUDE`, `SHIPPING_ORIGIN_LONGITUDE`
- `SHIPPING_BASE_METERS`, `SHIPPING_BASE_CENTS`, `SHIPPING_EXTRA_KM_CENTS`
- `SHIPPING_FREE_MIN_CENTS`, `SHIPPING_FREE_RADIUS_METERS`
- `SHIPPING_QUOTE_SECONDS`

Admin inicial: `ADMIN_USERNAME` e `ADMIN_PASSWORD` são lidas apenas por
`create_admin.py`. PostgreSQL local de `compose.yaml` usa `DD_POSTGRES_PASSWORD`.
`PYTHONUNBUFFERED` é recomendado no Render para logs imediatos.

## Consumer e worker

Com `WHATSAPP_ENABLED=true`, `AI_WHATSAPP_ENABLED=true` e
`WHATSAPP_EMBEDDED_CONSUMER=true`, o lifespan do Web Service inicia uma thread por processo.
O startup não espera a fila; falhas de iteração são isoladas e o shutdown sinaliza e aguarda
de forma limitada. Não é obrigatório contratar worker. Se a instância suspender,
mensagens/jobs continuam no PostgreSQL e serão processados na retomada, mas a resposta fica
atrasada.

Para processo sempre ativo separado, desative o consumer embutido e execute, a partir de
`backend/`, `python -m worker --hybrid` com o mesmo `DATABASE_URL` e variáveis Meta/LLM.
Use `python -m worker --hybrid --once` para um job. `--purge-expired` é manutenção de
retenção; não rode em paralelo por engano como start da API.

Consumer embutido e worker externo podem coexistir porque cada job usa claim PostgreSQL,
`SKIP LOCKED`, lease e ownership; a configuração operacional recomendada usa apenas um
modelo para reduzir capacidade ociosa. Réplicas do Web Service podem ter uma thread cada.
Não habilite worker externo com SQLite; produção usa o mesmo PostgreSQL da API.

## Rollout e rollback da IA do WhatsApp

| Estado | Configuração | Resultado |
| --- | --- | --- |
| Canal desligado | `WHATSAPP_ENABLED=false` | webhook indisponível (503) |
| Humano somente | WhatsApp `true`, IA `false` | persiste mensagem, saudação humana, `WAITING_HUMAN`, inbox ativa |
| Infra V2 segura | IA `true`, default `OFF` | V2 disponível, novas conversas sem participação da IA |
| Copiloto | conversa em `HUMAN + ASSIST` | sugestão somente por clique, sem envio automático |
| Automático | conversa/default `AUTO`, status `AI` | greeting e respostas automáticas via outbox |
| Worker externo | embedded `false` | execute `python -m worker --hybrid` |

Ativação gradual recomendada:

1. `AI_WHATSAPP_ENABLED=true`, `WHATSAPP_AI_DEFAULT_MODE=OFF`; valide webhook, inbox e fila.
2. Altere conversas humanas selecionadas para `ASSIST` e valide sugestões.
3. Ative `AUTO` manualmente somente em conversas de teste.
4. Depois da homologação, use `WHATSAPP_AI_DEFAULT_MODE=AUTO` para novos contatos.

Para rollback, defina `AI_WHATSAPP_ENABLED=false` e reinicie/republique API e worker. O
webhook passa ao fluxo humano, novas mensagens permanecem disponíveis na inbox e jobs
híbridos pendentes da identidade são cancelados quando ela escreve novamente. Não reverta
migration, não apague `Conversation.context` e não altere `CHAT_ENABLED`/LLM do Web Chat.
Restaurar a flag retoma a V2 com os dados preservados. O endpoint `/` continua sendo health
básico; flags operacionais ficam em logs/documentação e não são expostas publicamente.

## Ordem de publicação

1. Faça backup/defina janela conforme o risco da migration.
2. Publique código e aplique `python -m alembic upgrade head` no PostgreSQL correto.
3. Confirme `python -m alembic current` e `python -m alembic heads` no mesmo head.
4. Inicie/reinicie a API com as variáveis necessárias.
5. Publique o frontend compatível.
6. Valide health da API, endpoints públicos, admin e integrações autorizadas.

Para WhatsApp híbrido, conversas existentes ficam `OFF`; ative modos conscientemente.
Template de notificação precisa estar aprovado na Meta. Nunca teste com cliente real sem
autorização e nunca cole payloads, telefones ou tokens em logs/documentação.

Referências internas: `docs/whatsapp-hybrid.md`, `docs/render-whatsapp-worker.md`,
`docs/frete.md` e `backend/.env.example`.
