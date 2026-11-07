import type {IncomingMessage,ServerResponse} from 'node:http';
import {timingSafeEqual} from 'node:crypto';
import type {Company} from './company.js';
import {configuration,readiness} from './config.js';
import {object,text,type Json} from './domain.js';
import {CaseBusyError,RepositoryConflict} from './repository.js';

export function json(res:ServerResponse,status:number,value:unknown){res.writeHead(status,{'content-type':'application/json','cache-control':'no-store','x-content-type-options':'nosniff'});res.end(JSON.stringify(value));}
async function body(req:IncomingMessage):Promise<Json>{
  if(!String(req.headers['content-type']).startsWith('application/json'))throw new Error('Send a JSON request.');
  const existing=(req as IncomingMessage&{body?:unknown}).body;
  if(existing!==undefined){if(!object(existing)||Buffer.byteLength(JSON.stringify(existing))>500000)throw new Error('A request object under 500 KB is required.');return existing;}
  const chunks:Buffer[]=[];let size=0;
  for await(const chunk of req){size+=chunk.length;if(size>500000)throw new Error('Request exceeds the input limit.');chunks.push(Buffer.from(chunk));}
  const parsed:unknown=JSON.parse(Buffer.concat(chunks).toString());if(!object(parsed))throw new Error('A request object is required.');return parsed;
}
export function companyApi(resolveCompany:()=>Promise<Company>,options:{hosted:boolean;configured:()=>boolean;config?:typeof configuration}){
  return async(req:IncomingMessage,res:ServerResponse)=>{
    try{
      const host=String(req.headers.host||''),url=new URL(req.url||'/api/status',`${options.hosted?'https':'http'}://${host||'claimos.invalid'}`),config=(options.config||configuration)();
      if(req.method==='GET'&&url.pathname==='/api/health')return json(res,200,{providers:readiness(),requiresToken:options.hosted||Boolean(config.operatorToken),storage:{provider:config.databaseUrl?'Neon':'SQLite',configured:options.configured()}});
      if(!options.configured())return json(res,503,{error:'Connect the durable Neon case database before opening the hosted workspace.'});
      if(options.hosted&&!config.operatorToken)return json(res,503,{error:'Operator authentication is required for the hosted company workspace.'});
      if(config.operatorToken){const supplied=Buffer.from(String(req.headers.authorization||'').replace(/^Bearer /,'')),expected=Buffer.from(config.operatorToken);if(supplied.length!==expected.length||!timingSafeEqual(supplied,expected))return json(res,401,{error:'Enter the operator token.'});}
      if(req.headers.origin&&req.headers.origin!==`${options.hosted?'https':'http'}://${host}`)return json(res,403,{error:'Request origin is not permitted.'});
      if(req.headers['sec-fetch-site']==='cross-site')return json(res,403,{error:'Cross-site access is not permitted.'});
      const company=await resolveCompany(),parts=url.pathname.split('/').filter(Boolean),id=parts[1]==='cases'?parts[2]:undefined;
      if(req.method==='GET'&&url.pathname==='/api/status')return json(res,200,await company.status());
      if(req.method==='GET'&&id&&parts.length===3)return json(res,200,await company.store.get(id));
      if(req.method==='GET'&&id&&parts[3]==='inbox')return json(res,200,await company.inbox(id));
      if(req.method==='GET'&&id&&parts[3]==='artifacts'&&parts.length===5){
        const artifact=(await company.store.get(id)).artifacts.find(a=>a.id===parts[4]);if(!artifact)return json(res,404,{error:'Document not found.'});
        res.writeHead(200,{'content-type':'text/markdown; charset=utf-8','content-disposition':'attachment; filename="claim-evidence.md"','cache-control':'no-store','x-content-type-options':'nosniff'});res.end(artifact.markdown);return;
      }
      if(req.method==='POST'){
        const input=await body(req);
        if(url.pathname==='/api/activate')return json(res,200,await company.activate());
        if(url.pathname==='/api/cases')return json(res,201,await company.create(input));
        if(url.pathname==='/api/tick'){await company.tick();return json(res,200,await company.status());}
        if(!id)return json(res,404,{error:'Feature endpoint not found.'});
        if(parts[3]==='research'){if(input.approved!==true)throw new Error('Approve the free, official-county research policy.');return json(res,200,await company.enableResearch(id));}
        if(parts[3]==='run'){if(input.auto===true)await company.enableAuto(id);return json(res,202,await company.run(id));}
        if(parts[3]==='refresh')return json(res,200,await company.refresh(id));
        if(parts[3]==='recover')return json(res,200,await company.recoverLaunch(id));
        if(parts[3]==='advance')return json(res,200,await company.advance(id));
        if(parts[3]==='pause')return json(res,200,await company.pause(id));
        if(parts[3]==='tools'){if(input.approved!==true)throw new Error('Review and approve the Monid tool input and price.');return json(res,200,await company.executeTool(id,text(input.taskId,'Tool request')));}
        if(parts[3]==='mail'){if(input.approved!==true)throw new Error('Approve the exact recipient and email.');return json(res,200,await company.send(id,text(input.draftId,'Draft')));}
      }
      return json(res,404,{error:'Feature endpoint not found.'});
    }catch(error){const conflict=error instanceof CaseBusyError||error instanceof RepositoryConflict,provider=error instanceof Error&&error.name!=='Error'&&!conflict;json(res,conflict?409:400,{error:provider?'Provider request needs attention. Check the provider account and credentials.':error instanceof Error?error.message:'Request could not be completed.'});}
  };
}
