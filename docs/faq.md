# FAQ da Dark District

A página `/pages/faq/index.html`, acessível pelo link FAQ no rodapé, apresenta as
quatro respostas aprovadas: compra pelo fluxo atual do WhatsApp, entrega no endereço
definido, devolução em até 7 dias após o recebimento e atendimento em Juazeiro e região.

## Fonte das respostas

Edite `backend/content/faq.json` para atualizar perguntas e respostas. Cada entrada
tem `id`, `question` e `answer`. Os tópicos são `compra`, `entrega`, `devolucao` e
`atendimento`; IDs repetidos ou campos inválidos são rejeitados. Publique o backend
e reinicie API e worker após alterações, pois o conteúdo é carregado uma vez por
processo. Não há migração de banco nesta etapa nem edição do FAQ pelo ADM.

O endpoint público `GET /faq` retorna essa lista sem exigir login ou sessão de chat.
O frontend usa a API e renderiza as respostas como texto, com perguntas expansíveis,
estado de carregamento, opção de tentar novamente e contato com a equipe.

## Uso pela IA

Web Chat e WhatsApp usam o mesmo serviço de FAQ. Perguntas comuns são reconhecidas
localmente, inclusive com `LLM_PROVIDER=disabled`. Com provider habilitado, a
ferramenta `consultar_faq` também permite selecionar um tópico ou todos (`topic: null`).
O backend monta a resposta com os textos cadastrados; o modelo não redige novas
políticas. Perguntar sobre o FAQ preserva os filtros e produtos da conversa.

Perguntas gerais sobre devolução recebem o prazo cadastrado. Pedidos como “quero
devolver minha peça” e solicitações de atendente continuam encaminhados à equipe.
Uma conversa em atendimento humano permanece pausada para a IA. O FAQ não calcula
frete, define prazo de entrega, confirma endereços fora da região nem autoriza reembolsos.

## Publicação e verificação

Publique primeiro a API com `content/faq.json` e reinicie o worker; depois publique
o frontend. A página precisa alcançar o endpoint `/faq` da API configurada em
`frontend/js/core/api.js`. Configurações e migrations anteriores do chat continuam
necessárias para conversar com o agente; o FAQ público funciona sem ativar o chat.

Os testes cobrem conteúdo público, respostas compartilhadas nos dois canais,
seleção da ferramenta pelo provider simulado, contexto do catálogo, encaminhamento,
webhook com envio simulado, carregamento e retentativa da página e texto seguro no DOM.

Validação concluída: **263 testes de backend e 65 de frontend aprovados**. Os testes
de frontend usam jsdom; a validação visual no navegador integrado continua indisponível
neste ambiente. Nenhuma chamada real ao provider ou à Meta foi feita pelos testes.
