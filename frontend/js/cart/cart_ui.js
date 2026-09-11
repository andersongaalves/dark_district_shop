import { escapeHtml } from "../utils/dom.js";
import { formatPrice } from "../utils/format.js";
import { getImageUrl, getProductUrl } from "../utils/urls.js";
import { cartItemKey, MAX_CART_QUANTITY } from "./cart_state.js";
import { createShippingView } from "./shipping_ui.js";

function renderItem(item, busy) {
    const image = getImageUrl(item.image);
    return `<article class="cart-item" data-key="${escapeHtml(cartItemKey(item))}">
        ${image ? `<img src="${escapeHtml(image)}" alt="${escapeHtml(item.title)}" loading="lazy">` : '<div class="cart-item__placeholder">Sem imagem</div>'}
        <div class="cart-item__details">
            <a href="${escapeHtml(getProductUrl(item.productId))}">${escapeHtml(item.title)}</a>
            <p>${escapeHtml([item.size && `Tamanho: ${item.size}`, item.color && `Cor: ${item.color}`].filter(Boolean).join(" · "))}</p>
            <p>${item.validated ? formatPrice(Math.round(item.price * 100) / 100) : "Preço a confirmar"}</p>
            <label>Quantidade <input data-quantity type="number" min="1" max="${Math.max(1, Math.min(item.stock ?? MAX_CART_QUANTITY, MAX_CART_QUANTITY))}"
                step="1" value="${item.quantity}" ${busy ? "disabled" : ""} aria-label="Quantidade de ${escapeHtml(item.title)}"></label>
            <button type="button" data-remove ${busy ? "disabled" : ""}>Remover</button>
            ${item.issue ? `<p class="cart-item__issue">${escapeHtml(item.issue)}</p>` : ""}
        </div>
    </article>`;
}

export function createCartView(actions) {
    const dialog = document.createElement("dialog");
    dialog.id = "cart-drawer";
    dialog.className = "cart-drawer";
    dialog.setAttribute("aria-labelledby", "cart-title");
    dialog.innerHTML = `<div class="cart-drawer__header"><h2 id="cart-title" aria-label="Seu carrinho"><span class="cart-icon" aria-hidden="true"></span></h2>
        <button type="button" data-close aria-label="Fechar carrinho">×</button></div><div data-cart-content></div>`;
    document.body.appendChild(dialog);
    const content = dialog.querySelector("[data-cart-content]");
    const shipping = actions.onQuote ? createShippingView(actions) : null;
    if (shipping) dialog.append(shipping.element);
    let restoreFocus;
    const handle = (operation) => { Promise.resolve().then(operation).catch(() => {}); };
    dialog.addEventListener("click", (event) => {
        const button = event.target.closest("button");
        if (event.target === dialog || button?.hasAttribute("data-close")) { dialog.close(); return; }
        if (!button || button.disabled) return;
        const key = button.closest("[data-key]")?.dataset.key;
        if (button.hasAttribute("data-remove")) handle(() => actions.onRemove(key));
        if (button.hasAttribute("data-clear")) handle(actions.onClear);
        if (button.hasAttribute("data-refresh")) handle(actions.onRefresh);
        if (button.hasAttribute("data-checkout") && !shipping) handle(actions.onCheckout);
    });
    dialog.addEventListener("change", (event) => {
        if (event.target.matches("[data-quantity]")) {
            handle(() => actions.onQuantity(event.target.closest("[data-key]").dataset.key, Number(event.target.value)));
        }
    });
    return {
        open() { if (!dialog.open) dialog.showModal(); shipping?.loadPolicy(); },
        render(state) {
            const focused = document.activeElement;
            const focusControl = ["data-quantity", "data-remove", "data-clear", "data-refresh", "data-checkout"]
                .find((attribute) => content.contains(focused) && focused.hasAttribute(attribute));
            if (focusControl) restoreFocus = { key: focused.closest("[data-key]")?.dataset.key, attribute: focusControl };
            content.innerHTML = `
                <div class="cart-drawer__items">${state.items.length ? state.items.map((item) => renderItem(item, state.busy)).join("") : "<p>Nenhum item adicionado.</p>"}</div>
                <div class="cart-drawer__summary">
                    <p class="cart-drawer__subtotal">Subtotal estimado <strong>${state.items.every((item) => item.validated) ? formatPrice(state.subtotal) : "A confirmar"}</strong></p>
                    <p>Adicionar itens não reserva estoque. Confira o frete antes de continuar; o pagamento será combinado com a loja.</p>
                    <p role="status" aria-live="polite">${escapeHtml(state.busy ? "Consultando…" : state.message)}</p>
                    ${state.persisted ? "" : '<p role="alert">Não foi possível salvar neste navegador. Os itens ficarão disponíveis apenas nesta página.</p>'}
                    ${shipping ? "" : `<button class="cart-drawer__checkout" type="button" data-checkout ${state.busy || !state.items.length ? "disabled" : ""}>Continuar pelo WhatsApp</button>`}
                    <div class="cart-drawer__actions">
                        <button type="button" data-refresh ${state.busy ? "disabled" : ""}>Atualizar disponibilidade</button>
                        <button type="button" data-clear aria-label="Limpar carrinho" ${state.busy || !state.items.length ? "disabled" : ""}>Limpar <span class="cart-icon" aria-hidden="true"></span></button>
                    </div>
                </div>`;
            shipping?.render(state);
            if (restoreFocus && !state.busy) {
                const parent = restoreFocus.key ? [...content.querySelectorAll("[data-key]")].find((node) => node.dataset.key === restoreFocus.key) : content;
                if (dialog.open) (parent?.querySelector(`[${restoreFocus.attribute}]`) ?? dialog.querySelector("[data-close]")).focus();
                restoreFocus = null;
            }
        }
    };
}
