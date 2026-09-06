import { login } from "../auth.js";

const form = document.querySelector("#login-form");
const error = document.querySelector("#login-error");

form?.addEventListener("submit", async (event) => {
    event.preventDefault();

    error.textContent = "";

    const formData = new FormData(form);

    const username = formData.get("username");
    const password = formData.get("password");

    try {
        await login(username, password);

        window.location.href = "../index.html";
    } catch (err) {
        console.error("Erro ao fazer login:", err);

        error.textContent =
            "Usuário ou senha incorretos.";
    }
});