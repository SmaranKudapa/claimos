import { AgentMailClient } from 'agentmail';
import { object,type Json,type ToolRequest,type EmailDraft } from './domain.js';

export class MonidTools {
  constructor(private key:string,private fetcher:typeof fetch=fetch){}
  private async call(path:string,body?:Json):Promise<Json>{
    const response=await this.fetcher(`https://api.monid.ai${path}`,{method:body?'POST':'GET',headers:{authorization:`Bearer ${this.key}`,'content-type':'application/json'},...(body?{body:JSON.stringify(body)}:{}),signal:AbortSignal.timeout(45000)});
    const value:unknown=await response.json();
    if(!object(value))throw new Error('Monid returned an invalid response.');
    if(!response.ok&&!value.runId)throw new Error(`Monid request failed (${response.status}).`);
    return {...value,httpStatus:response.status};
  }
  async discover(query:string){const result=await this.call('/v1/discover/endpoints',{q:query,limit:4,readonly:true});if(!Array.isArray(result.items))throw new Error('Monid did not return a catalog.');return result;}
  inspect(provider:string,endpoint:string){return this.call('/v1/inspect',{provider,endpoint});}
  run(request:ToolRequest){return this.call('/v1/run',{provider:request.provider,endpoint:request.endpoint,input:request.input});}
  result(runId:string){return this.call(`/v1/runs/${encodeURIComponent(runId)}`);}
}
export function toolSucceeded(receipt:Json):boolean {
  return receipt.status==='COMPLETED'&&object(receipt.providerResponse)&&typeof receipt.providerResponse.httpStatus==='number'&&receipt.providerResponse.httpStatus>=200&&receipt.providerResponse.httpStatus<300;
}
export function flatPrice(inspection:Json):number|null {
  if(!object(inspection.price)||inspection.price.type!=='PER_CALL'||!object(inspection.price.amount))return null;
  const amount=inspection.price.amount;
  return amount.currency==='USD'&&typeof amount.value==='number'&&Number.isFinite(amount.value)&&amount.value>=0?amount.value:null;
}
export class AgentMailOffice {
  client:AgentMailClient;
  constructor(key:string){this.client=new AgentMailClient({apiKey:key,maxRetries:0});}
  createInbox(workspace:string){return this.client.inboxes.create({displayName:'Claim OS Recovery Desk',clientId:`claimos-${workspace}`});}
  send(inboxId:string,cid:string,draft:EmailDraft,draftId:string){
    return this.client.inboxes.messages.send(inboxId,{to:[draft.to],subject:`[Claim ${cid}] ${draft.subject}`,text:draft.text,trackOpens:false},{idempotencyKey:draftId,maxRetries:0});
  }
  messages(inboxId:string){return this.client.inboxes.messages.list(inboxId,{limit:50});}
  message(inboxId:string,messageId:string){return this.client.inboxes.messages.get(inboxId,messageId);}
}
