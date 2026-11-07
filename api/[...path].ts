import type { IncomingMessage,ServerResponse } from 'node:http';
import { timingSafeEqual } from 'node:crypto';

export default async function handler(req:IncomingMessage,res:ServerResponse){
  const send=(status:number,value:unknown)=>{res.writeHead(status,{'content-type':'application/json','cache-control':'no-store','x-content-type-options':'nosniff'});res.end(JSON.stringify(value));};
  const url=new URL(req.url||'/api/status','https://claimos.invalid'),origin=process.env.CLAIMOS_API_ORIGIN||'',token=process.env.CLAIMOS_OPERATOR_TOKEN||'';
  if(!origin){
    if(url.pathname==='/api/health')return send(200,{requiresToken:false,providers:[{name:'Naïve',ready:false,role:'Managed agents · sessions · native budgets'},{name:'Monid',ready:false,role:'Tool discovery · execution · receipts'},{name:'AgentMail',ready:false,role:'Claim inbox · correspondence · replies'}]});
    return send(503,{error:'The company workspace needs its durable provider backend. Use the local company workspace while the authenticated cloud backend is connected.'});
  }
  if(!token)return send(503,{error:'Operator authentication is required for the hosted company backend.'});
  if(url.pathname==='/api/health')return send(200,{requiresToken:true,providers:[{name:'Naïve',ready:false,role:'Connect through the authenticated company backend'},{name:'Monid',ready:false,role:'Connect through the authenticated company backend'},{name:'AgentMail',ready:false,role:'Connect through the authenticated company backend'}]});
  const supplied=Buffer.from(String(req.headers.authorization||'').replace(/^Bearer /,'')),expected=Buffer.from(token);
  if(supplied.length!==expected.length||!timingSafeEqual(supplied,expected))return send(401,{error:'Enter the operator token.'});
  const host=String(req.headers.host||'');
  if(req.headers.origin&&req.headers.origin!==`https://${host}`)return send(403,{error:'Request origin is not permitted.'});
  try{
    const base=new URL(origin);if(base.protocol!=='https:'||base.username||base.password)throw new Error('Invalid backend origin');
    const target=new URL(url.pathname+url.search,base);if(target.origin!==base.origin||!target.pathname.startsWith('/api/'))throw new Error('Invalid backend path');
    const chunks:Buffer[]=[];let size=0;for await(const chunk of req){size+=chunk.length;if(size>500000)return send(413,{error:'Request exceeds the input limit.'});chunks.push(Buffer.from(chunk));}
    const response=await fetch(target,{method:req.method||'GET',headers:{authorization:`Bearer ${token}`,...(chunks.length?{'content-type':'application/json'}:{})},...(chunks.length?{body:Buffer.concat(chunks)}:{}),signal:AbortSignal.timeout(45000),redirect:'error'});
    res.writeHead(response.status,{'content-type':response.headers.get('content-type')||'application/json','cache-control':'no-store','x-content-type-options':'nosniff',...(response.headers.has('content-disposition')?{'content-disposition':response.headers.get('content-disposition')!}:{})});res.end(Buffer.from(await response.arrayBuffer()));
  }catch{return send(502,{error:'The company backend could not be reached. No completed action is claimed.'});}
}
