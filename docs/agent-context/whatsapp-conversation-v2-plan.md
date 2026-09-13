# WhatsApp Conversational AI V2 Plan

Status: IN PROGRESS — F2A IMPLEMENTED; F2B–F2G PLANNED

Based on commit: `2c0ac2632d52fd8ab5b77115aa6c1392f333e514`

F2A implementation based on commit: `8efc9760c45072a6081b5ad94aaa37976e3fcf01`

Este documento especifica a evolução incremental. Somente a F2A marcada como
`IMPLEMENTED` está ativa; as demais seções continuam sendo desenho futuro até a fase de
implementação, testes e publicação correspondente. O comportamento atual consolidado
continua documentado em [whatsapp-ai.md](whatsapp-ai.md).

## 1. Problema original

Antes da F2A, o adaptador AUTO tratava algumas respostas genéricas do agente como baixa
confiança por comparação de prefixos do texto. Uma pergunta ambígua como “Como funcionam
os processos?” produzia o esclarecimento genérico do agente, mas o consumer convertia esse
texto em `LOW_CONFIDENCE` e fazia handoff imediato.

Essa política confunde duas situações:

- ambiguidade conversável, que admite uma pergunta curta e resposta multi-turn;
- incapacidade persistente, depois de tentativas orientadas, que exige humano.

O agente já recebia histórico limitado e mantinha `filters`/`product_ids`. A F2A passou a
expressar `CLARIFY` e a última decisão de forma estruturada. Contagem de esclarecimentos e
referências ordinais continuam planejadas para as fases seguintes.

## 2. Objetivos

- Conversar naturalmente e aproveitar mensagens anteriores do ciclo atual.
- Responder quando há informação suficiente e perguntar quando falta uma informação.
- Permitir até duas perguntas de esclarecimento antes de `LOW_CONFIDENCE`.
- Conduzir descoberta e refinamento de produtos reais sem concluir venda.
- Manter regras determinísticas para handoffs claros antes do planejamento por LLM.
- Separar ambiguidade, ausência de resultado, falha técnica e assunto não suportado.
- Manter o webhook curto, a fila durável e as garantias atuais de concorrência.
- Dar ao admin estado suficiente para explicar o que a IA está fazendo.

## 3. Non-goals

- Criar pedido, reserva, pagamento, PIX, desconto ou baixa de estoque.
- Alterar ferramentas de leitura para permitir mutações.
- Usar LLM para toda mensagem ou permitir fatos comerciais em texto livre.
- Enviar histórico completo ou manter memória sem limite entre ciclos.
- Criar event sourcing, nova fila, outro Customer/Conversation ou outro AI Agent.
- Resolver áudio, imagens, documentos, recibos Meta ou canais além de texto nesta fase.
- Implementar frontend, migration ou código de produção neste documento.

## 4. Invariantes

- `AUTO` só envia automaticamente em `status=AI`.
- `WAITING_HUMAN`, `HUMAN` e `CLOSED` bloqueiam respostas AUTO.
- `ASSIST` gera sugestões sob ação humana e nunca envia por conta própria.
- `OFF` não usa IA.
- Pedido explícito de humano e intenções comerciais/sensíveis claras fazem handoff sem
  passar pelo limite de esclarecimento.
- Explicar como comprar é pré-venda; decidir comprar é handoff.
- Produto, preço, estoque, variante e oferta vêm sempre das tools/dados atuais.
- Evento Meta, saudação, retomada, resposta e handoff preservam chaves idempotentes.
- LLM roda fora de transação; finalização revalida job, ciclo, versão, status e modo.
- Mensagens e contexto do cliente são entrada não confiável e não concedem capacidades.

## 5. Modelo de decisão

### Contrato proposto

Criar em `services/whatsapp_ai_service.py` um resultado interno tipado, sem tabela nova:

```text
WhatsAppDecision
  action: ANSWER | CLARIFY | HANDOFF | NO_ACTION
  response: AgentResponse opcional
  handoff_reason: HandoffReason opcional
  reason_code: código interno estável
  context_patch: estado V2 validado e limitado
  failure_kind: opcional, separado da action
  retryable: bool
```

`AgentResponse` continua sendo o conteúdo renderizável. A decisão é a política do canal.
Isso evita usar texto apresentado ao cliente como controle operacional e evita duplicar
o agente compartilhado. Na implementação, o agente precisa devolver um sinal estruturado
de esclarecimento/erro ao adaptador; não se deve testar `message.startswith(...)`.

### Significados

