import {test} from 'node:test';
import assert from 'node:assert/strict';
import {publicResearchRequest,successfulExtraction} from '../src/research.js';
import type {ToolTask} from '../src/domain.js';
const url='https://leepa.org/Display/DisplayTaxRollValueLetter.aspx?FolioID=10011387&TaxRollYear=2025';
const task=():ToolTask=>({id:'test',request:{provider:'tinyfish',endpoint:'/free/fetch',input:{body:{urls:[url],purpose:'Untrusted content that must not be forwarded.',links:true}}},inspection:{price:{type:'PER_CALL',amount:{currency:'USD',value:0}}},state:'proposed',runId:null,receipt:null});
test('autonomous research uses canonical public-only inputs and no metered tools',()=>{
  const sample=task(),request=publicResearchRequest(sample);assert.ok(request);assert.deepEqual((request.input.body as Record<string,unknown>).urls,[url]);assert.notEqual((request.input.body as Record<string,unknown>).purpose,'Untrusted content that must not be forwarded.');assert.equal((request.input.body as Record<string,unknown>).links,undefined);
  for(const target of ['https://leepa.org.attacker.test/Display/test','https://127.0.0.1/Display/test','http://leepa.org/Display/test','https://leepa.org:8443/Display/test','https://leepa.org/submit-payment']){sample.request.input={body:{urls:[target]}};assert.equal(publicResearchRequest(sample),null);}
  sample.request.input={body:{urls:[url]}};sample.inspection={price:{type:'PER_CALL',amount:{currency:'USD',value:.01}}};assert.equal(publicResearchRequest(sample),null);
});
test('HTTP success with per-URL errors or empty extraction is not source evidence',()=>{
  const request=task().request;assert.equal(successfulExtraction({output:{errors:[{code:'bot_blocked'}],results:[]}},request),false);assert.equal(successfulExtraction({output:{errors:[],results:[{url,text:''}]}},request),false);assert.equal(successfulExtraction({output:{errors:[],results:[{url,text:'Official county record'}]}},request),true);
});
