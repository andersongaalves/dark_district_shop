import { renderHeader } from "./components/header.js";
import { renderHero } from "./sections/hero.js";
import { renderFeatured } from "./sections/featured.js";
import { renderFooter } from "./components/footer.js";




document.addEventListener("DOMContentLoaded", () => {
    renderHeader();
    renderHero();
    renderFeatured();
    renderFooter();
});