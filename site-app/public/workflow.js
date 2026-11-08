const $=s=>document.querySelector(s);
const names={find:'Find',qualify:'Qualify',signup:'Sign up',evidence:'Evidence',file:'File',chase:'Chase',escalate:'Escalate',collect:'Collect'};
const outcomes={QUALIFIED:'Qualified',REJECTED:'Rejected',NEEDS_REVIEW:'Needs review',NEXT_CYCLE:'Next filing window',INCOMPLETE:'Missing information',candidate:'Candidates identified',needs_review:'Awaiting review / missing items',processing:'In progress',reviewed:'Reviewed evidence',blocked:'Blocked',prepared:'Preparation recorded',receipt_recorded:'Receipt recorded',test_fixture:'Test fixture',todo:'Queued',done:'Step activity recorded'};
const node=(tag,text,cls)=>{const n=document.createElement(tag);n.textContent=text;if(cls)n.className=cls;return n;};
let loading=false;
async function refresh(){
 if(loading)return;loading=true;$('#refresh-progress').disabled=true;
 try{
  const response=await fetch('/api/workflow',{cache:'no-store'});if(!response.ok)throw new Error('unavailable');const d=await response.json();
  const when=new Date(d.observed_at).toLocaleString();
  $('#sync-status').textContent=`${!d.automatic_refresh?'Recorded snapshot — automatic updates are not connected yet':d.stale?'Showing the last available snapshot':'Updated automatically'} · ${when}${d.stale?' · Live refresh is temporarily unavailable.':''}`;
  $('#sync-status').classList.toggle('workflow-sync-warning',d.stale);
  $('#workflow-counts').replaceChildren(...[[d.tracked_cases,'Cases with linked board activity'],[d.filing_receipts,'Filing receipts recorded']].map(([n,label])=>{const el=node('div','');el.append(node('strong',Number(n).toLocaleString()),node('span',label));return el;}));
  const cards=['qualify','evidence','file'].map((stage,index)=>{
   const s=d.stages[stage],card=node('article','','workflow-stage');card.append(node('span',`0${index+1} · RECORDED ACTIVITY`,'label'),node('h2',names[stage]),node('strong',String(s.cases),'stage-total'),node('p',s.cases===1?'Case with a result recorded for this step.':'Cases with a result recorded for this step.'));
   const list=node('dl','');for(const [key,count]of Object.entries(s.outcomes)){const row=node('div','');row.append(node('dt',outcomes[key]||'Other recorded status'),node('dd',String(count)));list.append(row);}if(!Object.keys(s.outcomes).length)card.append(node('p','No linked result has been recorded yet.'));card.append(list);
   const modes=node('div','','workflow-mode');for(const [key,label] of [['recorded','Recorded'],['replay','Replay'],['synthetic','Test fixture']])if(s[key])modes.append(node('span',`${s[key]} ${label}`,key));card.append(modes);
   if(stage==='file'){const a=node('a','Where and how to file →','pill');a.href='/filing';card.append(a);}return card;
  });$('#workflow-stages').replaceChildren(...cards);
 }catch{$('#sync-status').textContent='We could not refresh workflow records. Any previous figures remain unchanged; no new progress has been inferred.';$('#sync-status').classList.add('workflow-sync-warning');}
 finally{loading=false;$('#refresh-progress').disabled=false;}
}
$('#refresh-progress').addEventListener('click',refresh);refresh();setInterval(()=>{if(!document.hidden)refresh();},30_000);document.addEventListener('visibilitychange',()=>{if(!document.hidden)refresh();});
