import { postForm } from "./api.js";

export async function login(
    username,
    password
) {
    const data = await postForm(
        "/auth/login",
        {
            username,
            password
        }
    );

    localStorage.setItem(
        "access_token",
        data.access_token
    );

    return data;
}

export function logout() {
    localStorage.removeItem(
        "access_token"
    );
}

export function isAuthenticated() {
    return Boolean(
        localStorage.getItem(
            "access_token"
        )
    );
}