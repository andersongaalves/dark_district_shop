import { renderHeader } from "../components/header.js";
import { renderFooter } from "../components/footer.js";
import { renderSobre } from "./sobre_render.js";
import { initChat } from "../chat/chat.js";

document.addEventListener("DOMContentLoaded", () => {
    renderHeader();
    renderSobre(document.getElementById("sobre"));
    renderFooter();
    initChat();
});
