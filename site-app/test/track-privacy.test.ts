import {test} from 'node:test';
import assert from 'node:assert/strict';
import {sign} from '../lib/token';
process.env.DATABASE_REST_URL='https://database.invalid';
process.env.DATABASE_SERVICE_KEY='synthetic-unit-test-secret';
delete process.env.CLAIMOS_WORKFLOW_READ_KEY;
test('tracking rejects missing credentials before reading cases or workflow',async()=>{
 const old=globalThis.fetch;let calls=0;globalThis.fetch=async()=>{calls++;throw new Error('unexpected fetch');};
 try{const {GET}=await import('../api/track');const r=await GET(new Request('https://site.invalid/api/track'));assert.equal(r.status,401);assert.equal(calls,0);}finally{globalThis.fetch=old;}
});
test('tracking includes only the authenticated owner’s linked cases and status',async()=>{
 const old=globalThis.fetch;const owner='test-owner@example.com';
 globalThis.fetch=async(input)=>{
  const u=String(input);
  if(u.includes('/signups?'))return Response.json([{email:owner,address:'Fixture',case_id:'FL-36-2026-A'},{email:'other@example.com',address:'Private other address',case_id:'FL-36-2026-B'}]);
  if(u.includes('/cases?'))return Response.json([{case_id:'FL-36-2026-A',owner_email:owner,stage:'find',status:'todo',history:[]},{case_id:'FL-36-2026-B',owner_email:'other@example.com',address:'Private other address'}]);
  if(u.includes('/workflow_snapshots?'))return Response.json([{payload:{observed_at:new Date().toISOString(),cases:{'FL-36-2026-A':{case_id:'FL-36-2026-A',stage:'qualify',status:'QUALIFIED',mode:'replay',events:[{stage:'qualify',status:'QUALIFIED',mode:'replay',at:'2026-11-07T12:00:00Z',label:'Qualified for the next step'}],updated_at:'2026-11-07T12:00:00Z',filing_recorded:false}},summary:{}}}]);
  throw new Error('unexpected endpoint');
 };
 try{const {GET}=await import('../api/track');const r=await GET(new Request('https://site.invalid/api/track?t='+sign(owner)));const data=await r.json();assert.equal(r.status,200);assert.equal(data.cases.length,1);assert.equal(data.cases[0].case_id,'FL-36-2026-A');assert.equal(data.cases[0].workflow.mode,'replay');assert.ok(!JSON.stringify(data).includes('Private other address'));assert.equal(data.signups.length,1);}finally{globalThis.fetch=old;}
});