| Decisão | Uso | Efeito |
| --- | --- | --- |
| `ANSWER` | informação suficiente ou resposta de escopo | persiste contexto e enfileira resposta |
| `CLARIFY` | ambiguidade solucionável por conversa | incrementa contador e enfileira pergunta |
| `HANDOFF` | regra obrigatória ou limite atingido | `WAITING_HUMAN`, transição e notificação |
| `NO_ACTION` | job duplicado, obsoleto ou estado que bloqueia AUTO | encerra/cancela job sem mensagem |

Falha técnica é uma dimensão separada. Ela pode causar retry do job e, ao esgotar a
política técnica, `HANDOFF/AI_FAILURE`; nunca deve aparecer como `LOW_CONFIDENCE`.

### Ordem da decisão

1. Validar propriedade do job, ciclo, mensagem mais recente, versão, modo e status.
2. Aplicar regras determinísticas de hard handoff à intenção clara.
3. Se existe esclarecimento pendente, tentar resolver a resposta contra esse estado.
4. Aplicar regras locais/FAQ e detectar slots ou referência contextual suficiente.
5. Usar o LLM apenas para classificação/planejamento que exija linguagem natural.
6. Executar somente tools permitidas e classificar o resultado.
7. Produzir `ANSWER`, `CLARIFY`, `HANDOFF` ou `NO_ACTION` de forma estruturada.
8. Sob lock, revalidar estado e persistir decisão/contexto/outbox atomicamente.

## 6. Clarification flow

### Limite

`MAX_CLARIFICATION_ATTEMPTS = 2` é adequado como constante inicial. Permite uma pergunta
ampla e uma segunda pergunta mais concreta, sem prender o cliente em loop. Não precisa ser
variável de ambiente até existir necessidade operacional comprovada.

O contador representa perguntas de esclarecimento já enviadas no ciclo, não mensagens
recebidas. Falha técnica e pergunta normal de descoberta (“qual tamanho?” após encontrar
produtos) não devem consumir esse orçamento quando a intenção principal já está clara.

### Estado mínimo

Persistir dentro de `Conversation.context["conversation_v2"]`:

```json
{
  "schema_version": 1,
  "clarification": {
    "attempts": 1,
    "kind": "PROCESS_TOPIC",
    "options": ["compra", "entrega", "troca", "atendimento", "catalogo"],
    "source_message_id": "..."
  },
  "focus": {
    "product_ids": [],
    "selected_product_id": null
  },
  "preferences": {},
  "last_decision": {
    "action": "CLARIFY",
    "reason_code": "AMBIGUOUS_PROCESS",
    "source_message_id": "..."
  }
}
```

Não persistir cópias completas das mensagens. O texto já está em `Message`; o estado deve
usar códigos, IDs e filtros validados. Limitar produtos ao máximo já exibido, opções a uma
allowlist e o bloco inteiro a um tamanho pequeno antes de salvar.

### Algoritmo

```text
mensagem ambígua, sem regra de handoff
  -> CLARIFY; attempts=1; pergunta orientada

próxima mensagem
  -> tenta primeiro resolver clarification.kind com histórico/contexto
     -> resolveu: ANSWER ou busca; limpa clarification
     -> não resolveu e attempts < 2: CLARIFY; attempts=2; pergunta mais específica
     -> não resolveu e attempts == 2: HANDOFF/LOW_CONFIDENCE
```

Ao resolver a intenção, iniciar nova busca explícita, fechar conversa, abrir novo ciclo ou
retomar IA, limpar `clarification`. Novo ciclo começa com attempts zero. Handoff técnico
usa `AI_FAILURE`, sem consumir ou falsificar tentativas de compreensão.

Perguntas devem ser curtas, com escolhas relevantes e tom natural. Para “Como funcionam
os processos?”, usar template controlado:

> Claro 🖤 Qual processo você quer conhecer melhor? Posso explicar compra, entrega,
> troca/devolução, atendimento ou como funciona o catálogo da Dark District.

Se a resposta for “Compra”, o estado `PROCESS_TOPIC` determina que é uma escolha de
assunto, não decisão de fechar compra. O FAQ explica o processo e o contador volta a zero.

## 7. Context strategy

### Janela

Manter `CHAT_HISTORY_MESSAGES`, hoje 12, dentro da faixa desejada de 8–15. Selecionar
somente o ciclo atual, com texto limitado como já ocorre. O histórico fornece linguagem;
o bloco V2 fornece memória estruturada e previsível.

