# WhatsApp e AI Agent

Last verified against commit: `ea2d829128b4335d1fb508b9d147badd8dd50c78`

## Seleção do fluxo

`routers/whatsapp.py` preserva um único webhook. Depois de validar configuração, HMAC,
WABA, Phone Number ID e filtrar ecos/mensagens próprias, ele seleciona:

- `AI_WHATSAPP_ENABLED=false`: `whatsapp_human_service.receive_messages`, saudação fixa
  uma vez por conversa e atendimento humano.
- `AI_WHATSAPP_ENABLED=true`: `whatsapp_hybrid_service.receive_messages`, ciclos,
  modos de IA e fila persistente.

O Web Chat não passa por esses services; continua em `conversation_service` +
`ai_agent`. Não desative o provider do site para controlar o canal WhatsApp.

## Fluxo híbrido

```text
Meta POST
  -> routers/whatsapp.py: HMAC dos bytes originais
  -> channels/whatsapp_channel.py: valida conta e extrai texto
  -> whatsapp_hybrid_service.receive_messages
  -> Customer / ChannelIdentity / Conversation / Message + DeliveryJob (commit)
  -> whatsapp_consumer ou worker opcional
  -> whatsapp_ai_service / ai_agent / tools somente leitura
  -> DeliveryJob de saída
  -> integrations/whatsapp/client.py
  -> WhatsApp Cloud API
```

O webhook não espera LLM nem envio Meta. O lifespan em `whatsapp_consumer.py` inicia
uma thread quando IA e consumer embutido estão ativos. Réplicas coordenam jobs por
leases do PostgreSQL e `SKIP LOCKED`. `worker.py --hybrid` é alternativa separada.

## Modos e estados

Modo e estado são dimensões diferentes:

| `ai_mode` | Contrato |
| --- | --- |
| `AUTO` | pode gerar/enviar somente quando `status=AI` |
| `ASSIST` | apenas sugestão sob clique no admin; nenhum envio automático |
| `OFF` | não gera resposta nem sugestão |

| `status` | Contrato |
| --- | --- |
| `AI` | pipeline automático habilitável por `AUTO` |
| `WAITING_HUMAN` | handoff aberto; AUTO pausado |
| `HUMAN` | atendente assumiu; respostas somente humanas |
| `CLOSED` | ciclo encerrado; trabalho pendente é invalidado |

Assumir uma conversa muda para `HUMAN` e converte `AUTO` em `ASSIST`; `OFF` permanece.
Escolher `AUTO` não muda sozinho o status. “Retomar IA” usa o PATCH de status para `AI`
e só funciona com modo `AUTO` e feature ativa.

## Entrada, idempotência e ciclo

`resolve_whatsapp` localiza/cria a identidade `phone_number_id:sender`. A combinação
de conversa, ID Meta e sender torna a mensagem idempotente. A conversa é bloqueada
antes de testar duplicidade e mudar ciclo.

Primeiro contato e reabertura enfileiram uma saudação identificada por conversa/ciclo.
Se uma conversa `CLOSED` recebe evento novo, `cycle` incrementa, contexto, falhas e lease
da geração anterior são limpos. `AUTO` reabre em `AI`; `ASSIST`/`OFF` reabrem aguardando
humano. Repetição do mesmo evento não reabre nem duplica saudação.

Histórico da IA é limitado ao ciclo atual e a `CHAT_HISTORY_MESSAGES`. Mensagens legadas
sem ciclo entram somente no ciclo 1. Respostas humanas novas registram o ciclo.

## Handoff

`whatsapp_ai_service.reason_for` aplica regras determinísticas antes do LLM. Razões:

- `HUMAN_REQUESTED`
- `PURCHASE_INTENT`
- `PAYMENT`
- `ORDER_SUPPORT`
- `COMPLAINT`
- `RETURN_EXCHANGE`
- `NEGOTIATION`
- `DELIVERY_ISSUE`
- `LOW_CONFIDENCE`
- `AI_FAILURE`

