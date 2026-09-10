import { createChatController } from "./chat_state.js";
import { createChatView } from "./chat_ui.js";

let chat;
export function initChat() {
    if (chat && document.getElementById("dd-chat")) return chat;
    const controller = createChatController();
    const ownerDocument = document;
    let poll;
    const stopPolling = () => { clearTimeout(poll); poll = null; };
    const view = createChatView({
        onOpen: () => controller.open(), onClose: stopPolling,
        onSend: (message) => controller.send(message), onRetry: () => controller.retry(),
        onDiscard: () => controller.discard(), onEnd: () => controller.end()
    });
    const unsubscribe = controller.subscribe((state) => {
        view.render(state);
        stopPolling();
        if (view.isOpen() && state.hasSession && state.status !== "AI" && !state.busy && !state.error) {
            poll = setTimeout(() => {
                if (view.isOpen() && !document.hidden) controller.open();
            }, 15000);
            poll.unref?.();
        }
    });
    const onVisible = () => {
        if (!document.hidden && view.isOpen() && controller.getSnapshot().status !== "AI") controller.open();
    };
    document.addEventListener("visibilitychange", onVisible);
    chat = { controller, view, destroy() {
        stopPolling(); unsubscribe(); ownerDocument.removeEventListener("visibilitychange", onVisible); view.destroy(); chat = null;
    } };
    return chat;
}
