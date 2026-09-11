# FAQ da Dark District

A página `/pages/faq/index.html`, acessível pelo link FAQ no rodapé, apresenta as
quatro respostas aprovadas: compra pelo fluxo atual do WhatsApp, entrega no endereço
definido, devolução em até 7 dias após o recebimento e atendimento em Juazeiro e região.

## Fonte das respostas

Edite `backend/content/faq.json` para atualizar perguntas e respostas. Cada entrada
tem `id`, `question` e `answer`. Os tópicos são `compra`, `entrega`, `devolucao` e
`atendimento`; IDs repetidos ou campos inválidos são rejeitados. Publique o backend
e reinicie a API após alterações, pois o conteúdo é carregado uma vez por
processo. Não há migração de banco nesta etapa nem edição do FAQ pelo ADM.

O tópico `entrega` recebe também as regras dinâmicas de frete configuradas no backend,
compartilhadas com o cálculo do carrinho. Consulte [configuração do frete](frete.md).
O endpoint público `GET /faq` retorna essa lista sem exigir login ou sessão de chat.
O frontend usa a API e renderiza as respostas como texto, com perguntas expansíveis,
estado de carregamento, opção de tentar novamente e contato com a equipe.

## Uso pela IA

O Web Chat usa o serviço de FAQ. Perguntas comuns são reconhecidas
localmente, inclusive com `LLM_PROVIDER=disabled`. Com provider habilitado, a
ferramenta `consultar_faq` também permite selecionar um tópico ou todos (`topic: null`).
O backend monta a resposta com os textos cadastrados; o modelo não redige novas
políticas. Perguntar sobre o FAQ preserva os filtros e produtos da conversa.
O WhatsApp é exclusivamente humano, com uma única saudação fixa; não consulta o FAQ ou a IA.

Perguntas gerais sobre devolução recebem o prazo cadastrado. Pedidos como “quero
devolver minha peça” e solicitações de atendente continuam encaminhados à equipe.
Uma conversa em atendimento humano permanece pausada para a IA. O FAQ explica a tarifa
e a gratuidade; o valor para um endereço é calculado no formulário do carrinho.
O FAQ não define prazo de entrega, confirma endereços fora da região nem autoriza reembolsos.

## Publicação e verificação

Publique primeiro a API com `content/faq.json`; depois publique
o frontend. A página precisa alcançar o endpoint `/faq` da API configurada em
`frontend/js/core/api.js`. Configurações e migrations anteriores do chat continuam
necessárias para conversar com o agente; o FAQ público funciona sem ativar o chat.

Os testes cobrem conteúdo público, respostas do agente do site, seleção da ferramenta
pelo provider simulado, contexto do catálogo, encaminhamento, carregamento e retentativa
da página e texto seguro no DOM. O frontend é testado com jsdom. O WhatsApp tem
testes separados de saudação única e atendimento humano, sem consulta ao FAQ.
