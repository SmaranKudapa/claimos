const $=s=>document.querySelector(s),steps=['find','qualify','signup','evidence','file','chase','escalate','collect'],names={find:'Find',qualify:'Qualify',signup:'Sign up',evidence:'Evidence',file:'File',chase:'Chase',escalate:'Escalate',collect:'Collect'};
let token='',selected=new URL(location.href).searchParams.get('case'),busy=false,timer;
const n=(tag,value='',className='')=>{const el=document.createElement(tag);el.textContent=value;if(className)el.className=className;return el;};
const usd=m=>new Intl.NumberFormat('en-US',{style:'currency',currency:'USD',maximumFractionDigits:4}).format(m/1e6);
function notice(value,error=false){$('#notice').textContent=value;$('#notice').classList.toggle('error',error);}
async function api(path,body){const response=await fetch(`/api/${path}`,{method:body?'POST':'GET',headers:{...(body?{'content-type':'application/json'}:{}),...(token?{authorization:`Bearer ${token}`}:{})},...(body?{body:JSON.stringify(body)}:{})});const data=await response.json();if(!response.ok)throw new Error(data.error||'The request could not be completed.');return data;}
async function act(work){if(busy)return;busy=true;document.querySelectorAll('button').forEach(b=>b.disabled=true);notice('The company is working…');try{await work();await refresh();notice('Provider results are saved in the case ledger.');}catch(e){notice(e.message,true);}finally{busy=false;document.querySelectorAll('button').forEach(b=>b.disabled=false);}}
function providerCards(providers){$('#providers').replaceChildren(...providers.map(p=>{const card=n('article','','provider');card.append(n('b',p.name),n('small',p.role),n('span',p.ready?'Key configured':'Connect account',`provider-status ${p.ready?'ready':''}`));return card;}));}
async function refresh(){
  const status=await api('status');providerCards(status.providers);$('#case-count').textContent=`${status.cases.length} cases`;
  $('#activate').textContent=status.agents.length===8&&status.inbox?'Company active · 8 agents':'Activate company →';
  const list=$('#case-list');list.replaceChildren();
  if(!status.cases.length){const empty=n('p','No cases yet. Start with an official source.');empty.style.cssText='padding:20px;font-size:11px';list.append(empty);}
  for(const c of status.cases){const button=n('button','',`portfolio-item ${c.id===selected?'active':''}`);button.append(n('strong',c.address),n('small',`${names[c.stage]} · ${c.status}`));button.addEventListener('click',()=>{if(busy)return;selected=c.id;const url=new URL(location.href);url.searchParams.set('case',selected);history.replaceState(null,'',url);refresh().catch(e=>notice(e.message,true));});list.append(button);}
  if(selected)render(await api(`cases/${selected}`),status);
}
function section(title){const el=n('section','','case-section');el.append(n('h3',title));return el;}
function button(label,work,className=''){const b=n('button',label,className);b.type='button';b.disabled=busy;b.addEventListener('click',()=>act(work));return b;}
function render(c,status){
  const root=$('#case');root.replaceChildren();const head=n('header','','case-header');head.append(n('span',`${c.input.county} · ${c.status}`,'eyebrow'),n('h2',c.input.address),n('p',`${c.input.parcel} · ${c.id}`));root.append(head);
  const pipeline=n('div','','pipeline');steps.forEach((step,i)=>{const node=n('span','',step===c.stage?'current':'');node.append(n('small',String(i+1).padStart(2,'0')),n('b',names[step]));pipeline.append(node);});root.append(pipeline);
  const body=n('div','','case-body'),actions=n('div','','case-actions');
  actions.append(button('Run agent →',()=>api(`cases/${c.id}/run`,{auto:true}),'primary'),button('Refresh session',()=>api(`cases/${c.id}/refresh`,{})),button('Next stage',()=>api(`cases/${c.id}/advance`,{})),button('Pause company',()=>api(`cases/${c.id}/pause`,{})));body.append(actions);
  const metrics=n('div','','metrics');metrics.append(n('span',`Naïve spend: ${usd(c.runs.reduce((sum,r)=>sum+r.costMicroUsd,0))}`),n('span',`Case cap: ${usd(2e6)}`),n('span',c.auto?'Coordinator on':'Operator control'));body.append(metrics);
  if(c.blocker)body.append(n('div',c.blocker,'case-blocker'));
  if(status.inbox){const mail=n('p',`AgentMail claim inbox: ${status.inbox.email}`);mail.style.fontSize='11px';body.append(mail);}
  const runs=section('Naïve · managed agent sessions');
  if(!c.runs.length)runs.append(n('p','A managed agent session starts when you run this case. No simulated work is shown.'));
  for(const run of [...c.runs].reverse()){
    const item=n('article','','run'),top=n('div','','run-top');top.append(n('b',`${names[run.step]} agent`),n('span',run.status,'badge'));item.append(top,n('p',run.result?.summary||run.error||'Waiting for the Naïve runtime.'),n('small',`${run.sessionId||'Session ID pending'} · agent ${run.agentId} v${run.agentVersion} · ${usd(run.costMicroUsd)}`));
    if(['launch_unknown','launching'].includes(run.status)&&!run.sessionId)item.append(button('Reconcile session',()=>api(`cases/${c.id}/recover`,{})));
    runs.append(item);
  }body.append(runs);
  const tools=section('Monid · tool execution');
  if(!c.tools.length)tools.append(n('p','The Find agent receives an inspected Monid catalog and proposes the tool input needed for this property.'));
  for(const task of c.tools){const card=n('article','','task');card.append(n('span','MONID','badge'),n('h4',`${task.request.provider} · ${task.request.endpoint}`),n('p',`State: ${task.state}${task.runId?` · Run ${task.runId}`:''}`));
    const price=task.inspection?.price;card.append(n('p',price?.amount?.currency==='USD'?`Listed price: $${price.amount.value} · ${price.type}`:'A verified usage price is required.'));
    const details=n('details'),summary=n('summary','Review the exact tool input');details.append(summary,n('pre',JSON.stringify(task.request.input,null,2)));card.append(details);
    if(task.state==='proposed')card.append(button('Approve Monid tool run',()=>api(`cases/${c.id}/tools`,{taskId:task.id,approved:true}),'primary'));
    if(task.receipt){const receipt=n('p',`Provider result: ${task.receipt.status} · HTTP ${task.receipt.providerResponse?.httpStatus||task.receipt.httpStatus||'pending'}`);card.append(receipt);}
    tools.append(card);
  }body.append(tools);
  const correspondence=section('AgentMail · correspondence');
  if(!c.drafts.length)correspondence.append(n('p','Case emails appear here as drafts with an exact recipient and body. Sending requires owner-contact permission and operator approval.'));
  for(const draft of c.drafts){const card=n('article','','task');card.append(n('span','AGENTMAIL','badge'),n('h4',draft.subject),n('p',`To ${draft.to} · ${draft.state}`),n('div',draft.text,'document-preview'));
    if(['draft','unknown'].includes(draft.state))card.append(button(draft.state==='unknown'?'Reconcile delivery':'Approve and send this email',()=>api(`cases/${c.id}/mail`,{draftId:draft.id,approved:true}),'primary'));
    if(draft.messageId)card.append(n('p',`Delivered message: ${draft.messageId}`));correspondence.append(card);
  }
  if(c.inboxId){correspondence.append(button('Read case replies',()=>api(`cases/${c.id}/inbox`)));const received=c.receipts.filter(r=>r.kind==='message.received');for(const receipt of received){const row=n('article','','message');row.append(n('b',receipt.data.subject||'Case reply'),n('p',receipt.data.text||'Message has no plain-text body.'));correspondence.append(row);}}
  body.append(correspondence);
  if(c.artifacts.length){const documents=section('Agent-produced documents');for(const doc of c.artifacts){const row=n('div','','artifact');row.append(n('strong',doc.title),button('Download',async()=>{const response=await fetch(`/api/cases/${c.id}/artifacts/${doc.id}`,{headers:token?{authorization:`Bearer ${token}`}:{}});if(!response.ok)throw new Error('Document download failed.');const url=URL.createObjectURL(await response.blob()),link=n('a');link.href=url;link.download='claim-evidence.md';document.body.append(link);link.click();link.remove();setTimeout(()=>URL.revokeObjectURL(url),1000);}));documents.append(row);}body.append(documents);}
  const receipts=section('Live provider evidence'),ledger=n('div','','receipts');
  for(const r of [...c.receipts].reverse().slice(0,80)){const row=n('article','','receipt'),copy=n('div');copy.append(n('strong',r.kind),n('small',r.data.sessionId||r.data.runId||r.data.messageId||r.id),n('time',new Date(r.at).toLocaleString()));row.append(n('span',r.provider,'badge'),copy);ledger.append(row);}receipts.append(ledger);body.append(receipts);root.append(body);
}
$('#activate').addEventListener('click',()=>act(()=>api('activate',{})));
$('#login').addEventListener('submit',event=>{event.preventDefault();token=new FormData(event.currentTarget).get('token');event.currentTarget.reset();refresh().then(()=>notice('Company workspace unlocked.')).catch(e=>notice(e.message,true));});
$('#intake').addEventListener('submit',event=>{event.preventDefault();const form=new FormData(event.currentTarget);act(async()=>{const c=await api('cases',{address:form.get('address'),parcel:form.get('parcel'),county:form.get('county'),brief:form.get('brief'),ownerEmail:form.get('ownerEmail'),contactConsent:form.get('contactConsent')==='on',sources:String(form.get('sources')).split(/\n/).map(s=>s.trim()).filter(Boolean)});selected=c.id;const url=new URL(location.href);url.searchParams.set('case',selected);history.replaceState(null,'',url);});});
async function start(){try{const health=await api('health');providerCards(health.providers);$('#login').hidden=!health.requiresToken;if(!health.requiresToken)await refresh();notice(health.providers.every(p=>p.ready)?'Naïve, Monid and AgentMail keys are configured. Activate the company to provision its agents and inbox.':'Connect the three required provider accounts in .env. The workspace never substitutes simulated runs.');
  timer=setInterval(()=>{if(!busy)refresh().catch(()=>{});},5000);
}catch(e){notice(e.message,true);}}
start();
