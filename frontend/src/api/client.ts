import type {ActionApproval,ActionExecution,ActionPayload,AIAnalysis,CaseDetail,EvidenceSet,Explanation,GraphRevision,Reconciliation,SafetyAssessment,StoredFile,SupportIntakeRequest} from './types';
import {getAccessToken,getAuthenticatedSubject} from '../auth/session';

export class ApiError extends Error { constructor(public status:number, message:string, public detail:unknown=null){super(message);this.name='ApiError'} }

async function authHeaders(extra:HeadersInit={}):Promise<HeadersInit>{const token=await getAccessToken();return {...(token?{Authorization:`Bearer ${token}`}:{ }),...extra}}
async function request<T>(path:string,init:RequestInit={},signal?:AbortSignal,timeout=20000):Promise<T>{
  const c=new AbortController(); const timer=setTimeout(()=>c.abort(),timeout);
  try{
    const headers=await authHeaders({Accept:'application/json',...(init.body instanceof FormData?{}:{'Content-Type':'application/json'}),...(init.headers??{})});
    const r=await fetch(path,{...init,signal:signal??c.signal,headers}); const ct=r.headers.get('content-type')??''; const b:unknown=ct.includes('application/json')?await r.json():await r.text();
    if(!r.ok){const message=typeof b==='object'&&b&&'detail' in b?String((b as {detail:unknown}).detail):`HTTP ${r.status}`;throw new ApiError(r.status,message,b)} return b as T;
  }finally{clearTimeout(timer)}
}
const enc=encodeURIComponent;
export const api={
  health:()=>request<any>('/health'),
  listCases:()=>request<CaseDetail[]>('/api/cases'), getCase:(id:string)=>request<CaseDetail>(`/api/cases/${enc(id)}`),
  syncPayPal:(id:string)=>request<CaseDetail>(`/api/cases/sync/${enc(id)}`,{method:'POST'}),
  latestGraph:(id:string)=>request<GraphRevision>(`/api/cases/${enc(id)}/graphs/latest`),
  currentEvidence:(id:string)=>request<EvidenceSet|null>(`/api/cases/${enc(id)}/evidence/sets/current`),
  intake:async(id:string,p:SupportIntakeRequest)=>{const subject=(await getAuthenticatedSubject())??p.created_by;return request<EvidenceSet>(`/api/cases/${enc(id)}/intake`,{method:'POST',body:JSON.stringify({...p,created_by:subject})})},
  analyses:(id:string)=>request<AIAnalysis[]>(`/api/cases/${enc(id)}/ai/analyses`),
  analyze:async(id:string,rid:string)=>{const subject=(await getAuthenticatedSubject())??'operator';return request<AIAnalysis>(`/api/cases/${enc(id)}/ai/analyze`,{method:'POST',body:JSON.stringify({analysis_request_id:rid,requested_by:subject})},undefined,90000)},
  safety:(id:string,aid:string)=>request<SafetyAssessment>(`/api/cases/${enc(id)}/ai/analyses/${enc(aid)}/safety`),
  explain:(id:string,aid:string)=>request<Explanation>(`/api/cases/${enc(id)}/ai/analyses/${enc(aid)}/explain`),
  assessSafety:(id:string,aid:string)=>request<SafetyAssessment>(`/api/cases/${enc(id)}/ai/analyses/${enc(aid)}/safety`,{method:'POST'}),
  actions:(id:string)=>request<ActionApproval[]>(`/api/cases/${enc(id)}/actions`),
  reconciliations:(id:string,uid:string)=>request<Reconciliation[]>(`/api/cases/${enc(id)}/actions/${enc(uid)}/reconciliations`),
  approveAction:async(id:string,p:{actionRequestId:string;analysisUid:string;safetyUid:string;payload:ActionPayload})=>{const subject=(await getAuthenticatedSubject())??'operator';return request<ActionApproval>(`/api/cases/${enc(id)}/actions/approve`,{method:'POST',body:JSON.stringify({action_request_id:p.actionRequestId,approved_by:subject,analysis_uid:p.analysisUid,safety_uid:p.safetyUid,payload:p.payload})})},
  executeAction:(id:string,uid:string,hash:string)=>request<ActionExecution>(`/api/cases/${enc(id)}/actions/${enc(uid)}/execute`,{method:'POST',body:JSON.stringify({approval_hash:hash})},undefined,90000),
  reconcile:(id:string,uid:string)=>request<any>(`/api/cases/${enc(id)}/actions/${enc(uid)}/reconcile`,{method:'POST'},undefined,90000),
  files:(id:string)=>request<StoredFile[]>(`/api/cases/${enc(id)}/files`),
  uploadFile:async(id:string,file:File)=>{const form=new FormData();form.append('file',file);return request<StoredFile>(`/api/cases/${enc(id)}/files`,{method:'POST',body:form},undefined,90000)},
};
