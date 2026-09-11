# Frete local

O carrinho coleta CEP, rua, número (ou S/N), bairro, cidade, UF, nome do recebedor,
telefone com DDD, complemento e referência opcionais. Buscar CEP preenche os dados
disponíveis via ViaCEP; o cliente deve conferir rua e número. O botão Calcular frete
consulta o backend e exibe frete, total, distância de trajeto e raio.

## Regras

- Origem: Chácara Patrícia, Estrada Roçado, S/N, Dom José Rodrigues, Juazeiro/BA.
  Coordenadas do ponto compartilhado pelo proprietário: **-9.4741012, -40.516211**.
  [Local no Google Maps](https://maps.app.goo.gl/BAixkLj7TSwXfbGQ7).
- A partir de R$ 100,00 em roupas, inclusive, frete gratuito dentro de 7 km em
  linha reta, inclusive. O trajeto pode ser maior que esse raio.
- Nos demais casos: R$ 6,00 até 1,9 km de trajeto; depois R$ 1,50 por km adicional,
  proporcional aos metros, arredondado ao centavo. Fora dos 7 km aplica-se a tarifa
  completa, mesmo para compras de R$ 100,00 ou mais.
- Exemplos pagos: 1,9 km = R$ 6,00; 2 km = R$ 6,15; 2,9 km = R$ 7,50;
  8 km = R$ 15,15. O raio é arredondado para cima ao metro.
- O subtotal usa preços efetivos do banco, incluindo ofertas vigentes. A categoria
  identifica roupas (camisetas, calças, saias e demais tipos reconhecidos em
  `services/shipping.py`). Acessórios e categorias não reconhecidas não contribuem
  para a gratuidade. Cadastre roupas em categorias de vestuário reconhecidas.

O adicional de R$ 1,50/km usa como referência a tarifa publicada pela
[HumanLog](https://humanlog.online/precoshumanlog.html), que anuncia esse adicional
para motoboy. É uma referência comercial, não uma tabela oficial de Juazeiro.
A base de R$ 6,00 e as condições de gratuidade foram definidas pela loja.

## Ativação

1. No Google Cloud, habilite Geocoding API e Routes API no projeto com faturamento
   configurado. Crie uma chave de servidor restrita a essas APIs; quando houver
   IP de saída estável, restrinja também por IP. Configure cotas compatíveis.
2. Defina `SHIPPING_GOOGLE_API_KEY` no ambiente do backend. Não coloque a chave
   no frontend, no Git ou em mensagens. Os demais parâmetros estão em
   `backend/.env.example`, com valores monetários em centavos e distâncias em metros.
3. Publique o backend e reinicie API e worker, que compartilha as regras do FAQ.
   Publique o frontend. Não há migration nova nesta funcionalidade.
4. Confira `GET /shipping/policy`: `configured` indica presença da configuração,
   não comprova credenciais ou habilitação das APIs. Teste um endereço conhecido
   para conferir sua localização e o trajeto antes de operar.

Documentação dos serviços: [ViaCEP](https://viacep.com.br/),
[Google Geocoding](https://developers.google.com/maps/documentation/geocoding/guides-v3/requests-geocoding),
[Google Routes](https://developers.google.com/maps/documentation/routes/compute_route_directions).

## Conferência e limitações

O servidor recebe somente IDs, variantes, quantidades e endereço. Preço, estoque,
distância e benefício são calculados no backend; a conexão com o banco é liberada
durante a consulta externa. O destino deve retornar um único ponto preciso,
compatível com CEP, UF e número. Endereços ambíguos, sem número localizável ou
falhas de serviço exigem confirmação manual; não são convertidos em frete grátis.

A cotação assinada dura dez minutos e é vinculada aos itens, preços, endereço e
regras. Alterar esses dados exige recalcular. Antes de abrir o WhatsApp, o servidor
confere novamente a cotação, os preços e o estoque e monta a mensagem com o total
e os dados de entrega. Isso não reserva produtos, gera cobrança ou confirma pedido.

Sem chave ou com erro de localização, o cliente pode preencher os dados e escolher
**Confirmar frete com a loja**. A mensagem indica **frete a confirmar**. A loja confirma
a cobertura local e a entrega; uma rota calculável não confirma atendimento em outra cidade.

Nome, telefone, complemento e referência não são enviados ao Google. Endereço e
cotação ficam apenas na memória da página e não são persistidos no banco ou no
localStorage. Os dados completos seguem na mensagem de WhatsApp escolhida pelo cliente.
Os endpoints usam `no-store`, limite de corpo e de requisições por IP e por processo.
URLs do Maps são filtradas dos logs HTTP; o token contém hashes, não o endereço.
Em múltiplos workers, o limite em memória é individual por processo.

Os testes usam banco isolado, APIs simuladas e jsdom. Cobrem limites de tarifa,
ofertas, cotação adulterada/expirada, mudanças de estoque e endereço, falhas de
geocodificação, origem, privacidade, formulário e respostas da IA. Não fazem
chamadas pagas ao Google nem enviam mensagens reais.
