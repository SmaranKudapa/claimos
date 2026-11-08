import {object,type CaseRecord,type Json,type StepResult} from './domain.js';

export const evidenceResultSchema='claimos.evidence.result/1';
export const evidenceArtifactTitle=`Evidence result · ${evidenceResultSchema}`;
export type ArgumentSupport='supports_reduction'|'insufficient_evidence'|'does_not_support'|'contradicted'|'not_analyzed';
export interface EvidenceDeadline { date:string|null; status:'upcoming'|'passed'|'unknown'; verified:boolean; source:string|null; rule:string|null; trigger:string|null; basis:string|null; }
export interface EvidenceResult {
  schema:typeof evidenceResultSchema; case_id:string;
  run:{run_id:string;processing_status:'completed'|'partial'|'failed';errors:Json[];method_version:string;code_version:string;finished_at:string};
  appeal:{cycle_id:string;tax_year:number;appeal_type:string;valuation_date:string;parcel_id:string;jurisdiction:{state:string;county:string;county_code:string}};
  input_versions:{input_hash:string;find_case_id:string|null;find_run_id:string|null;qualification_ref:string|null;authorization_ref:string|null};
  intake:{status:'accepted'|'blocked';blockers:{code:string;message:string;resolver:string|null}[];file_blockers:{code:string;message:string;resolver:string|null}[]};
  conclusions:{package_complete:boolean;argument_support:ArgumentSupport;filing_readiness:'ready_for_human_review'|'not_ready';not_ready_reasons:string[]};
  valuation:{outcome:ArgumentSupport;outcome_reason:string;proposed_just_value:number|null;county_values:Json|null;versus_find:Json|null};
  deadlines:Record<string,EvidenceDeadline>;
  authorization:{status:string|null;instrument:string|null;document_ref:string|null;valid_for_filing:boolean};
  packet:{version:number|null;content_hash:string|null;format:string|null;county_facing:boolean|null;contains_personal_data:boolean|null};
  review:{human_review_required:true;filing_approval_required:true;status:string;reviewed_packet_hash:string|null;stale:boolean};
  next_action:{actor:string;action:string;reason:string};
  missing:string[];
}
export function parseEvidenceResult(result:StepResult|null|undefined):EvidenceResult|null{
  if(!result||result.step!=='evidence')return null;
  const artifact=result.artifacts.find(a=>a.title===evidenceArtifactTitle);if(!artifact)return null;
  const match=/^```json\n([\s\S]*)\n```$/.exec(artifact.markdown.trim());if(!match)return null;
  let parsed:unknown;try{parsed=JSON.parse(match[1]!);}catch{return null;}
  if(!object(parsed)||parsed.schema!==evidenceResultSchema||parsed.case_id!==result.case_id)return null;
  return parsed as unknown as EvidenceResult;
}
export function latestEvidence(c:CaseRecord):EvidenceResult|null{
  for(const run of [...c.runs].reverse()){if(run.step!=='evidence'||!run.result)continue;return parseEvidenceResult(run.result);}
  return null;
}
export function fileReadiness(c:CaseRecord,today=new Date().toISOString().slice(0,10)):{usable:boolean;problems:string[];packetHash:string|null;cycleId:string|null}{
  const e=latestEvidence(c),problems:string[]=[];
  if(!e)return {usable:false,problems:['No valid Evidence result is recorded for this case.'],packetHash:null,cycleId:null};
  if(e.run.processing_status!=='completed')problems.push('The latest Evidence run did not complete.');
  if(e.conclusions.filing_readiness!=='ready_for_human_review')problems.push(...(e.conclusions.not_ready_reasons.length?e.conclusions.not_ready_reasons:['Evidence is not ready for review.']));
  if(!e.packet.content_hash)problems.push('No evidence packet exists.');
  if(e.review.stale)problems.push('The evidence changed after the last review.');
  if(e.review.status!=='approved'||e.review.reviewed_packet_hash!==e.packet.content_hash)problems.push('No human has approved this exact packet.');
  if(!e.authorization.valid_for_filing)problems.push('Authorization is missing, invalid or test-only.');
  const petition=e.deadlines.petition_filing;if(!petition?.date||!petition.verified)problems.push('The petition deadline is not verified from the county.');else if(petition.date<today)problems.push(`The petition deadline ${petition.date} has passed.`);
  if(e.packet.contains_personal_data!==false)problems.push('The packet has not been confirmed free of personal data.');
  return {usable:!problems.length,problems,packetHash:e.packet.content_hash,cycleId:e.appeal.cycle_id};
}
