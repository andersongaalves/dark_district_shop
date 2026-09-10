import { getProduct } from "../api/products_api.js";
import { formatPrice } from "../utils/format.js";
import { getWhatsAppUrl } from "../utils/urls.js";
import { addCartItem, cartItemKey, cartCount, cartSubtotal, itemForSelection, reconcileCart,
    removeCartItem, validProductId, validQuantity } from "./cart_state.js";
import { loadCart, saveCart, clearCart, CART_STORAGE_KEY } from "./cart_storage.js";
import { createCartView } from "./cart_ui.js";

export function createCartController({ fetchProduct = getProduct,
    storage = { loadCart, saveCart, clearCart } } = {}) {
    let items = storage.loadCart().map((item) => ({ ...item, validated: false, issue: "" }));
    let queue = Promise.resolve(), pending = 0, message = "", persisted = true;
    const listeners = new Set();
    const getSnapshot = () => ({ items: items.map((item) => ({ ...item })),
        count: cartCount(items), subtotal: cartSubtotal(items), busy: pending > 0, message, persisted });
    const emit = () => listeners.forEach((listener) => listener(getSnapshot()));
    const persist = () => { persisted = storage.saveCart(items); };
    const run = (operation) => {
        pending++;
        emit();
        const result = queue.catch(() => {}).then(async () => {
            message = "";
            try { return await operation(); }
            catch (error) { message = error.message; throw error; }
            finally { pending--; emit(); }
        });
        queue = result;
        return result;
    };
    const currentProduct = async (id) => {
        if (!validProductId(id)) throw new Error("ID de produto inválido.");
        return fetchProduct(id);
    };
    const validate = async () => {
        const ids = [...new Set(items.map((item) => item.productId))];
        const responses = await Promise.allSettled(ids.map(currentProduct));
        const products = new Map(ids.map((id, index) => [id, responses[index].status === "fulfilled"
            ? responses[index].value : new Error("API indisponível")]));
        const result = reconcileCart(items, products);
        items = result.items;
        persist();
        return result;
    };
    return {
        getSnapshot,
        subscribe(listener) { listeners.add(listener); listener(getSnapshot()); return () => listeners.delete(listener); },
        add(productId, selection = {}, quantity = 1) {
            return run(async () => {
                const product = await currentProduct(productId);
                if (!product || product.id !== productId) throw new Error("Produto não encontrado.");
                items = addCartItem(items, itemForSelection(product, selection, quantity));
                persist();
                message = "Produto adicionado.";
            });
        },
        setQuantity(key, quantity) {
            return run(async () => {
                if (!validQuantity(quantity)) throw new Error("Informe uma quantidade inteira entre 1 e 999.");
                const item = items.find((entry) => cartItemKey(entry) === key);
                if (!item) throw new Error("Item não encontrado na seleção.");
                const product = await currentProduct(item.productId);
                const products = new Map([[item.productId, product]]);
                const candidate = reconcileCart([{ ...item, quantity }], products).items[0];
                const fresh = reconcileCart([item], products).items[0];
                items = items.map((entry) => cartItemKey(entry) === key ? (candidate.issue ? fresh : candidate) : entry);
                persist();
                if (candidate.issue) throw new Error(candidate.issue);
            });
        },
        remove(key) { return run(() => { items = removeCartItem(items, key); persist(); }); },
        clear() { return run(() => { items = []; persisted = storage.clearCart(); message = "Todos os itens foram removidos."; }); },
        refresh() {
            return run(async () => {
                const result = await validate();
                message = result.changed ? "Preços ou opções foram atualizados. Revise seus itens." : "Disponibilidade atualizada.";
            });
        },
        reload() {
            return run(async () => {
                items = storage.loadCart().map((item) => ({ ...item, validated: false, issue: "" }));
                await validate();
                message = "Itens atualizados.";
            });
        },
        prepareCheckout() {
            return run(async () => {
                if (!items.length) throw new Error("Nenhum item adicionado.");
                const result = await validate();
                if (items.some((item) => !item.validated || item.issue)) throw new Error("Revise os itens sinalizados antes de continuar.");
                if (result.changed) throw new Error("Preços ou opções mudaram. Revise os valores e clique novamente para continuar.");
                const lines = items.map((item) => `${item.quantity} × ${item.title} (ID: ${item.productId}${item.variantId === null ? "" : ` / variante ${item.variantId}`})` +
                    `${item.size ? ` — tamanho ${item.size}` : ""}${item.color ? ` — cor ${item.color}` : ""}: ${formatPrice(Math.round(item.price * 100) * item.quantity / 100)}`);
                return getWhatsAppUrl(["Olá! Tenho interesse nestes produtos:", ...lines,
                    `Subtotal: ${formatPrice(cartSubtotal(items))}`, "Gostaria de confirmar disponibilidade, entrega e pagamento."].join("\n"));
            });
        }
    };
}

let cart, view;
export function getCart() {
    cart ??= createCartController();
    return cart;
}

export function initCart(button) {
    const controller = getCart();
    if (!view) {
        view = createCartView({
            onQuantity: (key, quantity) => controller.setQuantity(key, quantity),
            onRemove: (key) => controller.remove(key), onClear: () => controller.clear(),
            onRefresh: () => controller.refresh(),
            onCheckout: async () => { window.location.assign(await controller.prepareCheckout()); }
        });
        controller.subscribe((state) => {
            view.render(state);
            document.querySelectorAll("[data-cart-count]").forEach((counter) => { counter.textContent = state.count; });
        });
        window.addEventListener("storage", (event) => {
            if (event.key === CART_STORAGE_KEY || event.key === null) controller.reload().catch(() => {});
        });
        controller.refresh().catch(() => {});
    }
    button.addEventListener("click", () => { view.open(); controller.refresh().catch(() => {}); });
    const counter = button.querySelector("[data-cart-count]");
    if (counter) counter.textContent = controller.getSnapshot().count;
}
