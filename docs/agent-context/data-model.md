# Modelo de dados

Last verified against commit: `215910f2eb29c90a3fd8d2456d292fb470ae8a05`

Last verified Alembic head: `e16a345c8f75`

## Atendimento

Os models ficam em `backend/models/atendimento.py` e são compartilhados entre Web Chat
e WhatsApp.

### Customer

Identidade interna mínima, com UUID e criação. Não contém nome, telefone ou credencial.
Um Customer pode ser referenciado por identidades de canal, mas o código não mescla
clientes por alegações enviadas em mensagem.

### ChannelIdentity

Liga Customer a um identificador verificado. `channel` aceita `web` ou `whatsapp` e a
combinação `(channel, external_id)` é única. Web guarda SHA-256 da credencial aleatória e
expiração; WhatsApp guarda `phone_number_id:sender`.

### Conversation

Uma conversa por identidade (`identity_id` único), ligada ao mesmo Customer e canal.
Campos operacionais:

- `status`: `AI`, `WAITING_HUMAN`, `HUMAN`, `CLOSED`;
- `ai_mode`: `AUTO`, `ASSIST`, `OFF`;
- `cycle`: inteiro a partir de 1;
- `handoff_reason`: enum opcional das razões de atendimento humano;
- `context`: memória JSON limitada pelos services;
- `failure_count`, `version`, `processing_token`, `processing_until`: falha,
  invalidação otimista e lease;
- `updated_at`: ordenação da inbox e retenção.

Modo e status são independentes. O banco aplica CHECKs e `identity_id` evita conversas
paralelas para a mesma identidade.

`context` não é um perfil permanente. No WhatsApp V2, seu bloco versionado
`conversation_v2` guarda somente estado operacional do ciclo: `clarification` (até duas
tentativas), `focus` (IDs apresentados e seleção), `preferences` allowlisted e
`last_decision`. Produtos e fatos voláteis não são copiados para esse JSON: preço,
oferta e estoque são reconsultados. O bloco é compatível com contexto legado, preservado
em handoff quando útil ao humano e limpo quando um novo ciclo começa.

### Message

Registra sender (`customer`, `assistant`, `human`, `system`), texto, metadados de canal,
resposta estruturada e timestamps. `(conversation_id, external_id, sender)` é único.
`metadata` pode guardar ciclo, timestamp Meta, status de entrega, ID externo ou erro.
O índice de histórico usa conversa, criação e ID.

### DeliveryJob

Fila persistente WhatsApp para `inbound`/`outbound`. `external_id` único deduplica jobs;
`routing_key` preserva ordem por identidade. Estados: `pending`, `processing`, `sent`,
`failed`, `uncertain`, `cancelled`. Attempts, disponibilidade e lock suportam lease/retry.
Jobs híbridos usam prefixo `hybrid:` e apontam opcionalmente para conversa/mensagem.

## Catálogo

### Produto

`backend/models/produto.py`. ID textual, título, descrição, preço original, tipo
(`catalogo`, `brecho`, `drop`), categoria obrigatória, coleção opcional, gênero,
disponibilidade e destaque. Oferta combina `is_offer`, `offer_price` menor que `price` e
`offer_ends_at`; `effective_price` só usa a promoção enquanto ativa.

Imagens são filhos com cascade delete-orphan e ordem estável. Variantes são filhos com
tamanho/cor opcionais e quantidade. Produto sem variante usa `available` como autoridade.

### Category e Collection

`backend/models/catalog.py`. Nome e slug únicos, ativo e timestamps. Collection acrescenta
descrição opcional. Produto referencia ambos com `RESTRICT`; categoria é obrigatória.
O campo textual `Produto.category` permanece como rótulo de compatibilidade; a identidade
é `category_id`.

## Usuário administrativo

`backend/models/usuario.py`. ID inteiro, username único, hash bcrypt, flag `active` e
criação. Password em texto e token JWT nunca são persistidos nesse model.

## Migrations

Sequência linear atual:

```text
fc910ce70e6d  initial tables
  -> a72c901e4b31  catálogo relacional/tipos
  -> b83d012f5c42  ofertas com preço e prazo
  -> c94e123a6d53  atendimento multicanal
  -> d05f234b7e64  inbox/status CLOSED
  -> e16a345c8f75  ai_mode/cycle/handoff_reason
```

`backend/alembic/env.py` importa todos os models e usa a URL de `settings`. A aplicação
não chama `Base.metadata.create_all`; isso aparece apenas em testes isolados. Ao alterar
model, crie migration, teste upgrade/downgrade quando aplicável e confirme `alembic heads`.
