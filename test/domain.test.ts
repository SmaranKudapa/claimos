import {test} from 'node:test';
import assert from 'node:assert/strict';
import {agentDefinition,NaiveCrew} from '../src/naive.js';
import {newCase,parseInput,parseResult,stages} from '../src/domain.js';
import {flatPrice,toolSucceeded} from '../src/providers.js';

export const caseInput={address:'Integration test property',parcel:'TEST-001',county:'Lee County, Florida',brief:'Verify the supplied public record. Synthetic test input.',ownerEmail:'owner@example.test',contactConsent:true,sources:['https://www.leepa.org/']};
test('case boundaries require HTTPS sources and a scoped recipient',()=>{
  assert.throws(()=>parseInput({...caseInput,sources:['file:///etc/passwd']}));
  assert.throws(()=>parseInput({...caseInput,ownerEmail:'invalid'}));
  const c=newCase(parseInput(caseInput));
  const result={case_id:c.id,step:'find',decision:'ready',summary:'Records located.',sources:c.input.sources,artifacts:[],tool_requests:[],email_drafts:[]};
  assert.equal(parseResult(result,c,'find').decision,'ready');
  assert.throws(()=>parseResult({...result,case_id:'other'},c,'find'));
  assert.throws(()=>parseResult({...result,email_drafts:[{to:'other@example.test',subject:'x',text:'x'}]},c,'find'));
});
test('all agents use the Naive managed runtime with bounded budgets and closed tools',()=>{
  for(const step of stages){const agent=agentDefinition(step,'vetta/auto','test');assert.equal(agent.harness,'pi');assert.equal(agent.handoffs,false);assert.equal(agent.structured_output_required,true);assert.equal(agent.budget.max_task_micro_usd,250000);assert.equal(agent.tools?.default_config?.permission,'deny');assert.match(agent.system||'',/Monid/);assert.match(agent.system||'',/AgentMail/);}
});
test('the official SDK sends version-pinned sessions with stable idempotency and output contracts',async()=>{
  let url='',payload:Record<string,unknown>={},headers=new Headers();
  const transport:typeof fetch=async(input,init)=>{url=String(input);payload=JSON.parse(String(init?.body));headers=new Headers(init?.headers);return new Response(JSON.stringify({error:{code:'unauthorized',message:'Test transport refuses execution'}}),{status:401,headers:{'content-type':'application/json'}});};
  const client=new NaiveCrew('test-key','vetta/auto',transport),c=newCase(parseInput(caseInput));
  await assert.rejects(client.launch(c,{id:'agt_test',version:2,step:'find'},'stable-session-key',[]));
  assert.match(url,/\/v1\/sessions$/);assert.equal(headers.get('idempotency-key'),'stable-session-key');assert.equal(payload.agent_version,2);assert.equal(payload.budget_micro_usd,250000);assert.equal(payload.structured_output_required,true);assert.ok(payload.output_schema);
});
test('Monid completion requires a successful provider HTTP status',()=>{
  assert.equal(toolSucceeded({status:'COMPLETED',providerResponse:{httpStatus:500}}),false);
  assert.equal(toolSucceeded({status:'BLOCKED',providerResponse:{httpStatus:200}}),false);
  assert.equal(toolSucceeded({status:'COMPLETED',providerResponse:{httpStatus:200}}),true);
  assert.equal(flatPrice({price:{type:'PER_RESULT',amount:{currency:'USD',value:.01}}}),null);
  assert.equal(flatPrice({price:{type:'PER_CALL',amount:{currency:'USD',value:.01}}}),.01);
});
