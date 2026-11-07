import { randomUUID } from 'node:crypto';
import { Store } from './store.js';
import { NaiveCrew } from './naive.js';
import { AgentMailOffice,MonidTools,flatPrice,toolSucceeded } from './providers.js';
import { configuration,readiness } from './config.js';
import { stages,object,newCase,parseInput,parseResult,type CaseRecord,type AgentRef,type Json,type Run } from './domain.js';

export interface Providers {naive:Pick<NaiveCrew,'create'|'launch'|'session'|'events'|'interrupt'>;monid:Pick<MonidTools,'discover'|'inspect'|'run'|'result'>;mail:Pick<AgentMailOffice,'createInbox'|'send'|'messages'|'message'>;}

export class Company {
  private locks=new Set<string>();
  private workspace:string;
  constructor(public store:Store,private factory?:()=>Providers){this.workspace=store.setting<string>('workspace')||randomUUID().slice(0,8);store.set('workspace',this.workspace);}
  status(){return {providers:readiness(),agents:this.store.setting<AgentRef[]>('agents')||[],inbox:this.store.setting<Json>('inbox'),budget:{sessionUsd:.25,caseUsd:2},cases:this.store.list().map(c=>({id:c.id,address:c.input.address,stage:c.stage,status:c.status,updatedAt:c.updatedAt})),verifiedRevenueUsd:0};}
  private providers():Providers{if(this.factory)return this.factory();const c=configuration();if(!c.naiveKey||!c.monidKey||!c.mailKey)throw new Error('Connect Naïve, Monid and AgentMail in .env to activate the company.');return {naive:new NaiveCrew(c.naiveKey,c.model),monid:new MonidTools(c.monidKey),mail:new AgentMailOffice(c.mailKey)};}
  private async locked<T>(id:string,work:()=>Promise<T>):Promise<T>{if(this.locks.has(id))throw new Error('This case is already working.');this.locks.add(id);try{return await work();}finally{this.locks.delete(id);}}
  async activate(){return this.locked('activate',async()=>{
    const p=this.providers();let agents=this.store.setting<AgentRef[]>('agents')||[];
    for(const step of stages){if(agents.some(a=>a.step===step))continue;const agent=await p.naive.create(step,this.workspace);agents=[...agents,agent];this.store.set('agents',agents);}
    if(!this.store.setting('inbox')){const inbox=await p.mail.createInbox(this.workspace);this.store.set('inbox',{id:inbox.inboxId,email:inbox.email});}
    return this.status();
  });}
  create(raw:unknown){const c=newCase(parseInput(raw));return this.store.save(c);}
  private async catalog(c:CaseRecord,p:ReturnType<Company['providers']>){
    const key=`catalog:${c.id}`;let catalog=this.store.setting<Json[]>(key);
    if(!catalog){
      const discovery=await p.monid.discover(`Official ${c.input.county} property assessment records and comparable property sales; retrieve ${c.input.sources.join(' ')}`);
      this.store.receipt(c,'Monid','catalog.discovered',{total:discovery.total??0});catalog=[];
      for(const item of (discovery.items as unknown[]).slice(0,3)){
        if(!object(item)||typeof item.provider!=='string'||typeof item.endpoint!=='string')continue;
        const inspection=await p.monid.inspect(item.provider,item.endpoint);catalog.push(inspection);
      }
      this.store.set(key,catalog);
    }
    return catalog;
  }
  async run(id:string){return this.locked(id,async()=>{
    const p=this.providers(),c=this.store.get(id),agents=this.store.setting<AgentRef[]>('agents')||[],agent=agents.find(a=>a.step===c.stage);
    if(!agent)throw new Error('Activate the company’s eight Naïve agents first.');
    if(c.runs.some(r=>['launching','launch_unknown','queued','running','idle'].includes(r.status)&&!r.result))throw new Error('Refresh or reconcile the active session before starting another.');
    if(c.tools.some(t=>t.state!=='completed')||c.drafts.some(d=>d.state!=='sent'))throw new Error('Resolve this case’s pending tool requests and correspondence first.');
    const budget=c.runs.reduce((s,r)=>s+r.costMicroUsd+r.reservedMicroUsd,0);if(budget+250000>2000000)throw new Error('This case has reached its $2 Naïve session budget.');
    const inbox=this.store.setting<Json>('inbox');if(!inbox||typeof inbox.id!=='string')throw new Error('Create the AgentMail claim inbox through company activation.');c.inboxId=inbox.id;
    const catalog=await this.catalog(c,p);
    const run:Run={id:randomUUID(),step:c.stage,agentId:agent.id,agentVersion:agent.version,sessionId:null,status:'launching',stopReason:null,costMicroUsd:0,reservedMicroUsd:250000,lastSeq:0,result:null,error:null,requestKey:randomUUID(),toolContext:c.tools.filter(t=>t.state==='completed').map(t=>t.id)};
    c.runs.push(run);c.status='Agent working';c.blocker=null;this.store.save(c);
    try{const session=await p.naive.launch(c,agent,run.requestKey,catalog);run.sessionId=session.id;run.status=session.status;this.store.receipt(c,'Naïve','session.created',{sessionId:session.id,agentId:agent.id,stage:c.stage,budgetMicroUsd:250000});}
    catch{run.status='launch_unknown';run.error='Session creation needs reconciliation. Retry uses the saved idempotency key.';c.status='Needs attention';this.store.save(c);throw new Error(run.error);}
    return this.store.save(c);
  });}
  async recoverLaunch(id:string){return this.locked(id,async()=>{
    const c=this.store.get(id),run=c.runs.at(-1);if(!run||!['launch_unknown','launching'].includes(run.status))throw new Error('No session creation is awaiting reconciliation.');
    const agent=(this.store.setting<AgentRef[]>('agents')||[]).find(a=>a.id===run.agentId);if(!agent)throw new Error('Agent mapping is unavailable.');
    const p=this.providers(),catalog=await this.catalog(c,p);const session=await p.naive.launch(c,agent,run.requestKey,catalog);run.sessionId=session.id;run.status=session.status;run.error=null;c.status='Agent working';return this.store.save(c);
  });}
  async refresh(id:string){return this.locked(id,async()=>{
    const c=this.store.get(id),p=this.providers();
    for(const tool of c.tools.filter(t=>t.state==='running'&&t.runId)){
      const receipt=await p.monid.result(tool.runId!);tool.receipt=receipt;
      if(toolSucceeded(receipt))tool.state='completed';else if(['FAILED','BLOCKED','STOPPED','TIMED_OUT','COMPLETED'].includes(String(receipt.status)))tool.state='blocked';
      this.store.receipt(c,'Monid','run.updated',receipt);
    }
    const run=c.runs.at(-1);
    if(run?.sessionId&&!run.result&&!['failed','cancelled','invalid'].includes(run.status)){
      const page=await p.naive.events(run.sessionId,run.lastSeq);
      for(const event of page.data){run.lastSeq=Math.max(run.lastSeq,event.seq);if(event.type==='message.delta'||event.type.startsWith('span.'))continue;this.store.receipt(c,'Naïve',event.type,{sessionId:run.sessionId,eventId:event.id,sequence:event.seq,payload:event.data});}
      const session=await p.naive.session(run.sessionId);run.status=session.status;run.stopReason=session.stop_reason;run.costMicroUsd=session.consumed_micro_usd;
      if(session.status==='idle'||session.status==='completed'){
        if(session.stop_reason==='awaiting_approval'||session.stop_reason==='awaiting_answer'){c.status='Operator input required';c.blocker='Open the session in Naïve Studio to answer the runtime’s pending request.';}
        else if(session.structured_output){
          try{
            const result=parseResult(session.structured_output,c,run.step);
            const catalog=this.store.setting<Json[]>(`catalog:${id}`)||[];
            const requests=result.tool_requests.map(request=>{const inspection=catalog.find(t=>t.provider===request.provider&&t.endpoint===request.endpoint);if(!inspection)throw new Error('Agent requested a tool outside the inspected Monid catalog.');return {request,inspection};});
            run.result=result;run.reservedMicroUsd=0;
            for(const doc of result.artifacts)c.artifacts.push({id:randomUUID(),...doc,sessionId:run.sessionId});
            for(const {request,inspection} of requests)c.tools.push({id:randomUUID(),request,inspection,state:'proposed',runId:null,receipt:null});
            for(const draft of result.email_drafts)c.drafts.push({...draft,id:randomUUID(),state:'draft',messageId:null,threadId:null});
            c.status=result.decision==='ready'?'Step ready':result.decision==='review'?'Needs review':'Blocked';c.blocker=result.decision==='ready'?null:result.summary;
            if(result.tool_requests.length||result.email_drafts.length){c.status='Approval queue';c.blocker='Review the proposed Monid tool execution and AgentMail correspondence.';}
          }catch(error){run.result=null;run.status='invalid';run.error=error instanceof Error?error.message:'Invalid structured result';c.status='Needs review';c.blocker=run.error;}
        }else{run.status='invalid';run.reservedMicroUsd=0;c.status='Needs review';c.blocker='Naïve did not produce a valid structured handoff.';}
      }else if(session.status==='failed'||session.status==='cancelled'){run.reservedMicroUsd=0;c.status='Needs attention';c.blocker=`Naïve session ${session.status}; no stage completion is claimed.`;}
    }
    return this.store.save(c);
  });}
  async executeTool(id:string,taskId:string){return this.locked(id,async()=>{
    const c=this.store.get(id),task=c.tools.find(t=>t.id===taskId);if(!task||task.state!=='proposed'||!task.inspection)throw new Error('This Monid request cannot be executed again.');
    const price=flatPrice(task.inspection);if(price===null||price>.25)throw new Error('Only inspected, flat-priced tools up to $0.25 are enabled. Metered tools require a separate spending policy.');
    task.state='submitting';this.store.save(c);
    try{const receipt=await this.providers().monid.run(task.request);if(typeof receipt.runId!=='string')throw new Error('Missing Monid run ID.');task.runId=receipt.runId;task.receipt=receipt;task.state=toolSucceeded(receipt)?'completed':['READY','RUNNING','STOPPING'].includes(String(receipt.status))?'running':'blocked';this.store.receipt(c,'Monid','run.receipt',receipt);}
    catch{task.state='unknown';c.status='Needs reconciliation';c.blocker='Monid execution may have been accepted. Check the provider run ledger before attempting another call.';}
    return this.store.save(c);
  });}
  async send(id:string,draftId:string){return this.locked(id,async()=>{
    const c=this.store.get(id),draft=c.drafts.find(d=>d.id===draftId);
    if(!draft||!['draft','unknown'].includes(draft.state)||!c.inboxId)throw new Error('This email cannot be sent.');
    if(!c.input.contactConsent||draft.to!==c.input.ownerEmail)throw new Error('Owner contact permission is required for this exact recipient.');
    draft.state='sending';this.store.save(c);
    try{const receipt=await this.providers().mail.send(c.inboxId,c.id,draft,draft.id);draft.messageId=receipt.messageId;draft.threadId=receipt.threadId;draft.state='sent';this.store.receipt(c,'AgentMail','message.sent',{inboxId:c.inboxId,messageId:receipt.messageId,threadId:receipt.threadId,to:draft.to});}
    catch{draft.state='unknown';c.blocker='Delivery requires reconciliation. A retry uses the same AgentMail idempotency key.';}
    return this.store.save(c);
  });}
  async inbox(id:string){return this.locked(id,async()=>{
    const c=this.store.get(id);if(!c.inboxId)throw new Error('The case has no AgentMail inbox.');const mail=this.providers().mail,result=await mail.messages(c.inboxId),threads=new Set(c.drafts.flatMap(d=>d.threadId?[d.threadId]:[]));
    const messages=result.messages.filter(m=>threads.has(m.threadId)||m.subject?.includes(`[Claim ${c.id}]`));
    for(const message of messages){
      if(c.drafts.some(d=>d.messageId===message.messageId)||c.receipts.some(r=>r.kind==='message.received'&&r.data.messageId===message.messageId))continue;
      const full=await mail.message(c.inboxId,message.messageId);
      this.store.receipt(c,'AgentMail','message.received',{messageId:message.messageId,threadId:message.threadId,subject:message.subject||'',text:(full.extractedText||full.text||'').slice(0,20000),from:message.from});
    }
    return {inboxId:c.inboxId,messages};
  });}
  advance(id:string){const c=this.store.get(id),run=c.runs.at(-1);if(!run?.result||run.result.decision!=='ready')throw new Error('A ready Naïve structured result is required.');if(c.tools.some(t=>t.state!=='completed')||c.drafts.some(d=>d.state!=='sent'))throw new Error('Resolve the pending provider actions first.');
    if(c.stage==='find'&&!c.tools.some(t=>t.state==='completed'))throw new Error('A completed Monid source-data run is required for this handoff.');
    if(['signup','file','collect'].includes(c.stage))throw new Error('This stage requires a verified authorization, filing or payment adapter receipt before advancement.');
    const index=stages.indexOf(c.stage);c.stage=stages[index+1]||'collect';c.status='Ready';c.blocker=null;return this.store.save(c);}
  async pause(id:string){return this.locked(id,async()=>{const c=this.store.get(id),run=c.runs.at(-1);if(run?.sessionId)await this.providers().naive.interrupt(run.sessionId);c.auto=false;c.status='Paused';return this.store.save(c);});}
  enableAuto(id:string){const c=this.store.get(id);c.auto=true;return this.store.save(c);}
  async tick(){
    for(const saved of this.store.list().filter(c=>c.auto)){
      if(this.locks.has(saved.id))continue;
      try{
        let c=saved;const active=c.runs.at(-1);
        if(active?.sessionId&&!active.result&&!['invalid','failed','cancelled'].includes(active.status))c=await this.refresh(c.id);
        else if(c.tools.some(t=>t.state==='running'))c=await this.refresh(c.id);
        const latest=c.runs.at(-1);
        if(c.tools.some(t=>t.state!=='completed')||c.drafts.some(d=>d.state!=='sent'))continue;
        if(!latest){await this.run(c.id);continue;}
        if(latest.result&&c.tools.some(t=>t.state==='completed'&&!latest.toolContext.includes(t.id))){await this.run(c.id);continue;}
        if(latest.result?.decision==='ready'){c=this.advance(c.id);await this.run(c.id);}
      }catch(error){const c=this.store.get(saved.id);c.auto=false;c.blocker=error instanceof Error?error.message:'Company needs operator input.';c.status='Needs review';this.store.save(c);}
    }
  }
}
