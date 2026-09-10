import { renderHeader } from "../components/header.js";
import { renderFooter } from "../components/footer.js";
import { initChat } from "../chat/chat.js";
import { renderFAQ } from "./faq_render.js";

document.addEventListener("DOMContentLoaded", () => {
    renderHeader();
    renderFooter();
    initChat();
    renderFAQ(document.getElementById("faq"));
});
