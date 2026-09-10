import { escapeHtml } from "../../js/utils/dom.js";

export function renderConfiguration(container, config, records, actions, selected = null) {
    container.innerHTML = `
        <div class="admin-produtos__header"><h1>${config.title}</h1></div>
        <p>Desative registros usados por produtos para retirá-los das opções de novos cadastros.</p>
        <div class="admin-configuracoes">
            <form class="admin-modal__form">
                <h2>${selected ? "Editar" : "Criar"} ${config.singular}</h2>
                <fieldset>
                    <div class="admin-modal__field"><label for="config-name">Nome</label>
                        <input id="config-name" name="name" maxlength="100" value="${escapeHtml(selected?.name)}" required></div>
                    <div class="admin-modal__field"><label for="config-slug">Slug</label>
                        <input id="config-slug" name="slug" maxlength="120" pattern="[a-z0-9]+(-[a-z0-9]+)*"
                            placeholder="exemplo-de-nome" value="${escapeHtml(selected?.slug)}" required></div>
                    ${config.description ? `<div class="admin-modal__field"><label for="config-description">Descrição</label>
                        <textarea id="config-description" name="description" maxlength="10000">${escapeHtml(selected?.description)}</textarea></div>` : ""}
                    <label><input type="checkbox" name="active" ${selected?.active !== false ? "checked" : ""}> Ativa</label>
                    <div class="admin-modal__actions">
                        ${selected ? '<button type="button" data-cancel>Cancelar edição</button>' : ""}
                        <button type="submit">Salvar</button>
                    </div>
                </fieldset>
            </form>
            <div class="admin-configuracoes__list">
                ${records.length ? records.map((record) => `
                    <article class="admin-produto">
                        <div><strong>${escapeHtml(record.name) || "(Sem nome — edite este registro)"}</strong>
                            <span>${escapeHtml(record.slug)} · ${record.active ? "Ativa" : "Desativada"}</span></div>
                        <div>
                            <button type="button" data-action="edit" data-id="${escapeHtml(record.id)}">Editar</button>
                            <button type="button" data-action="toggle" data-id="${escapeHtml(record.id)}">${record.active ? "Desativar" : "Ativar"}</button>
                            <button type="button" data-action="delete" data-id="${escapeHtml(record.id)}">Excluir</button>
                        </div>
                    </article>`).join("") : "<p>Nenhum registro cadastrado.</p>"}
            </div>
        </div>
        <p role="status" data-config-status aria-live="polite"></p>`;
    const form = container.querySelector("form");
    form.addEventListener("submit", (event) => {
        event.preventDefault();
        const data = new FormData(form);
        const payload = { name: data.get("name").trim(), slug: data.get("slug").trim(), active: data.get("active") === "on" };
        if (config.description) payload.description = data.get("description").trim() || null;
        actions.onSave(payload, selected);
    });
    container.querySelector("[data-cancel]")?.addEventListener("click", () => actions.onEdit(null));
    container.querySelectorAll("[data-action]").forEach((button) => button.addEventListener("click", () => {
        const record = records.find((item) => String(item.id) === button.dataset.id);
        if (!record) return;
        if (button.dataset.action === "edit") actions.onEdit(record);
        if (button.dataset.action === "toggle") actions.onToggle(record);
        if (button.dataset.action === "delete") actions.onDelete(record);
    }));
}

export function setConfigurationStatus(container, message, busy = false) {
    container.querySelector("[data-config-status]").textContent = message;
    container.querySelector("fieldset").disabled = busy;
    container.querySelectorAll("[data-action]").forEach((button) => { button.disabled = busy; });
}
