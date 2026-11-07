import {object,type Json,type ToolTask,type ToolRequest} from './domain.js';
import {flatPrice} from './providers.js';

export function publicResearchRequest(task:ToolTask):ToolRequest|null{
  if(task.request.provider!=='tinyfish'||task.request.endpoint!=='/free/fetch'||!task.inspection||flatPrice(task.inspection)!==0)return null;
  const body=task.request.input.body;if(!object(body)||!Array.isArray(body.urls)||body.urls.length<1||body.urls.length>3)return null;
  const urls:string[]=[];
  for(const value of body.urls){
    if(typeof value!=='string')return null;
    try{const url=new URL(value);if(url.protocol!=='https:'||url.username||url.password||url.port||!(url.hostname==='leepa.org'||url.hostname.endsWith('.leepa.org'))||!/^\/(Display|Search|Roll|FAQ|Exemption)\//i.test(url.pathname))return null;urls.push(url.toString());}catch{return null;}
  }
  return {provider:'tinyfish',endpoint:'/free/fetch',input:{body:{urls,format:'markdown',ttl:0,purpose:'Read official Lee County public property records for Claim OS research.',per_url_timeout_ms:20000}}};
}
export function successfulExtraction(receipt:Json,request?:ToolRequest):boolean{
  if(request?.provider!=='tinyfish'||!['/free/fetch','/fetch'].includes(request.endpoint))return true;
  const body=request.input.body,output=receipt.output;
  if(!object(body)||!Array.isArray(body.urls)||!body.urls.length||!object(output)||!Array.isArray(output.errors)||output.errors.length||!Array.isArray(output.results))return false;
  return body.urls.every(url=>(output.results as unknown[]).some(result=>object(result)&&result.url===url&&typeof result.text==='string'&&result.text.trim().length>0));
}