### Memória estruturada

- `preferences`: somente `garment`, `style_query`, `size`, `color`, `max_price`,
  `product_type` e `offer_only`, quando explicitamente inferidos/confirmados.
- `focus.product_ids`: ordem dos últimos produtos apresentados, para “a segunda”.
- `focus.selected_product_id`: produto inequivocamente escolhido para consultas seguintes.
- `clarification`: tipo, tentativas, opções e mensagem de origem.
- `last_decision`: ação/código/message ID para observabilidade e inbox.

Não salvar preço, estoque ou objetos completos de produto no contexto: IDs são
reconsultados. Ao mudar claramente de peça/assunto, limpar foco e filtros incompatíveis.
“Começar de novo” limpa preferências, foco e esclarecimento.

### Resumo

Não criar `conversation_summary` na primeira implementação. Doze mensagens do ciclo mais
o estado estruturado cobrem os cenários requeridos com menor risco de resumo desatualizado,
injetado ou contraditório. Reavaliar somente com métricas de conversas longas.

## 8. Product discovery

Descoberta é um fluxo de `ANSWER` e perguntas de slots, não handoff. O planejador deve:

1. extrair filtros explícitos e combinar com preferências compatíveis;
2. perguntar por um discriminador útil quando a consulta é ampla;
3. consultar catálogo real quando houver informação suficiente;
4. preservar a ordem dos IDs apresentados;
5. reconsultar produtos ao pedir preço, estoque, tamanho ou cor;
6. fazer handoff apenas quando o cliente decidir comprar/reservar.

Exemplos:

- “Quero uma camiseta dark até 80 reais” -> pergunta estilo se isso melhorar a busca;
  “Gótico” completa `style_query` -> busca; “preta” e “M” refinam os mesmos filtros.
- “Gostei da segunda” -> resolve o segundo ID de `focus.product_ids`, confirma foco sem
  assumir intenção de compra.
- “Tem essa em M?” -> consulta estoque do foco; “E preta?” preserva produto/tamanho e
  acrescenta cor; “Quanto fica?” consulta preço atual do produto selecionado.
- “Tem outra parecida?” -> busca mesma peça/estilo, exclui da apresentação o foco atual e
  atualiza a ordem dos resultados. Se “essa” apontar para vários produtos, `CLARIFY`.

Perguntas de preferência depois de uma intenção reconhecida são coleta de slots de
descoberta. Podem usar estado `pending_slot`, separado do contador de baixa confiança, para
que uma conversa normal sobre tamanho/cor não consuma as duas tentativas de compreensão.

## 9. Hard handoff rules

Continuar determinístico e anterior ao LLM quando a intenção estiver clara:

| Razão | Exemplos conceituais | Resultado |
| --- | --- | --- |
| `HUMAN_REQUESTED` | “quero falar com uma pessoa” | handoff imediato |
| `PURCHASE_INTENT` | “quero comprar essa”, “vou levar a segunda” | handoff imediato |
| `PAYMENT` | pagar, PIX, chave, cobrança ou confirmação de pagamento | handoff imediato |
| `ORDER_SUPPORT` | pedido existente, cancelamento, acompanhamento | handoff imediato |
| `COMPLAINT` | reclamação, fraude, golpe, defeito sensível | handoff imediato |
| `RETURN_EXCHANGE` | iniciar troca/devolução/reembolso | handoff imediato |
| `NEGOTIATION` | negociar valor ou pedir desconto aplicável | handoff imediato |
| `DELIVERY_ISSUE` | atraso, não recebimento ou problema de entrega | handoff imediato |

A classificação deve considerar frase e contexto, não palavra isolada. “Como funciona a
compra?” e “Compra” como resposta a `PROCESS_TOPIC` são informativos. “Quero comprar essa”
é compromisso claro. “Quero uma camiseta” é descoberta; não é compra concluída.

Pedido explícito de humano nunca recebe tentativa de retenção. `LOW_CONFIDENCE` só ocorre
depois do limite de esclarecimento. `AI_FAILURE` permanece separado e técnico.

## 10. Purchase boundary

A IA pode recomendar, comparar, explicar processo, consultar preço/estoque/tamanho/cor,
refinar preferência e ajudar a escolher. Ela não pode:

- criar ou confirmar pedido;
- reservar produto;
- gerar ou confirmar PIX/pagamento;
- aplicar desconto ou negociar fechamento;
- alterar produto/estoque;
- declarar a venda concluída.

