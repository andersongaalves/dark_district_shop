# WhatsApp humano no Render — somente Web Service

Este guia substitui a preparação anterior de Background Worker. O WhatsApp agora
usa apenas o **Web Service existente `dark-district-api`**. Não é necessário criar
`dark-district-worker` nem contratar Background Worker pago.

## Fluxo atual

```text
Meta webhook → FastAPI → Customer / ChannelIdentity / Conversation / Message
                     → reservar uma única saudação → commit
                     → enviar texto fixo pela WhatsApp Cloud API → registrar resultado

Conversation.status = HUMAN
Próximas mensagens → somente persistência, sem novas respostas automáticas
```

O status HUMAN é gravado junto com a primeira mensagem, antes da chamada externa.
Mesmo se o envio falhar, o contato permanece salvo e o atendimento continua humano.
O webhook mantém validação GET, HMAC-SHA256 sobre os bytes originais, conferência
de WABA e Phone Number ID. Não chama AI Agent, LLM ou ferramentas de catálogo.
O Web Chat mantém sua arquitetura de IA e suas configurações atuais.

A saudação, em `services/whatsapp_human_service.py`, é exatamente:

```text
Olá! 🖤 Recebemos sua mensagem.

Em breve, um atendente da Dark District entrará em contato com você.

Obrigado pela preferência.
Dark District — Vista o seu lado obscuro.
```

## Configuração do serviço existente

| Campo no Render | Valor |
| --- | --- |
| Tipo | Web Service, Python 3 |
| Nome | `dark-district-api` (preservar o existente) |
| Root Directory | `backend` |
| Build Command | `python -m pip install -r requirements.txt` |
| Start Command | `python -m uvicorn main:app --host 0.0.0.0 --port $PORT --log-config logging.json` |
| Pre-Deploy Command, se disponível | `python -m alembic upgrade head` |
| Callback Meta | `https://dark-district-api.onrender.com/webhooks/whatsapp` |

Mantenha o mesmo PostgreSQL e versão de Python da API. `DATABASE_URL` e `SECRET_KEY`
são obrigatórias em `core.config.Settings`. As variáveis de ambiente do Render
prevalecem sobre o arquivo local `backend/.env`. O caminho desse arquivo independe
do diretório de execução. Não há banco ou fila separada para o WhatsApp.

| Variável na API | Uso |
| --- | --- |
| `DATABASE_URL` | PostgreSQL já utilizado pela loja |
| `SECRET_KEY` | preservar o segredo existente da API |
| `WHATSAPP_ENABLED=true` | ativa o webhook |
| `WHATSAPP_VERIFY_TOKEN` | token configurado na validação GET da Meta |
| `META_APP_SECRET` | secret do aplicativo que assina o POST |
| `WHATSAPP_WABA_ID` | conta WhatsApp Business autorizada |
| `WHATSAPP_PHONE_NUMBER_ID` | ID numérico do número Cloud API |
| `WHATSAPP_BUSINESS_PHONE_NUMBER` | telefone da empresa com país e DDD, apenas dígitos; protege contra mensagens próprias |
| `WHATSAPP_ACCESS_TOKEN` | token Meta autorizado para enviar pelo número |
| `WHATSAPP_GRAPH_VERSION` | versão habilitada no aplicativo, formato `vNN.0` |
| `WHATSAPP_HTTP_TIMEOUT_SECONDS=15` | limite de espera HTTP do envio |
| `PYTHONUNBUFFERED=1` | recomendado para logs imediatos |

O telefone da empresa não é o Phone Number ID. O parser também compara o remetente
com `metadata.display_phone_number`, quando fornecido pela Meta, e ignora ecos,
eventos de saída (`smb_message_echoes`) e recibos de entrega. Configure o telefone
explicitamente para cobrir eventos sem `display_phone_number`.

Não remova `LLM_PROVIDER`, `LLM_MODEL`, `LLM_API_KEY`, `LLM_BASE_URL` ou os demais
parâmetros de IA da API: **o site continua usando essas configurações**. O WhatsApp
humano não consulta nenhuma delas. Preserve também CORS, frete, catálogo e autenticação.
`DELIVERY_*` e `WORKER_POLL_SECONDS` são legados e não controlam a saudação.

## Publicar manualmente

1. Disponibilize o código revisado no repositório quando estiver pronto. Esta
   preparação não faz deploy automaticamente.
2. Se chegou a criar/iniciar um worker com a versão antiga, **suspenda-o antes
   da atualização**, para não continuar processando respostas de IA já na fila.
   Não crie um novo Background Worker.
3. Confira as variáveis acima no Web Service existente. Não coloque segredos em
   arquivos versionados, logs ou mensagens.
4. A mudança humana não adiciona migration. Para instalações que ainda não tenham
   as tabelas de atendimento, aplique as migrations existentes primeiro:

   ```sh
   python -m alembic upgrade head
   python -m alembic current
   python -m alembic heads
   ```

   A migration `c94e123a6d53` cria os registros de atendimento. Execute no banco
   correto, com backup e código atualizado. `current` deve coincidir com `heads`.
   Use o Pre-Deploy Command da API quando disponível; caso contrário, execute
   manualmente antes de iniciar a versão nova. Não use `stamp` para pular schema.
5. Publique manualmente somente o Web Service e mantenha o callback Meta no mesmo
   endereço. A inscrição do campo `messages` e a vinculação do aplicativo à WABA
   continuam necessárias; validar o GET não substitui essas configurações.
6. Faça o teste manual autorizado abaixo. Não execute `worker.py` para testar
   envio: ele não é usado por este fluxo.

