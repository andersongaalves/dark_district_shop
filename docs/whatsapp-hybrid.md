# Atendimento híbrido de WhatsApp

> Documento histórico da implementação híbrida. A fonte operacional atual para IA,
> estados, rollout e testes é [docs/agent-context/whatsapp-ai.md](agent-context/whatsapp-ai.md).

## Arquitetura e permissões

`Meta → webhook HMAC → Message/Conversation + DeliveryJob no PostgreSQL → consumidor → agente existente → outbox → Cloud API`.
O webhook híbrido não chama LLM ou Meta. Saudação, resposta e notificação ficam na
fila persistente. IDs únicos e locks da conversa deduplicam eventos; leases e
`SKIP LOCKED` coordenam consumidores. Só jobs `hybrid:` são consumidos pelo fluxo novo.
O Web Chat mantém seu pipeline. Nenhum modelo de cliente/conversa foi duplicado.

O mesmo `ai_agent` e registro estrito de ferramentas de leitura são reutilizados.
Não há ferramenta de pedido, PIX, pagamento, desconto, reserva, escrita de estoque,
SQL livre, filesystem ou acesso a outros clientes. O LLM escolhe consultas: preços,
estoque e texto comercial são renderizados a partir dos resultados reais.

## Modos e estados

| Modo | Comportamento |
| --- | --- |
| AUTO | Só responde quando o status é AI; HUMAN, WAITING_HUMAN e CLOSED bloqueiam o envio automático |
| ASSIST | Sugestões sob clique na inbox, nunca envio automático ao cliente |
| OFF | Sem geração de respostas ou sugestões |

Modo e status são campos separados. Conversas existentes migram para OFF. O padrão
configurado no ambiente é aplicado apenas a conversas novas. Selecionar AUTO não
retoma conversas humanas: clique **Retomar IA** explicitamente para mudar o status
para AI. Em CLOSED, aguarde novo contato. Assumir muda para HUMAN e converte AUTO
em ASSIST; OFF é preservado. Encerrar muda para CLOSED e invalida trabalho pendente.

## Handoff e compra

Regras determinísticas anteriores ao LLM encaminham compra/reserva, pedido de pessoa,
PIX/pagamento, pedido existente/cancelamento, reclamação, troca/devolução, problema de
entrega e negociação/desconto. A razão usa enum: HUMAN_REQUESTED, PURCHASE_INTENT,
PAYMENT, ORDER_SUPPORT, COMPLAINT, RETURN_EXCHANGE, NEGOTIATION, LOW_CONFIDENCE,
AI_FAILURE ou DELIVERY_ISSUE. Falha de consulta/LLM e ausência de interpretação
confiável também encaminham. Um resultado confiável de catálogo vazio é informado
como indisponibilidade, sem inventar outra peça.

Compra muda para WAITING_HUMAN e envia a transição para finalizar **com um atendente**.
A IA não fecha venda nem altera produtos. Novas mensagens enquanto aguarda apenas
atualizam o histórico; não disparam outro handoff. A inbox evidencia esse estado.

## Ciclos, saudação e contexto

Após CLOSED, uma mensagem nova incrementa `cycle`, limpa contexto temporário e
falhas e enfileira a saudação fixa uma vez. AUTO reabre em AI; ASSIST/OFF reabrem
em WAITING_HUMAN e notificam o atendente. Repetir o mesmo evento da Meta nunca
reabre, incrementa ciclo ou repete saudação. A saudação e a resposta automática
são serializadas pela fila da identidade; podem chegar em sequência.

O contexto é limitado às últimas CHAT_HISTORY_MESSAGES do ciclo atual. Registros
legados sem ciclo só entram no ciclo 1. Sugestões não são geradas a cada polling ou
tecla. O cache dura até 30 segundos e é invalidado por mudanças de contexto; “Gerar
novamente” força consulta. Preço/estoque podem mudar após uma sugestão: o humano
deve conferir antes de usá-la. AUTO revalida os produtos antes de enviar uma resposta
que ficou aguardando na fila.

## Inbox e endpoints

Em `/admin/#atendimento`, a lista e o histórico mantêm paginação e polling. O painel
Assistente IA fica à direita no desktop e é colapsável no mobile. Clique no texto
ou em **Usar resposta** para copiar ao campo. **Enviar agora** usa exatamente o
mesmo POST `/admin/conversations/{id}/messages` com UUID e registro de envio humano.
Assuma a conversa antes de enviar. Não há endpoint paralelo de envio de sugestões.

Novos endpoints, ambos com autenticação administrativa:

- PATCH `/admin/conversations/{id}/ai-mode`: `{"ai_mode":"AUTO|ASSIST|OFF"}`.
- POST `/admin/conversations/{id}/ai-suggestion`: `{"force":false}`.

PATCH `/admin/conversations/{id}` com `{"status":"AI"}` é reutilizado para retomada
explícita; exige AUTO e a funcionalidade ativada. Lista/histórico retornam `ai_mode`,
`handoff_reason` e `cycle`. Clientes não podem alterar esses campos pelo webhook.

## Notificação do atendente

`attendant_notification_service` centraliza o transporte. O destinatário autorizado
vem exclusivamente de WHATSAPP_ATTENDANT_NUMBER. Contém telefone do cliente, motivo,
até 300 caracteres da mensagem relevante e link para a inbox (STOREFRONT_URL).
Configure somente um destinatário autorizado a receber esses dados pessoais.
Não envie notificação ao próprio cliente ou ao número comercial. Mensagens do
atendente não acionam IA/notificações, evitando loops.