Compra/reserva envia texto de transição para finalizar com atendente. Os demais casos
sensíveis também pausam a IA. Handoff grava `WAITING_HUMAN`, razão, nova versão e uma
chave de evento; mensagens posteriores não repetem transição ou notificação.

`LOW_CONFIDENCE` cobre respostas de esclarecimento consideradas insuficientes no AUTO.
Erros de provider/consulta viram `AI_FAILURE`. Resultado vazio e confiável do catálogo é
respondido como indisponibilidade e não deve sugerir outra peça como se fosse a pedida.

## Notificação do atendente

`attendant_notification_service.py` envia ao número autorizado configurado, nunca ao
cliente ou ao número comercial. O payload contém identificador do cliente, razão, trecho
limitado e URL da inbox. Cada handoff enfileira no máximo uma notificação.

O caminho preferido usa template Meta aprovado com quatro parâmetros. Texto livre só é
possível dentro da janela de 24 horas iniciada pelo atendente. Sem configuração/template
válido, o job falha de forma observável; não há fallback para e-mail ou push.

## AI Agent e tools

`services/ai_agent.py` é compartilhado com o Web Chat. O LLM opcional escolhe chamadas;
o servidor renderiza fatos a partir dos resultados atuais. O registry é uma allowlist:

| Tool | Implementação | Responsabilidade | Tipo |
| --- | --- | --- | --- |
| `buscar_produto` | `tools/catalog_tools.py` | busca por texto/filtros | read-only |
| `listar_produtos` | `tools/catalog_tools.py` | seleção do catálogo | read-only |
| `consultar_estoque` | `tools/catalog_tools.py` | variantes e quantidade | read-only |
| `consultar_preco` | `tools/catalog_tools.py` | preço e oferta vigente | read-only |
| `buscar_por_categoria` | `tools/catalog_tools.py` | filtro de categoria | read-only |
| `buscar_por_tamanho` | `tools/catalog_tools.py` | tamanho com estoque | read-only |
| `buscar_por_cor` | `tools/catalog_tools.py` | cor com estoque | read-only |
| `consultar_faq` | `tools/faq_tools.py` | respostas oficiais | read-only |

Não existe tool mutating registrada. Não adicione pedidos, pagamentos, reservas,
descontos, escrita de estoque, SQL livre ou dados privados a esse registry.

## Sugestões da inbox

`whatsapp_ai_service.suggest` exige autenticação via router, feature ativa, modo diferente
de `OFF` e conversa aberta. Usa lease/versionamento, não segura transação no LLM e mantém
cache de 30 segundos por contexto. Polling e digitação não geram sugestões. “Enviar
agora” usa o endpoint humano normal e seu UUID de idempotência.

## Invariantes

- IA nunca conclui compra, pagamento, reserva ou alteração comercial.
- `HUMAN`, `WAITING_HUMAN` e `CLOSED` bloqueiam envio AUTO.
- Evento Meta duplicado não cria outra Message, ciclo, saudação ou notificação.
- Mensagens da empresa/atendente não podem iniciar loops.
- LLM roda fora de transação; resultado atrasado é descartado por versão/status/modo.
- Outbox revalida estado e dados de produto antes do envio.
- Envio `uncertain` nunca é repetido automaticamente.
- A fila híbrida consome apenas chaves com prefixo `hybrid:`.

## Known current behavior

- O parser aceita somente mensagens de texto; mídia, áudio e documentos são ignorados.
- `sent` significa aceitação pela Cloud API, não leitura; recibos não são conciliados.
- Entradas têm retry limitado. Saídas ambíguas ficam em `uncertain`.
- O consumer embutido pausa quando o Web Service dorme; jobs persistem e retomam depois.
- A chamada Meta segura brevemente lock da conversa para serializar claim/close/mode.
- Conversas existentes receberam `OFF` na migration; o modo padrão vale só para novas.
- Com a feature desligada, continua válido o comportamento legado de saudação única por
  conversa; a regra de novo ciclo pertence ao modo híbrido.

Detalhes operacionais adicionais: `docs/whatsapp-hybrid.md` e
`docs/render-whatsapp-worker.md`.
