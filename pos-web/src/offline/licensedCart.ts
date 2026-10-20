/** Call only with cryptographically verified entitlement claims, never cache metadata. */
export function offlineCartLicenseError(features:Record<string,boolean>|undefined,items:{variant_id?:string|null;product_type?:string}[]):string|null{
 if(features===undefined)return null; // Existing unmodified entitlement protocol.
 for(const item of items){
  if(item.variant_id&&features.variants!==true)return 'Your subscription does not include variant sales.';
  if(['composite','bundle'].includes(item.product_type||'')&&features.composites!==true)return 'Your subscription does not include composite product sales.';
  if(!item.product_type&&features.composites!==true)return 'Reconnect to refresh product licensing before completing this sale.';
 }
 return null;
}
