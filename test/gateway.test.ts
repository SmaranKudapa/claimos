import {test} from 'node:test';
import assert from 'node:assert/strict';
import {createServer} from 'node:http';
import {mkdtempSync} from 'node:fs';
import {join} from 'node:path';
import {tmpdir} from 'node:os';
import handler from '../api/[...path].js';
import {companyApi} from '../src/http.js';
import {Company} from '../src/company.js';
import {Store} from '../src/store.js';
import {configuration} from '../src/config.js';

async function serve(api:typeof handler,work:(base:string)=>Promise<void>){const server=createServer(api);await new Promise<void>(resolve=>server.listen(0,'127.0.0.1',resolve));const address=server.address();if(!address||typeof address==='string')throw new Error('Test server unavailable.');try{await work(`http://127.0.0.1:${address.port}`);}finally{await new Promise<void>(resolve=>server.close(()=>resolve()));}}
test('hosted workspace refuses private cases without a durable database',async()=>{
  const previous=process.env.DATABASE_URL;delete process.env.DATABASE_URL;
  try{await serve(handler,async base=>{const health=await fetch(base+'/api/health');assert.equal(health.status,200);const data=await health.json();assert.equal(data.providers.length,3);assert.equal(data.requiresToken,true);assert.equal(data.storage.configured,false);const response=await fetch(base+'/api/cases',{method:'POST',headers:{'content-type':'application/json'},body:'{}'});assert.equal(response.status,503);assert.match((await response.json()).error,/durable/);});}finally{if(previous!==undefined)process.env.DATABASE_URL=previous;}
});
test('hosted cases require authentication and same-origin writes',async()=>{
  const db=new Store(join(mkdtempSync(join(tmpdir(),'claimos-http-')),'fixture.sqlite')),company=new Company(db),api=companyApi(async()=>company,{hosted:true,configured:()=>true,config:()=>({...configuration(),operatorToken:'test-only-token',databaseUrl:'test-only'})});
  try{await serve(api,async base=>{
    assert.equal((await fetch(base+'/api/status')).status,401);
    const headers={authorization:'Bearer test-only-token','content-type':'application/json'},input={address:'HTTP fixture',parcel:'TEST',county:'Lee County, Florida',brief:'Fixture; no external actions.',sources:['https://www.leepa.org/']};
    assert.equal((await fetch(base+'/api/cases',{method:'POST',headers:{...headers,origin:'https://untrusted.test'},body:JSON.stringify(input)})).status,403);
    const response=await fetch(base+'/api/cases',{method:'POST',headers,body:JSON.stringify(input)});assert.equal(response.status,201);const record=await response.json();assert.ok(record.id);
    const read=await fetch(base+'/api/cases/'+record.id,{headers});assert.equal(read.status,200);assert.equal((await read.json()).input.parcel,'TEST');
    const status=await fetch(base+'/api/status',{headers});assert.equal((await status.json()).cases.length,1);
  });}finally{db.close();}
});
