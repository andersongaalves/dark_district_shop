import { getProductPrice, isOfferActive } from "../core/products.js";
import { formatDateTime, formatPrice } from "../utils/format.js";
import { escapeHtml } from "../utils/dom.js";

export function renderProductPrice(product, { showDeadline = false } = {}) {
    const price = getProductPrice(product);
    const discounted = price < product.price;
    const active = isOfferActive(product);
    return `${discounted ? `<del class="price-original" aria-label="Preço original">${formatPrice(product.price)}</del> ` : ""}
        <span class="${discounted ? "price-offer" : "price-current"}">${formatPrice(price)}</span>
        ${showDeadline && product.is_offer && product.offer_ends_at ? `<small class="price-deadline">${active
            ? `Oferta até ${escapeHtml(formatDateTime(product.offer_ends_at))}` : "Oferta encerrada"}</small>` : ""}`;
}

// One timer per container, replaced on filtering/re-render. Long deadlines are
// checked in short intervals so detached views release their references promptly.
const expiryTimers = new WeakMap();
export function watchOfferExpiry(container, products, onExpire) {
    clearTimeout(expiryTimers.get(container));
    expiryTimers.delete(container);
    const ends = products.filter((product) => product.is_offer && product.offer_ends_at)
        .map((product) => Date.parse(product.offer_ends_at)).filter((end) => end > Date.now());
    if (!ends.length) return;
    const nextEnd = Math.min(...ends);
    const schedule = () => {
        const timer = setTimeout(() => {
            expiryTimers.delete(container);
            if (!container.isConnected) return;
            if (Date.now() >= nextEnd) onExpire();
            else schedule();
        }, Math.min(60000, Math.max(1, nextEnd - Date.now())));
        timer.unref?.();
        expiryTimers.set(container, timer);
    };
    schedule();
}
