import {resolveCompany,requireViewer,json,fail,input} from '../../../lib/gateway';
import {text} from '../../../lib/domain';
export const dynamic='force-dynamic';
export const runtime='nodejs';
export const maxDuration=60;
async function handle(request:Request){
  try{
    const write=request.method!=='GET';await requireViewer(request,write);const url=new URL(request.url),parts=url.pathname.split('/').filter(Boolean),id=parts[1]==='cases'?parts[2]:undefined;
    const company=await resolveCompany();
    if(!write){
      if(url.pathname==='/api/status')return json(await company.status());
      if(id&&parts.length===3)return json(await company.store.get(id));
      if(id&&parts[3]==='inbox')return json(await company.inbox(id));
      if(id&&parts[3]==='artifacts'&&parts.length===5){const artifact=(await company.store.get(id)).artifacts.find(a=>a.id===parts[4]);if(!artifact)return json({error:'Document not found.'},404);return new Response(artifact.markdown,{headers:{'content-type':'text/markdown; charset=utf-8','content-disposition':'attachment; filename="claim-evidence.md"','cache-control':'no-store','x-content-type-options':'nosniff'}});}
    }else{
      const body=await input(request);
      if(url.pathname==='/api/activate')return json(await company.activate());
      if(url.pathname==='/api/cases')return json(await company.create(body),201);
      if(!id)return json({error:'Feature endpoint not found.'},404);
      if(parts[3]==='research'){if(body.approved!==true)throw new Error('Approve the free public-research policy.');return json(await company.enableResearch(id));}
      if(parts[3]==='run'){if(body.auto===true)await company.enableAuto(id);return json(await company.run(id),202);}
      if(parts[3]==='refresh')return json(await company.refresh(id));
      if(parts[3]==='recover')return json(await company.recoverLaunch(id));
      if(parts[3]==='repair')return json(await company.repairHandoff(id));
      if(parts[3]==='advance')return json(await company.advance(id));
      if(parts[3]==='pause')return json(await company.pause(id));
      if(parts[3]==='tools'){if(body.approved!==true)throw new Error('Approve the exact Monid request and price.');return json(await company.executeTool(id,text(body.taskId,'Tool request')));}
      if(parts[3]==='mail'){if(body.approved!==true)throw new Error('Approve the exact recipient and email.');return json(await company.send(id,text(body.draftId,'Draft')));}
    }
    return json({error:'Feature endpoint not found.'},404);
  }catch(error){return fail(error);}
}
export const GET=handle;
export const POST=handle;
