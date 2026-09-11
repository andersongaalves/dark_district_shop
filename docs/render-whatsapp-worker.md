# API e worker WhatsApp no Render

Configuração preparada em 11/09/2026. Este guia não cria serviços, não aplica
migrations e não envia mensagens automaticamente.

## Análise do projeto

O fluxo permanece:

```text
Meta webhook → FastAPI → DeliveryJob no PostgreSQL
                                  ↓
                         Background Worker
                                  ↓
                              AI Agent
                                  ↓
                       outbox DeliveryJob
                                  ↓
                        WhatsApp Cloud API
```

- `routers/whatsapp.py` valida assinatura e conta e confirma a persistência antes
  de responder HTTP 200. Não chama o agente nem a Meta.
- `services/delivery_service.py` grava entrada e saída separadas. Um `--once`
  processa no máximo **um job**, não necessariamente uma conversa inteira.
- `worker.py` usa `run_once`, que abre sessões próprias com `database.SessionLocal`.
  API, worker e Alembic importam o mesmo `core.config.settings`.
- `Settings` carrega `DATABASE_URL` e `SECRET_KEY` obrigatórias via
  `pydantic-settings`. Variáveis do processo prevalecem sobre `backend/.env`, cujo
  caminho absoluto é resolvido a partir de `config.py`. Não há banco alternativo
  para o worker, cópia de catálogo ou fila em memória.
- Cada processo tem seu próprio engine/pool, conectado ao **mesmo PostgreSQL**.
  `pool_pre_ping` descarta conexões antigas inválidas antes de reutilizá-las.
- O repositório não tinha `render.yaml`, Dockerfile ou Procfile de backend.
  `compose.yaml` só descreve PostgreSQL local. A configuração do painel Render
  não está versionada; os comandos abaixo são a configuração recomendada.
- Nesta preparação foram acrescentados SIGTERM/SIGINT, finalização do job ativo,
  descarte do pool, validação da configuração, recuperação do loop após falhas
  de banco e logs de início, claim, recuperação e encerramento.

## Configuração exata dos serviços

Use o repositório `andersongaalves/dark_district_shop`, branch `main`, runtime
**Python 3** e a mesma versão de Python utilizada pela API nos dois serviços.
Comece com uma instância de worker. Use a mesma região e rede privada do PostgreSQL
existente. Não crie um segundo banco.

| Campo Render | Web Service existente | Novo Background Worker |
| --- | --- | --- |
| Name | `dark-district-api` | `dark-district-worker` |
| Root Directory | `backend` | `backend` |
| Build Command | `python -m pip install -r requirements.txt` | `python -m pip install -r requirements.txt` |
| Start Command | `python -m uvicorn main:app --host 0.0.0.0 --port $PORT --log-config logging.json` | `python -m worker` |
| Pre-Deploy Command | `python -m alembic upgrade head` (quando disponível no plano) | vazio |
| Auto-Deploy | Off durante a preparação coordenada | Off durante a preparação coordenada |

O worker não é um Web Service: não tem porta, domínio, endpoint de health check
ou comando Uvicorn. Escolha um plano de Background Worker disponível no painel.
Build/Start são relativos a `backend`; não adicione `cd backend` nesses campos.

