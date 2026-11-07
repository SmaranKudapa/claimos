import {test} from 'node:test';
import assert from 'node:assert/strict';
import {Company,type Providers} from '../lib/company';
import type {Repository} from '../lib/repository';
import {newCase,parseInput} from '../lib/domain';

test('neither teammate Find agent receives a new session from the native app',async()=>{
  for(const protectedId of ['agt_xy70yv97k94f0zwt0h552gj486','agt_nkzq336mtm8t2wv3dcc93hp8ps']){
    let writes=0;const unexpected=():never=>{writes++;throw new Error('Unexpected provider call');};
    const providers:Providers={naive:{create:unexpected,launch:unexpected,session:unexpected,events:unexpected,interrupt:unexpected,repair:unexpected},monid:{discover:unexpected,inspect:unexpected,run:unexpected,result:unexpected},mail:{createInbox:unexpected,send:unexpected,messages:unexpected,message:unexpected}};
    const record=newCase(parseInput({address:'Protected-agent fixture',parcel:'TEST',county:'Lee County, Florida',brief:'No external actions.',sources:['https://www.leepa.org/']}));
    const repository:Repository={setting:<T>(key:string)=>(key==='agents'?[{id:protectedId,version:2,step:'find'}]:null) as T|null,set:()=>{},ensureSetting:(_key,value)=>value,get:()=>record,list:()=>[record],save:()=>{throw new Error('Unexpected case mutation');},receipt:()=>{throw new Error('Unexpected receipt');},acquire:()=>true,release:()=>{}};
    await assert.rejects(new Company(repository,()=>providers).run(record.id),/teammate/);assert.equal(writes,0);
  }
});
