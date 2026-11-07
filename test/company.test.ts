import {test} from 'node:test';
import assert from 'node:assert/strict';
import {mkdtempSync} from 'node:fs';
import {join} from 'node:path';
import {tmpdir} from 'node:os';
import {Company,type Providers} from '../src/company.js';
import {Store} from '../src/store.js';
import {newCase,parseInput,type Stage} from '../src/domain.js';

const input={address:'Provider integration fixture',parcel:'TEST-002',county:'Lee County, Florida',brief:'Synthetic integration fixture; no real owner contact.',ownerEmail:'owner@example.test',contactConsent:true,sources:['https://www.leepa.org/']};
const store=()=>new Store(join(mkdtempSync(join(tmpdir(),'claimos-event-test-')),'company.sqlite'));
function setup(){
  let nextResult:unknown=null,failLaunch=false,monidHttp=200;
  const keys:string[]=[],sent:string[]=[],created:Stage[]=[];
  const session=(id='ses_fixture')=>({id,status:'idle',stop_reason:'end_turn',consumed_micro_usd:1200,structured_output:nextResult});
  const providers={
    naive:{create:async(step:Stage)=>{created.push(step);return {id:`agt_${step}`,version:1,step};},launch:async(_c:unknown,_a:unknown,key:string)=>{keys.push(key);if(failLaunch)throw new Error('Test timeout');return {...session(),status:'running'};},session:async()=>session(),events:async()=>({data:[{id:'evt_fixture',seq:1,type:'session.idle',data:{},created_at:new Date().toISOString()}],has_more:false}),interrupt:async()=>session()},
    monid:{discover:async()=>({items:[{provider:'fixture-search',endpoint:'/search'}],total:1}),inspect:async()=>({provider:'fixture-search',endpoint:'/search',price:{type:'PER_CALL',amount:{currency:'USD',value:.01}},input:{body:{type:'object'}}}),run:async()=>({runId:'run_fixture',status:'COMPLETED',providerResponse:{httpStatus:monidHttp}}),result:async()=>({runId:'run_fixture',status:'COMPLETED',providerResponse:{httpStatus:monidHttp}})},
    mail:{createInbox:async()=>({inboxId:'inbox_fixture',email:'fixture@agentmail.to'}),send:async(_i:unknown,_c:unknown,_d:unknown,key:string)=>{sent.push(key);return {messageId:'msg_fixture',threadId:'thread_fixture'};},messages:async()=>({messages:[]})}
  } as unknown as Providers;
  const db=store(),company=new Company(db,()=>providers);
  return {db,company,created,keys,sent,providers,setResult:(r:unknown)=>nextResult=r,setFail:(v:boolean)=>failLaunch=v,setHttp:(v:number)=>monidHttp=v};
}
const result=(id:string,step='find',extra={})=>({case_id:id,step,decision:'ready',summary:'Fixture agent result.',sources:input.sources,artifacts:[],tool_requests:[],email_drafts:[],...extra});
test('activation provisions eight Naive agents and one durable AgentMail inbox',async()=>{
  const t=setup();await t.company.activate();await t.company.activate();assert.equal(t.created.length,8);assert.equal((await t.company.status()).agents.length,8);assert.equal((await t.company.status()).inbox?.id,'inbox_fixture');t.db.close();
});
test('a case uses Monid inspection and a real-session handoff before advancing',async()=>{
  const t=setup();await t.company.activate();const c=await t.company.create(input);await t.company.run(c.id);
  t.setResult(result(c.id,'find',{tool_requests:[{provider:'fixture-search',endpoint:'/search',input:{body:{query:'public record'}}}]}));
  let updated=await t.company.refresh(c.id);assert.equal(updated.tools.length,1);await assert.rejects(t.company.advance(c.id));
  updated=await t.company.executeTool(c.id,updated.tools[0]!.id);assert.equal(updated.tools[0]!.state,'completed');
  assert.ok(updated.receipts.some(r=>r.provider==='Naïve'));assert.ok(updated.receipts.some(r=>r.provider==='Monid'&&r.data.runId==='run_fixture'));
  await assert.rejects(t.company.advance(c.id),/interpret/);await t.company.run(c.id);t.setResult(result(c.id));await t.company.refresh(c.id);
  const advanced=await t.company.advance(c.id);assert.equal(advanced.stage,'qualify');t.db.close();
});
test('provider error responses never satisfy a source-data handoff',async()=>{
  const t=setup();await t.company.activate();const c=await t.company.create(input);await t.company.run(c.id);
  t.setResult(result(c.id,'find',{tool_requests:[{provider:'fixture-search',endpoint:'/search',input:{}}]}));let saved=await t.company.refresh(c.id);t.setHttp(500);saved=await t.company.executeTool(c.id,saved.tools[0]!.id);assert.equal(saved.tools[0]!.state,'blocked');await assert.rejects(t.company.advance(c.id));t.db.close();
});
test('session creation retries preserve the SDK idempotency key and block duplicate launches',async()=>{
  const t=setup();await t.company.activate();const c=await t.company.create(input);t.setFail(true);await assert.rejects(t.company.run(c.id));await assert.rejects(t.company.run(c.id));t.setFail(false);await t.company.recoverLaunch(c.id);assert.equal(t.keys.length,2);assert.equal(t.keys[0],t.keys[1]);t.db.close();
});
test('AgentMail delivery requires owner permission and stores provider message IDs',async()=>{
  const t=setup();await t.company.activate();const c=await t.company.create(input);await t.company.run(c.id);
  t.setResult(result(c.id,'find',{email_drafts:[{to:input.ownerEmail,subject:'Review the opportunity',text:'Fixture message.'}]}));let saved=await t.company.refresh(c.id);const draft=saved.drafts[0]!;
  saved=await t.company.send(c.id,draft.id);assert.equal(saved.drafts[0]!.messageId,'msg_fixture');assert.equal(t.sent[0],draft.id);await assert.rejects(t.company.send(c.id,draft.id));
  saved.input.contactConsent=false;saved.drafts.push({...draft,id:'second',state:'draft',messageId:null,threadId:null});t.db.save(saved);await assert.rejects(t.company.send(c.id,'second'));t.db.close();
});
test('invalid structured results do not create documents or provider requests',async()=>{
  const t=setup();await t.company.activate();const c=await t.company.create(input);await t.company.run(c.id);
  t.setResult(result(c.id,'find',{artifacts:[{title:'Fixture artifact',markdown:'Text'}],tool_requests:[{provider:'uninspected',endpoint:'/send',input:{}}]}));const saved=await t.company.refresh(c.id);assert.equal(saved.status,'Needs review');assert.equal(saved.artifacts.length,0);assert.equal(saved.tools.length,0);t.db.close();
});
test('signup, filing and collection require adapter proof beyond an agent assertion',async()=>{
  const t=setup();for(const step of ['signup','file','collect'] as const){const c=newCase(parseInput(input));c.stage=step;c.runs.push({id:'run',step,agentId:'agt',agentVersion:1,sessionId:'ses',status:'idle',stopReason:'end_turn',costMicroUsd:1,reservedMicroUsd:0,lastSeq:0,result:result(c.id,step) as never,error:null,requestKey:'key',toolContext:[]});t.db.save(c);await assert.rejects(t.company.advance(c.id),/receipt/);}t.db.close();
});
test('case state and provider evidence survive reopening the workspace',async()=>{
  const t=setup(),c=await t.company.create(input);t.db.receipt(c,'Monid','fixture',{runId:'fixture-id'});const reopened=new Company(t.db,()=>t.providers);assert.equal((await reopened.store.get(c.id)).receipts[0]!.data.runId,'fixture-id');t.db.close();
});

test('a coordinator resumes the new stage after an interrupted handoff',async()=>{
  const t=setup();await t.company.activate();const c=await t.company.create(input);c.stage='qualify';c.auto=true;c.runs.push({id:'prior',step:'find',agentId:'agt_find',agentVersion:1,sessionId:'prior-session',status:'idle',stopReason:'end_turn',costMicroUsd:1,reservedMicroUsd:0,lastSeq:0,result:result(c.id) as never,error:null,requestKey:'prior-key',toolContext:[]});t.db.save(c);await t.company.tick();const saved=t.db.get(c.id);assert.equal(saved.stage,'qualify');assert.equal(saved.runs.at(-1)?.step,'qualify');assert.equal(saved.runs.length,2);t.db.close();
});
