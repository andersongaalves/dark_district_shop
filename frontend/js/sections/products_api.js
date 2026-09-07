const LOCAL_API = "http://127.0.0.1:8000";
const PROD_API = "https://dark-district-api.onrender.com";

const API_URL = window.location.hostname === "127.0.0.1" ||
                window.location.hostname === "localhost"
    ? LOCAL_API
    : PROD_API;

export async function getProducts() {
    const response = await fetch(`${API_URL}/produtos`);

    if (!response.ok) {
        throw new Error("Não foi possível carregar os produtos.");
    }

    return await response.json();
}

export async function getProduct(id) {
    const response = await fetch(`${API_URL}/produtos/${id}`);

    if (!response.ok) {
        if (response.status === 404) {
            return null;
        }

        throw new Error("Não foi possível carregar o produto.");
    }

    return await response.json();
}