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
- `schemas/`: validação/serialização. PUT preserva campos omitidos; `collection_id: null`
  remove a coleção; `offer_price: null` e `offer_ends_at: null` limpam os campos de oferta,
  e `category_id: null` é inválido. Nos demais campos, o comportamento
  anterior de ignorar nulos foi preservado. Arrays vazios removem imagens/variantes;
  `false`/zero são valores válidos. IDs de variantes existentes são preservados.
- `database.py`: engine, sessões e dependência de banco.
- `core/`: configuração e autenticação existentes.

A estratégia oficial de schema continua sendo Alembic. Para um banco previamente
configurado e escolhido pelo operador, aplique migrations com:

```powershell
python -m alembic upgrade head
```

A migration `a72c901e4b31`, após `fc910ce70e6d`, cria categorias/coleções e migra as
categorias textuais, preservando produtos, imagens e variantes. Produtos antigos
recebem `product_type=catalogo`, `is_offer=false` e nenhuma coleção. A aplicação
não executa `Base.metadata.create_all`; esse recurso só é usado em testes isolados.

Publique a migration e o backend de forma coordenada antes do novo frontend:
o backend anterior não preenche a nova FK obrigatória. Detalhes de implantação,
compatibilidade e reversão estão no [relatório desta etapa](../docs/catalogo-admin-carrinho.md).

A migration seguinte, `b83d012f5c42`, adiciona preço promocional e vencimento opcional,
sem alterar preços originais ou ofertas antigas. Consulte [ofertas com prazo](../docs/ofertas-com-prazo.md)
para os novos campos, validações e publicação.

## Produtos, categorias e coleções

`GET /produtos` aceita `product_type` (`catalogo`, `brecho`, `drop`), `category_id`,
`collection_id`, `featured`, `is_offer`, `offer_active` e `available`, combinados por AND.
`is_offer` filtra a configuração; `offer_active` considera também o vencimento.
O CRUD existente de produtos e o endpoint de vendido permanecem disponíveis.

`/categorias` e `/colecoes` oferecem GET/POST na raiz e PATCH/DELETE por ID.
GET aceita `active=true` ou `active=false`; omitir retorna todos. Escritas exigem
o mesmo Bearer token administrativo dos produtos. Exclusão de registros vinculados
retorna 409; desativação preserva os produtos e impede novos vínculos.

O novo ADM envia `category_id`. O campo `category` continua na resposta como nome
sincronizado e é aceito em escritas legadas, convertendo o texto para uma entidade.
Esse caminho está marcado como legado no OpenAPI e pode ser removido numa etapa
futura após a migração de todos os clientes.

## Validar

```powershell
python -m pytest tests -q
```

Testes de API utilizam SQLite em memória, chave efêmera e foreign keys ativas.
Testes de migration usam um arquivo temporário e compilação PostgreSQL offline.
O fixture `public_client` mantém a autenticação real; `client` substitui apenas o
usuário para testes focados no CRUD. Bancos locais existentes não são usados.
Essa cobertura não substitui uma execução contra PostgreSQL de homologação.

## Segurança

Consulte [a revisão de segurança](SECURITY.md) para proteções de autenticação,
limites configuráveis de requisição/login, resultados dos testes e pendências de
chave de assinatura e infraestrutura. Credenciais não devem ser impressas em logs
nem versionadas; a leitura explícita de campos `SecretStr` fica restrita aos pontos
que precisam utilizá-los para assinar/verificar tokens ou conectar ao banco.

## Atendimento multicanal

Para separar API e WhatsApp no Render, siga [o guia de deploy do worker](../docs/render-whatsapp-worker.md),
com comandos dos dois serviços, variáveis, migrations, encerramento e validação da fila.

O cálculo de frete está em `/shipping/quote`, com consulta de CEP e conferência
da cotação em `/shipping/checkout`. Veja [configuração e regras](../docs/frete.md).
É necessário configurar `SHIPPING_GOOGLE_API_KEY` no servidor para calcular trajetos.
Esta funcionalidade não precisa de migration.

O agente também reconhece abreviações, sugere correções com confirmação e mantém
diálogos de ajuda e refinamento. Veja [conversa e sugestões de escrita](../docs/agente-interacao.md).

O FAQ público está em `GET /faq`. A página e o agente usam as respostas de
`content/faq.json` sobre compra, entrega, devolução e região atendida. A ferramenta
`consultar_faq` consulta a mesma fonte. Esta etapa não requer migration; veja
[edição, publicação e funcionamento do FAQ](../docs/faq.md).

O Web Chat e o adapter oficial WhatsApp compartilham `conversation_service`, o
agente, ferramentas de catálogo e o banco existente. A migration `c94e123a6d53`,
após as ofertas, cria identidades, conversas, mensagens e jobs persistentes.

Veja [.env.example](.env.example) e [o guia de atendimento](../docs/agente-multicanal.md)
para execução, API, provider, Meta, worker, retenção e limitações. Para testar buscas
locais, mantenha `LLM_PROVIDER=disabled`; WhatsApp começa desativado. Ativar o provider
requer modelo e chave apenas no backend. Ativar WhatsApp requer credenciais Meta e
um processo separado `python -m worker`. Nenhuma dessas integrações inicia sozinha.

O comando recomendado da API com os logs de atendimento é:

```powershell
python -m uvicorn main:app --host 127.0.0.1 --port 8000 --log-config logging.json
```
