# Conversa e sugestões de escrita

O agente do Web Chat do site oferece diálogos sem depender de
um modelo externo. O provider configurado continua disponível para planejar buscas
mais complexas; preços, estoque, descrições e políticas vêm do cadastro da loja.
O WhatsApp agora é humano, com uma única saudação fixa e sem uso desse agente.

## O que mudou

- Saudações com perguntas, agradecimentos, despedidas, menu de ajuda, orientação
  para escolher tamanho e ideias gerais de combinação recebem respostas próprias.
- Abreviações como `vc`, `vcs`, `obg`, `vlw` e `pfv` são reconhecidas.
- Erros próximos de palavras conhecidas podem gerar uma sugestão. Exemplo:
  `Tem camissta preta M?` → `Você quis dizer “Tem camiseta preta M?”?`.
  A busca acontece depois de `sim`; `não` descarta a sugestão e pede nova escrita.
  Outra pergunta substitui a confirmação pendente. O histórico mantém o texto original.
- A correção é conservadora: até um erro de letra, inclusive transposição, com um
  único candidato, em mensagens de até 500 caracteres. IDs, links, valores e tamanhos
  não são corrigidos. Palavras distantes ou ambíguas precisam ser reformuladas.
- Perguntas sobre tecido, material e detalhes de uma peça recuperam sua descrição
  cadastrada. Sem descrição, o agente informa a ausência; não deduz composição ou medidas.
- Perguntas curtas como `Quanto custa?`, `Quais cores tem?` e `E G?` aproveitam a
  seleção anterior e consultam o banco novamente. `Começar de novo` limpa os filtros.
- Perguntas distintas do FAQ podem ser respondidas na mesma mensagem. Uma busca de
  produto pode incluir as respostas conhecidas do FAQ, por exemplo `Tem camiseta M?
  Como comprar?`.
- Uma dúvida sem resposta cadastrada oferece atendimento humano e mantém o chat
  disponível. Pedir um atendente ou solicitar uma devolução continua pausando a IA.

## Interação no site

Perguntas diretas como `Tem calça?` e `Tem saia?` consultam o tipo solicitado no
título ou categoria, com estoque e filtros atuais, e respondem antes de listar
produtos: `Sim, encontrei calças disponíveis...` ou `Não encontrei calças disponíveis...`.
Menções na descrição não classificam o tipo de roupa. Trocar de tipo não reutiliza
o produto anterior. Quando não há resultado, outras peças só aparecem depois de
o cliente escolher `Ver outras peças`.

O chat oferece atalhos iniciais e sugestões nas respostas: confirmar a escrita,
consultar compra, buscar outras cores ou começar de novo. `ChatAction` aceita
`human_handoff` e `suggestion`; a segunda envia apenas uma mensagem curta de texto
após o clique. Não há execução de URL ou código em ações.

Atalhos ficam desativados durante envio, retentativa pendente e atendimento humano.
Sugestões de respostas antigas também são desativadas quando a conversa avança,
evitando confirmar uma correção fora de contexto. Essas sugestões são exclusivas do site.

## Publicação e testes

Não há migração, nova dependência ou troca de modelo nesta etapa. Atualize a API
com o contrato de ações antes de publicar o frontend. Não é necessário worker.

Os testes cobrem confirmação/rejeição, isolamento entre sessões, preservação do texto
original, busca com dados atuais, refinamentos, perguntas mistas, limites de ações,
texto seguro no DOM e bloqueio de atalhos antigos ou durante atendimento humano.

Validação desta etapa: **298 testes de backend e 68 de frontend aprovados**.
O frontend foi validado com jsdom; não houve teste visual nem chamada real à Meta
ou ao provider de IA. Os testes usam banco isolado e integrações simuladas.
