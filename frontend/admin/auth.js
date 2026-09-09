import { request } from "../js/core/api.js";

const TOKEN_KEY = "access_token";

export function getToken() {
    return localStorage.getItem(TOKEN_KEY);
}

export async function login(
    username,
    password
) {
    const data = await request(
        "/auth/login",
        {
            method: "POST",
            headers: { "Content-Type": "application/x-www-form-urlencoded" },
            body: new URLSearchParams({ username, password })
        }
    );

    localStorage.setItem(
        TOKEN_KEY,
        data.access_token
    );

    return data;
}

export function logout() {
    localStorage.removeItem(
        TOKEN_KEY
    );
}

export function isAuthenticated() {
    return Boolean(getToken());
}