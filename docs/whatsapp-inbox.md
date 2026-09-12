# Inbox de WhatsApp no admin

Acesse `/admin/#atendimento`, entre com o usuário administrativo existente e clique
em **WhatsApp**. O frontend nunca recebe credenciais da Meta. O fluxo usa os mesmos
Customer, ChannelIdentity, Conversation e Message e o mesmo PostgreSQL da API.

## Operação

1. O webhook validado por HMAC persiste a mensagem. No primeiro contato reserva e
   envia a saudação fixa uma única vez; a conversa fica `WAITING_HUMAN`.
2. Abra uma conversa e clique **Assumir atendimento** para mudar para `HUMAN`.
3. Digite e envie a resposta. A API registra a tentativa, envia pela integração
   oficial e registra o resultado no histórico, sem executar IA ou worker.
4. Clique **Encerrar atendimento** para mudar para `CLOSED`.
5. Uma nova mensagem do cliente reabre como `WAITING_HUMAN`. Um evento duplicado não
   reabre a conversa e não repete a saudação. Novas mensagens em `HUMAN` mantêm o estado.

O cliente aparece pelo telefone: não existe campo confiável de nome no modelo atual.
Os filtros são Todas, Aguardando, Em atendimento e Encerradas. Aguardando tem prioridade,
depois Em atendimento; dentro de cada grupo, aparecem primeiro as atualizações recentes.
A lista usa páginas de 50; o histórico carrega as 50 últimas mensagens e permite
consultar as anteriores. O polling ocorre a cada 5 segundos, pausa em abas ocultas e
durante envio, e termina ao sair da tela. Não há WebSocket ou contador de não lidas
neste MVP: “Aguardando” representa uma conversa ainda não assumida, não recibo de leitura.
No mobile, **Voltar** retorna à lista. Rascunhos permanecem apenas na memória da tela.

## API administrativa

Todos os endpoints exigem o Bearer administrativo existente (`get_current_user`),
que valida um usuário ativo; a credencial de visitante do Web Chat não dá acesso.
Respostas da inbox têm `Cache-Control: no-store`.

| Método | URL | Uso |
| --- | --- | --- |
| GET | `/admin/conversations?channel=whatsapp&status=WAITING_HUMAN&limit=50&offset=0` | Lista paginada, status opcional |
| GET | `/admin/conversations/{id}/messages?limit=50&before={message_id}` | Histórico; `before` opcional, da mesma conversa |
| POST | `/admin/conversations/{id}/claim` | Assumir |
| POST | `/admin/conversations/{id}/close` | Encerrar |
| POST | `/admin/conversations/{id}/messages` | Resposta manual |

Lista e histórico ampliam endpoints existentes; claim, close e envio são novos.
O PATCH administrativo existente continua disponível. Listagem sem `channel` e histórico
web preservam o contrato anterior. Não foi necessário um segundo endpoint de detalhe.

Envio requer `{"message_id":"UUID da tentativa", "message":"Texto"}`. Texto é validado,
limitado a 2000 caracteres; somente conversas WhatsApp em `HUMAN` podem ser respondidas.
O destinatário vem da identidade persistida, nunca do body. O phone number ID precisa
corresponder à configuração atual do servidor.

## Falhas e idempotência

A chave UUID é reservada no banco antes da chamada externa. Repetir a mesma chave e
texto consulta o resultado sem reenviar; reutilizar a chave com outro texto retorna 409.
O lock da conversa e a restrição única existente protegem reservas concorrentes no PostgreSQL.
Falha de rede no painel mantém o texto e a chave para consultar/repetir a requisição.
Não há retentativa automática da Meta. `failed` permite uma nova tentativa explícita;
`uncertain` exige conferir a entrega antes de reenviar. Após recarregar/sair da tela,
confira sempre o histórico antes de redigitar uma resposta sem confirmação.

`sent` significa **aceita pela API**, sem afirmar entrega ou leitura. O MVP preserva
o comportamento existente de ignorar recibos de status da Meta. `sending` sem resultado
por mais de dois minutos aparece como incerto; nunca é reenviado automaticamente.
Se a API cair depois do envio, a reserva continua no banco. Não é possível prometer
entrega exatamente uma vez por uma API externa sem idempotência própria.

