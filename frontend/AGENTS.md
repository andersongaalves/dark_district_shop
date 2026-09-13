# Frontend

Estas regras se aplicam a `frontend/`. Leia também o `AGENTS.md` da raiz e o documento
de arquitetura, admin ou testes adequado à tarefa.

## Estrutura e estilo

- HTML, CSS e JavaScript vanilla com ES Modules; não há build nem framework de runtime.
- `js/api/` acessa APIs públicas; `js/core/` contém transporte e regras compartilhadas.
- `js/components/` contém header, footer e cards; `js/sections/` monta páginas.
- `js/cart/` e `js/chat/` separam estado, storage e interface.
- `admin/` concentra autenticação, API protegida, produtos, configurações e inbox.
- Reuse tokens de `css/base/variables.css` e componentes existentes. Preserve a
  identidade visual e teste desktop e mobile quando alterar layout.

Mantenha nomes portugueses já usados em páginas/admin e nomes ingleses dos helpers já
existentes. Não renomeie módulos apenas para uniformizar idioma.

## Contratos e segurança

- `js/core/api.js` é a fonte única da URL da API por ambiente.
- `js/utils/urls.js` centraliza rotas, URL de produto e contato WhatsApp.
- APIs públicas nunca recebem token administrativo.
- `admin/api.js` adiciona o Bearer e encerra a sessão após 401.
- Conteúdo da API e storage é não confiável: renderize como texto ou use os helpers de
  escape existentes. Não aceite `javascript:`, `data:` ou HTML arbitrário em URLs.
- Carrinho não reserva estoque e não cria pedido. Revalide produto, variante, preço e
  frete pelos endpoints existentes antes de continuar pelo WhatsApp.
- Não coloque segredo, chave de Maps, token Meta ou chave LLM no frontend.

## Navegação e testes

O site deve funcionar hospedado na raiz e servido como `/frontend/`. O admin usa hash;
a inbox é `/admin/#atendimento`. Páginas públicas são arquivos estáticos e módulos.

Na raiz:

```powershell
npm.cmd run test:frontend
backend/venv/Scripts/python.exe -m http.server 5500 --directory frontend
```

Atualize os testes de `tests/frontend/` ao mudar contratos, DOM ou eventos. jsdom cobre
comportamento; mudanças visuais relevantes também exigem conferência em navegador.
