# Revisão de segurança do backend

Revisão local em 09/09/2026, limitada ao backend. Nenhum arquivo do frontend,
credencial existente, registro de banco ou migration foi alterado.

## Correções aplicadas

| Problema | Proteção |
| --- | --- |
| Login revelava usuários desativados e retornava rapidamente para usuários inexistentes | Mesma resposta 401 para credenciais inválidas/contas inativas; verificação de hash também para conta inexistente, reduzindo diferença de tempo. |
| Login sem limitação de tentativas | Até 10 requisições por endereço de cliente em janela de 60 segundos, incluindo formulários inválidos e logins bem-sucedidos. Excesso retorna 429 com `Retry-After`. |
| JWT assinado sem expiração era aceito | `exp` e `sub` obrigatórios; validação de tipos, tamanho e assinatura; tokens inválidos retornam 401. O algoritmo continua fixado pela configuração do servidor. |
| bcrypt truncava senhas após 72 bytes; byte nulo podia gerar erro interno | Senhas acima de 72 bytes UTF-8 ou contendo byte nulo são rejeitadas; hashes inválidos falham de forma fechada. Hashes existentes permanecem intactos. |
| Respostas de login sem controle explícito de cache | `Cache-Control: no-store` e `Pragma: no-cache`, inclusive em erros. |
| Corpos de requisição sem limite na aplicação | Limites antes de interpretar JSON/formulários; verificação do tamanho recebido mesmo sem `Content-Length` ou com tamanho declarado incorreto. |
| Configuração podia exibir valores sensíveis | `SecretStr` para chave e URL do banco, ocultação de entradas nas mensagens padrão de validação e parâmetros SQL ocultos nos logs da engine da aplicação. |
| Entradas incompatíveis com os limites do banco | Tamanhos máximos conforme colunas existentes, limites de inteiros e rejeição de preços infinitos/NaN. Entradas inválidas retornam 422 antes de persistir. |

A resposta específica “Usuário desativado.” foi substituída pela resposta genérica
de credenciais inválidas para evitar enumeração de contas. Login bem-sucedido,
formato de token, rotas e CRUD válido foram preservados. Senhas legadas acima de
72 bytes deixam de ser aceitas: bcrypt anteriormente ignorava seu sufixo. Se houver
uma conta nessa condição, sua redefinição exige ação explícita do responsável.

## Configuração dos limites

Os defaults podem ser ajustados por variáveis de ambiente; todos devem ser positivos.

| Variável | Default |
| --- | --- |
| `LOGIN_ATTEMPTS` | 10 |
| `LOGIN_WINDOW_SECONDS` | 60 segundos |
| `MAX_REQUEST_BODY_BYTES` | 1.048.576 bytes (1 MiB), para POST/PUT/PATCH/DELETE |
| `MAX_LOGIN_BODY_BYTES` | 16.384 bytes (16 KiB), limitado também pelo máximo geral |

O limitador é local a cada processo, com memória limitada a 10.000 endereços e
controle de concorrência. Não armazena senhas/tokens. Reiniciar o processo reinicia
as janelas; múltiplos workers/réplicas têm contadores independentes. Para limites
globais e proteção contra tráfego distribuído, configure também a borda/proxy ou
um armazenamento compartilhado. A aplicação não interpreta `X-Forwarded-For`
diretamente: o endereço vem do ASGI. O servidor deve confiar somente nos proxies
conhecidos; sem essa configuração, clientes podem compartilhar o endereço do proxy.

Os testes cobrem caminho canônico, redirecionamento com barra final e `root_path`.
Limites de tamanho não substituem timeouts e limites de conexões na infraestrutura.

## Pendência: chave de assinatura

A chave no `.env` local ficou abaixo do mínimo de comprimento para o HMAC
configurado. Seu valor não foi exibido nem alterado. A aplicação emite um aviso
sem revelar a chave; não a troca automaticamente nem interrompe a inicialização
por esse motivo. A configuração de produção não foi acessada.

O responsável deve definir uma chave aleatória forte no ambiente apropriado:
HS256 exige ao menos 32 bytes de material de chave, HS384 48 e HS512 64. Comprimento
sozinho não comprova aleatoriedade. Trocar a chave invalida tokens anteriores,
portanto a rotação precisa ser coordenada. Referência: [RFC 7518, seção 3.2](https://www.rfc-editor.org/rfc/rfc7518#section-3.2).

## Dependências

Foram consultadas as versões instaladas de 36 dependências de runtime, incluindo
dependências transitivas, pela [API de vulnerabilidades do PyPI](https://docs.pypi.org/api/json/).
A consulta retornou um aviso: `ecdsa==0.19.2`, associado a
[CVE-2024-23342 / GHSA-wj6h-64fc-37mp](https://github.com/tlsfuzzer/python-ecdsa/security/advisories/GHSA-wj6h-64fc-37mp).
O mantenedor informa que não há versão corrigida e que o problema afeta assinatura,
geração de chaves e ECDH; verificação de assinatura não é afetada.

É uma dependência transitiva de `python-jose`. A configuração local revisada usa
HMAC e o backend selecionado é `cryptography`, inclusive para operações EC. Por
isso, não identifiquei o caminho vulnerável no fluxo atual. O aviso continua
existindo no inventário; não foi suprimido nem foi removida uma dependência
necessária. O [projeto python-jose documenta a preferência por cryptography](https://github.com/mpdavis/python-jose#cryptographic-backends).
Não foram instaladas ou atualizadas dependências nesta revisão.

## Validação e limites da revisão

85 testes de backend passaram, incluindo as regressões existentes de CRUD e
migrations e 37 casos novos de segurança: claims JWT inválidas, algoritmos
divergentes, senhas especiais/longas, enumeração, cache, concorrência do limitador,
limites por chunks, cabeçalhos forjados, ocultação de segredos e validação de dados.
`git diff --check` passou. Testes executados em bancos isolados; migrations
validadas em SQLite temporário e SQL PostgreSQL offline.

Foi necessário usar diretório temporário novo e desativar o cache do pytest nesta
sessão devido às permissões das pastas de cache antigas. Nenhuma pasta de cache
existente foi apagada ou teve suas permissões alteradas. Permanecem avisos de
depreciação das dependências/timestamps, fora deste escopo de segurança.

Não houve pentest em Render, auditoria de TLS/proxy em produção ou leitura dos
bancos existentes. A análise de versões não garante ausência de vulnerabilidades
desconhecidas. As consultas SQL continuam parametrizadas, mutações exigem usuário
autenticado ativo, CORS mantém origens explícitas e a API não busca remotamente as
URLs de imagem armazenadas.

A mitigação de diferença de tempo no login segue o padrão de verificação com hash
substituto mostrado na [documentação do FastAPI](https://fastapi.tiangolo.com/tutorial/security/oauth2-jwt/).
O limite de senha preserva o algoritmo existente e considera o comportamento
documentado pelo [projeto bcrypt](https://github.com/pyca/bcrypt#maximum-password-length).
