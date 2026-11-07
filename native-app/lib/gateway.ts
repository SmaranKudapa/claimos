import {timingSafeEqual} from 'node:crypto';
import {viewer,type Viewer} from '@usenaive-sdk/app';
import {Company} from './company';
import {PostgresStore} from './postgres';
import {configuration} from './config';
import {CaseBusyError,RepositoryConflict} from './repository';
import {object,type Json} from './domain';

let cached:Promise<Company>|undefined;
export async function resolveCompany(){
  if(!configuration().databaseUrl)throw new Error('Connect the Neon case database.');
  if(!cached)cached=(async()=>{const store=new PostgresStore(configuration().databaseUrl);await store.initialize();return new Company(store);})().catch(error=>{cached=undefined;throw error;});
  return cached;
}
export async function requireViewer(request:Request,write=false):Promise<Viewer>{
  const who=await viewer(request,process.env);if(!who)throw Object.assign(new Error('Open this workspace through Naïve to sign in.'),{status:401});
  if(write&&!['owner','admin'].includes(who.role||''))throw Object.assign(new Error('A company owner or administrator must approve this action.'),{status:403});
  if(write&&request.headers.get('origin')&&request.headers.get('origin')!==new URL(request.url).origin)throw Object.assign(new Error('Request origin is not permitted.'),{status:403});
  return who;
}
export function mcpAuthorized(request:Request){
  const expected=Buffer.from(process.env.CLAIMOS_COORDINATOR_TOKEN||process.env.VETTA_MCP_TOKEN||''),supplied=Buffer.from((request.headers.get('authorization')||'').replace(/^Bearer /,''));
  return expected.length>0&&expected.length===supplied.length&&timingSafeEqual(expected,supplied);
}
export function json(value:unknown,status=200){return Response.json(value,{status,headers:{'cache-control':'no-store','x-content-type-options':'nosniff'}});}
export function fail(error:unknown){
  const conflict=error instanceof CaseBusyError||error instanceof RepositoryConflict;
  const status=conflict?409:object(error)&&typeof error.status==='number'&&[400,401,403,404,409,413,503].includes(error.status)?error.status:400;
  const known=error instanceof Error&&(error.name==='Error'||conflict)&&!/(?:sk_live_|monid_live_|am_us_|postgres(?:ql)?:\/\/)/.test(error.message);
  return json({error:known?error.message:'The provider request needs attention. Check the company connections.'},status);
}
export async function input(request:Request):Promise<Json>{
  if(!request.headers.get('content-type')?.startsWith('application/json'))throw new Error('Send a JSON request.');
  const stream=request.body?.getReader();if(!stream)throw new Error('A request object is required.');const chunks:Uint8Array[]=[];let size=0;
  try{while(true){const next=await stream.read();if(next.done)break;size+=next.value.length;if(size>500000)throw Object.assign(new Error('Request exceeds the input limit.'),{status:413});chunks.push(next.value);}}finally{await stream.cancel();}
  const value:unknown=JSON.parse(Buffer.concat(chunks).toString());if(!object(value))throw new Error('A request object is required.');return value;
}
