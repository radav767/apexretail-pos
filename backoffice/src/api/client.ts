import axios from "axios";

export const api = axios.create({
  baseURL:
    import.meta.env.VITE_API_BASE_URL ||
    "https://api.apexpos.cloud/api",
  timeout: 15000,
});

api.interceptors.request.use((config) => {
  const token = localStorage.getItem("backoffice_token");

  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }

  return config;
});
