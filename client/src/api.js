const API_URL = "http://jsx-1.railway.internal/api";

const apiFetch = async (endpoint, options = {}) => {
    
    if (!endpoint || typeof endpoint !== "string") {
        throw new Error("Invalid API endpoint");
    }

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