O Render executa workers continuamente e não encaminha tráfego HTTP para eles.
[Background Workers](https://render.com/docs/background-workers) ·
[Root Directory em monorepos](https://render.com/docs/monorepo-support)

## Variáveis: quais são realmente necessárias

Preferencialmente crie um Environment Group `dark-district-shared` e associe aos
dois serviços, com `DATABASE_URL`, `SECRET_KEY`, `WHATSAPP_ENABLED` e
`WHATSAPP_PHONE_NUMBER_ID`. Preserve os valores atuais da API. Remova divergências
entre definições por serviço e grupo; não gere uma nova SECRET_KEY ao criar o worker.

`DATABASE_URL` deve ser a **mesma Internal Database URL** do PostgreSQL existente,
no formato `postgresql://...`. Se uma URL antiga começar com `postgres://`, use
`postgresql://` mantendo o restante. Use a URL externa apenas fora da rede Render.
Não imprima a URL para comparar serviços e não copie credenciais para este guia.
[Conexões PostgreSQL no Render](https://render.com/docs/postgresql-creating-connecting)

| Variável | API | Worker | Valor/uso |
| --- | --- | --- | --- |
| `DATABASE_URL` | obrigatória | obrigatória | mesmo PostgreSQL, banco e schema; sem SQLite no Render |
| `SECRET_KEY` | obrigatória | obrigatória | mesmo segredo existente; Settings exige também no worker |
| `WHATSAPP_ENABLED` | `true` | `true` | habilita persistência e processamento |
| `WHATSAPP_PHONE_NUMBER_ID` | obrigatória | obrigatória | mesmo ID numérico da Cloud API; não é o telefone de `wa.me` |
| `WHATSAPP_WABA_ID` | obrigatória | dispensável | confere a conta no webhook |
| `WHATSAPP_VERIFY_TOKEN` | obrigatória | dispensável | validação GET do webhook |
| `META_APP_SECRET` | obrigatória | dispensável | assinatura HMAC do POST |
| `WHATSAPP_ACCESS_TOKEN` | dispensável para webhook | obrigatória | token Meta autorizado para enviar pelo número; escolha credencial adequada à operação contínua |
| `WHATSAPP_GRAPH_VERSION` | dispensável para webhook | obrigatória | versão habilitada no aplicativo Meta, formato `vNN.0`; não copiar versão de testes |
| `PYTHONUNBUFFERED` | `1` recomendado | `1` recomendado | saída imediata de logs |
| `STOREFRONT_URL` | manter atual | `https://darkdistrict.com.br/` | links de produtos nas respostas |

Não é necessário fornecer ao worker `PORT`, `CORS_ORIGINS`, credenciais de admin,
`DD_POSTGRES_PASSWORD` ou `SHIPPING_GOOGLE_API_KEY`. Mantenha as configurações de
CORS, autenticação, frete e chat já existentes na API.

### IA e regras compartilhadas

Configure **o mesmo provider/modelo e regras comerciais** na API e no worker para
preservar o comportamento do Web Chat e WhatsApp:

| Variável | Necessidade/default |
| --- | --- |
| `LLM_PROVIDER` | `disabled` funciona sem chave; para o modelo atual use o mesmo `openai_compatible` da API |
| `LLM_API_KEY`, `LLM_MODEL` | obrigatórias se `LLM_PROVIDER=openai_compatible` |
| `LLM_BASE_URL` | manter o mesmo endpoint da API; default `https://api.openai.com/v1` |
| `LLM_TIMEOUT_SECONDS` | `20` |
| `LLM_MAX_OUTPUT_TOKENS` | `600` |
| `LLM_MAX_TOOL_CALLS` | `4` |
| `CHAT_MAX_MESSAGE_LENGTH` | `2000`; alinhar os dois serviços |
| `CHAT_HISTORY_MESSAGES`, `CHAT_MAX_PRODUCTS` | `12`, `5` |
| `CHAT_PROCESSING_LEASE_SECONDS` | `120` |
| `CHAT_RETENTION_DAYS` | `30`, usado por `--purge-expired` |
| `SHIPPING_BASE_METERS`, `SHIPPING_BASE_CENTS`, `SHIPPING_EXTRA_KM_CENTS` | `1900`, `600`, `150`; alinhar se customizados, pois o FAQ usa esses valores |
| `SHIPPING_FREE_MIN_CENTS`, `SHIPPING_FREE_RADIUS_METERS` | `10000`, `7000`; alinhar se customizados |

`CHAT_ENABLED` e os limites de sessão/rate limit do Web Chat controlam as rotas web;
não são a chave de ativação do worker WhatsApp. Desabilitar o LLM mantém respostas
locais de catálogo e FAQ, mas não oferece a mesma compreensão do provider configurado.

### Operação do worker

```dotenv
WORKER_POLL_SECONDS=2
DELIVERY_LEASE_SECONDS=180
DELIVERY_MAX_ATTEMPTS=3
WHATSAPP_HTTP_TIMEOUT_SECONDS=15
PYTHONUNBUFFERED=1
```

Mantenha `DELIVERY_LEASE_SECONDS` maior que o tempo máximo esperado de um job e
`CHAT_PROCESSING_LEASE_SECONDS` maior que a geração esperada da resposta. Não
reduza leases para acelerar a fila: isso pode recuperar processamento ainda ativo.

## Ordem de migrations e publicação manual

1. Disponibilize no Git o código revisado, mantendo Auto-Deploy Off enquanto
   coordena a implantação. Esta preparação não faz commit, push ou deploy.
2. Confira que os dois serviços recebem a mesma `DATABASE_URL`. Tenha backup do
   banco antes de aplicar alterações de schema.
3. **Antes de iniciar o worker**, execute no ambiente da API, com o código novo:

   ```sh
   python -m alembic upgrade head
   python -m alembic current
   python -m alembic heads
   ```

   O schema de atendimento foi criado por `c94e123a6d53`, após `b83d012f5c42`.
   Esta preparação não adiciona migration. `current` deve coincidir com `heads`.
   Não use `stamp head` como substituto de executar migrations.
4. O Pre-Deploy Command da **API somente** pode executar `upgrade head` em planos
   que oferecem esse recurso. Se não houver esse campo, execute manualmente em
   uma sessão controlada com acesso ao banco e código atualizado, antes de iniciar
   os serviços novos. Não coloque migrations nos builds de ambos os serviços nem
   no loop do worker.
5. Publique manualmente a API. Confira as variáveis Meta e o callback
   `https://dark-district-api.onrender.com/webhooks/whatsapp`.
6. Crie/inicie manualmente `dark-district-worker` com a configuração acima.
   Confira `whatsapp_worker_started ... database=postgresql` e ausência de
   `whatsapp_worker_cycle_failed` repetido.
7. Valide o fluxo abaixo antes de liberar a operação. Em mudanças futuras de
   schema, coordene a ordem novamente; não suponha que dois deploys independentes
   executem migrations em sequência.

Pre-deploy é separado do build e está disponível para serviços pagos compatíveis.
[Comandos de deploy](https://render.com/docs/deploys#pre-deploy-command)

## Encerramento no Render

O processo trata SIGTERM e SIGINT: sinaliza parada, termina o job ativo, não busca
outro e descarta o pool. A espera entre consultas ou retentativas é interrompível.
Use `python -m worker` diretamente, sem executar em background com `&` ou combinar
API e worker na mesma linha de Start Command.

O Render espera 30 segundos por padrão e depois usa SIGKILL. Recomenda-se configurar
**`maxShutdownDelaySeconds=180`** para permitir a conclusão de trabalhos em andamento.
Esse campo é configurado pela API do Render ou por Blueprint, não por uma variável
de ambiente. Para um serviço criado manualmente, após obter seu ID `srv-...`, envie
você mesmo um PATCH autorizado a
`https://api.render.com/v1/services/SEU_SERVICE_ID` com JSON:

```json
{"maxShutdownDelaySeconds": 180}
```

Use um token Render no cabeçalho Authorization Bearer por um cliente seguro; não
salve esse token no projeto. Em um Blueprint futuro, o campo equivalente no
serviço é `maxShutdownDelaySeconds: 180`. Nenhuma chamada de alteração do Render
foi executada nesta preparação.

SIGKILL ou indisponibilidade prolongada de banco não permitem garantir finalização
normal; a recuperação por leases continua necessária. Observe os tempos reais
para ajustar o período de encerramento e leases.
[SIGTERM e shutdown delay](https://render.com/docs/deploys#graceful-shutdown)

## Testar `--once` e confirmar o caminho completo

`--once` **não é dry-run**. Pode consumir um job real e enviar uma mensagem real.
Use uma conversa de teste autorizada e, para uma observação determinística, pause
o worker contínuo antes do teste. Não insira payloads fictícios no banco de produção.

1. Envie manualmente uma mensagem de texto, como “Como funciona a compra?”, de um
   destinatário de teste para o número Meta configurado. No modo de teste Meta,
   confirme que o destinatário está habilitado. Callback validado sozinho não
   comprova assinatura do campo `messages` ou vinculação do aplicativo à WABA.
2. Nos logs da API, procure `whatsapp_events_persisted count=1`. `count=0` pode
   significar evento repetido, status de entrega ou mídia ignorada.
3. No PostgreSQL, confira a fila sem exibir texto, telefone ou payload completo:

   ```sql
   SELECT id, kind, status, attempts, available_at, locked_at,
          conversation_id, source_message_id, error_code, created_at
   FROM delivery_jobs
   ORDER BY created_at DESC, id DESC
   LIMIT 20;
   ```

   O novo `inbound` deve estar `pending`, com `attempts=0`. O webhook repetido
   com o mesmo ID Meta não cria outro job, por restrição única de `external_id`.
4. Em `backend`, usando o mesmo ambiente/banco do serviço:

   ```sh
   python -m worker --once
   ```

   Procure `whatsapp_job_claimed ... kind=inbound`, `support_processed` e
   `whatsapp_inbound_processed`. O inbound muda para `sent` (processamento
   concluído) e normalmente aparece um outbound `pending` para a mesma conversa.
   Uma conversa pausada para humano pode não gerar outbound.
5. Execute `python -m worker --once` outra vez. Procure claim `kind=outbound` e
   `whatsapp_job_finished ... status=sent`. Confirme o ID atribuído pela Meta:

   ```sql
   SELECT id, status, attempts, error_code,
          payload ->> 'meta_message_id' AS meta_message_id
   FROM delivery_jobs
   WHERE kind = 'outbound'
   ORDER BY created_at DESC, id DESC
   LIMIT 10;
   ```

   `sent` + `meta_message_id` comprova aceitação pela Cloud API, não entrega ou
   leitura. Confira também a resposta no aparelho de teste. Status de entrega
   recebidos por webhook são ignorados pelo fluxo atual, sem conciliação no banco.
6. Se houver outros jobs, os dois comandos podem processar outras conversas:
   correlacione `job_id`, `conversation_id` e `source_message_id`; não conclua
   sucesso apenas por exit code zero. `processed=false` significa que não havia
   job elegível. Jobs em backoff/processing podem existir mesmo assim.
7. Retome o worker com Start Command `python -m worker` e repita uma mensagem de
   teste, agora sem executar `--once` manualmente.

Para comparar a conexão, execute em uma sessão SQL controlada de cada serviço:

```sql
SELECT current_database(), current_schema(), inet_server_addr(), inet_server_port();
SELECT version_num FROM alembic_version;
```

Confira também a mesma referência de banco no painel. Esses metadados e o mesmo
job visível aos dois processos ajudam a detectar serviço ligado a outro banco.
Não execute o worker local contra a fila de produção apenas para testar a importação.

## Falhas, logs e prevenção de duplicatas

- Claim usa transação curta e `FOR UPDATE SKIP LOCKED` em PostgreSQL. Jobs da mesma
  identidade respeitam o primeiro pendente/em processamento; outras identidades
  podem seguir. O dono do lease é conferido ao concluir.
- IDs únicos de eventos e mensagens, replay de resposta persistida e outbox
  atômica evitam duplicar a resposta quando a Meta repete um webhook ou o worker
  reinicia. Recuperação de inbound pode repetir computação após um crash; não se
  promete execução exatamente uma vez de todo o código externo.
- Erros comprovados de conexão e HTTP 429 recebem retry limitado com backoff
  (10 s, 20 s, até esgotar três tentativas por padrão). HTTP 401/403 falha sem loop
  de retry; confira token, permissões e vínculo do número.
- Read timeout, HTTP 5xx e interrupção durante envio têm resultado ambíguo:
  `uncertain`, sem reenvio automático. Se a Meta aceitou e o banco falhou ao gravar
  o resultado, o lease expirado também leva a `uncertain`. Confira na operação;
  não transforme em `pending` cegamente, pois isso pode duplicar a mensagem.
- Falhas de banco no claim/commit não derrubam o loop. O log
  `whatsapp_worker_cycle_failed error_type=... retry_seconds=...` traz somente a
  classe do erro, sem URL, senha, payload ou traceback sensível. O backoff do
  processo cresce de 2 s até 30 s. `--once` retorna código 1 se o ciclo falhar;
  falhas de job tratadas devem ser avaliadas pelo status persistido.
- `whatsapp_worker_recovered` sinaliza retomada. Erro persistente de tabela/coluna
  geralmente exige conferir migration e banco; erro de conexão exige verificar
  URL/rede/estado do PostgreSQL. Não há migration automática na inicialização.
- `whatsapp_job_ownership_lost` informa que um processo antigo perdeu o lease.
  Não registra falsamente a conclusão. `whatsapp_worker_shutdown_requested` e
  `whatsapp_worker_stopped` confirmam a finalização normal.
- Janela de resposta vencida (24 h), troca de conta ou atendimento humano podem
  cancelar uma saída. O worker não envia campanhas nem templates.

## Testes e limites da verificação

Na raiz, com dependências de desenvolvimento instaladas:

```powershell
$workerTestBase = Join-Path $env:TEMP ('dd-worker-' + [guid]::NewGuid().ToString('N'))
backend/venv/Scripts/python.exe -m pytest backend/tests/test_worker.py backend/tests/test_whatsapp.py backend/tests/test_conversations.py backend/tests/test_migrations.py -q -p no:cacheprovider --basetemp $workerTestBase
```

Cobrem o comando real `python -m worker --once` num subprocesso com banco isolado,
sinais, parada sem novo claim, descarte do pool, backoff e recuperação, logs sem
segredos, configuração, assinatura, deduplicação, leases, falhas Meta simuladas,
falha de banco após aceitação, replay, transações e migrations.

Há ainda `backend/tests/test_delivery_postgres.py` para concorrência real entre
conexões PostgreSQL. Defina **explicitamente** `TEST_POSTGRES_URL` no ambiente com
um banco de homologação dedicado (nunca produção) e execute:

```sh
python -m pytest tests/test_delivery_postgres.py -q
```

Esse comando parte de `backend`. Os testes criam e removem somente schemas próprios
`dd_worker_test_<uuid>`, não usam `DATABASE_URL` como fallback e não chamam a Meta.
Sem essa variável, são pulados. Testes SQLite e compilação SQL não substituem
essa validação de concorrência. Nenhum envio Meta real ou deploy foi feito.
