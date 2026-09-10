import { createProductCard } from "../components/product_card.js";
import { renderProductPrice, watchOfferExpiry } from "../components/product_price.js";
import { getProductUrl } from "../utils/urls.js";
import { MAX_CHAT_MESSAGE_LENGTH } from "./chat_state.js";

const STATUS_TEXT = {
    AI: "Assistente de IA da Dark District",
    WAITING_HUMAN: "Atendimento humano solicitado. Você pode deixar sua mensagem.",
    HUMAN: "Conversa com a equipe Dark District"
};

export function createChatView(actions) {
    const viewport = window.visualViewport;
    const launcher = document.createElement("button");
    launcher.type = "button";
    launcher.className = "dd-chat-launcher";
    launcher.setAttribute("aria-label", "Abrir atendimento Dark District");
    launcher.setAttribute("aria-controls", "dd-chat");
    launcher.setAttribute("aria-expanded", "false");
    launcher.innerHTML = '<span aria-hidden="true">✦</span> Fale com a DD';
    const dialog = document.createElement("dialog");
    dialog.id = "dd-chat";
    dialog.className = "dd-chat";
    dialog.setAttribute("aria-labelledby", "dd-chat-title");
    dialog.setAttribute("aria-describedby", "dd-chat-status");
    dialog.innerHTML = `<header class="dd-chat__header">
        <div><h2 id="dd-chat-title">Dark District</h2><p id="dd-chat-status"></p></div>
        <button type="button" data-close aria-label="Fechar atendimento">×</button>
        </header>
        <div class="dd-chat__messages" role="log" aria-label="Mensagens do atendimento" aria-live="polite" aria-relevant="additions text" data-messages></div>
        <p class="dd-chat__activity" role="status" aria-live="polite" data-activity></p>
        <div class="dd-chat__error" role="alert" hidden data-error><p data-error-message></p>
            <button type="button" data-retry>Tentar novamente</button>
            <button type="button" data-discard hidden>Escrever outra mensagem</button>
        </div>
        <p class="dd-chat__storage" hidden data-storage>A conversa ficará disponível apenas nesta página porque o navegador não permitiu salvar a sessão.</p>
        <form class="dd-chat__form">
            <label for="dd-chat-message">Sua mensagem</label>
            <div><textarea id="dd-chat-message" name="message" rows="2" maxlength="${MAX_CHAT_MESSAGE_LENGTH}" required placeholder="O que você procura?" autocomplete="off"></textarea>
            <button type="submit">Enviar</button></div>
        </form>
        <footer class="dd-chat__footer"><span>Vista o seu lado obscuro.</span><button type="button" data-end>Encerrar conversa</button></footer>`;
    document.body.append(launcher, dialog);
    const transcript = dialog.querySelector("[data-messages]");
    const input = dialog.querySelector("textarea");
    const form = dialog.querySelector("form");
    let state, renderedMessages = "", restoreFocus;
    const messageNodes = new Map();
    const run = (operation) => Promise.resolve().then(operation).catch(() => {});
    const close = () => {
        if (!dialog.open) return;
        dialog.close();
    };
    const updateViewport = () => {
        if (!viewport) return;
        dialog.style.setProperty("--chat-viewport-height", `${Math.round(viewport.height)}px`);
        dialog.style.setProperty("--chat-viewport-top", `${Math.round(viewport.offsetTop)}px`);
    };
    launcher.addEventListener("click", () => {
        // Another native modal (such as the cart) owns focus until it closes.
        if (document.querySelector("dialog[open]") || dialog.open) return;
        restoreFocus = document.activeElement;
        updateViewport();
        dialog.showModal();
        launcher.setAttribute("aria-expanded", "true");
        input.focus({ preventScroll: true });
        run(actions.onOpen);
    });
    dialog.addEventListener("close", () => {
        launcher.setAttribute("aria-expanded", "false");
        (restoreFocus?.isConnected ? restoreFocus : launcher).focus({ preventScroll: true });
        actions.onClose?.();
    });
    dialog.addEventListener("click", (event) => {
        if (event.target === dialog || event.target.closest("[data-close]")) close();
        if (event.target.closest("[data-retry]")) run(actions.onRetry);
        if (event.target.closest("[data-discard]")) { actions.onDiscard(); input.focus(); }
        if (event.target.closest("[data-handoff]") && !state?.busy && !state?.pending) {
            run(() => actions.onSend("Quero falar com a equipe"));
        }
        if (event.target.closest("[data-end]")) run(async () => { await actions.onEnd(); input.focus(); });
    });
    form.addEventListener("submit", (event) => {
        event.preventDefault();
        if (state?.busy || state?.pending || !input.value.trim()) return;
        const message = input.value;
        input.value = "";
        run(async () => { await actions.onSend(message); if (dialog.open) input.focus({ preventScroll: true }); });
    });
    input.addEventListener("keydown", (event) => {
        if (event.key === "Enter" && !event.shiftKey && !event.isComposing && !event.ctrlKey && !event.altKey) {
            event.preventDefault();
            form.requestSubmit();
        }
    });
    // Native dialog supplies Escape and modal focus; explicitly cycle keyboard
    // focus as well so the behavior is stable in embedded/mobile browsers.
    dialog.addEventListener("keydown", (event) => {
        if (event.key !== "Tab") return;
        const controls = [...dialog.querySelectorAll("button:not(:disabled), textarea:not(:disabled), a[href]")]
            .filter((element) => !element.closest("[hidden]"));
        const first = controls[0], last = controls.at(-1);
        if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last?.focus(); }
        if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first?.focus(); }
    });
    viewport?.addEventListener("resize", updateViewport);
    viewport?.addEventListener("scroll", updateViewport);

    return {
        isOpen: () => dialog.open,
        close,
        render(next) {
            state = next;
            dialog.querySelector("#dd-chat-status").textContent = STATUS_TEXT[state.status] ?? STATUS_TEXT.AI;
            dialog.querySelector("[data-activity]").textContent = state.busy ? "Consultando atendimento…" : "";
            dialog.querySelector("[data-error]").hidden = !state.error;
            dialog.querySelector("[data-error-message]").textContent = state.error;
            dialog.querySelector("[data-discard]").hidden = !state.pending;
            dialog.querySelector("[data-storage]").hidden = state.persisted;
            input.readOnly = state.busy || Boolean(state.pending);
            form.querySelector("button").disabled = state.busy || Boolean(state.pending);
            dialog.querySelector("[data-end]").disabled = state.busy || !state.hasSession;
            dialog.querySelectorAll("[data-retry], [data-discard]").forEach((button) => { button.disabled = state.busy; });
            dialog.querySelectorAll("[data-handoff]").forEach((button) => {
                button.disabled = state.busy || Boolean(state.pending) || state.status !== "AI";
            });
            const signature = JSON.stringify(state.messages);
            if (renderedMessages === signature) return;
            renderedMessages = signature;
            const nearBottom = transcript.scrollHeight - transcript.scrollTop - transcript.clientHeight < 80;
            const currentKeys = new Set();
            const nodes = state.messages.map((message, index) => {
                const key = `${message.sender}:${message.id || index}`;
                const signature = JSON.stringify(message);
                currentKeys.add(key);
                const existing = messageNodes.get(key);
                if (existing?.signature === signature) return existing.element;
                const item = document.createElement("article");
                item.className = `dd-chat__message dd-chat__message--${message.sender}`;
                const label = document.createElement("span");
                label.className = "dd-chat__sender";
                label.textContent = message.sender === "customer" ? "Você" : message.sender === "human" ? "Equipe DD" : "Assistente DD";
                const text = document.createElement("p");
                text.textContent = message.message;
                item.append(label, text);
                for (const action of message.actions ?? []) {
                    if (action.type !== "human_handoff") continue;
                    const button = document.createElement("button");
                    button.type = "button";
                    button.dataset.handoff = "";
                    button.textContent = action.label;
                    button.disabled = state.busy || Boolean(state.pending) || state.status !== "AI";
                    item.append(button);
                }
                if (message.products?.length) {
                    const products = document.createElement("div");
                    products.className = "dd-chat__products";
                    for (const product of message.products) {
                        const card = createProductCard(product);
                        const link = document.createElement("a");
                        link.className = "dd-chat__product-link";
                        link.href = getProductUrl(product.id);
                        link.textContent = "Ver produto";
                        link.setAttribute("aria-label", `Ver produto: ${product.title}`);
                        card.append(link);
                        watchOfferExpiry(card, [product], () => {
                            card.querySelector(".product-card__price").innerHTML = renderProductPrice(product);
                        });
                        products.append(card);
                    }
                    item.append(products);
                }
                messageNodes.set(key, { signature, element: item });
                return item;
            });
            for (const key of messageNodes.keys()) if (!currentKeys.has(key)) messageNodes.delete(key);
            if (!nodes.length) {
                const welcome = document.createElement("p");
                welcome.className = "dd-chat__welcome";
                welcome.textContent = "Oi! Sou a IA da DD. Posso ajudar a encontrar peças e consultar o catálogo. Se precisar da equipe, é só pedir.";
                nodes.push(welcome);
            }
            // Retain existing bubbles so assistive technology announces only new content.
            nodes.forEach((node, index) => {
                if (transcript.children[index] !== node) transcript.insertBefore(node, transcript.children[index] ?? null);
            });
            while (transcript.children.length > nodes.length) transcript.lastElementChild.remove();
            if (nearBottom || state.messages.at(-1)?.sender === "customer") transcript.scrollTop = transcript.scrollHeight;
        },
        destroy() {
            viewport?.removeEventListener("resize", updateViewport);
            viewport?.removeEventListener("scroll", updateViewport);
            launcher.remove(); dialog.remove();
        }
    };
}
