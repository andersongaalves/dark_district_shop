# Backend

Estas regras se aplicam a `backend/`. Leia também o `AGENTS.md` da raiz e o documento
de contexto correspondente à tarefa.

## Camadas

- `main.py` monta a aplicação, middlewares, handlers e routers.
- `routers/` valida contratos HTTP, injeta dependências e traduz erros.
- `services/` contém regras de negócio, consultas e limites transacionais.
- `models/` define o mapeamento SQLAlchemy; `schemas/` define contratos Pydantic.
- `integrations/` encapsula serviços externos; `tools/` expõe consultas permitidas à IA.
- `channels/` converte contratos de canal; não coloque regras comerciais no parser.

Mantenha imports no estilo atual, executado com `backend/` no `PYTHONPATH`. Evite criar
uma segunda instância de engine, sessão ou model para resolver um fluxo existente.

## Banco e transações

- `database.py` é a fonte de `engine`, `SessionLocal`, `Base` e `get_db`.
- `DATABASE_URL` vem de `core.config.settings`; não leia outra variável paralela.
- Faça alterações de schema com uma nova revision em `alembic/versions/`.
- Preserve FKs, CHECKs, índices, unicidade e compatibilidade SQLite/PostgreSQL.
- Não mantenha transação aberta durante LLM. IO Meta só pode ocorrer com a estratégia
  explícita de idempotência/serialização do serviço de WhatsApp.
- Em falhas, faça rollback antes de reutilizar a sessão. Não imprima parâmetros secretos.

## Segurança e atendimento

- Use `get_current_user` para endpoints administrativos.
- Preserve limites de corpo, rate limits e `Cache-Control: no-store` nas rotas privadas.
- Web Chat autentica por credencial aleatória; apenas o hash fica no banco.
- Webhook Meta deve verificar os bytes originais com HMAC antes de interpretar JSON.
- O registry da IA é uma allowlist. Não adicione ferramenta mutating ao atendimento.
- Compra, pagamento, pedido, reclamação, troca, negociação e problemas de entrega no
  WhatsApp devem continuar encaminhando para humano.
- Reserve IDs persistentes antes de IO externo. `uncertain` exige reconciliação humana.

## Validação

Dentro de `backend/`:

```powershell
python -m pytest tests -q
python -m alembic heads
python -m worker --hybrid --once
```

Para model/migration, execute `tests/test_migrations.py`. Para concorrência real, use
`TEST_POSTGRES_URL` de um banco descartável; o fixture cria e remove um schema aleatório.
