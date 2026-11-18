import axios from 'axios';
import { clearBusinessContext, contextGeneration, installBusinessContext } from './businessSession';

export const api = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || 'https://api.apexpos.cloud/api',
  timeout: 15000,
  withCredentials: true,
});
let renewing: Promise<boolean> | null = null;
export function refreshBusinessSession(): Promise<boolean> {
  if (!renewing) {
    const epoch = contextGeneration();
    renewing = api.post('/auth/refresh').then(({data}) => installBusinessContext(data, epoch))
      .catch(() => { if (epoch === contextGeneration()) clearBusinessContext(); return false; })
      .finally(() => { renewing = null; });
  }
  return renewing;
}
export async function beginBusinessLogin() {
  clearBusinessContext();
  if (renewing) await renewing;
  await api.post('/auth/logout-browser');
  return contextGeneration();
}
api.interceptors.request.use((config) => {
  (config as typeof config & { _businessGeneration: number })._businessGeneration = contextGeneration();
  const token = sessionStorage.getItem('backoffice_token');
  if (token && !config.url?.startsWith('/auth/')) config.headers.Authorization = `Bearer ${token}`;
  return config;
});
api.interceptors.response.use(response => response, async (error) => {
  const config = error.config;
  if (error.response?.status !== 401 || !config || config._businessGeneration !== contextGeneration() || config.url?.startsWith('/auth/') || config._renewed) throw error;
  const epoch = contextGeneration();
  const previousCompany = sessionStorage.getItem('backoffice_company_id');
  const renewed = await refreshBusinessSession();
  // Never replay a mutation or a request from another account context.
  if (renewed && epoch === contextGeneration() && previousCompany === sessionStorage.getItem('backoffice_company_id') &&
      ['get', 'head'].includes(config.method || 'get')) {
    config._renewed = true;
    return api.request(config);
  }
  throw error;
});
