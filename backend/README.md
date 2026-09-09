# Dark District — backend

FastAPI, SQLAlchemy, PostgreSQL e Alembic. Execute os comandos deste documento
a partir de `backend/`, com o ambiente virtual ativado.

```powershell
python -m pip install -r requirements-dev.txt
python -m uvicorn main:app --host 127.0.0.1 --port 8000
```

`requirements.txt` contém as dependências da aplicação; `requirements-dev.txt`
adiciona as ferramentas utilizadas pelos testes existentes.

## Configuração

Defina `DATABASE_URL` e `SECRET_KEY` no ambiente ou no arquivo local ignorado
`backend/.env`. O caminho do `.env` independe do diretório de execução.
Valores do ambiente têm precedência. Não versione credenciais.

`ALGORITHM` e `ACCESS_TOKEN_EXPIRE_MINUTES` mantêm seus defaults existentes.
`CORS_ORIGINS` aceita uma lista JSON no ambiente para permitir outras origens;
os defaults de produção e desenvolvimento foram preservados, incluindo loopback IPv6.

`create_admin.py` continua exigindo `ADMIN_USERNAME` e `ADMIN_PASSWORD` no
ambiente do processo. Não há credenciais embutidas nem criação automática de usuários.

## Camadas e banco

- `routers/`: contratos HTTP, autenticação das mutações e tradução de erros de domínio.
- `services/`: consultas, atualização das relações e commit/rollback.
- `models/`: mapeamento e relacionamentos; imagens ordenadas por `ordem` e ID.
- `schemas/`: validação/serialização. PUT preserva campos omitidos ou nulos;
  arrays vazios removem imagens/variantes, e `false`/zero são valores válidos.
- `database.py`: engine, sessões e dependência de banco.
- `core/`: configuração e autenticação existentes.

A estratégia oficial de schema continua sendo Alembic. Para um banco previamente
configurado e escolhido pelo operador, aplique migrations com:

```powershell
python -m alembic upgrade head
```

Nenhuma migration nova foi necessária nesta refatoração. O processo da aplicação
não executa `Base.metadata.create_all`; esse recurso só é usado nos bancos
isolados dos testes.

## Validar

```powershell
python -m pytest tests -q
```

Testes de API utilizam SQLite em memória, chave efêmera e foreign keys ativas.
Testes de migration usam um arquivo temporário e compilação PostgreSQL offline.
O fixture `public_client` mantém a autenticação real; `client` substitui apenas o
usuário para testes focados no CRUD. Bancos locais existentes não são usados.
Essa cobertura não substitui uma execução contra PostgreSQL de homologação.
