import { get, post, patch } from "../api.js";
import { escapeHtml } from "../../js/utils/dom.js";

export const STATUS_LABELS = { WAITING_HUMAN: "Aguardando humano", HUMAN: "Atendimento humano", CLOSED: "Encerrada", AI: "IA ativa" };
export const MODE_LABELS = { AUTO: "Automático", ASSIST: "Assistido", OFF: "Desativado" };
export const DECISION_LABELS = { ANSWER: "Resposta automática", CLARIFY: "Pergunta de esclarecimento", HANDOFF: "Encaminhado para humano", NO_ACTION: "Sem ação automática" };
export const HANDOFF_LABELS = {
    HUMAN_REQUESTED: "Cliente pediu atendente", PURCHASE_INTENT: "Cliente quer finalizar compra",
    PAYMENT: "Pagamento", ORDER_SUPPORT: "Suporte de pedido", COMPLAINT: "Reclamação",
    RETURN_EXCHANGE: "Troca ou devolução", NEGOTIATION: "Negociação",
    DELIVERY_ISSUE: "Problema de entrega", LOW_CONFIDENCE: "IA não conseguiu compreender",
    AI_FAILURE: "Falha técnica da IA"
};
const EVENT_LABELS = { AI_ACTIVATED: "Atendimento automático ativado", AI_RESUMED: "Atendimento automático retomado", HUMAN_CLAIMED: "Atendimento assumido por humano", CONVERSATION_CLOSED: "Atendimento encerrado", AI_HANDOFF: "Encaminhado para humano" };
const PREFERENCE_LABELS = { garment: "Peça", style_query: "Estilo", size: "Tamanho", color: "Cor", max_price: "Preço máximo", product_type: "Tipo", offer_only: "Somente ofertas" };
const VALUE_LABELS = { gotico: "Gótico", catalogo: "Catálogo", brecho: "Brechó", camiseta: "Camiseta", calca: "Calça" };
const DELIVERY_LABELS = { pending: "Na fila", sending: "Enviando…", sent: "Aceita pelo WhatsApp", failed: "Falha no envio", uncertain: "Envio sem confirmação — confira antes de reenviar", cancelled: "Não enviada" };
const date = (value) => new Date(value).toLocaleString("pt-BR");
const escape = (value) => escapeHtml(String(value ?? ""));

