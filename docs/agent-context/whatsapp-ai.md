# WhatsApp e AI Agent

Last verified against commit: `8c2e52445ac4cfacaca320d3a7986b64a216391e`

Conversational V2:
[whatsapp-conversation-v2-plan.md](whatsapp-conversation-v2-plan.md). F2A–F2E estão
implementadas; F2F–F2G permanecem `PLANNED` e não descrevem comportamento atualmente
implementado.

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
Escolher `AUTO` não muda sozinho o status. “Retomar IA” usa o PATCH de status para `AI`:
sob lock, ativa `AUTO`, limpa esclarecimento e handoff, preserva foco/preferências e
enfileira uma mensagem `AI_RESUMED`. Se já estiver em `AUTO` + `AI`, não repete a transição
nem a mensagem; `CLOSED` rejeita a retomada.

## Entrada, idempotência e ciclo

`resolve_whatsapp` localiza/cria a identidade `phone_number_id:sender`. A combinação
de conversa, ID Meta e sender torna a mensagem idempotente. A conversa é bloqueada
antes de testar duplicidade e mudar ciclo.

Primeiro contato e reabertura enfileiram uma saudação identificada por conversa/ciclo.
`AUTO` usa a saudação que identifica o atendimento automático e reabre em `AI`;
`ASSIST`/`OFF` preservam a saudação humana e reabrem em `WAITING_HUMAN`. A saudação tem
metadados `AI_ACTIVATED`/`HUMAN_GREETING` e é despachada pelo mesmo outbox da conversa,
antes da resposta ao primeiro turno. Se uma conversa `CLOSED` recebe evento novo, `cycle`
incrementa e contexto, falhas e lease da geração anterior são limpos. Repetição do mesmo
evento não reabre nem duplica saudação.

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

Ambiguidade simples produz `CLARIFY` e mantém a conversa em `AI`; o consumer não infere
`LOW_CONFIDENCE` por prefixo da mensagem. A IA pode enviar no máximo duas perguntas de
esclarecimento. Se a entrada seguinte continuar incompreensível, ocorre
`HANDOFF/LOW_CONFIDENCE`. Erros de provider/consulta ou saída inválida continuam como
`AI_FAILURE`. Resultado vazio e confiável do catálogo é respondido como indisponibilidade
e não deve sugerir outra peça como se fosse a pedida.

## Core de decisão conversacional

`whatsapp_ai_service.WhatsAppDecision` valida quatro ações operacionais:

- `ANSWER`: responde com conteúdo factual do `AgentResponse`;
- `CLARIFY`: envia uma pergunta de esclarecimento sem fazer handoff;
- `HANDOFF`: exige um `HandoffReason` válido;
- `NO_ACTION`: não permite resposta nem handoff.

As regras determinísticas produzem `HANDOFF` antes de chamar o agente. O `AgentResponse`
usa hints internos e excluídos da resposta HTTP para sinalizar esclarecimento, mantendo o
contrato do Web Chat. O consumer persiste `conversation_v2.schema_version`,
`conversation_v2.last_decision` e, enquanto necessário, `conversation_v2.clarification`
no JSON existente. Contexto antigo ou vazio continua válido; foco e preferências V2 são
normalizados pelo Context Builder da F2C.

## Estado de clarification

`MAX_CLARIFICATION_ATTEMPTS = 2` fica em `whatsapp_ai_service.py`. A existência do bloco
abaixo significa que há esclarecimento ativo:

```json
{
  "conversation_v2": {
    "schema_version": 1,
    "clarification": {
      "attempts": 1,
      "kind": "PROCESS_TOPIC",
      "options": ["compra", "entrega", "troca_devolucao", "atendimento", "catalogo"],
      "source_message_id": "<id interno da mensagem>"
    },
    "last_decision": {
      "action": "CLARIFY",
      "reason_code": "AMBIGUOUS_PROCESS",
      "source_message_id": "<id interno da mensagem>"
    }
  }
}
```

A primeira ambiguidade grava tentativa 1. Nova resposta ainda ambígua grava tentativa 2
e usa uma pergunta mais orientada. Outra resposta incompreensível mantém o contador em 2,
registra `HANDOFF` como última decisão e muda para `WAITING_HUMAN` com
`LOW_CONFIDENCE`. Respostas allowlisted como “Compra”, “Entrega” ou “Troca” usam o assunto
pendente para formular uma consulta clara e removem `clarification` após `ANSWER`.