Cada handoff tem uma chave única. Mensagens posteriores em WAITING_HUMAN não repetem
a notificação. Novo handoff em outro momento cria outra chave. Se já foi assumido,
encerrado ou substituído por outro ciclo antes do despacho, o aviso antigo é cancelado.

Prefira um template aprovado, idioma configurado, com **quatro parâmetros de corpo**:
cliente, motivo, trecho e URL. Exemplo de texto a submeter à Meta:

```text
Novo atendimento — Dark District
Cliente: {{1}}
Motivo: {{2}}
Mensagem: {{3}}
Painel: {{4}}
Aguardando atendimento humano.
```

O nome/configuração não aprova o template automaticamente. Sem template, texto livre
só é tentado se existir mensagem recente do atendente para este número, dentro da
janela de 24 horas. Caso contrário, o job falha com `attendant_template_required`.
Dados da Meta não são devolvidos ao frontend nem incluídos em logs.
Referência: [Cloud API oficial da Meta](https://www.postman.com/meta/whatsapp-business-platform/documentation/wlk6lh4/whatsapp-cloud-api).

## Deploy

1. No Web Service existente, Root Directory `backend`, aplique
   `python -m alembic upgrade head` **antes** de iniciar a versão nova.
   A migration `e16a345c8f75` adiciona somente `ai_mode`, `cycle` e `handoff_reason`,
   com defaults e CHECK constraints. Downgrade remove os três campos.
2. Preserve DATABASE_URL, SECRET_KEY, variáveis Meta e LLM existentes. Configure:

| Variável | Configuração |
| --- | --- |
| AI_WHATSAPP_ENABLED | true para ativar o híbrido; false mantém o fluxo humano legado |
| WHATSAPP_AI_DEFAULT_MODE | AUTO, ASSIST ou OFF; padrão seguro OFF |
| WHATSAPP_EMBEDDED_CONSUMER | true para consumir no Web Service |
| WHATSAPP_ATTENDANT_NUMBER | número autorizado em dígitos, sem valor real no repositório |
| WHATSAPP_ATTENDANT_TEMPLATE | nome do template aprovado, recomendado |
| WHATSAPP_ATTENDANT_TEMPLATE_LANGUAGE | idioma aprovado, padrão pt_BR |
| STOREFRONT_URL | https://darkdistrict.com.br/ em produção |

3. Build permanece `python -m pip install -r requirements.txt`. Start:
   `python -m uvicorn main:app --host 0.0.0.0 --port $PORT --log-config logging.json`.
   Use pre-deploy para Alembic; se indisponível, execute a migration manualmente antes.
4. Publique o frontend atual, sem framework/build novo. Na inbox, defina modos
   individualmente para conversas existentes. AUTO padrão não altera históricos.

**Não há Background Worker pago obrigatório.** O lifespan inicia um consumidor
limitado no Web Service. Em suspensão/restart, os jobs ficam no PostgreSQL e voltam
quando a instância iniciar. Isso preserva os eventos, mas não garante resposta imediata
enquanto o serviço estiver suspenso. Para disponibilidade contínua, use um processo
sempre ativo; opcionalmente desative WHATSAPP_EMBEDDED_CONSUMER e execute
`python -m worker --hybrid` em infraestrutura própria/worker.

`python -m worker --once` (ou `python -m worker --hybrid --once`) processa um job híbrido
quando a flag está ativa. Encerramento
solicita parada e aguarda o trabalho atual por tempo limitado; leases recuperam jobs
interrompidos. LLM não segura transação. O despacho Meta segura brevemente o lock da
conversa para serializar com assumir/encerrar; essas ações podem aguardar o timeout
HTTP. Uma mensagem já aceita pela Meta não pode ser retirada.

## Falhas e limites

Entradas têm retentativa limitada. Envios externos ambíguos ficam `uncertain` e nunca
são reenviados automaticamente; falhas definitivas ficam `failed`. Conferir DeliveryJob
e logs é necessário para notificações que falharam — não há email/push alternativo.
A fila persiste mensagens pendentes, mas exatamente uma entrega não é garantida pela
API externa. Se houver interrupção entre aceitação e commit, o resultado é incerto.
Os rótulos de envio indicam aceitação da API, não leitura pelo destinatário.

Mensagens de texto são suportadas; áudio, imagem e documentos continuam fora do parser
atual. O modo legado com flag false mantém a regra anterior de saudação única por
conversa: a nova regra por ciclo é ativada com o híbrido. Nenhuma variável real, migration
de produção ou mensagem a clientes foi aplicada durante o desenvolvimento.

## Testes locais

Use banco local de desenvolvimento. Os testes substituem LLM e Meta por mocks e
não usam o PostgreSQL de produção:

```powershell
backend/venv/Scripts/python.exe -m pytest backend/tests -q
npm.cmd run test:frontend
```

No Windows com ACL temporária incompatível, use `--basetemp` com diretório novo e
`-p no:cacheprovider`. TEST_POSTGRES_URL habilita somente testes opcionais em banco
dedicado. Para a interface, suba API local e `python -m http.server 5500 --directory
frontend`; entre em `/admin/#atendimento`. Em teste de integração autorizado, envie
texto ao número comercial: consulta → compra → assumir → encerrar → novo contato.
