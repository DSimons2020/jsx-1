const API_URL = process.env.REACT_APP_API_URL || "";

const apiFetch = async (endpoint, options = {}) => {
    
    console.log("REACT_APP_API_URL:", process.env.REACT_APP_API_URL);
    
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
