import { cleanup, render, screen, fireEvent } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import InvoiceWorkflow from './InvoiceWorkflow';
afterEach(()=>{cleanup();vi.unstubAllGlobals();window.history.replaceState({},'','/');});
const failed={id:'failed-run',document_id:'doc',parent_run_id:null,status:'FAILED',attempt:1,outcome:null,created_at:'2026-06-15T00:00:00Z',error:'OCR processing failed.',events:[{id:1,stage:'text_extraction',outcome:'FAILED',attempt:1,detail:'Real OCR failure.',created_at:'2026-06-15T00:00:00Z'}],extraction:null,decision:null,pages:null};
it('renders persisted technical failure separately from a decision and queues retry',async()=>{
  window.history.replaceState({},'','/?run=failed-run');
  const fetcher=vi.fn().mockImplementation(async(url:string)=>({ok:true,json:async()=>url.endsWith('/retry')?{run_id:'retry-run'}:url.includes('/runs?')?{runs:[failed]}:url.endsWith('/retry-run')?{...failed,id:'retry-run',status:'QUEUED',error:null,events:[]}:failed}));
  vi.stubGlobal('fetch',fetcher);
  render(<InvoiceWorkflow/>);
  expect(await screen.findByRole('heading',{name:'FAILED'})).toBeInTheDocument();
  expect(screen.queryByRole('heading',{name:'Financial decision'})).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole('button',{name:'Retry failed run'}));
  expect(await screen.findByRole('heading',{name:'QUEUED'})).toBeInTheDocument();
  expect(fetcher).toHaveBeenCalledWith('/api/v1/runs/failed-run/retry',{method:'POST'});
  expect(screen.queryByText('decision · SUCCEEDED')).not.toBeInTheDocument();
});
it('does not invent progress while a persisted run remains queued',async()=>{
  window.history.replaceState({},'','/?run=queued-run');
  vi.stubGlobal('fetch',vi.fn().mockImplementation(async(url:string)=>({ok:true,json:async()=>url.includes('/runs?')?{runs:[]}:{...failed,status:'QUEUED',error:null,events:[]}})));
  render(<InvoiceWorkflow/>);
  expect(await screen.findByRole('heading',{name:'QUEUED'})).toBeInTheDocument();
  expect(screen.getByText(/Waiting for the Python worker/)).toBeInTheDocument();
  expect(screen.queryByText('decision · SUCCEEDED')).not.toBeInTheDocument();
});