Quando a linguagem muda de descoberta para decisão (“quero comprar”, “pode reservar”,
“vou levar”), a decisão é `HANDOFF/PURCHASE_INTENT`, a conversa vai para
`WAITING_HUMAN`, a transição é enfileirada e o atendente é notificado uma vez.

## 11. AI activation greeting

Em primeiro contato ou novo ciclo, escolher a saudação pelo `ai_mode` capturado no início:

- `AUTO`: saudação automática V2 e `status=AI`;
- `ASSIST` ou `OFF`: saudação humana atual e `status=WAITING_HUMAN`.

Texto recomendado para AUTO:

> 🖤 Olá! Você está falando com o atendimento automático da Dark District.
>
> Posso ajudar a encontrar peças e consultar preços, tamanhos, cores, disponibilidade,
> entrega e outras dúvidas da loja.
>
> Se quiser falar com uma pessoa da equipe, é só pedir.

Reutilizar uma única Message/DeliveryJob de saudação por conversa/ciclo. O payload deve
registrar `greeting_kind=auto|human`; a fila por identidade garante que a saudação saia
antes da primeira resposta/transição do mesmo evento. Não criar `ai_intro_sent`.

## 12. AI resume message

“Retomar IA” deve ser uma transição explícita e idempotente de `WAITING_HUMAN` ou
`HUMAN` para a combinação canônica `AUTO` + `AI`. Quando partir de `HUMAN`/`ASSIST`, modo
e status mudam juntos na mesma transação; `AUTO` + `HUMAN` não vira estado persistente.
Sob lock:

1. confirmar feature ativa e aplicar `ai_mode=AUTO` como parte da retomada explícita;
2. se já estiver em `AI`, retornar sem nova Message/job;
3. incrementar `version`, limpar handoff, falhas, sugestão e esclarecimento pendente;
4. preservar foco/preferências úteis do ciclo;
5. registrar `AI_RESUMED` e enfileirar uma única mensagem com chave baseada em
   conversa, ciclo e versão da transição.

Texto recomendado:

> 🖤 O atendimento automático da Dark District foi retomado.
>
> Posso continuar ajudando com produtos e dúvidas da loja. Se quiser falar com uma
> pessoa da equipe novamente, é só pedir.

O outbox de retomada exige a mesma versão, ciclo, `AUTO` e `AI` antes de enviar. Clique
duplicado ou retry HTTP retorna o resultado atual sem repetir a mensagem.

## 13. State machine

```text
META MESSAGE
    |
    v
persist/deduplicate -> cycle/status/mode gate ---- stale/blocked ---> NO_ACTION
    |
    v
clear hard-handoff rule? ---- yes ----> HANDOFF(reason) -> WAITING_HUMAN
    |
    no
    v
pending clarification? ---- yes ----> resolve against context
    |                                      | understood -> ANSWER/search
    |                                      | unclear, attempts < 2 -> CLARIFY
    |                                      | unclear, attempts == 2 -> LOW_CONFIDENCE
    no
    v
deterministic FAQ/intent/slots sufficient? ---- yes ----> ANSWER or CLARIFY
    |
    no
    v
bounded LLM planning -> allowlisted tools -> structured result
    |                    | valid facts/no results -> ANSWER
    |                    | missing intent/slot -> CLARIFY
    |                    | unsupported -> ANSWER with capability boundary
    |                    | technical failure -> retry; exhausted -> AI_FAILURE
    v
lock + revalidate job/cycle/version/status/mode
    | valid -> persist context/message/outbox atomically
    | changed -> NO_ACTION/cancel
```

Transições operacionais:

```text
new cycle + AUTO              -> AI + AI_ACTIVATED
new cycle + ASSIST/OFF        -> WAITING_HUMAN + human greeting
AI + hard handoff/limit       -> WAITING_HUMAN + AI_HANDOFF
WAITING_HUMAN + claim         -> HUMAN; AUTO becomes ASSIST
active + close                -> CLOSED
WAITING/HUMAN + AUTO + resume -> AI + AI_RESUMED
AI + mode ASSIST/OFF          -> WAITING_HUMAN
CLOSED + new unique message   -> cycle + 1, then rule by mode
```

## 14. ai_mode × status matrix

