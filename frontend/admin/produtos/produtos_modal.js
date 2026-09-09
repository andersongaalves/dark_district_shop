import { renderProductForm } from "./produtos_form.js";
import { addImage, setupImageRemoval, getImages } from "./produtos_imagens.js";
import { addVariant, setupVariantRemoval, getVariants } from "./produtos_variantes.js";

let activeModal;

export function openProductModal({ produto = null, onSubmit }) {
    activeModal?.remove();
    const modal = document.createElement("div");
    activeModal = modal;
    modal.className = "admin-modal";
    modal.setAttribute("role", "dialog");
    modal.setAttribute("aria-modal", "true");
    modal.setAttribute("aria-label", produto ? "Editar produto" : "Novo produto");
    modal.innerHTML = renderProductForm(produto);
    document.body.appendChild(modal);

    const form = modal.querySelector("#produto-form");
    const images = modal.querySelector("#produto-images");
    const variants = modal.querySelector("#produto-variants");
    const submit = form.querySelector('[type="submit"]');
    const errorMessage = document.createElement("p");
    errorMessage.setAttribute("role", "alert");
    form.appendChild(errorMessage);
    let saving = false;

    const close = () => {
        if (saving) return;
        modal.remove();
        if (activeModal === modal) activeModal = null;
    };
    modal.querySelectorAll("[data-close]").forEach((button) => button.addEventListener("click", close));
    modal.querySelector("#add-image").addEventListener("click", () => addImage(images));
    modal.querySelector("#add-variant").addEventListener("click", () => addVariant(variants));
    setupImageRemoval(images);
    setupVariantRemoval(variants);

    form.addEventListener("submit", async (event) => {
        event.preventDefault();
        if (saving) return;
        const data = new FormData(form);
        const payload = {
            id: data.get("id"),
            title: data.get("title"),
            description: data.get("description"),
            price: Number(data.get("price")),
            category: data.get("category"),
            gender: data.get("gender") || "",
            available: data.get("available") === "on",
            featured: data.get("featured") === "on",
            images: getImages(images),
            variants: getVariants(variants)
        };
        saving = true;
        submit.disabled = true;
        errorMessage.textContent = "";
        try {
            await onSubmit(payload);
            saving = false;
            close();
        } catch (error) {
            errorMessage.textContent = error.message;
        } finally {
            saving = false;
            submit.disabled = false;
        }
    });
}
