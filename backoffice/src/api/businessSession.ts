export type BusinessContext = { token: string; company_id: string; user: { id: string } };
let generation = 0;
export const contextGeneration = () => generation;
export function clearBusinessContext() {
  generation += 1;
  for (const store of [localStorage, sessionStorage]) {
    store.removeItem('backoffice_token'); store.removeItem('backoffice_company_id'); store.removeItem('backoffice_user_id');
  }
  window.dispatchEvent(new Event('business-context-changed'));
}
export function installBusinessContext(context: BusinessContext, expected = generation) {
  if (expected !== generation) return false;
  const previousUser = sessionStorage.getItem('backoffice_user_id');
  if (previousUser && previousUser !== context.user.id) { clearBusinessContext(); return false; }
  localStorage.removeItem('backoffice_token'); localStorage.removeItem('backoffice_company_id');
  sessionStorage.setItem('backoffice_user_id', context.user.id);
  sessionStorage.setItem('backoffice_token', context.token);
  sessionStorage.setItem('backoffice_company_id', context.company_id);
  window.dispatchEvent(new Event('business-context-changed'));
  return true;
}
// Migrate away from persistent bearer credentials without touching POS storage.
localStorage.removeItem('backoffice_token'); localStorage.removeItem('backoffice_company_id');