| Modo | Status | Válida? | AUTO responde? | Sugestão? | Humano | Transições principais |
| --- | --- | --- | --- | --- | --- | --- |
| AUTO | AI | canônica | sim | possível, sem envio humano até claim | não | handoff, close, mudar modo |
| AUTO | WAITING_HUMAN | sim | não | pode preparar; envio exige claim | aguardado | claim, resume, close |
| AUTO | HUMAN | não | não | não | estado inconsistente | converter para ASSIST ou retomar atomicamente em AUTO + AI |
| AUTO | CLOSED | sim, modo retido | não | não | encerrado | nova mensagem abre ciclo em AI |
| ASSIST | AI | não | não | não | necessário | normalizar para WAITING_HUMAN |
| ASSIST | WAITING_HUMAN | sim | não | pode preparar; envio exige claim | aguardado | claim, mudar modo, close |
| ASSIST | HUMAN | canônica | não | sim | atendendo | mudar modo, close |
| ASSIST | CLOSED | sim, modo retido | não | não | encerrado | nova mensagem abre WAITING_HUMAN |
| OFF | AI | não | não | não | necessário | normalizar para WAITING_HUMAN |
| OFF | WAITING_HUMAN | sim | não | não | aguardado | claim, mudar modo, close |
| OFF | HUMAN | sim | não | não | atendendo | mudar modo, close |
| OFF | CLOSED | sim, modo retido | não | não | encerrado | nova mensagem abre WAITING_HUMAN |

Mudar AUTO para ASSIST/OFF enquanto `AI` deve pausar em `WAITING_HUMAN`. Claim de AUTO
continua atômico com a conversão para ASSIST. Resume nunca é implícito ao selecionar AUTO.

## 15. Data model changes proposed

Não é recomendada migration para V2. Usar `Conversation.context`, `Message.metadata`,
`Message`, `DeliveryJob`, `cycle`, `version`, `ai_mode` e `handoff_reason` existentes.

| Candidato | Decisão | Persistência/reset | Justificativa |
| --- | --- | --- | --- |
| `clarification_attempts` | necessário no contexto, sem coluna | persistente; zero ao resolver/resumir/novo ciclo | precisa sobreviver a jobs/restart |
| `last_ai_decision` | necessário no contexto | por ciclo; substituído a cada decisão | leitura barata para inbox |
| `ai_intro_sent` | rejeitado | derivável da Message/job única por ciclo | coluna duplicaria idempotência existente |
| `conversation_summary` | rejeitado inicialmente | não persistir | histórico 12 + estado estruturado bastam |
| `active_product_id` | rejeitado como coluna | `focus.selected_product_id` no contexto | memória conversacional, não domínio relacional |
| `active_product_ids` | usar contexto | por ciclo/busca; IDs limitados | resolve referências/ordem sem dados obsoletos |
| `customer_preferences` | usar contexto allowlisted | por ciclo; limpar em nova busca/ciclo | mantém filtros multi-turn previsíveis |
| `last_ai_decision_detail` | derivar de reason code/tentativas | não salvar texto livre | evita duplicação e conteúdo sensível |

O contexto V2 deve ser validado por schema interno e mesclado por função única; não usar
`dict.update` irrestrito com objetos do provider. `Message.metadata` registra eventos da
mensagem, sem nova tabela.

## 16. Idempotency strategy

- Entrada: manter unicidade `(conversation_id, Meta message_id, customer)` antes de
  incrementar tentativas ou enfileirar qualquer efeito.
- Pergunta/resposta: preservar a chave atual `hybrid:reply:{source_message_id}`; o mesmo
  evento não cria outra.
- Clarification: é uma resposta do source message, com decisão/attempt gravados na mesma
  finalização atômica do outbound.
- Handoff: manter chave por conversa/ciclo/version e `handoff_event`; estado
  `WAITING_HUMAN` impede repetição por mensagens seguintes.
- Saudação: preservar `hybrid:welcome:{conversation_id}:{cycle}`; `greeting_kind` define
  o texto correto.
- Retomada: lock e transição somente se status anterior não era `AI`; chave por
  conversa/ciclo/version da transição.
- Restart: leases recuperam inbound; outbound cuja aceitação seja desconhecida continua
  `uncertain`, sem retry automático.
- Concorrência: antes do LLM capturar cycle/version; depois revalidar ownership, última
  mensagem, cycle, version, mode e status sob lock. Mudança pelo admin cancela resultado.
- Ordem: manter `routing_key` da identidade para saudação, resposta, transição e resume.

## 17. Tool failure behavior

