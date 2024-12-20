const API_URL = process.env.REACT_APP_API_URL || "";

const apiFetch = async (endpoint, options = {}) => {
    const url = `${API_URL}${endpoint.startsWith("/") ? endpoint : `/${endpoint}`}`;

    console.log("API Fetch URL:", url); // Debugging log

    const response = await fetch(url, {
        ...options,
        headers: {
            "Content-Type": "application/json",
            ...options.headers,
        },
    });

    if (!response.ok) {
        throw new Error(`API Error: ${response.status}`);
    }

    return response.json();
};

export default apiFetch;
