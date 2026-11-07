import {createServer} from 'node:http';
import {readFile} from 'node:fs/promises';
import {resolve,extname,sep} from 'node:path';
import {Company} from './company.js';
import {Store} from './store.js';
import {PostgresStore} from './postgres.js';
import {configuration} from './config.js';
import {companyApi,json} from './http.js';

const config=configuration(),root=resolve('public'),store=config.databaseUrl?new PostgresStore(config.databaseUrl):new Store(resolve('.claimos/company.sqlite'));
if(store instanceof PostgresStore)await store.initialize();
const company=new Company(store),api=companyApi(async()=>company,{hosted:false,configured:()=>true});
const server=createServer(async(req,res)=>{
  try{
    const host=String(req.headers.host||'');if(!/^(localhost|127\.0\.0\.1)(:\d+)?$/.test(host))return json(res,403,{error:'Open the local Claim OS workspace.'});
    const url=new URL(req.url||'/',`http://${host}`);if(url.pathname.startsWith('/api/'))return await api(req,res);
    const file=resolve(root,`.${url.pathname==='/'||url.pathname==='/company'?'/index.html':decodeURIComponent(url.pathname)}`);if(!file.startsWith(root+sep))return json(res,404,{error:'Not found.'});
    const mime:Record<string,string>={'.html':'text/html','.js':'text/javascript','.css':'text/css','.svg':'image/svg+xml'};
    const bytes=await readFile(file);res.writeHead(200,{'content-type':mime[extname(file)]||'application/octet-stream','x-content-type-options':'nosniff'});res.end(bytes);
  }catch{json(res,404,{error:'Page not found.'});}
});
let ticking=false;
const timer=setInterval(async()=>{if(ticking)return;ticking=true;try{await company.tick();}catch{console.error('Company coordinator needs attention.');}finally{ticking=false;}},5000);timer.unref();
server.listen(config.port,'127.0.0.1',()=>console.log(`Claim OS company workspace: http://127.0.0.1:${config.port}`));
