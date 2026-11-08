import {test} from 'node:test';
import assert from 'node:assert/strict';
import {projectCards,publicProgress,mergeProgress,type Card} from '../lib/workflow-model';
import {filingGuide} from '../lib/filing';
const cid='FL-36-2026-TEST';
const card=(body:string,patch:Partial<Card>={}):Card=>({id:'crd_test',title:'Candidate',body,note:null,status:'todo',assignee:null,updated_at:'2026-11-08T03:00:00Z',...patch});
const json=(o:unknown)=>'```json\n'+JSON.stringify(o)+'\n```';
test('qualified replay and rejection remain distinct even when both cards are done',()=>{
 const s=projectCards([card('QUALIFIED (replay)\n'+json({find_case_id:cid,status:'QUALIFIED'}),{status:'done'}),card('REJECTED (replay)\n'+json({find_case_id:'FL-36-2026-OTHER',status:'REJECTED'}),{id:'crd_other',status:'done'})]);
 assert.equal(s.summary.stages.qualify.outcomes.QUALIFIED,1);assert.equal(s.summary.stages.qualify.outcomes.REJECTED,1);assert.equal(s.summary.stages.qualify.replay,2);assert.equal(s.summary.filing_receipts,0);
});
test('File blocked card never becomes a filing because its body says evidence ready',()=>{
 const s=projectCards([card('EVIDENCE ready\n'+json({case_id:cid,desk:'property_tax'}),{title:'File · fixture',assignee:'File',status:'blocked'})]);
 assert.equal(s.cases[cid].stage,'file');assert.equal(s.cases[cid].status,'blocked');assert.equal(s.cases[cid].filing_recorded,false);
});
test('evidence fixture and incomplete review do not become complete',()=>{
 const s=projectCards([card('EVIDENCE TEST FIXTURE (replay)\n'+json({step:'evidence',case_id:cid,evidence_status:'complete',replay:true}),{status:'done'})]);
 assert.equal(s.cases[cid].status,'test_fixture');assert.equal(s.cases[cid].mode,'synthetic');
});
test('multiple stages for one case are retained without double-counting one stage',()=>{
 const s=projectCards([card(json({case_id:cid,desk:'property_tax'})),card('QUALIFIED (replay)\n'+json({find_case_id:cid,status:'QUALIFIED'}),{id:'crd_q'}),card(json({step:'evidence',case_id:cid,status:'evidence_ready_for_review',evidence_status:'incomplete',replay:true}),{id:'crd_e',status:'blocked'}),card(json({case_id:cid,step:'file'}),{id:'crd_f',status:'blocked'}),card(json({case_id:cid,step:'file'}),{id:'crd_f2',status:'blocked',updated_at:'2026-11-08T04:00:00Z'})]);
 assert.equal(s.summary.tracked_cases,1);assert.equal(s.summary.stages.file.cases,1);assert.equal(s.cases[cid].events.length,4);
});
test('malformed, missing and conflicting case identities are not attached to an owner',()=>{
 const s=projectCards([card('```json\ntruncated'),card('Private message without a case block'),card(json({case_id:cid})+'\n'+json({case_id:'FL-13-2026-OTHER'}))]);assert.equal(s.summary.tracked_cases,0);assert.equal(s.unlinked_cards,3);
});
test('public summary excludes case identifiers, addresses, email, notes and artifact references',()=>{
 const s=projectCards([card('QUALIFIED (replay) owner-secret@example.com fil_private\n'+json({find_case_id:cid,status:'QUALIFIED',address:'Private address'}))]);
 const p=JSON.stringify(publicProgress(s));for(const secret of [cid,'owner-secret','fil_private','Private address','cases":{'])assert.ok(!p.includes(secret));assert.ok(!('cases' in publicProgress(s)));
});
test('owner progress is merged only for the explicitly supplied case, with no raw card notes',()=>{
 const s=projectCards([card('QUALIFIED (replay)\n'+json({find_case_id:cid,status:'QUALIFIED'}))]);const c=mergeProgress({case_id:cid,owner_email:'private@example.com',history:[]},s.cases[cid]);assert.ok(c.workflow);assert.equal(c.workflow.mode,'replay');assert.equal(c.workflow.steps[0].status,'QUALIFIED');assert.equal(mergeProgress({case_id:'other'},undefined).workflow,null);
});
test('done without receipt never means filed; a structured receipt stays acceptance-pending',()=>{
 const s=projectCards([card(json({case_id:cid,step:'file',status:'receipt_recorded',receipt:{confirmation_id:'TEST',sha256:'a'.repeat(64)}}),{status:'done'})]);assert.equal(s.summary.filing_receipts,1);assert.match(s.cases[cid].events[0].label,/acceptance/);
 const missing=projectCards([card(json({case_id:cid,step:'file',submitted:true}),{status:'done'})]);assert.equal(missing.summary.filing_receipts,0);
});
test('filing directory uses official sources and keeps Bay automation disabled',()=>{
 for(const county of ['Lee','Hendry','Bay']){const g=filingGuide(county)!;assert.ok(g);assert.match(g.instructions_url,/^https:\/\/www\.(leeclerk|hendryclerk|baycoclerk)\./);assert.match(g.form_url,/^https:\/\/floridarevenue\.com\//);assert.equal(g.submission_state,'not_asserted');}assert.match(filingGuide('Bay')!.adapter,/not enabled/);assert.equal(filingGuide('unknown'),null);
});

test('Find evidence-quality prose is not an Evidence result',()=>{
 const c=card('Find flagged a home.\nEvidence quality 0.9 (strong).\n'+json({case_id:cid,desk:'property_tax',status:'candidate'}),{note:'QUALIFIED (replay) · rules result',status:'done'});
 const snapshot=projectCards([c]);assert.equal(snapshot.summary.stages.qualify.cases,1);assert.equal(snapshot.summary.stages.evidence.cases,0);
});
