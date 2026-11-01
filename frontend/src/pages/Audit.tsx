import { useState } from 'react';
import { Link,useSearchParams } from 'react-router-dom';
import { when } from '../client';
import { Notice,PageTitle,useResource } from '../ui';
export default function Audit(){
 const [params]=useSearchParams();const [offset,setOffset]=useState(0);const [search,setSearch]=useState('');
 const path='/audit-events?'+new URLSearchParams({...Object.fromEntries(params),offset:String(offset),limit:'50'});
 const {data,error}=useResource<{events:any[]}>(path,5000);
 return <><PageTitle eyebrow="CONTROL / AUDIT HISTORY" title="A record you can follow." description="Persisted processing events, decisions and attributed reviewer actions. Previous records remain visible."/><Notice error={error}/><div className="toolbar"><input aria-label="Filter audit events" placeholder="Filter action or actor on this page" value={search} onChange={e=>setSearch(e.target.value)}/><button disabled={offset===0} onClick={()=>setOffset(Math.max(0,offset-50))}>Newer</button><button disabled={(data?.events.length??0)<50} onClick={()=>setOffset(offset+50)}>Older</button></div><section className="panel audit-list">{data?.events.filter(e=>(e.action+' '+e.actor).toLowerCase().includes(search.toLowerCase())).map(event=><article key={event.id}><div><strong>{event.action.replaceAll('_',' ')}</strong><span>{when(event.created_at)} · {event.actor}</span></div>{event.run_id&&<Link to={'/runs/'+event.run_id}>Open run →</Link>}<details><summary>Event details</summary><pre>{JSON.stringify(event.detail,null,2)}</pre></details></article>)}{data&&!data.events.length&&<div className="empty-state">No audit events match this selection.</div>}</section></>;
}
