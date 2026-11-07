import {test} from 'node:test';
import assert from 'node:assert/strict';
import {createServer} from 'node:http';
import handler from '../api/[...path].js';

test('hosted workspace reports missing durable execution instead of accepting private cases',async()=>{
  const previous=process.env.CLAIMOS_API_ORIGIN;delete process.env.CLAIMOS_API_ORIGIN;
  const server=createServer(handler);await new Promise<void>(resolve=>server.listen(0,'127.0.0.1',resolve));
  const address=server.address();if(!address||typeof address==='string')throw new Error('Test server unavailable.');
  const base=`http://127.0.0.1:${address.port}`;
  try{
    const health=await fetch(base+'/api/health');assert.equal(health.status,200);const data=await health.json();assert.equal(data.providers.length,3);
    const create=await fetch(base+'/api/cases',{method:'POST',headers:{'content-type':'application/json'},body:'{}'});assert.equal(create.status,503);assert.match((await create.json()).error,/durable/);
  }finally{await new Promise<void>(resolve=>server.close(()=>resolve()));if(previous!==undefined)process.env.CLAIMOS_API_ORIGIN=previous;}
});
