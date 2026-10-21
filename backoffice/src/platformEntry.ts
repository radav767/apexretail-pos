// Host selection is UI routing, never an authentication/authorization boundary.
export function isPlatformHost(hostname:string):boolean {
  return hostname.toLowerCase().replace(/\.$/,'')==='admin.apexpos.cloud';
}

export function platformEntry(hostname:string,search:string):boolean {
  return isPlatformHost(hostname)||new URLSearchParams(search).get('console')==='platform';
}

export function platformApiBase(hostname:string,businessBase:string|undefined):string|undefined {
  // Dedicated vhost exposes only /api/platform/, preserving the upstream URI.
  return isPlatformHost(hostname)?'/api':businessBase;
}
