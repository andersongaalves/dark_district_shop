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
- `css/base/`, `css/components/`, `css/sections/`: fundamentos, componentes e páginas.

Mantenha os nomes portugueses dos módulos de página/Admin existentes; helpers
compartilhados usam os nomes ingleses já adotados. Evite renomear arquivos apenas
para traduzir. Controllers coordenam renderização e serviços, sem dependências
inversas das camadas compartilhadas para páginas ou Admin.

`featured` continua independente de categoria/disponibilidade e alimenta a home
com até quatro produtos. Brechó e Drops permanecem como “Em breve”; a API ainda
não possui campos `type` ou `offer`.

## Testes

Na raiz, com Node.js 22 ou superior:

```powershell
npm.cmd run test:frontend
```

Em outros shells, `npm run test:frontend`. Não é necessário `npm install`:
os testes utilizam apenas APIs nativas do Node. Os testes de controllers usam
objetos que representam contratos do DOM e não substituem validação visual no navegador.

Consulte [a revisão arquitetural](../docs/revisao-arquitetural.md) para decisões,
limites, cobertura e lista dos arquivos alterados.