| Classe | Significado | Comportamento |
| --- | --- | --- |
| `NO_RESULTS` | consulta válida sem produtos | `ANSWER`: informar ausência e oferecer ajuste; zero baixa confiança |
| `TEMPORARY_TOOL_FAILURE` | banco/tool indisponível ou exceção transitória | retry técnico limitado; não incrementa clarification |
| `INVALID_QUERY` | argumentos incompletos/inválidos, mas corrigíveis | `CLARIFY` direcionado ao campo necessário |
| `UNSUPPORTED_REQUEST` | pedido claro fora das capacidades | `ANSWER` honesto com escopo e opção de pedir humano |
| produto inexistente | ID/referência não resolve mais | `ANSWER` e pedir nova escolha; limpar foco obsoleto |

Não trocar peça pedida por outra silenciosamente. Resultado vazio é fato válido. Após
falhas técnicas esgotarem `DELIVERY_MAX_ATTEMPTS`, usar `AI_FAILURE`, mensagem segura e
handoff; detalhes internos ficam somente em log sem payload/segredo.

## 18. LLM failure behavior

Timeout, resposta inválida, parser inválido e erro do provider recebem código técnico
estável, `retryable` quando apropriado, e não consomem clarification. O job pode repetir a
geração enquanto ainda possui ownership válido e dentro do limite atual.

Quando houver caminho determinístico suficiente, responder sem LLM. Se não houver e as
tentativas técnicas se esgotarem, usar `HANDOFF/AI_FAILURE`. `LOW_CONFIDENCE` fica
reservado à linguagem ainda incompreensível depois de duas perguntas enviadas.

Não expor nome do provider, stack trace, prompt ou argumentos em mensagens/logs públicos.

## 19. Security

- Manter HMAC sobre bytes originais, WABA/Phone Number ID e filtro de mensagens próprias.
- Manter allowlist de tools e schemas estritos; nenhum estado administrativo vira tool.
- Contexto do cliente não pode alterar `ai_mode`, status, cycle, roles, permissões ou IDs.
- IDs de produto vindos do contexto são apenas referências e sempre são reconsultados.
- System prompt continua tratando mensagem/histórico como conteúdo não confiável.
- Nunca incluir outro Customer, secrets, SQL, filesystem ou comandos no contexto/provider.
- Templates de esclarecimento não repetem instruções maliciosas nem dados internos.
- Limitar textos, histórico, contexto, tools e output como já ocorre.
- Handoff e mudança de status continuam em services sob autenticação/lock, nunca por tool.

## 20. Required tests

### UNIT

- Mapeamento estruturado de `ANSWER`, `CLARIFY`, `HANDOFF`, `NO_ACTION` sem prefixo textual.
- Hard handoff positivo e frases informativas negativas (“como comprar?”).
- Contador 0 -> 1 -> 2 -> LOW_CONFIDENCE e resets.
- Validação/tamanho do contexto V2, preferências, foco e referências ordinais.
- Classificação de NO_RESULTS, INVALID_QUERY, UNSUPPORTED e falhas técnicas/LLM.
- Textos exatos de ativação, saudação humana e retomada.

### INTEGRATION

- Webhook persiste antes de LLM/Meta e enfileira greeting correto por modo.
- Consumer produz decisão, Message e outbound na mesma finalização válida.
- Handoff preserva transição/notificação e ferramentas continuam read-only.
- Resume muda status, limpa temporários e enfileira uma mensagem.
- Respostas list/history expõem modo, status, última decisão, tentativas e motivo.

### MULTI-TURN

- “Como funcionam os processos?” -> CLARIFY; “Compra” -> FAQ/ANSWER, sem handoff.
- Camiseta dark -> pergunta estilo -> gótica -> busca -> até 80 -> refina.
- Produto em foco -> M -> preta -> preço -> outra parecida.
- “Gostei da segunda” resolve a ordem apresentada e reconsulta o produto.
- Nova busca limpa filtros incompatíveis.

### REGRESSION

- “Quero comprar essa” -> PURCHASE_INTENT imediato.
- “Quero falar com uma pessoa” -> HUMAN_REQUESTED imediato, sem LLM.
- PAYMENT, ORDER_SUPPORT, COMPLAINT, RETURN_EXCHANGE, NEGOTIATION e DELIVERY_ISSUE.
- Web Chat mantém comportamento/contrato atual.
- ASSIST nunca envia; OFF não gera; claim AUTO -> ASSIST; CLOSED bloqueia.
- Catálogo vazio responde disponibilidade antes de alternativas.

### IDEMPOTENCY

