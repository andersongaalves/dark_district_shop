import { request } from "../js/core/api.js";
import { getToken, logout } from "./auth.js";
import { ROUTES } from "../js/utils/urls.js";

async function adminRequest(endpoint, options = {}) {
    const headers = new Headers(options.headers);
    const token = getToken();
    if (token) headers.set("Authorization", `Bearer ${token}`);
    if (options.body) headers.set("Content-Type", "application/json");
    try {
        return await request(endpoint, { ...options, headers });
    } catch (error) {
        if (error.status === 401) {
            logout();
            window.location.assign(ROUTES.login);
        }
        throw error;
    }
}

export function get(endpoint) {
    return adminRequest(endpoint);
}

export function post(endpoint, data) {
    return adminRequest(endpoint, { method: "POST", body: JSON.stringify(data) });
}

export function put(endpoint, data) {
    return adminRequest(endpoint, { method: "PUT", body: JSON.stringify(data) });
}

export function deleteRequest(endpoint) {
    return adminRequest(endpoint, { method: "DELETE" });
}
