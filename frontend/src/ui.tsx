import { useEffect,useState } from 'react';
import { apiFetch,request } from './client';
export function useResource<T>(path:string,interval=0){
  const [data,setData]=useState<T|null>(null);const [error,setError]=useState('');const [refresh,setRefresh]=useState(0);
  useEffect(()=>{let cancelled=false;setData(null);const load=async()=>{try{const value=await request<T>(path);if(!cancelled){setData(value);setError('');}}catch(e){if(!cancelled)setError((e as Error).message);}};void load();const id=interval?window.setInterval(load,interval):null;return()=>{cancelled=true;if(id)window.clearInterval(id);};},[path,interval,refresh]);
  return {data,error,reload:()=>setRefresh(v=>v+1)};
}
export function Notice({error}:{error:string}){return error?<div className="error-banner" role="alert">{error}</div>:null;}
export function Status({value}:{value:string}){return <span className={'status status-'+value.toLowerCase()}>{value.replaceAll('_',' ')}</span>;}
export function PageTitle({eyebrow,title,description}:{eyebrow:string;title:string;description:string}){return <div className="page-title"><p className="eyebrow">{eyebrow}</p><h1>{title}</h1><p>{description}</p></div>;}
export function PdfPreview({documentId,file}:{documentId?:string;file?:File|null}){
  const [url,setUrl]=useState('');const [error,setError]=useState('');
  useEffect(()=>{let cancelled=false;let object='';setError('');setUrl('');const load=async()=>{try{const blob=file??(await (async()=>{const response=await apiFetch('/api/v1/documents/'+documentId+'/content');if(!response.ok)throw new Error('Document preview could not be loaded.');return response.blob();})());object=URL.createObjectURL(blob);if(!cancelled)setUrl(object);else URL.revokeObjectURL(object);}catch(e){if(!cancelled)setError((e as Error).message);}};if(file||documentId)void load();return()=>{cancelled=true;if(object)URL.revokeObjectURL(object);};},[documentId,file]);
  if(!file&&!documentId)return null;
  return <section className="pdf-preview"><Notice error={error}/>{url?<><a href={url} target="_blank" rel="noreferrer">Open source PDF</a><iframe title="Original invoice PDF" src={url}/></>:<p>Loading document evidence…</p>}</section>;
}
