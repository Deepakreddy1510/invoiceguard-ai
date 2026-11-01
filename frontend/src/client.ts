let accessToken: (()=>Promise<string>) | null = null;
export function setAccessToken(getter:(()=>Promise<string>)|null){accessToken=getter;}
export async function apiFetch(path:string,init?:RequestInit):Promise<Response>{
  if(!accessToken)return fetch(path,init);
  const token=await accessToken();const headers=new Headers(init?.headers);headers.set('Authorization','Bearer '+token);
  return fetch(path,{...init,headers});
}
export async function request<T>(path:string,init?:RequestInit):Promise<T>{
  const response=await apiFetch('/api/v1'+path,init);
  if(!response.ok){const body=await response.json().catch(()=>({detail:'Request failed.'}));throw new Error(typeof body.detail==='string'?body.detail:'Request rejected. Check your fields and access.');}
  return response.json();
}
export function jsonPost(path:string,body:unknown){return request<any>(path,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});}
export function money(value:string|number|null|undefined,currency:string='USD'){
  if(value==null)return '—';const raw=String(value);if(!/^-?\d+(\.\d+)?$/.test(raw))return raw;
  const [whole,fraction='']=raw.split('.');const places=currency==='JPY'?0:currency==='KWD'?3:2;
  const decimals=fraction.replace(/0+$/,'').padEnd(places,'0');
  return currency+' '+whole.replace(/\B(?=(\d{3})+(?!\d))/g,',')+(decimals?'.'+decimals:'');
}
export function when(value:string|null|undefined){return value?new Date(value).toLocaleString(): '—';}
