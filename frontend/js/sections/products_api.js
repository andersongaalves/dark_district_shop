const API_URL = "http://127.0.0.1:8000";

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