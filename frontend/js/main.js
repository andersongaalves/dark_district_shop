import { renderHeader } from "./components/header.js";
import { renderHero } from "./sections/hero.js";
import { renderFeatured, renderOffers } from "./sections/featured.js";
import { renderFooter } from "./components/footer.js";
import { initChat } from "./chat/chat.js";




document.addEventListener("DOMContentLoaded", () => {
    renderHeader();
    renderHero();
    renderFeatured();
    renderOffers();
    renderFooter();
    initChat();
});
