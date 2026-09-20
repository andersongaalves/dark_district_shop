# SEO técnico e indexação

Last verified against commit: `675ac1850fcb2ba2ddf54fd5066628373edbfd1e`

## Fonte e domínio canônico

O domínio público canônico é `https://darkdistrict.com.br`. Metadados, dados
estruturados, `robots.txt` e sitemap usam somente esse domínio. A configuração de
redirecionamento de HTTP, `www` e domínios temporários do Cloudflare não fica no
repositório: confirme no painel/DNS que essas variantes redirecionam para o domínio
canônico antes da publicação.

O frontend continua estático em `frontend/`, publicado por Cloudflare/Wrangler. Não há
SSR nem Worker de SEO. As páginas HTML fornecem os metadados institucionais no primeiro
carregamento; a página de produto completa seus metadados depois de consultar a API
pública, mantendo a arquitetura vanilla existente.

## Indexação e URLs

Páginas indexáveis:

- `/`
- `/pages/catalogo/index.html`
- `/pages/brecho/index.html`
- `/pages/drops/index.html`
- `/pages/sobre/index.html`
- `/pages/faq/index.html`
- `/politica-de-privacidade`
- `/pages/produto/index.html?id=<id-do-produto>` para produtos públicos disponíveis.

O ID é a identidade estável do produto. `getProductUrl()` continua sendo a única fonte
de URLs navegáveis no frontend; não há slug, campo novo ou segundo formato de rota. A
URL canônica de produto contém somente `id`, portanto parâmetros de campanha e filtros
não se tornam canônicos nem entram no sitemap.

`/admin/` e `/admin/login/` usam `noindex,nofollow,noarchive`, não entram no sitemap e
são bloqueados para crawling em `robots.txt`. Isso não substitui a autenticação da API.
API, webhook e outros endpoints técnicos também não entram no sitemap.

## Metadados e dados estruturados

As páginas públicas possuem title, description, canonical, Open Graph e Twitter Card.
Os titles são específicos para página; a home descreve moda alternativa e streetwear, e
Sobre usa a referência verdadeira ao Vale do São Francisco sem criar endereço comercial.

A home publica `Organization` e `WebSite` JSON-LD somente com nome, domínio e logo
público existente. Não há CNPJ, telefone, endereço, redes ou dados de clientes no
schema. Não adicione `SearchAction` enquanto não houver uma busca compatível no site.

Depois de carregar um produto, `frontend/js/core/seo.js` atualiza title, description,
canonical, Open Graph, Twitter e JSON-LD `Product` + `BreadcrumbList`. O schema usa
nome, descrição, SKU/ID, imagens válidas, preço efetivo em BRL e disponibilidade real.
Não declara `brand`, pois o catálogo não tem essa informação confiável. O produto pode
permanecer com página canônica quando estiver temporariamente indisponível, mas recebe
`OutOfStock` e sai do sitemap. Quando a API responde 404 para um ID removido, a página
mostra a mensagem de inexistência e aplica `noindex` no cliente.

FAQ é carregado da API pública; após uma resposta válida, a página publica `FAQPage`
JSON-LD com as perguntas efetivamente retornadas. Não mantenha uma cópia manual do FAQ
no HTML apenas para SEO.

## Sitemap e robots

`frontend/robots.txt` permite páginas públicas, desestimula crawling das rotas
administrativas/técnicas e referencia `https://darkdistrict.com.br/sitemap.xml`.

`frontend/sitemap.xml` versionado contém as páginas institucionais. Antes de cada
deploy do frontend, gere novamente o mesmo arquivo a partir da fonte pública real:

```powershell
npm.cmd run generate:sitemap
```

O gerador em `frontend/scripts/generate-sitemap.mjs` consulta `GET /produtos?available=true`
na API de produção, acrescenta apenas produtos realmente disponíveis (incluindo estoque
de variantes quando existir) e usa `updated_at` como `lastmod` quando válido. O endpoint
base pode ser trocado somente para uma API segura por `DARK_DISTRICT_API_URL`; não usa
nem aceita token. Se a consulta falhar, o comando encerra com erro e o deploy deve ser
interrompido, em vez de publicar um sitemap de catálogo incompleto por acidente.

Filtros de catálogo não são landing pages SEO e nunca devem ser adicionados ao sitemap.
Não edite uma lista de produtos manualmente no XML.

Como a hospedagem é estática, ela não devolve um status HTTP 404 específico para cada
ID de produto ausente. O frontend não redireciona esse caso para a home e aplica
`noindex` depois do 404 da API. Se a loja precisar de 404 HTTP por produto no futuro,
isso exigirá renderização/roteamento no edge ou no servidor e deve ser uma decisão de
arquitetura separada.

## Publicação e validação

Antes de publicar o frontend:

```powershell
npm.cmd run test:frontend
npm.cmd run generate:sitemap
git diff --check
```

Depois do deploy, confira:

- [ ] `https://darkdistrict.com.br/` responde.
- [ ] `https://darkdistrict.com.br/robots.txt` responde 200.
- [ ] `https://darkdistrict.com.br/sitemap.xml` responde 200 e contém URLs canônicas.
- [ ] Admin possui `noindex` e não aparece no sitemap.
- [ ] Um produto real abre por sua URL canônica com `?id=`.
- [ ] Home e produto têm title, canonical, JSON-LD e preview Open Graph corretos.
- [ ] Links de catálogo, Brechó, Drops e Sobre continuam navegáveis.
- [ ] Não há URL canônica com `pages.dev`, localhost ou domínio da API.

## Google Search Console e rich results

O código não cria nem verifica uma propriedade no Google. A ação manual recomendada é:

1. Abra o Google Search Console e adicione a propriedade de domínio `darkdistrict.com.br`.
2. Copie o registro TXT fornecido pelo Google e publique-o no DNS/Cloudflare.
3. Conclua a verificação no Search Console.
4. Envie `https://darkdistrict.com.br/sitemap.xml`.
5. Use Inspeção de URL para a home, catálogo, Sobre, política e um produto real; solicite
   indexação quando fizer sentido.
6. Valide um produto no Rich Results Test e os schemas no Schema.org Validator.

Não coloque um token de verificação DNS ou meta tag no Git. A propriedade de domínio por
DNS é preferível. Enviar um sitemap ajuda o Google a descobrir e diagnosticar URLs, mas
não garante indexação imediata.

## Manutenção

Ao alterar rotas públicas, metadata, estrutura de produto, catálogo, domínio ou deploy,
atualize este documento e `tests/frontend/seo.test.mjs`. Ao alterar somente produto,
execute o teste SEO/frontend completo e gere o sitemap antes de publicar. Não introduza
endereços, telefones, avaliações, marcas ou preços que não estejam presentes na fonte de
dados real.
