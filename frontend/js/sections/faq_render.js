import { getFAQ } from "../api/faq_api.js";
import { getWhatsAppUrl } from "../utils/urls.js";

export async function renderFAQ(container, focusFirst = false) {
    if (!container) return;
    container.innerHTML = `
        <div class="faq-heading">
            <p class="faq-label">Estamos por aqui</p>
            <h1 id="faq-title">Perguntas frequentes</h1>
            <p>Da escolha da peça até a entrega, tire suas dúvidas sobre comprar na Dark District.</p>
        </div>
        <div class="faq-list" aria-busy="true">
            <p role="status">Carregando perguntas frequentes…</p>
        </div>
        <div class="faq-contact">
            <h2>Ainda ficou alguma dúvida?</h2>
            <p>Converse com a nossa equipe.</p>
            <a href="${getWhatsAppUrl()}" target="_blank" rel="noopener noreferrer">Falar pelo WhatsApp <span aria-hidden="true">↗</span></a>
        </div>
    `;
    const list = container.querySelector(".faq-list");
    try {
        const items = await getFAQ();
        const fragment = document.createDocumentFragment();
        for (const [index, item] of items.entries()) {
            const details = document.createElement("details");
            details.className = "faq-item";
            details.open = index === 0;
            const summary = document.createElement("summary");
            summary.textContent = item.question;
            const answer = document.createElement("p");
            answer.className = "faq-answer";
            answer.textContent = item.answer;
            details.append(summary, answer);
            fragment.append(details);
        }
        list.replaceChildren(fragment);
        if (focusFirst) list.querySelector("summary")?.focus();
    } catch {
        const message = document.createElement("p");
        message.setAttribute("role", "alert");
        message.textContent = "Não foi possível carregar o FAQ. Tente novamente ou fale com a equipe pelo WhatsApp.";
        const retry = document.createElement("button");
        retry.type = "button";
        retry.className = "faq-retry";
        retry.textContent = "Tentar novamente";
        retry.addEventListener("click", () => renderFAQ(container, true), { once: true });
        list.replaceChildren(message, retry);
        if (focusFirst) retry.focus();
    } finally {
        list.setAttribute("aria-busy", "false");
    }
}