Os comandos são relativos ao Root Directory configurado.
[Monorepos no Render](https://render.com/docs/monorepo-support) ·
[Build e Pre-deploy](https://render.com/docs/deploys)

## Conferir a saudação e o atendimento humano

Use um contato de teste sem conversa anterior persistida e envie manualmente um
texto ao número da empresa. A resposta fixa deve chegar uma vez. Envie outros
textos: devem aparecer no histórico, sem novas respostas automáticas. Faça a
continuação humana pela ferramenta de atendimento conectada ao número oficial.

Nos logs da API:

- `whatsapp_messages_persisted count=1 greetings=1`: primeiro contato reservado;
- `whatsapp_greeting_finished ... status=sent`: aceitação pela Cloud API;
- mensagens seguintes: `count=1 greetings=0`;
- evento duplicado: `count=0 greetings=0`;
- `whatsapp_greeting_result_unrecorded`: a mensagem foi persistida, mas não foi
  possível salvar o resultado do envio. Não reenviar automaticamente.

No PostgreSQL, sem imprimir texto ou telefone:

```sql
SELECT id, channel, status, created_at, updated_at
FROM conversations WHERE channel = 'whatsapp'
ORDER BY updated_at DESC LIMIT 20;

SELECT id, conversation_id, sender, created_at,
       metadata ->> 'delivery_status' AS delivery_status,
       metadata ->> 'meta_message_id' AS meta_message_id,
       metadata ->> 'error_code' AS error_code
FROM messages
WHERE conversation_id = 'ID_DA_CONVERSA'
ORDER BY created_at, id;
```

Há uma Message `customer` por ID de entrada e uma Message `assistant` reservada
para a saudação. `assistant` aqui identifica automação fixa, não uso de IA.
`sent` indica aceitação pela Meta; confira a entrega no aparelho. Recibos não são
conciliados no banco atualmente. Este fluxo não cria novos `DeliveryJob`.

## Idempotência e falhas

A conversa é bloqueada durante a transação PostgreSQL. A mensagem de entrada e
a reserva da saudação são persistidas com restrições únicas antes de qualquer
envio. Um webhook repetido não envia de novo. A conexão de banco é liberada antes
da chamada à Meta. Os novos textos mantêm HUMAN, inclusive se uma conversa antiga
estava AI; o endpoint administrativo também impede reativar IA para WhatsApp.

Uma conversa corresponde à identidade persistida do contato neste número da
empresa. Não reinicia a saudação por dia, mensagem ou tempo ocioso. Conversas
anteriores com histórico não recebem nova saudação. Se dados forem removidos pela
retenção/exclusão, um contato posterior poderá criar uma conversa nova.

Há **no máximo uma tentativa automática por conversa**. HTTP 429, credencial
inválida, timeout e demais falhas não perdem o texto recebido; ficam registradas
como `failed` ou `uncertain`, sem retry automático. Interrupção depois da reserva
pode deixar `sending` sem confirmação. A equipe deve conferir o atendimento;
é impossível garantir simultaneamente envio externo exatamente uma vez e entrega
garantida quando a aceitação pela Meta é desconhecida.

Eventos mais antigos que a janela de 24 horas são armazenados, mas não recebem
saudação fora da janela. Se uma falha de banco impede persistir a entrada, o POST
falha para permitir retry da Meta. Se apenas o envio falha, o POST retorna sucesso,
pois o conteúdo recebido já está salvo. Não são logados payloads, telefones ou segredos.

`worker.py` permanece como utilitário de manutenção. `python -m worker` e
`python -m worker --once` encerram com `whatsapp_worker_not_required`, sem consumir
a fila antiga. `python -m worker --purge-expired` continua removendo dados fora do
prazo de retenção quando executado explicitamente. As rotinas legadas de delivery
ficam preservadas, mas o consumidor padrão não executa IA nem envia saídas antigas.

## Testes

Os testes de WhatsApp usam eventos assinados e Meta simulada; cobrem saudação exata,
eventos duplicados, mensagens consecutivas, contatos distintos, ecos próprios,
falhas de envio/banco, janela de resposta e bloqueio da IA. Os testes do Web Chat
continuam verificando o agente, catálogo, memória e encaminhamento humano.

```powershell
$humanTestBase = Join-Path $env:TEMP ('dd-human-' + [guid]::NewGuid().ToString('N'))
backend/venv/Scripts/python.exe -m pytest backend/tests/test_whatsapp.py backend/tests/test_whatsapp_human.py backend/tests/test_webchat.py backend/tests/test_conversations.py backend/tests/test_worker.py -q -p no:cacheprovider --basetemp $humanTestBase
```

`test_delivery_postgres.py` inclui concorrência de webhooks humanos, reservando uma
única saudação para dois requests simultâneos. Requer `TEST_POSTGRES_URL` explícita
para um PostgreSQL de testes dedicado, cria/remove apenas schemas próprios e nunca
usa `DATABASE_URL` como fallback. Sem essa variável, os testes são pulados.

Nenhuma mensagem real é enviada pelos testes. O projeto não adiciona uma caixa
de entrada visual ou ferramenta de resposta manual: a equipe precisa usar sua
ferramenta humana compatível com o número Cloud API. Não se deve presumir que
todo número Cloud API possa ser usado simultaneamente no app WhatsApp Business.

Validação desta mudança: **363 testes de backend e 75 de frontend aprovados**.
Cinco testes opcionais PostgreSQL foram pulados por falta de `TEST_POSTGRES_URL`;
a concorrência real ainda precisa ser executada em homologação.