- Evento duplicado cria uma pergunta, resposta, handoff e notificação no máximo.
- Dois consumers não processam o mesmo inbound/outbound.
- Restart recupera lease sem duplicar envio confirmado.
- Clique duplo/retry em Retomar IA cria uma mensagem.
- Novo ciclo recebe uma saudação, inclusive com webhooks concorrentes.
- Claim/close/mode durante geração cancela o resultado atrasado.

### FRONTEND

- Inbox mostra modo, status, decisão, tentativa 1/2 e detalhe derivado.
- Retomar IA mantém botão ocupado e reconcilia retry sem duplicar.
- ASSIST permite gerar/copiar/usar; envio continua pelo POST humano.
- Layout e timeline funcionam em desktop/mobile e escapam todo conteúdo.

## 21. Implementation phases

### F2A — Contrato de decisão

Status: IMPLEMENTED

Arquivos: `backend/schemas/atendimento.py`, `backend/services/ai_agent.py`,
`backend/services/whatsapp_ai_service.py` e `backend/services/whatsapp_hybrid_service.py`.

Resultado: decisão/códigos estruturados, remoção do controle por prefixo e separação de
falha técnica e ambiguidade. O Web Chat preserva seu contrato público porque os hints do
agente são internos e excluídos da serialização.

### F2B — Clarification e contexto

Status: PLANNED

Arquivos prováveis: `whatsapp_ai_service.py`, `whatsapp_hybrid_service.py` e, se
necessário, `agent_language.py`.

Responsabilidade: schema V2 no JSON, contador, pending clarification, merge/reset e
resolução contextual. Risco: contexto obsoleto ou contador duplo sob concorrência.
Testes: unit, multi-turn, limites, cycle/reset e idempotência.

### F2C — Descoberta e referências de produto

Status: PLANNED

Arquivos prováveis: `ai_agent.py`, `whatsapp_ai_service.py`, `tools/catalog_tools.py`
somente se faltar filtro de leitura.

Responsabilidade: preferências, ordem/foco, slots e reconsulta. Risco: referência errada
ou informação de catálogo vencida. Testes: jornadas multi-turn e revalidação.

### F2D — Saudação por modo e retomada

Status: PLANNED

Arquivos prováveis: `whatsapp_hybrid_service.py`, `conversation_service.py`,
`whatsapp_ai_service.py` e constantes de texto do fluxo WhatsApp.

Responsabilidade: greeting kind, AI_ACTIVATED, AI_RESUMED, reset seletivo e chaves únicas.
Risco: ordem incorreta, saudação dupla ou mensagem após mudança de estado. Testes:
integração, races, restart, CLOSED e clique duplicado.

### F2E — Observabilidade e contrato da inbox

Status: PLANNED

Arquivos prováveis: `whatsapp_inbox_service.py`, `routers/atendimento_admin.py` e schemas
administrativos existentes.

Responsabilidade: metadados/eventos mínimos e campos derivados na resposta. Risco:
exposição de texto/PII ou consultas N+1. Testes: auth, no-store, serialização e paginação.

### F2F — Interface administrativa

Status: PLANNED

Arquivos prováveis: `frontend/admin/atendimento/atendimento.js`, `.css` e
`tests/frontend/inbox.test.mjs`.

Responsabilidade: exibir decisão/tentativas/timeline e UX idempotente de retomada. Risco:
estado de polling atrasado e regressão mobile. Testes: frontend + visual desktop/mobile.

### F2G — Integração, documentação e rollout

Status: PLANNED

Arquivos: suítes WhatsApp/AI/Web Chat, `.env.example` somente se surgir configuração,
`whatsapp-ai.md`, deploy e este plano.

Responsabilidade: cenários completos, concorrência PostgreSQL opcional e ativação gradual.
Risco: comportamento divergente entre SQLite e PostgreSQL/Meta. Testes: suítes completas,
homologação autorizada e rollout inicial com modo padrão seguro.

## 22. Eventos operacionais mínimos

Não criar event table. Usar `Message.metadata` e logs estruturados existentes:

| Evento | Persistir? | Local |
| --- | --- | --- |
| `AI_ACTIVATED` | sim | metadata da saudação assistant |
| `AI_RESUMED` | sim | metadata da mensagem de retomada |
| `AI_ANSWERED` | sim | metadata da resposta assistant |
| `AI_CLARIFICATION_REQUESTED` | sim | metadata da pergunta + attempt/max |
| `AI_HANDOFF` | sim | metadata da transição/system + reason |
| `HUMAN_CLAIMED` | sim | Message system já criada, com metadata estruturada |
| `CONVERSATION_CLOSED` | sim | Message system já criada, com metadata estruturada |
| `AI_TOOL_USED` | log apenas | logger `catalog_tool`, sem argumentos/conteúdo |

