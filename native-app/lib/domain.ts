import { randomUUID } from 'node:crypto';

export const stages = ['find','qualify','signup','evidence','file','chase','escalate','collect'] as const;
export type Stage = typeof stages[number];
export const names: Record<Stage,string> = { find:'Find',qualify:'Qualify',signup:'Sign up',evidence:'Evidence',file:'File',chase:'Chase',escalate:'Escalate',collect:'Collect' };
export const missions: Record<Stage,string> = {
  find:'Find official property assessment records and candidate comparable sales using Monid. Preserve sources and valuation dates. Never invent records.',
  qualify:'Assess the supplied evidence against sourced current county rules, filing windows, cost and conservative expected return. Missing rules, expired deadlines and uncertain savings require review.',
  signup:'Prepare a plain-language engagement email, fee terms and owner-authorization request. Identify every required signer. Never claim a signature, card authorization or customer consent that was not supplied.',
  evidence:'Prepare a sourced evidence document with comparable sales, calculations, missing-item checklist and source citations. Distinguish assessed value, just value and taxable value. Never invent appraisals or documents.',
  file:'Prepare the filing checklist and draft submission from official county instructions. Require signed authorization, current deadline, a configured filing adapter and a genuine provider receipt before claiming submission.',
  chase:'Read the case correspondence, identify unanswered requests, schedule the next follow-up and draft a concise email. A draft is not a delivered message.',
  escalate:'Identify the precise reason for a denial, locate the permitted next remedy and draft the response with evidence. Missing legal procedure or authority requires operator review.',
  collect:'Reconcile an actual outcome notice with the agreed fee terms. Calculate an invoice only from verified savings and an existing agreement. Never claim a charge or payment without a payment-provider receipt.'
};
export class HandoffFormatError extends Error {}
export type Json = Record<string,unknown>;
export const object = (v:unknown): v is Json => Boolean(v) && typeof v==='object' && !Array.isArray(v);
export function text(v:unknown,label:string,max=2000):string { if(typeof v!=='string'||!v.trim()||v.length>max)throw new Error(`${label} is required and must be shorter than ${max} characters.`);return v.trim(); }
export function https(v:unknown):string { const url=new URL(text(v,'Source URL'));if(url.protocol!=='https:'||url.username||url.password)throw new Error('Source URLs must use HTTPS.');return url.toString(); }
export interface CaseInput { address:string; parcel:string; county:string; ownerEmail:string|null; contactConsent:boolean; brief:string; sources:string[]; }
export interface ToolRequest { provider:string; endpoint:string; input:Json; }
export interface EmailDraft { to:string; subject:string; text:string; }
export interface StepResult { case_id:string; step:Stage; decision:'ready'|'review'|'blocked'; summary:string; sources:string[]; artifacts:{title:string;markdown:string}[]; tool_requests:ToolRequest[]; email_drafts:EmailDraft[]; }
export interface Run { id:string;step:Stage;agentId:string;agentVersion:number;sessionId:string|null;status:string;stopReason:string|null;costMicroUsd:number;reservedMicroUsd:number;lastSeq:number;result:StepResult|null;error:string|null;requestKey:string;toolContext:string[];catalog?:Json[];repairAttempts?:number; }
export interface Receipt { id:string;provider:'Naïve'|'Monid'|'AgentMail';kind:string;at:string;data:Json; }
export interface ToolTask { id:string;request:ToolRequest;inspection:Json|null;state:'proposed'|'submitting'|'running'|'completed'|'blocked'|'unknown';runId:string|null;receipt:Json|null;automatic?:boolean; }
export interface DraftTask extends EmailDraft { id:string;state:'draft'|'sending'|'sent'|'unknown';messageId:string|null;threadId:string|null; }
export interface CaseRecord { id:string;input:CaseInput;stage:Stage;status:string;auto:boolean;publicResearch?:boolean;createdAt:string;updatedAt:string;runs:Run[];receipts:Receipt[];tools:ToolTask[];drafts:DraftTask[];artifacts:{id:string;title:string;markdown:string;sessionId:string}[];inboxId:string|null;blocker:string|null; }
export interface AgentRef { id:string;version:number;step:Stage; }
export function parseInput(raw:unknown):CaseInput {
  if(!object(raw))throw new Error('A case form is required.');
  const ownerEmail=typeof raw.ownerEmail==='string'&&raw.ownerEmail.trim()?raw.ownerEmail.trim():null;
  if(ownerEmail&&!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(ownerEmail))throw new Error('Enter a valid owner email.');
  if(!Array.isArray(raw.sources)||!raw.sources.length||raw.sources.length>20)throw new Error('Supply at least one official source URL.');
  return {address:text(raw.address,'Property address',500),parcel:text(raw.parcel,'Parcel reference',100),county:text(raw.county,'County',100),brief:text(raw.brief,'Case brief',12000),ownerEmail,contactConsent:raw.contactConsent===true,sources:raw.sources.map(https)};
}
export function newCase(input:CaseInput):CaseRecord { const now=new Date().toISOString();return {id:randomUUID(),input,stage:'find',status:'Ready',auto:false,createdAt:now,updatedAt:now,runs:[],receipts:[],tools:[],drafts:[],artifacts:[],inboxId:null,blocker:null}; }
export const outputSchema:Json = {
  type:'object',additionalProperties:false,required:['case_id','step','decision','summary','sources','artifacts','tool_requests','email_drafts'],
  properties:{case_id:{type:'string'},step:{type:'string',enum:[...stages]},decision:{type:'string',enum:['ready','review','blocked']},summary:{type:'string',maxLength:6000},sources:{type:'array',maxItems:30,items:{type:'string',format:'uri',pattern:'^https://',description:'Absolute HTTPS source URLs only. Put provider receipt IDs and labels in summary.'}},artifacts:{type:'array',maxItems:8,items:{type:'object',additionalProperties:false,required:['title','markdown'],properties:{title:{type:'string'},markdown:{type:'string',maxLength:40000}}}},tool_requests:{type:'array',maxItems:3,items:{type:'object',additionalProperties:false,required:['provider','endpoint','input'],properties:{provider:{type:'string'},endpoint:{type:'string'},input:{type:'object'}}}},email_drafts:{type:'array',maxItems:3,items:{type:'object',additionalProperties:false,required:['to','subject','text'],properties:{to:{type:'string'},subject:{type:'string'},text:{type:'string',maxLength:10000}}}}}
};
export function parseResult(raw:unknown,c:CaseRecord,step:Stage):StepResult {
  if(!object(raw)||raw.case_id!==c.id||raw.step!==step||!['ready','review','blocked'].includes(String(raw.decision)))throw new Error('The agent result does not match this case and step.');
  const list=(v:unknown,max:number)=>{if(!Array.isArray(v)||v.length>max)throw new Error('Invalid agent result collection.');return v;};
  let sources:string[];try{sources=list(raw.sources,30).map(https);}catch{throw new HandoffFormatError('Source citations must contain only absolute HTTPS URLs. Put receipt IDs and explanatory text in the summary.');}
  return {case_id:c.id,step,decision:raw.decision as StepResult['decision'],summary:text(raw.summary,'Agent summary',6000),sources,
    artifacts:list(raw.artifacts,8).map(v=>{if(!object(v))throw new Error('Invalid artifact.');return {title:text(v.title,'Artifact title',200),markdown:text(v.markdown,'Artifact document',40000)};}),
    tool_requests:list(raw.tool_requests,3).map(v=>{if(!object(v)||!object(v.input))throw new Error('Invalid Monid request.');return {provider:text(v.provider,'Tool provider',100),endpoint:text(v.endpoint,'Tool endpoint',1000),input:v.input};}),
    email_drafts:list(raw.email_drafts,3).map(v=>{if(!object(v))throw new Error('Invalid email draft.');const to=text(v.to,'Email recipient',250);if(to!==c.input.ownerEmail)throw new Error('An agent email must target this case’s owner.');return {to,subject:text(v.subject,'Email subject',300),text:text(v.text,'Email body',10000)};})};
}
