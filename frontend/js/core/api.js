const LOCAL_API = "http://127.0.0.1:8000";
const PROD_API = "https://dark-district-api.onrender.com";
const LOCAL_HOSTS = new Set(["localhost", "127.0.0.1", "[::1]", "::1"]);

export const API_URL = LOCAL_HOSTS.has(globalThis.location?.hostname)
    ? LOCAL_API
    : PROD_API;

export class ApiError extends Error {
    constructor(message, status = 0) {
        super(message);
        this.name = "ApiError";
        this.status = status;
    }
}

export async function request(endpoint, options = {}) {
    let response;
    let text;
    try {
        response = await fetch(`${API_URL}${endpoint}`, options);
        text = response.status === 204 ? "" : await response.text();
    } catch (error) {
        if (error.name === "AbortError") throw error;
        throw new ApiError("Não foi possível conectar à API. Tente novamente.");
    }

    let data = null;
    if (text) {
        try {
            data = JSON.parse(text);
        } catch {
            if (response.ok) {
                throw new ApiError("A API retornou uma resposta inválida.", response.status);
            }
        }
    }

    if (!response.ok) {
        let message = "Erro na requisição. Tente novamente.";
        if (Array.isArray(data?.detail)) {
            message = data.detail.map((error) =>
                `${error.loc?.join(".") || "campo"}: ${error.msg}`
            ).join("\n");
        } else if (typeof data?.detail === "string") {
            message = data.detail;
        }
        throw new ApiError(message, response.status);
    }
    return data;
}
