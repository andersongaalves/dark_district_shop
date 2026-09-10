"""Small, bounded language helpers; never rewrite identifiers, prices or sizes."""
import re
import unicodedata


COLORS = {
    "preto": "preto", "preta": "preto", "branco": "branco", "branca": "branco",
    "azul": "azul", "vermelho": "vermelho", "vermelha": "vermelho", "roxo": "roxo",
    "roxa": "roxo", "rosa": "rosa", "cinza": "cinza", "verde": "verde",
    "amarelo": "amarelo", "amarela": "amarelo", "laranja": "laranja",
    "bege": "bege", "marrom": "marrom",
}
PIECES = ("camiseta", "cropped", "jaqueta", "saia", "vestido", "calca", "moletom",
          "short", "bermuda", "blusa", "regata", "top", "corset", "camisa")
ALIASES = {"vc": "voce", "vcs": "voces", "q": "que", "oq": "o que", "tb": "tambem",
           "tbm": "tambem", "pfv": "por favor", "pf": "por favor", "obg": "obrigado",
           "vlw": "valeu", "blz": "beleza", "vdd": "verdade"}
VOCABULARY = set(PIECES) | {piece + "s" for piece in PIECES} | {
    "entrega", "entregam", "devolucao", "devolver", "atendente", "catalogo",
    "tamanho", "tamanhos", "oferta", "ofertas", "promocao", "promocoes",
}
# Valid words near our vocabulary must not become unsolicited spelling guesses.
COMMON_WORDS = {"comprar", "compra", "compras", "compro", "entregar", "entregas", "entregue",
                "atendem", "atende", "camisetas", "camisas", "calcas", "calce", "camisola",
                "carta", "casas", "causa", "calma", "casaco", "cabelo", "casamento",
                "preto", "preta", "perto", "preco", "troca", "tenho", "tenha"}


def normalize(value: str) -> str:
    text = "".join(char for char in unicodedata.normalize("NFKD", value.lower())
                   if not unicodedata.combining(char))
    return re.sub(r"(?<![\w/@.:-])(?:" + "|".join(ALIASES) + r")(?![\w/@.:-])",
                  lambda match: ALIASES[match[0]], text)


def _one_edit(left: str, right: str) -> bool:
    if abs(len(left) - len(right)) > 1:
        return False
    if len(left) == len(right):
        differences = [index for index, pair in enumerate(zip(left, right)) if pair[0] != pair[1]]
        if len(differences) == 1:
            return True
        return (len(differences) == 2 and differences[1] == differences[0] + 1
                and left[differences[0]] == right[differences[1]]
                and left[differences[1]] == right[differences[0]])
    shorter, longer = sorted((left, right), key=len)
    return any(longer[:index] + longer[index + 1:] == shorter for index in range(len(longer)))


def spelling_suggestion(text: str) -> str | None:
    """Suggest only unique one-edit matches, requiring confirmation by the user."""
    if len(text) > 500:
        return None
    replacements = {}
    pattern = r"(?<![\w/@.:-])[^\W\d_]{5,20}(?![\w/@.:-])"
    for original in re.findall(pattern, text):
        word = normalize(original)
        if word in VOCABULARY or word in COMMON_WORDS:
            continue
        candidates = [candidate for candidate in VOCABULARY
                      if candidate[0] == word[0] and _one_edit(word, candidate)]
        if len(candidates) == 1:
            replacements[word] = candidates[0]
        if len(replacements) > 3:
            return None
    if not replacements:
        return None
    return re.sub(pattern, lambda match: replacements.get(normalize(match[0]), match[0]), text)


def wants_products(text: str) -> bool:
    return bool(re.search(r"\b(tem|quero|procuro|busco|mostre|mostrar|ver|sugira|sugestao|recomenda|recomende)\b", text)
                and re.search(r"\b(" + "|".join(PIECES) + r"|peca|roupa|produto)s?\b", text))
