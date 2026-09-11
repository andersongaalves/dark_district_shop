import { renderHeader } from "../components/header.js";
import { renderFooter } from "../components/footer.js";
import { initChat } from "../chat/chat.js";
import { getWhatsAppUrl } from "../utils/urls.js";

export function renderPrivacyContacts() {
    document.querySelectorAll("[data-privacy-contact]").forEach((link) => {
        link.href = getWhatsAppUrl();
    });
}

export function initPrivacyPage() {
    renderPrivacyContacts();
    renderHeader();
    renderFooter();
    initChat();
}

document.addEventListener("DOMContentLoaded", initPrivacyPage);
