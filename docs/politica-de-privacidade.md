# Política de Privacidade

URL pública: https://darkdistrict.com.br/politica-de-privacidade

O arquivo `frontend/politica-de-privacidade.html` contém o texto completo, título,
descrição e URL canônica. Não exige API, autenticação ou JavaScript para ler a
política. O controller reutiliza header, footer e chat existentes; os estilos da
página usam as fontes e variáveis globais. O rodapé compartilhado contém o link.

## Publicação e teste local

Publique o diretório `frontend`, como na configuração atual. Não há build.
O tratamento padrão de HTML dos assets Cloudflare resolve a URL sem extensão para
o arquivo `.html`, tanto em Pages quanto no Workers Static Assets atual.
Não são necessárias migrations ou alterações no Render.

Para validar esse roteamento, execute em `frontend`:

```powershell
npx.cmd wrangler@4 dev --local --port 8788
```

Abra `http://127.0.0.1:8788/politica-de-privacidade`. Com `python -m http.server`,
que não implementa as URLs limpas da Cloudflare, use `/politica-de-privacidade.html`.
Execute também `npm.cmd run test:frontend` na raiz.
Após a publicação automática, confirme a URL pública antes de cadastrá-la na Meta.

## Conteúdo e manutenção

O contato foi reutilizado de `CONTACTS.whatsapp`, já utilizado pelo site. O teste
verifica que os contatos estáticos da política continuam iguais ao oficial.
Não foram encontrados CNPJ, razão social ou endereço empresarial confiáveis para
identificar o controlador; esses dados não foram inventados. A equipe deve
complementar a identificação quando houver dados empresariais oficiais confirmados.

O texto descreve carrinho local, sessão temporária e IA do Web Chat, WhatsApp
humano com saudação inicial, endereço para frete e fornecedores presentes no código.
Não promete limpeza automática: a retenção depende da execução da manutenção.
Não há analytics publicitários implementados no código analisado; configurações
adicionadas diretamente nos provedores precisam ser consideradas em futuras revisões.

Ao mudar os tratamentos, provedores ou contato, atualize o texto e sua data.
A referência legal é a LGPD (Lei 13.709/2018), vinculada na página.