`Conversation.context.last_decision` atende a lista da inbox; o histórico detalhado deriva
das Messages. O detalhe de `LOW_CONFIDENCE` é montado por código a partir de reason e
attempts, sem persistir explicação livre: “Não foi possível determinar a intenção após 2
tentativas.”

### Dados para a inbox futura

O backend deve montar o read model administrativo com dados existentes e o bloco V2:

| Campo exibido | Fonte |
| --- | --- |
| Modo IA | `Conversation.ai_mode` |
| Status | `Conversation.status` |
| Última decisão | `context.conversation_v2.last_decision.action` |
| Tentativas | `context.conversation_v2.clarification.attempts` + máximo constante |
| Motivo do handoff | `Conversation.handoff_reason` |
| Detalhe | texto controlado derivado de `reason_code`, motivo e tentativas |

Esses campos podem integrar as respostas existentes de lista/detalhe; não exigem endpoint,
coluna nem texto livre novo. Ausência do bloco V2 representa decisão/tentativas vazias,
mantendo compatibilidade com conversas anteriores.

## 23. Riscos

- Regex ampla pode confundir pesquisa com intenção de compra; exigir frase contextual.
- LLM pode sugerir decisão incorreta; hard handoff e allowlist permanecem no servidor.
- Contexto JSON pode crescer ou ficar inconsistente; schema, allowlist, limite e merge único.
- Mensagens concorrentes podem avançar tentativa duas vezes; lock/version/job ownership.
- Greeting/resume podem ficar fora de ordem; mesma routing key e chaves persistentes.
- Provider indisponível pode aumentar latência/retry; regras locais devem cobrir casos comuns.
- Foco por ordinal pode apontar para resultado antigo; guardar source/ordem e reconsultar ID.
- A inbox pode confundir modo com status; mostrar ambos com rótulos separados.

## 24. Cenários obrigatórios

1. “Como funcionam os processos?” -> `CLARIFY(1/2)` com opções, sem handoff.
2. “Compra” após essa pergunta -> resolve `PROCESS_TOPIC`, consulta FAQ e `ANSWER`; limpa
   clarification, sem interpretar como PURCHASE_INTENT.
3. “Quero uma camiseta dark” -> slot de estilo; “Gótica” -> catálogo; “Até 80” -> refina
   `max_price` preservando peça/estilo.
4. “Tem essa em M?” -> foco + tamanho; “E preta?” -> mantém foco; “Quanto fica?” -> preço
   atual; “Tem outra parecida?” -> busca relacionada.
5. “Quero comprar essa” -> `HANDOFF/PURCHASE_INTENT` imediato.
6. “Quero falar com uma pessoa” -> `HANDOFF/HUMAN_REQUESTED`, sem persuasão/LLM.
7. Três entradas incompreensíveis -> perguntas 1/2 e 2/2; depois
   `HANDOFF/LOW_CONFIDENCE`.
8. `CLOSED` + mensagem única + AUTO -> novo cycle, AI greeting uma vez, status AI e
   processamento normal.
9. `LOW_CONFIDENCE` -> WAITING; Retomar IA -> AI, mensagem de retomada uma vez,
   clarification limpa e próximo turno normal.

## 25. Acceptance criteria

- Os nove cenários obrigatórios passam em testes sem chamadas externas reais.
- Nenhuma mensagem ambígua faz LOW_CONFIDENCE antes de duas perguntas entregues.
- Hard handoffs claros continuam imediatos e não chamam LLM.
- “Como comprar?” explica; “quero comprar” encaminha.
- Multi-turn preserva filtros/foco apenas no ciclo e reconsulta fatos.
- AUTO/ASSIST/OFF e os quatro statuses obedecem à matriz.
- AUTO usa saudação automática; ASSIST/OFF usam saudação humana, uma vez por ciclo.
- Retomar IA é explícito, limpa temporários e envia uma mensagem idempotente.
- Falha técnica usa AI_FAILURE/retry e nunca LOW_CONFIDENCE.
- Duplicatas, restart e races não geram efeito externo repetido confirmado.
- Tools continuam somente leitura e Web Chat não sofre regressão.
- Inbox pode exibir modo, status, decisão, tentativa, razão e detalhe sem nova tabela.
- Suítes backend/frontend e checks de migration passam antes do rollout.
- Documentação atual é atualizada somente quando a V2 for implementada.
