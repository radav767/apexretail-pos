export function readAuthEntry(location: Pick<Location, 'hash' | 'pathname' | 'search'>, history: Pick<History, 'replaceState'>) {
  const fragment = new URLSearchParams(location.hash.slice(1));
  const reset = fragment.get('reset'); const handoff = fragment.get('handoff');
  if (reset !== null || handoff !== null) history.replaceState(null, '', location.pathname + location.search);
  return { reset, handoff };
}
