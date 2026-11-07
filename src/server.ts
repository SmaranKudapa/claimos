import { createServer,type IncomingMessage,type ServerResponse } from 'node:http';
import { readFile } from 'node:fs/promises';
import { resolve,extname,sep } from 'node:path';
import { timingSafeEqual } from 'node:crypto';
import { Company } from './company.js';
import { Store } from './store.js';
import { configuration,readiness } from './config.js';
import { object,text,type Json } from './domain.js';

const company=new Company(new Store(resolve('.claimos/company.sqlite'))),root=resolve('public');
const json=(res:ServerResponse,status:number,value:unknown)=>{res.writeHead(status,{'content-type':'application/json','cache-control':'no-store','x-content-type-options':'nosniff'});res.end(JSON.stringify(value));};
async function body(req:IncomingMessage):Promise<Json>{
  if(!String(req.headers['content-type']).startsWith('application/json'))throw new Error('Send a JSON request.');
  const chunks:Buffer[]=[];let size=0;
  for await(const chunk of req){size+=chunk.length;if(size>500000)throw new Error('Request exceeds the input limit.');chunks.push(Buffer.from(chunk));}
  const parsed:unknown=JSON.parse(Buffer.concat(chunks).toString());if(!object(parsed))throw new Error('A request object is required.');return parsed;
}
const server=createServer(async(req,res)=>{
  try{
    const host=String(req.headers.host||'');
    if(!/^(localhost|127\.0\.0\.1)(:\d+)?$/.test(host))return json(res,403,{error:'Open the local Claim OS workspace.'});
    const url=new URL(req.url||'/',`http://${host}`);
    if(url.pathname.startsWith('/api/')){
      if(req.headers.origin&&req.headers.origin!==`http://${host}`)return json(res,403,{error:'Request origin is not permitted.'});
      if(req.headers['sec-fetch-site']==='cross-site')return json(res,403,{error:'Cross-site access is not permitted.'});
      const config=configuration();
      if(url.pathname==='/api/health')return json(res,200,{providers:readiness(),requiresToken:Boolean(config.operatorToken)});
      if(config.operatorToken){const supplied=Buffer.from(String(req.headers.authorization||'').replace(/^Bearer /,'')),expected=Buffer.from(config.operatorToken);if(supplied.length!==expected.length||!timingSafeEqual(supplied,expected))return json(res,401,{error:'Enter the operator token.'});}
      const parts=url.pathname.split('/').filter(Boolean),id=parts[2];
      if(req.method==='GET'&&url.pathname==='/api/status')return json(res,200,company.status());
      if(req.method==='GET'&&id&&parts.length===3)return json(res,200,company.store.get(id));
      if(req.method==='GET'&&id&&parts[3]==='inbox')return json(res,200,await company.inbox(id));
      if(req.method==='GET'&&id&&parts[3]==='artifacts'){
        const artifact=company.store.get(id).artifacts.find(a=>a.id===parts[4]);if(!artifact)return json(res,404,{error:'Document not found.'});
        res.writeHead(200,{'content-type':'text/markdown; charset=utf-8','content-disposition':'attachment; filename="claim-evidence.md"','cache-control':'no-store','x-content-type-options':'nosniff'});return res.end(artifact.markdown);
      }
      if(req.method==='POST'){
        const input=await body(req);
        if(url.pathname==='/api/activate')return json(res,200,await company.activate());
        if(url.pathname==='/api/cases')return json(res,201,company.create(input));
        if(!id)throw new Error('Select a case.');
        if(parts[3]==='run'){if(input.auto===true)company.enableAuto(id);return json(res,202,await company.run(id));}
        if(parts[3]==='refresh')return json(res,200,await company.refresh(id));
        if(parts[3]==='recover')return json(res,200,await company.recoverLaunch(id));
        if(parts[3]==='advance')return json(res,200,company.advance(id));
        if(parts[3]==='pause')return json(res,200,await company.pause(id));
        if(parts[3]==='tools'){if(input.approved!==true)throw new Error('Review and approve the Monid tool input and price.');return json(res,200,await company.executeTool(id,text(input.taskId,'Tool request')));}
        if(parts[3]==='mail'){if(input.approved!==true)throw new Error('Approve the exact recipient and email.');return json(res,200,await company.send(id,text(input.draftId,'Draft')));}
      }
      return json(res,404,{error:'Feature endpoint not found.'});
    }
    const file=resolve(root,`.${url.pathname==='/'||url.pathname==='/company'?'/index.html':decodeURIComponent(url.pathname)}`);
    if(!file.startsWith(root+sep))return json(res,404,{error:'Not found.'});
    const mime:Record<string,string>={'.html':'text/html','.js':'text/javascript','.css':'text/css','.svg':'image/svg+xml'};
    const bytes=await readFile(file);res.writeHead(200,{'content-type':mime[extname(file)]||'application/octet-stream','x-content-type-options':'nosniff'});res.end(bytes);
  }catch(error){const provider=error instanceof Error&&error.name!=='Error';json(res,400,{error:provider?'Provider request needs attention. Check the provider account and credentials.':error instanceof Error?error.message:'Request could not be completed.'});}
});
let ticking=false;
const timer=setInterval(async()=>{if(ticking)return;ticking=true;try{await company.tick();}finally{ticking=false;}},3000);
timer.unref();
server.listen(configuration().port,'127.0.0.1',()=>console.log(`Claim OS company workspace: http://127.0.0.1:${configuration().port}`));
