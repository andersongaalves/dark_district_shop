import { get, post } from "../api.js";
import { escapeHtml } from "../../js/utils/dom.js";

export const STATUS_LABELS = { WAITING_HUMAN: "Aguardando", HUMAN: "Em atendimento", CLOSED: "Encerrada", AI: "Aguardando" };
const DELIVERY_LABELS = { sending: "Enviando…", sent: "Aceita pelo WhatsApp", failed: "Falha no envio", uncertain: "Envio sem confirmação — confira antes de reenviar", cancelled: "Não enviada" };
const date = (value) => new Date(value).toLocaleString("pt-BR");
const escape = (value) => escapeHtml(String(value ?? ""));

export function mountInbox(root, { api = { get, post }, interval = 5000 } = {}) {
    let active = true, selected = null, busy = false, refreshing = false, revision = 0, timer;
    let messages = new Map(), hasOlder = false, offset = 0, more = false;
    const drafts = new Map(), retries = new Map();
    root.innerHTML = `<h1>WhatsApp</h1><p>Atendimento humano · atualização automática</p>
        <p class="inbox-notice" role="status"></p>
        <div class="inbox"><aside class="inbox-sidebar" aria-label="Conversas">
        <label>Filtrar <select data-filter><option value="">Todas</option><option value="WAITING_HUMAN">Aguardando</option><option value="HUMAN">Em atendimento</option><option value="CLOSED">Encerradas</option></select></label>
        <div class="inbox-list"></div><div class="inbox-pagination"><button data-prev>Anterior</button><button data-next>Próxima</button></div></aside>
        <section class="inbox-thread" aria-label="Histórico da conversa"><p data-empty>Selecione uma conversa.</p>
        <div data-conversation hidden><header class="inbox-toolbar"><button data-back>Voltar</button><strong data-phone></strong><span data-status></span><button data-claim>Assumir atendimento</button><button data-close>Encerrar atendimento</button></header>
        <button data-older hidden>Carregar mensagens anteriores</button><div class="inbox-messages" aria-label="Mensagens"></div>
        <form><label for="inbox-text">Sua resposta</label><textarea id="inbox-text" maxlength="2000" rows="3" required></textarea><button type="submit">Enviar</button></form></div></section></div>`;
    const q = (selector) => root.querySelector(selector);
    const textarea = q("textarea");
    const notify = (text) => { if (active) q(".inbox-notice").textContent = text; };
    const path = () => `/admin/conversations/${selected.conversation_id}`;
    function controls() {
        if (!active || !selected) return;
        q("[data-status]").textContent = STATUS_LABELS[selected.status] || selected.status;
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
        if (older || messages.size <= 50) hasOlder = result.has_more;
        result.messages.forEach((message) => messages.set(message.id, message));
        showMessages();
    }
    async function open(item) {
        if (busy) return;
        if (selected) drafts.set(selected.conversation_id, textarea.value);
        revision++;
        selected = item; messages = new Map(); hasOlder = false;
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
