# Decisões arquiteturais

Last verified against commit: `ea2d829128b4335d1fb508b9d147badd8dd50c78`

## Frontend permanece vanilla

Status: Accepted

Decision: manter HTML, CSS e JavaScript com ES Modules e hospedagem estática.

Implications: reutilizar componentes/módulos atuais, sem introduzir framework ou build
para uma mudança localizada; testar caminhos na raiz e sob `/frontend/`.

## PostgreSQL e Alembic são a fonte do schema

Status: Accepted

Decision: produção usa o banco configurado por `DATABASE_URL`; mudanças estruturais usam
migrations Alembic lineares.

Implications: não executar `create_all` no startup, não criar banco/fila paralelos e
manter models e migrations sincronizados.

## Routers delegam regras aos services

Status: Accepted

Decision: HTTP, dependências e contratos ficam nos routers; regras e transações ficam em
services; integrações externas têm módulos próprios.

Implications: novos fluxos devem reutilizar services e erros de domínio, evitando lógica
duplicada no endpoint ou frontend.

## Identidades de atendimento são verificadas por canal

Status: Accepted

Decision: Web usa credencial aleatória com hash; WhatsApp usa conta/número verificados.

Implications: não unir Customers por texto, telefone alegado ou conteúdo de conversa;
preservar unicidade e expiração no banco.

## WhatsApp usa Cloud API oficial

Status: Accepted

Decision: webhook e envio usam a API oficial da Meta, com verificação GET, HMAC no POST,
validação de conta/número e filtro de ecos.

Implications: não substituir por automação de WhatsApp Web; manter idempotência e tratar
aceitação externa ambígua como `uncertain`.

## AI Agent compartilhado, ferramentas somente leitura

Status: Accepted

Decision: Web Chat e WhatsApp híbrido reutilizam `services/ai_agent.py` e o mesmo registry
restrito de catálogo/FAQ.

Implications: respostas factuais vêm do banco/FAQ; não expor escrita comercial, dados
privados, filesystem, SQL livre, pagamento ou pedido como tool do atendimento.

## Modos de IA separados do estado operacional

Status: Accepted

Decision: `AUTO`, `ASSIST`, `OFF` definem automação; `AI`, `WAITING_HUMAN`, `HUMAN`,
`CLOSED` definem a situação da conversa.

Implications: selecionar AUTO não retoma sozinho; assumir converte AUTO em ASSIST;
WAITING/HUMAN/CLOSED bloqueiam respostas automáticas.

## Fechamento comercial permanece humano

Status: Accepted

Decision: intenção de compra, reserva, pagamento e outros assuntos sensíveis fazem
handoff antes de qualquer conclusão pela IA.

Implications: o agente pode consultar produtos/FAQ, mas não promete reserva, recebe PIX,
negocia preço, cria pedido ou altera estoque.

## Fila durável no modo AUTO

Status: Accepted

Decision: webhook persiste Message/Conversation/DeliveryJob e retorna sem aguardar LLM ou
Meta. PostgreSQL coordena consumer embutido ou worker separado.

Implications: leases, versionamento e chaves únicas são invariantes. Suspensão do Web
Service atrasa processamento, sem perder jobs. Envio externo não oferece exatamente uma
vez quando a aceitação é desconhecida.

## Inbox administrativa é o centro humano

Status: Accepted

Decision: claim, close, mensagem manual, modo, retomada e sugestão convergem para
`/admin/#atendimento` e endpoints protegidos existentes.

Implications: “Enviar agora” reutiliza o envio humano idempotente; não criar rota paralela
que contorne histórico, janela Meta ou autenticação.

## Carrinho não é sistema de pedidos

Status: Accepted

Decision: o carrinho persiste seleção local e segue para WhatsApp após revalidações; não
reserva estoque e não há model de Order/Payment.

Implications: backend continua autoridade de produto, preço, estoque e cotação; qualquer
futuro pedido/pagamento exige desenho explícito e migration própria.
