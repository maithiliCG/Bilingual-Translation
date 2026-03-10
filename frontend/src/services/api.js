import axios from 'axios';
import config from '../config';

const API_BASE_URL = config.API_BASE_URL;

// Create axios instance
const api = axios.create({
    baseURL: API_BASE_URL,
    headers: {
        'Content-Type': 'application/json',
    },
});

// Translation API
export const translateAPI = {
    // Upload PDF and start translation
    uploadAndTranslate: (formData) => api.post('/api/translate', formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
    }),

    // Get job status (polling fallback)
    getStatus: (jobId) => api.get(`/api/translate/${jobId}/status`),

    // Get specific page result
    getPage: (jobId, pageNum) => api.get(`/api/translate/${jobId}/page/${pageNum}`),

    // Start SSE stream - returns EventSource URL
    getStreamUrl: (jobId) => `${API_BASE_URL}/api/translate/${jobId}/stream`,

    // Trigger pipeline for pre-uploaded PDF
    startPipeline: (jobId, targetLanguage, translationMode = "bilingual") => {
        const formData = new FormData();
        formData.append('target_language', targetLanguage);
        formData.append('translation_mode', translationMode);
        return api.post(`/api/translate/${jobId}/start`, formData, {
            headers: { 'Content-Type': 'multipart/form-data' },
        });
    },

    // Download URLs — these are direct GET requests (file downloads)
    getDocxDownloadUrl: (jobId) => `${API_BASE_URL}/api/translate/${jobId}/download/docx`,
    getPdfDownloadUrl: (jobId) => `${API_BASE_URL}/api/translate/${jobId}/download/pdf`,
    // Legacy: HTML preview (opens in browser, user can print manually)
    getPdfHtmlUrl: (jobId) => `${API_BASE_URL}/api/translate/${jobId}/download/pdf-html`,
};

// Resource APIs
export const resourceAPI = {
    getLanguages: () => api.get('/api/languages'),
};

// Health API
export const healthAPI = {
    check: () => api.get('/api/health'),
};

export default api;
