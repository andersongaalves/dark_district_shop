import { getShippingPolicy, lookupCEP } from "../api/shipping_api.js";
import { formatPrice } from "../utils/format.js";

export function createShippingView(actions, { policy = getShippingPolicy, cep = lookupCEP } = {}) {
    const form = document.createElement("form");
    form.className = "cart-shipping";
    form.setAttribute("aria-labelledby", "delivery-title");
    form.innerHTML = `<h3 id="delivery-title">Entrega</h3>
        <p data-policy>Informe seu endereço para consultar o frete.</p>
        <fieldset><legend>Endereço e recebedor</legend>
        <div class="cart-shipping__grid">
            <label>CEP <input name="cep" inputmode="numeric" autocomplete="postal-code" pattern="[0-9]{5}-?[0-9]{3}" maxlength="9" required placeholder="00000-000"></label>
            <button type="button" data-cep>Buscar CEP</button>
            <label class="cart-shipping__wide">Rua ou avenida <input name="street" autocomplete="address-line1" minlength="3" maxlength="150" required></label>
            <label>Número <input name="number" maxlength="20" required placeholder="Número ou S/N"></label>
            <label>Bairro <input name="neighborhood" maxlength="100" minlength="2" required></label>
            <label>Cidade <input name="city" autocomplete="address-level2" maxlength="100" minlength="2" required></label>
            <label>UF <input name="state" autocomplete="address-level1" pattern="[A-Za-z]{2}" maxlength="2" required placeholder="BA"></label>
            <label class="cart-shipping__wide">Nome do recebedor <input name="recipient" autocomplete="name" minlength="2" maxlength="100" required></label>
            <label class="cart-shipping__wide">Telefone com DDD <input name="phone" type="tel" autocomplete="tel" minlength="10" maxlength="22" required></label>
            <label class="cart-shipping__wide">Complemento (opcional) <input name="complement" autocomplete="address-line2" maxlength="150" placeholder="Apartamento, bloco, casa…"></label>
            <label class="cart-shipping__wide">Ponto de referência (opcional) <input name="reference" maxlength="200"></label>
        </div>
        <p class="cart-shipping__privacy">O endereço é consultado no Google Maps para calcular a distância. Nome e telefone não são enviados ao serviço de mapas. Os dados de entrega serão incluídos na mensagem para a loja.</p>
        <button type="submit" data-quote>Calcular frete</button>
        <div data-shipping-result role="status" aria-live="polite"></div>
        <button type="button" data-checkout class="cart-drawer__checkout" disabled>Continuar pelo WhatsApp</button>
        <button type="button" data-manual>Confirmar frete com a loja</button>
        </fieldset><p data-address-status role="status" aria-live="polite"></p>`;
    const fields = ["cep", "street", "number", "neighborhood", "city", "state", "recipient", "phone", "complement", "reference"];
    const getAddress = () => Object.fromEntries(fields.map((name) => [name,
        name === "state" ? form.elements.namedItem(name).value.trim().toUpperCase() : form.elements.namedItem(name).value.trim()]));
    const status = form.querySelector("[data-address-status]");
    let state, expiryTimer, currentToken, policyLoaded = false, lookingUp = false;
    const handle = (operation) => Promise.resolve().then(operation).catch((error) => { status.textContent = error.message; });
    form.addEventListener("input", () => { status.textContent = ""; actions.onAddressChange(); });
    form.addEventListener("submit", (event) => {
        event.preventDefault();
        if (state?.busy || lookingUp || !form.reportValidity()) return;
        status.textContent = "";
        handle(() => actions.onQuote(getAddress()));
    });
    form.querySelector("[data-cep]").addEventListener("click", () => handle(async () => {
        if (lookingUp || state?.busy) return;
        const requested = form.elements.namedItem("cep").value;
        lookingUp = true;
        form.querySelector("[data-cep]").disabled = true;
        status.textContent = "Consultando CEP…";
        try {
            const data = await cep(requested);
            if (form.elements.namedItem("cep").value !== requested) return;
            for (const name of ["street", "neighborhood", "city", "state"]) {
                if (typeof data[name] === "string") form.elements.namedItem(name).value = data[name];
            }
            actions.onAddressChange();
            status.textContent = "Confira o endereço e informe o número.";
            form.elements.namedItem("number").focus();
        } finally {
            lookingUp = false;
            form.querySelector("[data-cep]").disabled = Boolean(state?.busy);
        }
    }));
    for (const [selector, manual] of [["[data-checkout]", false], ["[data-manual]", true]]) {
        form.querySelector(selector).addEventListener("click", () => {
            if (state?.busy || lookingUp || !form.reportValidity()) return;
            handle(() => actions.onCheckout(getAddress(), { manual }));
        });
    }
    const render = (next) => {
        state = next;
        form.hidden = !state.items.length;
        form.querySelector("fieldset").disabled = state.busy;
        const result = form.querySelector("[data-shipping-result]");
        const quote = state.shippingQuote;
        const valid = quote && quote.expires_at * 1000 > Date.now();
        form.querySelector("[data-checkout]").disabled = !valid || state.busy;
        result.replaceChildren();
        if (quote) {
            for (const text of [
                `Roupas para o benefício: ${formatPrice(quote.clothing_subtotal_cents / 100)}`,
                `Frete: ${quote.shipping_cents === 0 ? "Grátis" : formatPrice(quote.shipping_cents / 100)}`,
                `Total com entrega: ${formatPrice(quote.total_cents / 100)}`,
                `Trajeto: ${(quote.route_meters / 1000).toFixed(3)} km · Raio: ${(quote.radius_meters / 1000).toFixed(3)} km`,
                valid ? "Cotação temporária. Os valores e o estoque serão conferidos antes de continuar." : "A cotação expirou. Calcule novamente."
            ]) {
                const paragraph = document.createElement("p"); paragraph.textContent = text; result.append(paragraph);
            }
        }
        if (currentToken !== quote?.quote_token) {
            clearTimeout(expiryTimer);
            currentToken = quote?.quote_token;
            if (valid) expiryTimer = setTimeout(() => render(state), Math.min(2147483647, quote.expires_at * 1000 - Date.now() + 1));
        }
        if (!state.items.length) { form.reset(); status.textContent = ""; }
    };
    return { element: form, render,
        loadPolicy: () => handle(async () => {
            if (policyLoaded) return;
            const data = await policy();
            if (typeof data?.description !== "string") throw new Error("Não foi possível consultar as regras de frete.");
            form.querySelector("[data-policy]").textContent = data.description;
            policyLoaded = true;
            if (!data.configured) status.textContent = "O cálculo automático ainda não está disponível. Preencha os dados e confirme o frete com a loja.";
        }),
        destroy() { clearTimeout(expiryTimer); form.remove(); }
    };
}