Respostas livres respeitam a janela de 24 horas da última mensagem do cliente. Fora
dela, a API solicita aguardar uma nova mensagem; envio de templates não faz parte deste MVP.
Referência: [documentação da Meta](https://www.postman.com/meta/whatsapp-business-platform/documentation/wlk6lh4/whatsapp-cloud-api?entity=request-13382743-accf558f-2cde-4c15-8921-8fcb11b375ac).

## Migration e Render

Migration nova: `d05f234b7e64`, posterior a `c94e123a6d53`. Ela somente amplia a CHECK
constraint de status para aceitar `CLOSED`; não cria tabelas ou colunas. Downgrade
converte `CLOSED` em `HUMAN` antes de restaurar a restrição anterior. Conversas antigas
em `HUMAN` permanecem nesse estado até serem encerradas ou alteradas pelo atendente.

No Web Service existente, Root Directory `backend`:

1. Antes de iniciar o código novo, execute `python -m alembic upgrade head` usando
   a mesma `DATABASE_URL` da API (pre-deploy existente ou Shell do Render).
2. Start Command: `python -m uvicorn main:app --host 0.0.0.0 --port $PORT --log-config logging.json`.
3. Mantenha as variáveis de banco, autenticação e Meta descritas em
   [configuração do Render](render-whatsapp-worker.md). Não há variável nova.
4. Publique o frontend existente em `frontend`; não há build obrigatório.
5. Abra `/admin/#atendimento` e valide um contato real apenas quando desejar enviar mensagens.

Se não houver pre-deploy disponível, use como Start Command
`python -m alembic upgrade head && python -m uvicorn main:app --host 0.0.0.0 --port $PORT --log-config logging.json`.
Execute migrations uma única vez por implantação; não inicie múltiplas instâncias migrando juntas.

**Não é necessário criar Background Worker pago.** Webhook, saudação e respostas
manuais rodam no Web Service. `worker.py` continua disponível e o Web Chat continua com IA.

## Teste local

Use banco de desenvolvimento e as configurações locais já documentadas. Em `backend`:

```powershell
python -m alembic upgrade head
python -m uvicorn main:app --host 127.0.0.1 --port 8000 --log-config logging.json
```

Na raiz: `backend/venv/Scripts/python.exe -m http.server 5500 --directory frontend`.
Abra `http://localhost:5500/admin/#atendimento` e faça login. Sem eventos recebidos,
a lista ficará vazia. Para validar sem mensagens reais, execute os testes: eles
criam eventos isolados e substituem a integração Meta por mocks.

```powershell
backend/venv/Scripts/python.exe -m pytest backend/tests -q
npm.cmd run test:frontend
```

Se o diretório temporário padrão do pytest tiver ACL incompatível no Windows, use
`--basetemp` apontando para um novo diretório temporário seu e `-p no:cacheprovider`.
Testes PostgreSQL opcionais exigem `TEST_POSTGRES_URL` de banco exclusivo de testes.
Nunca use o banco de produção para a suíte.

## Arquivos desta implementação

Criados:

- `backend/services/whatsapp_inbox_service.py`
- `backend/alembic/versions/d05f234b7e64_whatsapp_inbox.py`
- `backend/tests/test_whatsapp_inbox.py`
- `frontend/admin/atendimento/atendimento.js`
- `frontend/admin/atendimento/atendimento.css`
- `tests/frontend/inbox.test.mjs`
- `docs/whatsapp-inbox.md`

Alterados:

- `backend/models/atendimento.py`
- `backend/routers/atendimento_admin.py`
- `backend/services/conversation_service.py`
- `backend/services/whatsapp_human_service.py`
- `backend/tests/test_whatsapp.py`
- `backend/tests/test_whatsapp_human.py`
- `backend/tests/test_delivery_postgres.py`
- `backend/tests/test_migrations.py`
- `frontend/admin/admin.js`
- `frontend/admin/index.html`
- `backend/README.md`
- `docs/render-whatsapp-worker.md`