Hard handoff remove o esclarecimento antes de preservar sua razão real. Claim, close,
retomada atual para `AI` e mudança para ASSIST/OFF também removem o bloco. Reabertura
zera todo o contexto do ciclo anterior. Mensagens em `WAITING_HUMAN`/`HUMAN`, sugestões
ASSIST, modo OFF, eventos duplicados e jobs sem ownership não consomem tentativas.

## Contexto multi-turn

`whatsapp_ai_service.build_whatsapp_agent_input` é o Context Builder do canal. Ele lê no
máximo 12 mensagens relevantes do ciclo atual, preserva os papéis `customer`, `assistant`
e `human`, exclui mensagens técnicas e respostas ainda não enviadas e limita cada texto.
Mensagens humanas entram como conteúdo de conversa não confiável, nunca como instrução de
sistema. Ciclos anteriores não entram no input; mensagens legadas sem ciclo continuam
aceitas apenas no ciclo 1.

O JSON versionado contém memória operacional do ciclo:

```json
{
  "conversation_v2": {
    "schema_version": 1,
    "focus": {
      "product_ids": ["id-na-ordem-apresentada"],
      "selected_product_id": "id-selecionado-ou-null"
    },
    "preferences": {
      "garment": "camiseta",
      "style_query": "dark",
      "size": "M",
      "color": "preto",
      "max_price": 80.0
    }
  }
}
```

As preferências aceitas são somente `garment`, `style_query`, `size`, `color`,
`max_price`, `product_type` e `offer_only`. Estilos e demais valores passam por allowlist
e validação; objetos do provider não são persistidos livremente. `focus.product_ids`
mantém a ordem apresentada, limitado por `CHAT_MAX_PRODUCTS` (5 por padrão) e por um teto
defensivo de 10 IDs. “Primeira”, “segunda”, “terceira” e “última” selecionam um ID;
“essa”, “aquela” e equivalentes usam o produto já selecionado ou o único apresentado.
Sem referência suficiente, a decisão é `CLARIFY`, sem adivinhar.

Preço, oferta, estoque e variantes não são guardados no contexto. O agente passa apenas
o ID para as tools e reconsulta o catálogo antes de responder. Foco e preferências são
preservados em handoff para ajudar o atendente, mas todo o bloco é limpo quando uma
conversa `CLOSED` inicia novo ciclo. As chaves raiz `filters` e `product_ids` continuam
como espelhos controlados para compatibilidade com F2A/F2B e com o agente compartilhado.

## Descoberta guiada de produtos

F2D usa `preferences` e `focus` da F2C para conduzir a busca sem criar outro estado. Uma
intenção ampla compreendida recebe uma pergunta comercial curta com decisão `ANSWER`:
“Quero camiseta” pergunta tamanho/cor/estilo; “Quero algo gótico” pergunta o tipo de peça.
Essas perguntas não criam nem incrementam `clarification`, que continua reservado para
intenção ou referência realmente incompreensível.

Os filtros suportados são `garment`, busca textual de estilo, tamanho, cor, preço máximo,
tipo de produto e oferta. Filtros explícitos suficientes consultam o catálogo sem nova
pergunta; respostas curtas como “M”, “até 80” e “pode ser G” refinam a mesma busca.
“Não precisa ser preta”, “outras cores”, “outros tamanhos” e “sem limite” removem o filtro
correspondente quando a intenção é clara.

Resultados usam somente produtos reais das tools, são numerados e limitados por
`CHAT_MAX_PRODUCTS` (5 por padrão). A ordem dos IDs apresentada substitui a lista anterior,
portanto “a segunda” sempre se refere ao resultado atual. Se não houver resultado, a IA
permanece em `AI`, informa a ausência e sugere relaxar somente um filtro; não usa
`LOW_CONFIDENCE` nem handoff para ausência de catálogo.

Comparações reconsultam as opções indicadas e descrevem apenas preço, estoque, variantes,
tipo ou outros dados cadastrados. Uma busca por peça parecida exclui o produto selecionado
e reaplica as preferências atuais. Consultas posteriores de preço, promoção, tamanho, cor,
material e estoque usam `selected_product_id` apenas como referência e leem novamente o
catálogo; valores voláteis nunca vêm do histórico.

A descoberta termina antes do fechamento. “Quero comprar”, “vou levar”, reserva, PIX ou
pagamento continuam interceptados pelas regras de hard handoff antes do planejador. Nenhuma
tool de pedido, pagamento, reserva, desconto ou escrita de estoque existe no registry.

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