export function mountInbox(root, { api = { get, post, patch }, interval = 5000 } = {}) {
    let suggestion = "", generating = false, aiContext = "";
    let active = true, selected = null, busy = false, refreshing = false, revision = 0, timer;
    let messages = new Map(), hasOlder = false, offset = 0, more = false;
    const drafts = new Map(), retries = new Map();
    root.innerHTML = `<h1>WhatsApp</h1><p>Atendimento · IA e equipe Dark District</p>
        <p class="inbox-notice" role="status"></p>
        <div class="inbox"><aside class="inbox-sidebar" aria-label="Conversas">
        <label>Filtrar <select data-filter><option value="">Todas</option><option value="WAITING_HUMAN">Aguardando</option><option value="HUMAN">Em atendimento</option><option value="CLOSED">Encerradas</option></select></label>
        <div class="inbox-list"></div><div class="inbox-pagination"><button data-prev>Anterior</button><button data-next>Próxima</button></div></aside>
        <section class="inbox-thread" aria-label="Histórico da conversa"><p data-empty>Selecione uma conversa.</p>
        <div data-conversation hidden><header class="inbox-toolbar"><button data-back>Voltar</button><strong data-phone></strong><span data-status></span><button data-claim>Assumir atendimento</button><button data-close>Encerrar atendimento</button></header>
        <button data-older hidden>Carregar mensagens anteriores</button><div class="inbox-messages" aria-label="Mensagens"></div>
        <form><label for="inbox-text">Sua resposta</label><textarea id="inbox-text" maxlength="2000" rows="3" required></textarea><button type="submit">Enviar</button></form></div></section>
        <aside class="inbox-ai" hidden><details><summary>Assistente IA</summary><p class="inbox-ai-summary" data-ai-summary></p>
        <dl class="inbox-ai-state"><div><dt>Modo IA</dt><dd data-ai-mode-label></dd></div><div><dt>Status</dt><dd data-ai-status></dd></div><div data-ai-decision-row><dt>Última ação da IA</dt><dd data-ai-decision></dd></div></dl>
        <section data-ai-clarification hidden><h3>Esclarecimento</h3><p data-ai-clarification-text></p></section>
        <section data-ai-handoff hidden><h3>Motivo do encaminhamento</h3><p data-ai-reason></p></section>
        <section data-ai-focus hidden><h3>Produto em foco</h3><p data-ai-focus-text></p><small data-ai-presented></small></section>
        <section data-ai-preferences hidden><h3>Preferências detectadas</h3><dl data-ai-preferences-list></dl></section>
        <section data-ai-events hidden><h3>Eventos recentes</h3><ol data-ai-events-list></ol></section>
        <label>Alterar modo <select data-ai-mode><option value="OFF">Desativado</option><option value="ASSIST">Assistido</option><option value="AUTO">Automático</option></select></label>
        <p>A IA não finaliza compras.</p>
        <button data-ai-resume>Retomar IA</button><p data-ai-notice role="status"></p><button data-ai-generate>Gerar sugestão</button>
        <button data-ai-suggestion class="inbox-suggestion" aria-label="Copiar sugestão"></button><div class="inbox-ai-actions"><button data-ai-use>Usar resposta</button><button data-ai-send>Enviar agora</button></div></details></aside></div>`;
    const q = (selector) => root.querySelector(selector);
    const textarea = q("textarea");
    const notify = (text) => { if (active) q(".inbox-notice").textContent = text; };
    const path = () => `/admin/conversations/${selected.conversation_id}`;
    const money = (value) => Number(value).toLocaleString("pt-BR", { style: "currency", currency: "BRL" });
    const title = (value) => value ? String(value).charAt(0).toUpperCase() + String(value).slice(1) : "";
    function renderAIState() {
        const state = selected.ai_state || { mode: selected.ai_mode || "OFF", status: selected.status, actions: {} };
        const actions = state.actions || {};
        const summary = state.status === "CLOSED" ? "Atendimento encerrado" : state.mode === "OFF" ? "IA desativada" :
            state.mode === "ASSIST" ? "IA em modo assistido" : state.status === "AI" ? "Atendimento automático ativo" : "Atendimento automático pausado";
        q("[data-ai-summary]").textContent = summary;
        q("[data-ai-mode-label]").textContent = MODE_LABELS[state.mode] || "Não informado";
        q("[data-ai-status]").textContent = STATUS_LABELS[state.status] || state.status || "Não informado";
        const decision = state.last_decision?.action;
        q("[data-ai-decision-row]").hidden = !decision;
        q("[data-ai-decision]").textContent = DECISION_LABELS[decision] || "";

        const clarification = state.clarification;
        q("[data-ai-clarification]").hidden = !clarification;
        q("[data-ai-clarification-text]").textContent = clarification ? `Tentativa: ${clarification.attempts} de ${clarification.max_attempts}${clarification.kind === "PROCESS_TOPIC" ? ". A IA está identificando qual processo o cliente quer conhecer." : ". A IA está esclarecendo a solicitação."}` : "";

        const handoff = state.handoff;
        q("[data-ai-handoff]").hidden = !handoff;
        q("[data-ai-reason]").textContent = handoff?.reason === "LOW_CONFIDENCE" ?
            `Não foi possível compreender a solicitação após ${handoff.clarification_attempts || 2} tentativas de esclarecimento.` :
            (HANDOFF_LABELS[handoff?.reason] || "");

        const focus = state.focus || {};
        q("[data-ai-focus]").hidden = !focus.selected_product;
        q("[data-ai-focus-text]").textContent = focus.selected_product?.name || "";
        q("[data-ai-presented]").textContent = focus.presented_count > 1 ? `${focus.presented_count} produtos apresentados nesta conversa.` : "";

        const preferences = Object.entries(state.preferences || {});
        q("[data-ai-preferences]").hidden = preferences.length === 0;
        q("[data-ai-preferences-list]").innerHTML = preferences.map(([key, value]) => {
            const shown = key === "max_price" ? money(value) : key === "offer_only" ? (value ? "Sim" : "Não") : (VALUE_LABELS[value] || title(value));
            return `<div><dt>${escape(PREFERENCE_LABELS[key] || key)}</dt><dd>${escape(shown)}</dd></div>`;
        }).join("");

        const events = state.recent_events || [];
        q("[data-ai-events]").hidden = events.length === 0;
        q("[data-ai-events-list]").innerHTML = events.map((event) => `<li><time datetime="${escape(event.created_at)}">${escape(new Date(event.created_at).toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" }))}</time> ${escape(EVENT_LABELS[event.type] || event.type)}</li>`).join("");
        q("[data-ai-resume]").hidden = !actions.resume_ai;
        q("[data-claim]").hidden = actions.claim === false;
        q("[data-close]").hidden = actions.close === false;
        q("[data-ai-generate]").hidden = actions.suggest === false;
        q("[data-ai-mode]").disabled = busy || actions.change_mode === false;
    }
    function controls() {
        if (!active || !selected) return;
        q("[data-status]").textContent = STATUS_LABELS[selected.status] || selected.status;
        q(".inbox-ai").hidden = false;
        q("[data-ai-mode]").value = selected.ai_mode || "OFF";
        renderAIState();
        q("[data-ai-resume]").disabled = busy;
        q("[data-ai-generate]").disabled = busy || generating || !selected.ai_mode || selected.ai_mode === "OFF" || selected.status === "CLOSED";
        q("[data-ai-generate]").textContent = generating ? "Consultando…" : suggestion ? "Gerar novamente" : "Gerar sugestão";
        ["[data-ai-use]", "[data-ai-send]", "[data-ai-suggestion]"].forEach((selector) => {
            q(selector).disabled = busy || !suggestion || selected.status !== "HUMAN";
        });
        q("[data-claim]").disabled = busy || selected.status === "HUMAN";
        q("[data-close]").disabled = busy || selected.status === "CLOSED";
        textarea.disabled = busy || selected.status !== "HUMAN";
        q('[type="submit"]').disabled = busy || selected.status !== "HUMAN" || !textarea.value.trim();
        q('[type="submit"]').textContent = busy ? "Aguarde…" : "Enviar";
        q("[data-older]").hidden = !hasOlder;
        q("[data-older]").disabled = busy;
    }
    function showMessages() {
        const box = q(".inbox-messages");
        const bottom = box.scrollHeight - box.scrollTop - box.clientHeight < 80;
        const rows = [...messages.values()].sort((a, b) => a.created_at.localeCompare(b.created_at) || a.id.localeCompare(b.id));
        box.innerHTML = rows.map((m) => `<article class="inbox-message ${m.sender === "customer" ? "from-customer" : "from-store"}">
            <strong>${m.sender === "customer" ? "Cliente" : m.sender === "system" ? "Sistema" : "Dark District"}</strong><p>${escape(m.content)}</p>
            <time datetime="${escape(m.created_at)}">${escape(date(m.created_at))}</time>${m.delivery_status ? `<small>${escape(DELIVERY_LABELS[m.delivery_status] || "Sem confirmação")}</small>` : ""}</article>`).join("");
        if (bottom) box.scrollTop = box.scrollHeight;
        controls();
    }
    async function loadList() {
        const pageOffset = offset, filter = q("[data-filter]").value;
        const result = await api.get(`/admin/conversations?channel=whatsapp&limit=50&offset=${offset}${filter ? `&status=${filter}` : ""}`);
        if (!active || pageOffset !== offset || filter !== q("[data-filter]").value) return;
        more = result.has_more;
        q("[data-prev]").disabled = offset === 0;
        q("[data-next]").disabled = !more;
        q(".inbox-list").innerHTML = result.items.map((item) => `<button class="inbox-item ${item.status === "WAITING_HUMAN" ? "is-waiting" : ""}" data-id="${escape(item.conversation_id)}" aria-pressed="${selected?.conversation_id === item.conversation_id}">
            <strong>${escape(item.phone)}</strong><span>${escape(STATUS_LABELS[item.status])}</span><p>${escape(item.last_message?.content?.slice(0, 120) || "Sem mensagens")}</p><time>${escape(date(item.last_message?.created_at || item.updated_at))}</time></button>`).join("") || "<p>Nenhuma conversa neste filtro.</p>";
        q(".inbox-list").querySelectorAll("[data-id]").forEach((button) => button.addEventListener("click", () => open(result.items.find((item) => item.conversation_id === button.dataset.id))));
    }
    async function loadMessages(older = false) {
        if (!selected) return;
        const current = revision, conversationPath = path();
        const first = [...messages.values()].sort((a, b) => a.created_at.localeCompare(b.created_at) || a.id.localeCompare(b.id))[0];
        const result = await api.get(`${conversationPath}/messages?limit=50${older && first ? `&before=${first.id}` : ""}`);
        if (!active || current !== revision) return;
        selected.status = result.status;
        selected.ai_mode = result.ai_mode || selected.ai_mode || "OFF";
        selected.handoff_reason = result.handoff_reason;
        selected.ai_state = result.ai_state;
        const latestMessage = result.messages.at(-1)?.id;
        const context = `${selected.conversation_id}:${result.cycle}:${selected.status}:${selected.ai_mode}:${latestMessage}`;
        if (!older && context !== aiContext) { suggestion = ""; aiContext = context; q("[data-ai-suggestion]").textContent = ""; }
        if (older || messages.size <= 50) hasOlder = result.has_more;
        result.messages.forEach((message) => messages.set(message.id, message));
        showMessages();
    }
    async function open(item) {
        if (busy) return;
        if (selected) drafts.set(selected.conversation_id, textarea.value);
        revision++;
        selected = item; messages = new Map(); hasOlder = false;
        suggestion = ""; aiContext = ""; q("[data-ai-suggestion]").textContent = "";
        q(".inbox-ai details").open = window.innerWidth > 720;
        textarea.value = drafts.get(item.conversation_id) || "";
        q("[data-phone]").textContent = item.phone;
        q("[data-empty]").hidden = true; q("[data-conversation]").hidden = false;
        q(".inbox").classList.add("has-selection");
        q(".inbox-messages").textContent = "Carregando…";
        controls(); notify("");
        try { await loadMessages(); } catch (error) { notify(error.message); }
    }
    async function refresh() {
        if (!active || refreshing || busy || document.hidden) return;
        refreshing = true;
        try { await loadList(); if (active && !busy) await loadMessages(); }
        catch (error) { notify(error.message); }
        finally { refreshing = false; }
    }
    async function changeStatus(action) {
        if (busy || !selected) return;
        busy = true; revision++; controls();
        try {
            const result = await api.post(`${path()}/${action}`, {});
            if (!active) return;
            selected.status = result.status; notify(""); await loadMessages();
        } catch (error) { notify(error.message); }
        finally { busy = false; controls(); if (active) refresh(); }
    }
    q("form").addEventListener("submit", async (event) => {
        event.preventDefault();
        const text = textarea.value.trim();
        if (!selected || busy || selected.status !== "HUMAN" || !text) return;
        const id = selected.conversation_id;
        let attempt = retries.get(id);
        if (attempt && attempt.message !== text) {
            notify("Confirme o envio anterior usando o mesmo texto antes de editar a resposta."); return;
        }
        attempt ||= { message_id: crypto.randomUUID(), message: text };
        retries.set(id, attempt);
        busy = true; revision++; controls(); notify("Enviando…");
        try {
            const result = await api.post(`${path()}/messages`, attempt);
            if (!active) return;
            messages.set(result.id, result);
            if (result.delivery_status === "failed") {
                retries.delete(id); notify("Não enviada. O texto foi mantido; você pode tentar novamente.");
            } else if (result.delivery_status === "sending") {
                notify("Envio em andamento. Confira o histórico antes de reenviar.");
            } else {
                retries.delete(id); drafts.delete(id); textarea.value = "";
                notify(result.delivery_status === "sent" ? "Resposta aceita pelo WhatsApp." : "Envio sem confirmação. Confira com o cliente antes de enviar novamente.");
            }
            showMessages();
        } catch (error) {
            if ([401, 403, 404, 409, 422].includes(error.status)) retries.delete(id);
            notify(`${error.message} O texto foi mantido.`);
        } finally { busy = false; controls(); if (active) refresh(); }
    });
    textarea.addEventListener("input", controls);
    q("[data-ai-generate]").addEventListener("click", async () => {
        if (generating || busy || !selected) return;
        const context = aiContext, conversationId = selected.conversation_id;
        generating = true; controls(); q("[data-ai-notice]").textContent = "";
        try {
            const result = await api.post(`${path()}/ai-suggestion`, { force: Boolean(suggestion) });
            if (!active || conversationId !== selected?.conversation_id || context !== aiContext) return;
            suggestion = result.message; q("[data-ai-suggestion]").textContent = suggestion;
        } catch (error) { if (active) q("[data-ai-notice]").textContent = error.message; }
        finally { generating = false; controls(); }
    });
    function useSuggestion() {
        if (!suggestion || busy || selected?.status !== "HUMAN") return false;
        textarea.value = suggestion; textarea.focus(); controls(); return true;
    }
    q("[data-ai-use]").addEventListener("click", useSuggestion);
    q("[data-ai-suggestion]").addEventListener("click", useSuggestion);
    q("[data-ai-send]").addEventListener("click", () => {
        if (useSuggestion()) q("form").dispatchEvent(new window.Event("submit", { bubbles: true, cancelable: true }));
    });
    async function updateAI(resume = false) {
        if (busy || !selected) return;
        busy = true; revision++;
        const mode = q("[data-ai-mode]").value;
        controls();
        try {
            const result = await api.patch(path() + (resume ? "" : "/ai-mode"), resume ? { status: "AI" } : { ai_mode: mode });
            if (!active) return;
            selected.status = result.status; if (result.ai_mode) selected.ai_mode = result.ai_mode;
            notify(resume ? "Atendimento automático retomado." : "Modo da IA atualizado.");
            await loadMessages();
        } catch (error) { notify(error.message); }
        finally { busy = false; controls(); }
    }
    q("[data-ai-mode]").addEventListener("change", () => updateAI());
    q("[data-ai-resume]").addEventListener("click", () => updateAI(true));
    q("[data-claim]").addEventListener("click", () => changeStatus("claim"));
    q("[data-close]").addEventListener("click", () => changeStatus("close"));
    q("[data-back]").addEventListener("click", () => q(".inbox").classList.remove("has-selection"));
    q("[data-older]").addEventListener("click", async () => {
        if (busy) return; busy = true; controls();
        try { await loadMessages(true); } catch (error) { notify(error.message); }
        finally { busy = false; controls(); }
    });
    q("[data-filter]").addEventListener("change", () => { offset = 0; refresh(); });
    q("[data-prev]").addEventListener("click", () => { if (!refreshing) { offset = Math.max(0, offset - 50); refresh(); } });
    q("[data-next]").addEventListener("click", () => { if (!refreshing && more) { offset += 50; refresh(); } });
    const ready = refresh();
    timer = setInterval(refresh, interval);
    return { ready, destroy() { active = false; revision++; clearInterval(timer); drafts.clear(); retries.clear(); root.textContent = ""; } };
}
