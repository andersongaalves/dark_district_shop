const LOCAL_API = "http://127.0.0.1:8000";
const PROD_API = "https://dark-district-api.onrender.com";

const API_URL = window.location.hostname === "localhost" ||
                window.location.hostname === "127.0.0.1"
    ? LOCAL_API
    : PROD_API;

function getToken() {
    return localStorage.getItem("access_token");
}

async function request(
    endpoint,
    options = {}
) {
    const token = getToken();

    const headers = {
        "Content-Type": "application/json",
        ...options.headers
    };

    if (token) {
        headers.Authorization = `Bearer ${token}`;
    }

    const response = await fetch(
        `${API_URL}${endpoint}`,
        {
            ...options,
            headers
        }
    );

    if (response.status === 204) {
        return null;
    }

    const data = await response.json();

    if (!response.ok) {
        let message = "Erro na requisição.";

        if (Array.isArray(data.detail)) {
            message = data.detail
                .map((error) => {
                    const location = error.loc
                        ? error.loc.join(".")
                        : "campo";

                    return `${location}: ${error.msg}`;
                })
                .join("\n");
        } else if (data.detail) {
            message = data.detail;
        }

        throw new Error(message);
    }

    return data;
}

export function get(endpoint) {
    return request(endpoint);
}

export function post(endpoint, data) {
    return request(endpoint, {
        method: "POST",
        body: JSON.stringify(data)
    });
}

export function postForm(endpoint, data) {
    const body = new URLSearchParams();

    Object.entries(data).forEach(
        ([key, value]) => {
            body.append(key, value);
        }
    );

    return request(endpoint, {
        method: "POST",
        headers: {
            "Content-Type":
                "application/x-www-form-urlencoded"
        },
        body
    });
}

export function put(endpoint, data) {
    return request(endpoint, {
        method: "PUT",
        body: JSON.stringify(data)
    });
}

export function deleteRequest(endpoint) {
    return request(endpoint, {
        method: "DELETE"
    });
}