import {test} from 'node:test';
import assert from 'node:assert/strict';
import {newCase,parseInput,type StepResult} from '../src/domain.js';
import {evidenceArtifactTitle,fileReadiness,parseEvidenceResult} from '../src/evidence.js';

const input={address:'Evidence contract fixture',parcel:'TEST-003',county:'Bay County, Florida',brief:'Synthetic evidence fixture; no owner contact.',ownerEmail:null,contactConsent:false,sources:['https://floridarevenue.com/property/dataportal/']};
function evidence(id:string,overrides:Record<string,unknown>={}){
  const hash='a'.repeat(64);
  return {schema:'claimos.evidence.result/1',case_id:id,run:{run_id:'evr_1',processing_status:'completed',errors:[],method_version:'fl-sales-comparison/1',code_version:'0.1.0',finished_at:'2026-11-07T00:00:00Z'},
    appeal:{cycle_id:'FL-13-2027-TEST-003/vab_just_value',tax_year:2027,appeal_type:'vab_just_value',valuation_date:'2027-01-01',parcel_id:'TEST-003',jurisdiction:{state:'FL',county:'Bay',county_code:'13'}},
    input_versions:{input_hash:'x',find_case_id:'FL-13-2027-TEST-003',find_run_id:'FL-RUN',qualification_ref:'q',authorization_ref:'fil_poa'},
    intake:{status:'accepted',blockers:[],file_blockers:[]},
    conclusions:{package_complete:true,argument_support:'supports_reduction',filing_readiness:'ready_for_human_review',not_ready_reasons:[]},
    valuation:{outcome:'supports_reduction',outcome_reason:'fixture',proposed_just_value:300000,county_values:null,versus_find:null},
    deadlines:{petition_filing:{date:'2027-09-10',status:'upcoming',verified:true,source:'https://example.gov/vab',rule:'194.011(3)',trigger:'TRIM mailing',basis:'fixture'}},
    authorization:{status:'signed',instrument:'power_of_attorney_dr486poa',document_ref:'fil_poa',valid_for_filing:true},
    packet:{version:1,content_hash:hash,format:'text/markdown',county_facing:true,contains_personal_data:false},
    review:{human_review_required:true,filing_approval_required:true,status:'approved',reviewed_packet_hash:hash,stale:false},
    next_action:{actor:'operator',action:'review_packet_then_hand_to_file',reason:'fixture'},missing:[],...overrides};
}
function step(id:string,payload:unknown):StepResult{return {case_id:id,step:'evidence',decision:'ready',summary:'Evidence fixture.',sources:input.sources,artifacts:[{title:'Evidence packet v1',markdown:'# Packet'},{title:evidenceArtifactTitle,markdown:'```json\n'+JSON.stringify(payload)+'\n```'}],tool_requests:[],email_drafts:[]};}
function withEvidence(payload:(id:string)=>unknown){const c=newCase(parseInput(input));c.stage='file';c.runs.push({id:'r',step:'evidence',agentId:'agt',agentVersion:1,sessionId:'ses',status:'idle',stopReason:'end_turn',costMicroUsd:1,reservedMicroUsd:0,lastSeq:0,result:step(c.id,payload(c.id)),error:null,requestKey:'k',toolContext:[]});return c;}

test('File reads the structured Evidence result from the shared case record',()=>{
  const c=withEvidence(id=>evidence(id));const parsed=parseEvidenceResult(c.runs[0]!.result);
  assert.equal(parsed?.appeal.cycle_id,'FL-13-2027-TEST-003/vab_just_value');assert.equal(parsed?.packet.content_hash,'a'.repeat(64));
  assert.equal(parseEvidenceResult({...c.runs[0]!.result!,case_id:'another-case'}),null);
});
test('File accepts only a reviewed, current, authorized packet inside a verified deadline',()=>{
  assert.equal(fileReadiness(withEvidence(id=>evidence(id)),'2027-08-01').usable,true);
  const stale=fileReadiness(withEvidence(id=>evidence(id,{review:{human_review_required:true,filing_approval_required:true,status:'pending',reviewed_packet_hash:'b'.repeat(64),stale:true}})),'2027-08-01');
  assert.equal(stale.usable,false);assert.ok(stale.problems.some(p=>/changed after the last review/.test(p)));
  const test=fileReadiness(withEvidence(id=>evidence(id,{authorization:{status:'internal_test',instrument:'internal_test',document_ref:null,valid_for_filing:false}})),'2027-08-01');
  assert.ok(test.problems.some(p=>/test-only/.test(p)));
  assert.ok(fileReadiness(withEvidence(id=>evidence(id)),'2027-10-01').problems.some(p=>/has passed/.test(p)));
  const weak=fileReadiness(withEvidence(id=>evidence(id,{conclusions:{package_complete:true,argument_support:'insufficient_evidence',filing_readiness:'not_ready',not_ready_reasons:['argument outcome is insufficient_evidence']}})),'2027-08-01');
  assert.equal(weak.usable,false);
  const empty=newCase(parseInput(input));assert.equal(fileReadiness(empty).usable,false);
});
