import { get, post, patch, deleteRequest } from "../api.js";
import { escapeHtml } from "../../js/utils/dom.js";
import { renderConfiguration, setConfigurationStatus } from "./configuracoes_ui.js";

const CONFIGURATIONS = Object.freeze({
    categorias: { title: "Categorias", singular: "categoria", endpoint: "/categorias" },
    colecoes: { title: "Coleções", singular: "coleção", endpoint: "/colecoes", description: true }
});

export async function carregarConfiguracoes({ resource = "categorias", isCurrent = () => true } = {}) {
    const config = CONFIGURATIONS[resource];
    const container = document.querySelector("#admin-configuracoes");
    if (!config || !container) return;
    let records = [], saving = false;
    const recordPath = (record) => `${config.endpoint}/${encodeURIComponent(record.id)}`;
    const render = (selected = null) => {
        if (isCurrent()) renderConfiguration(container, config, records, actions, selected);
    };
    const refresh = async () => { records = await get(config.endpoint); render(); };
    const run = async (operation) => {
        if (saving || !isCurrent()) return;
        saving = true;
        setConfigurationStatus(container, "Salvando…", true);
        try {
            await operation();
            await refresh();
        } catch (error) {
            if (isCurrent()) setConfigurationStatus(container, error.message);
        } finally {
            saving = false;
            if (isCurrent()) setConfigurationStatus(container, container.querySelector("[data-config-status]").textContent, false);
        }
    };
    const actions = {
        onEdit: render,
        onSave: (payload, selected) => run(() => selected
            ? patch(recordPath(selected), payload) : post(config.endpoint, payload)),
        onToggle: (record) => run(() => patch(recordPath(record), { active: !record.active })),
        onDelete: (record) => {
            if (confirm(`Excluir "${record.name}"? Produtos vinculados impedem a exclusão.`)) {
                run(() => deleteRequest(recordPath(record)));
            }
        }
    };
    try {
        await refresh();
    } catch (error) {
        if (!isCurrent()) return;
        container.innerHTML = `<p role="alert">${escapeHtml(error.message)}</p><button type="button">Tentar novamente</button>`;
        container.querySelector("button").addEventListener("click", () => carregarConfiguracoes({ resource, isCurrent }));
    }
}
