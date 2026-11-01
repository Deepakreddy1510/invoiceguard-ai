import { apiFetch } from './client';
import { PdfPreview } from './ui';
import { useCallback, useEffect, useState } from 'react';

type Evidence = {value: string | null; verified: boolean; page: number | null; quote: string | null; method: string | null; document_id: string};
type LineItem = Record<string,Evidence>;
type Event = {id: number;stage: string;outcome: string;attempt: number;detail: string;created_at: string};
type Rule = {rule_id: string;outcome: string;explanation: string;actual: string | null;expected: string | null};
type RunSummary = {invoice_number?:string|null;vendor_name?:string|null;id: string;document_id: string;parent_run_id: string|null;status: string;attempt: number;outcome: string|null;created_at: string;error: string|null};
type Detail = RunSummary & {review_task_id?:string|null;events: Event[];pages: {page:number;text:string;method:string}[]|null;extraction: {provider:string;fallback_reason:string|null;fields:Record<string, unknown>}|null;decision:{outcome:string;rules:Rule[];summary:Record<string,unknown>;policy_version:string}|null};
async function request<T>(path:string, init?:RequestInit):Promise<T> {
  const response=await apiFetch('/api/v1'+path,init);
  if(!response.ok) {
    const body=await response.json().catch(()=>({detail:'Request failed.'}));
    throw new Error(typeof body.detail==='string'?body.detail:'Request failed. Check server readiness.');
  }
  return response.json();
}
const dateTime=(v:string)=>new Date(v).toLocaleString();
export default function InvoiceWorkflow({initialRunId,onSelectRun}:{initialRunId?:string;onSelectRun?:(id:string)=>void}={}) {
  const [runs,setRuns]=useState<RunSummary[]>([]);
  const [selected,setSelected]=useState<string|null>(()=>initialRunId??new URLSearchParams(window.location.search).get('run'));
  const [detail,setDetail]=useState<Detail|null>(null);
  const [file,setFile]=useState<File|null>(null);
  const [error,setError]=useState('');
  const [message,setMessage]=useState('');
  const [busy,setBusy]=useState(false);
  const [offset,setOffset]=useState(0);
  const selectRun=useCallback((id:string)=>{
    if(onSelectRun){onSelectRun(id);return;}setSelected(id);setDetail(null);
    const url=new URL(window.location.href);url.searchParams.set('run',id);window.history.replaceState({},'',url);
  },[onSelectRun]);
  useEffect(()=>{
    let stopped=false;
    async function refresh() {
      try {
        const history=await request<{runs:RunSummary[]}>(`/runs?offset=${offset}&limit=20`);
        const record=selected?await request<Detail>('/runs/'+selected):null;
        if(!stopped){setRuns(history.runs);setDetail(record);}
      } catch(e){if(!stopped)setError((e as Error).message);}
    }
    void refresh();
    // Polling observes persisted state. It never advances workflow stages locally.
    const interval=window.setInterval(refresh,1500);
    return ()=>{stopped=true;window.clearInterval(interval);};
  },[selected,offset]);
  async function upload(e:React.FormEvent) {
    e.preventDefault();if(!file)return;
    setBusy(true);setError('');setMessage('');
    try {
      const body=new FormData();body.append('file',file);
      const result=await request<{run_id:string;replayed:boolean}>('/documents',{method:'POST',body,headers:{'Idempotency-Key':crypto.randomUUID()}});
      setMessage(result.replayed?'Already uploaded — showing the existing processing record.':'PDF accepted and queued for the worker.');
      selectRun(result.run_id);setOffset(0);
    } catch(e){setError((e as Error).message);}
    finally{setBusy(false);}
  }
  async function retry() {
    if(!selected)return;setBusy(true);
    try {const result=await request<{run_id:string}>('/runs/'+selected+'/retry',{method:'POST'});selectRun(result.run_id);setMessage('Retry queued. The original failed run remains in history.');}
    catch(e){setError((e as Error).message);}finally{setBusy(false);}
  }
  const fields=detail?.extraction?.fields;
  const scalarFields=fields?Object.entries(fields).filter(([,v])=>typeof v==='object' && v!==null && !Array.isArray(v)) as [string,Evidence][]:[];
  return <section className="workflow" aria-labelledby="processing-title">
    <div className="panel upload-panel"><p className="eyebrow">REAL PDF → EXPLAINABLE DECISION</p><h2 id="processing-title">Process an invoice</h2><p>Up to 10 MiB and 20 pages. Digital text and English scanned PDFs are supported.</p>
      <form onSubmit={upload}><label htmlFor="invoice-pdf">Invoice PDF</label><input id="invoice-pdf" type="file" accept="application/pdf,.pdf" onChange={e=>setFile(e.target.files?.[0]??null)} required/><button disabled={!file||busy} type="submit">{busy?'Submitting…':'Upload and process'}</button></form>
      {file&&<details className="source-panel"><summary>Selected PDF preview</summary><PdfPreview file={file}/></details>}
      {message&&<p role="status">{message}</p>}{error&&<p role="alert">{error}</p>}
    </div>
    <div className="workflow-columns">
      <section className="panel history"><h2>Processing history</h2><p>Runs include retries and duplicate assessments; they are not unique invoice counts.</p>
        {!runs.length&&<p>No processing runs on this page.</p>}
        {runs.map(run=><button className={'history-run '+(run.id===selected?'selected':'')} key={run.id} onClick={()=>selectRun(run.id)}><strong>{run.invoice_number??'Unidentified invoice'}</strong><span>{run.vendor_name??'Vendor unresolved'}</span><span>{run.outcome??'Awaiting decision'} · Processing {run.status}</span><span>{dateTime(run.created_at)}</span><code>{run.id}</code></button>)}
        <button disabled={offset===0} onClick={()=>setOffset(Math.max(0,offset-20))}>Newer</button><button disabled={runs.length<20} onClick={()=>setOffset(offset+20)}>Older</button>
      </section>
      <section className="panel run-detail" aria-label="Processing run">
        {!detail?<p>{selected?'Loading persisted run…':'Select a run to inspect its execution and decision.'}</p>:<>
          <div className="run-heading"><h2>{detail.decision?.outcome??detail.status}</h2><span className="badge">Processing: {detail.status}</span></div>
          <p><code data-testid="run-id">{detail.id}</code><br/>{dateTime(detail.created_at)} · attempt {detail.attempt}</p>
          <div className="toolbar"><a className="button" href={`/audit?run_id=${detail.id}`}>Audit trail</a>{detail.review_task_id?<a className="button primary" href={'/reviews/'+detail.review_task_id}>Open exception review</a>:<button onClick={async()=>{try{const task=await request<{id:string}>('/runs/'+detail.id+'/review',{method:'POST'});window.location.assign('/reviews/'+task.id);}catch(e){setError((e as Error).message);}}}>Request source correction</button>}</div><details className="source-panel"><summary>Original PDF and evidence</summary><PdfPreview documentId={detail.document_id}/></details>
          {detail.parent_run_id&&<p>Retry of <button onClick={()=>selectRun(detail.parent_run_id!)}>{detail.parent_run_id}</button></p>}
          {detail.status==='QUEUED'&&<p>Waiting for the Python worker. Start it with <code>python -m app.worker.main</code> in the backend environment.</p>}
          {detail.error&&<p role="alert">{detail.error}</p>}
          {detail.status==='FAILED'&&<button disabled={busy} onClick={retry}>Retry failed run</button>}
          <h3>Actual execution events</h3><ol className="timeline">{detail.events.map(event=><li key={event.id}><strong>{event.stage.replaceAll('_',' ')} · {event.outcome}</strong><span>{dateTime(event.created_at)} · attempt {event.attempt}</span><p>{event.detail}</p></li>)}</ol>
          {detail.extraction&&<><h3>Extracted fields</h3><p>Provider: {detail.extraction.provider}. {detail.extraction.fallback_reason}</p><div className="table-scroll"><table><thead><tr><th>Field / value</th><th>Source evidence</th></tr></thead><tbody>{scalarFields.map(([name,value])=><tr key={name}><td>{name}<strong className="vendor">{value.value??'Missing / ambiguous'}</strong></td><td><span className={value.verified?'':'warning'}>{value.verified?'Source verified':'Requires review'}</span><span className="vendor">Page {value.page??'—'} · {value.method??'No evidence'}</span><q>{value.quote??'No supported source quote'}</q></td></tr>)}</tbody></table></div>
          {Array.isArray(fields?.items)&&<details><summary>Extracted line items ({fields.items.length})</summary><div className="table-scroll"><table><thead><tr><th>Item</th><th>Quantity / unit price</th><th>Net / tax / gross</th></tr></thead><tbody>{(fields.items as LineItem[]).map((item,index)=><tr key={index}><td>{item.sku.value??'Unresolved item'}<span className="vendor">Page {item.sku.page??'—'} · {Object.values(item).every(v=>v.verified)?'Source verified':'Review required'}</span></td><td>{item.quantity.value??'—'} × {item.unit_price.value??'—'}</td><td>{item.net.value??'—'} / {item.tax.value??'—'} / {item.gross.value??'—'}</td></tr>)}</tbody></table></div></details>}
          </>}
          {detail.decision&&<><h3>Financial decision</h3><p>Policy: {detail.decision.policy_version}. Payment has not been executed.</p><dl className="financial-summary">{Object.entries(detail.decision.summary).filter(([k])=>!['payment_executed'].includes(k)).map(([key,value])=><div key={key}><dt>{key.replaceAll('_',' ')}</dt><dd>{value==null?'Unresolved':String(value)}</dd></div>)}</dl><h3>Rule results</h3><ul className="rules">{detail.decision.rules.map(rule=><li key={rule.rule_id}><strong>{rule.outcome} · {rule.rule_id}</strong><p>{rule.explanation}</p>{rule.actual!==null&&<span>Actual: {rule.actual} · Expected: {rule.expected??'—'}</span>}</li>)}</ul></>}
        </>}
      </section>
    </div>
  </section>;
}
