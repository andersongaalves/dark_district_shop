# Dark District — frontend

HTML, CSS e JavaScript com ES Modules, sem build e sem dependências de runtime.

## Executar localmente

A partir da raiz do repositório:

```powershell
backend/venv/Scripts/python.exe -m http.server 5500 --directory frontend
```

Abra `http://localhost:5500`. Também é possível servir a raiz do repositório e
acessar `/frontend/`: os links são resolvidos a partir de `js/utils/urls.js`.
Use HTTP para os ES Modules; não abra os HTML diretamente pelo sistema de arquivos.

O backend local deve estar na porta 8000. `js/core/api.js` escolhe ambiente local
para localhost, loopback IPv4 e IPv6, mantendo o endpoint de produção existente.
Não coloque segredos em arquivos do frontend. A configuração Cloudflare continua
em `wrangler.jsonc`, servindo este diretório como assets.

## Responsabilidades

- `js/api/`: acesso à API pública de produtos, sem token administrativo.
- `js/core/`: transporte HTTP e regras puras compartilhadas dos produtos.
- `js/utils/`: URLs, escape de texto/atributos e preços.
- `js/components/`: header, footer e card reutilizáveis.
- `js/sections/`: controllers e renderização das páginas. Produto mantém seus
  módulos de descrição, galeria, opções, disponibilidade e interesse.
- `admin/`: autenticação e chamadas protegidas; `produtos/` contém controller,
  lista, modal, formulário, imagens e variantes. Falhas ao salvar mantêm o modal.
- `admin/configuracoes/`: CRUD compartilhado de categorias e coleções, com controller
  e renderização separados. A navegação por hash dispensa configuração de rotas no host.
- `js/cart/`: controller de operações/validação, estado puro, storage versionado e drawer.
- `css/base/`, `css/components/`, `css/sections/`: fundamentos, componentes e páginas.

Mantenha os nomes portugueses dos módulos de página/Admin existentes; helpers
compartilhados usam os nomes ingleses já adotados. Evite renomear arquivos apenas
para traduzir. Controllers coordenam renderização e serviços, sem dependências
inversas das camadas compartilhadas para páginas ou Admin.

Catálogo, Brechó e Drops usam `catalogo.js` com `data-product-type` e a API única
filtrada. A home consulta `featured=true&available=true` e `is_offer=true&offer_active=true&available=true`,
exibindo até quatro produtos por seleção com o mesmo card.

O ADM permite definir preço promocional e término opcional da oferta, usando o horário
local do navegador e enviando UTC à API. A listagem mostra a primeira imagem entre
título e preço. Cards e página de produto mostram o preço original riscado e o preço
promocional; a oferta expira sem recarregar a página. O carrinho usa `effective_price`
da API nas validações, incluindo a confirmação após uma oferta vencer. Detalhes em
[ofertas com prazo](../docs/ofertas-com-prazo.md).

O carrinho usa `darkDistrictCart:v1` no localStorage, com produto e variante como
identidade. Preço e estoque são consultados novamente na API ao adicionar, alterar
quantidade, abrir/atualizar o drawer e continuar pelo WhatsApp. O carrinho não reserva
estoque nem cria pedidos. Produtos sem variantes usam `available`, pois não possuem
estoque numérico no contrato atual. Categorias/coleções desativadas podem continuar
nos produtos antigos, mas não são oferecidas para novos vínculos.

## Testes

Na raiz, com Node.js 22.22.2+, 24.15.0+ ou 26+:

```powershell
npm.cmd ci
npm.cmd run test:frontend
```

Em outros shells, `npm ci` e `npm run test:frontend`. O jsdom é uma dependência
exclusiva de desenvolvimento para testar formulários, eventos e integração do DOM;
o site continua sem dependências de runtime ou etapa de build. Os testes não
substituem validação visual no navegador.

Consulte [o relatório de catálogo, ADM e carrinho](../docs/catalogo-admin-carrinho.md)
para decisões, limites, cobertura e inventário desta etapa. A
[revisão arquitetural anterior](../docs/revisao-arquitetural.md) é um registro histórico.
