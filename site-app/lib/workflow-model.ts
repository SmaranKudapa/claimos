export type Stage = 'find' | 'qualify' | 'signup' | 'evidence' | 'file' | 'chase' | 'escalate' | 'collect';
export const stages: Stage[] = ['find','qualify','signup','evidence','file','chase','escalate','collect'];
export type Card = {id:string;title:string;body:string;note:string|null;status:string;assignee:string|null;updated_at:string};
export type Event = {stage:Stage;status:string;mode:'recorded'|'replay'|'synthetic';at:string;card_id:string;label:string};
export type CaseProgress = {case_id:string;county:string|null;stage:Stage;status:string;mode:Event['mode'];events:Event[];updated_at:string;filing_recorded:boolean};
export type Snapshot = {observed_at:string;board_cards:number;unlinked_cards:number;cases:Record<string,CaseProgress>;summary:ReturnType<typeof summarize>};
const decisions = new Set(['QUALIFIED','REJECTED','NEEDS_REVIEW','NEXT_CYCLE','INCOMPLETE']);
const labels:Record<string,string>={QUALIFIED:'Qualified for the next step',REJECTED:'Not pursuing this case',NEEDS_REVIEW:'Qualification needs review',NEXT_CYCLE:'Waiting for a filing window',INCOMPLETE:'Qualification needs more information'};
const object=(v:unknown):v is Record<string,any>=>v!==null&&typeof v==='object'&&!Array.isArray(v);
const validId=(v:unknown):v is string=>typeof v==='string'&&/^FL-\d{2}-\d{4}-.{1,220}$/.test(v);
const texts=(v:unknown):string=>typeof v==='string'?v:'';
export function blocks(text:string):Record<string,any>[] {
  const parsed:Record<string,any>[]=[];
  for(const match of text.matchAll(/```(?:json)?\s*([\s\S]*?)```/g)){try{const v=JSON.parse(match[1]);if(object(v))parsed.push(v);}catch{}}
  if(!parsed.length){try{const v=JSON.parse(text);if(object(v))parsed.push(v);}catch{}}
  return parsed;
}
function decision(text:string, records:Record<string,any>[]) {
  const match=text.match(/(?:^|\n)\s*(QUALIFIED|REJECTED|NEEDS_REVIEW|NEXT_CYCLE|INCOMPLETE)\b/);
  if(match)return match[1];
  return records.map(r=>r.status).find(s=>decisions.has(s))||null;
}
function cardEvent(card:Card, records:Record<string,any>[]):Event|null {
  const text=[card.note||'',card.body||''].join('\n');
  const mode:Event['mode']=records.some(r=>r.synthetic===true)||/TEST FIXTURE|synthetic fixture/i.test(text)?'synthetic':records.some(r=>Boolean(r.replay)||Boolean(r.judgedAsOf))||/\breplay\b/i.test(text)?'replay':'recorded';
  const at=Number.isFinite(Date.parse(card.updated_at))?card.updated_at:new Date(0).toISOString();
  const common={mode,at,card_id:card.id};
  const boardStatus=['todo','doing','blocked','done'].includes(card.status)?card.status:'unknown';
  if(/^File\s*[·:]/i.test(card.title)||card.assignee?.toLowerCase()==='file'||records.some(r=>r.step==='file')){
    const receipt=records.find(r=>r.step==='file'&&r.status==='receipt_recorded'&&object(r.receipt)&&r.receipt.confirmation_id&&r.receipt.sha256);
    return {...common,stage:'file',status:receipt?'receipt_recorded':card.status==='blocked'?'blocked':'prepared',label:receipt?'Filing receipt recorded; acceptance still needs verification':card.status==='blocked'?'Filing is blocked; requirements still need to be resolved':'Filing preparation recorded; no submission receipt'};
  }
  const ev=records.find(r=>r.step==='evidence'&&(r.packet_sha256||r.evidence_status||r.readiness));
  if(ev||/(?:^|\n)\s*EVIDENCE\s+(?:ready|complete|blocked|retry|test fixture|validation failed|rejected by reviewer|approved|insufficient evidence|does not support|contradicted)\b/i.test(text)||card.assignee?.toLowerCase()==='evidence'){
    const complete=mode==='recorded'&&ev?.evidence_status==='complete'&&ev?.readiness?.human_review==='reviewed'&&ev?.readiness?.authorization==='valid_for_filing';
    return {...common,stage:'evidence',status:complete?'reviewed':mode==='synthetic'?'test_fixture':card.status==='doing'?'processing':'needs_review',label:complete?'Evidence reviewed for the File handoff':mode==='synthetic'?'Synthetic evidence verification; not a customer filing':card.status==='doing'?'Evidence preparation is running':'Evidence recorded; review or supporting items are still needed'};
  }
  const q=decision(text,records);
  if(q)return {...common,stage:'qualify',status:q,label:labels[q]};
  const assigned=card.assignee?.toLowerCase();
  if(assigned&&stages.includes(assigned as Stage)&&assigned!=='find')return {...common,stage:assigned as Stage,status:boardStatus,label:`${assigned==='signup'?'Sign-up':assigned.charAt(0).toUpperCase()+assigned.slice(1)} ${card.status==='blocked'?'is waiting on a requirement':'activity recorded'}`};
  if(records.some(r=>r.schema_version&&r.status==='candidate'||r.desk==='property_tax'))return {...common,stage:'find',status:'candidate',label:'Candidate identified; qualification is separate'};
  return null;
}
export function summarize(cases:Record<string,CaseProgress>) {
  const totals=Object.fromEntries(stages.map(stage=>[stage,{cases:0,replay:0,recorded:0,synthetic:0,outcomes:{} as Record<string,number>}])) as Record<Stage,{cases:number;replay:number;recorded:number;synthetic:number;outcomes:Record<string,number>}>;
  for(const c of Object.values(cases))for(const stage of stages){const e=c.events.filter(e=>e.stage===stage).at(-1);if(!e)continue;totals[stage].cases++;totals[stage][e.mode]++;totals[stage].outcomes[e.status]=(totals[stage].outcomes[e.status]||0)+1;}
  return {tracked_cases:Object.keys(cases).length,stages:totals,filing_receipts:Object.values(cases).filter(c=>c.filing_recorded).length};
}
export function projectCards(cards:Card[], observedAt=new Date().toISOString()):Snapshot {
  const grouped=new Map<string,{county:string|null;events:Event[]}>();let unlinked=0;
  for(const card of cards){
    const records=[...blocks(card.body||''),...blocks(card.note||'')];
    const ids=[...new Set(records.flatMap(r=>[r.find_case_id,r.case_id,r.candidate?.case_id]).filter(validId))];
    if(ids.length!==1){unlinked++;continue;}
    const event=cardEvent(card,records);if(!event){unlinked++;continue;}
    const id=ids[0];const known=grouped.get(id)||{county:null,events:[]};
    const county=records.map(r=>r.jurisdiction?.county||r.candidate?.jurisdiction?.county||r.appeal?.jurisdiction?.county).find(v=>typeof v==='string');
    known.county=county||known.county||({'13':'Bay','36':'Hendry','46':'Lee'}[id.split('-')[1]]??null);
    known.events.push(event);
    const q=decision([card.note||'',card.body||''].join('\n'),records);
    if(q&&event.stage!=='qualify')known.events.push({...event,stage:'qualify',status:q,label:labels[q]});
    grouped.set(id,known);
  }
  const cases:Record<string,CaseProgress>={};
  for(const [case_id,{county,events}] of grouped){
    events.sort((a,b)=>a.at.localeCompare(b.at)||a.card_id.localeCompare(b.card_id));
    const byStage=new Map<Stage,Event>();for(const event of events)byStage.set(event.stage,event);
    const current=[...byStage.values()].sort((a,b)=>stages.indexOf(b.stage)-stages.indexOf(a.stage))[0];
    cases[case_id]={case_id,county,stage:current.stage,status:current.status,mode:current.mode,events:[...byStage.values()].sort((a,b)=>stages.indexOf(a.stage)-stages.indexOf(b.stage)),updated_at:events.at(-1)!.at,filing_recorded:byStage.get('file')?.status==='receipt_recorded'};
  }
  return {observed_at:observedAt,board_cards:cards.length,unlinked_cards:unlinked,cases,summary:summarize(cases)};
}
export function publicProgress(snapshot:Snapshot, stale=false) {
  return {observed_at:snapshot.observed_at,stale,board_cards:snapshot.board_cards,unlinked_cards:snapshot.unlinked_cards,...snapshot.summary,note:'Recorded workflow activity. Replay qualifications are historical checks, not current filing eligibility. A completed board card is not proof of a filed appeal.'};
}
export function mergeProgress(c:Record<string,any>, progress:CaseProgress|undefined) {
  if(!progress)return {...c,workflow:null};
  const history=Array.isArray(c.history)?c.history:[];
  const steps=progress.events.map(e=>({stage:e.stage,status:e.status,mode:e.mode,at:e.at,label:e.label}));
  return {...c,stage:progress.stage,status:progress.status,needs_from_owner:c.needs_from_owner || (progress.status==='blocked'||progress.status==='needs_review'?'See the recorded requirements below; this case is not ready to file.':''),workflow:{mode:progress.mode,steps,updated_at:progress.updated_at,filing_recorded:progress.filing_recorded},history:[...history,...steps.map(e=>({at:e.at,line:`${e.stage}: ${e.label}${e.mode==='replay'?' (replay)':e.mode==='synthetic'?' (test fixture)':''}`}))]};
}
