/**
 * GLM-5 Application Configuration
 * Points to GLM-5 backend on port 8000
 */

const getApiBaseUrl = () => {
    const hostname = window.location.hostname;
    if (hostname !== 'localhost' && hostname !== '127.0.0.1' && import.meta.env.DEV) {
        return `http://${hostname}:8000`;
    }
    return import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';
};

const config = {
    API_BASE_URL: getApiBaseUrl(),
};

export default config;
