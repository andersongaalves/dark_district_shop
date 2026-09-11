import { renderHeader } from "../components/header.js";
import { renderFooter } from "../components/footer.js";
import { initChat } from "../chat/chat.js";

export function initPrivacyPage() {
    renderHeader();
    renderFooter();
    initChat();
}

document.addEventListener("DOMContentLoaded", initPrivacyPage);
