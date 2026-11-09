import {createClient} from '@usenaive-sdk/managed-agents';
import {db} from './lookup.js';
import {projectCards, type Card, type Snapshot} from './workflow-model.js';
const BOARD='brd_3kb4zft8yttkhm04sv6vn8ydw2';
const TTL=60_000;
let memory:Snapshot|null=null;
let pending:Promise<{snapshot:Snapshot;stale:boolean}>|null=null;
const fresh=(s:Snapshot|null)=>Boolean(s&&Date.now()-Date.parse(s.observed_at)<TTL);
async function refresh(cached:Snapshot|null) {
  const key=process.env.CLAIMOS_WORKFLOW_READ_KEY;
  if(!key){if(cached)return {snapshot:cached,stale:true};throw new Error('workflow_not_configured');}
  try{
    const client=createClient({apiKey:key,baseUrl:'https://api.vetta.sh'});const cards:Card[]=[];let after:string|undefined;
    for(let page=0;page<50;page++){
      const r=await client.board.cards.list(BOARD,{limit:100,...(after?{after}:{})});
      cards.push(...r.data);
      if(!r.has_more){const snapshot=projectCards(cards);memory=snapshot;try{await db('workflow_snapshots?on_conflict=id',{method:'POST',prefer:'resolution=merge-duplicates,return=representation',body:JSON.stringify({id:'latest',payload:snapshot,observed_at:snapshot.observed_at})});}catch{console.warn('workflow_cache_write_failed');}return {snapshot,stale:false};}
      if(!r.next_cursor)throw new Error('workflow_pagination_incomplete');after=r.next_cursor;
    }
    throw new Error('workflow_board_limit');
  }catch{
    if(cached)return {snapshot:cached,stale:true};
    throw new Error('workflow_unavailable');
  }
}
export async function getWorkflow() {
  if(fresh(memory))return {snapshot:memory!,stale:false};
  if(pending)return pending;
  pending=(async()=>{
    let cached=memory;
    try{const rows=await db('workflow_snapshots?id=eq.latest&select=payload');if(rows[0]?.payload?.cases&&rows[0]?.payload?.summary)cached=rows[0].payload as Snapshot;}catch{console.warn('workflow_cache_read_failed');}
    if(fresh(cached)){memory=cached;return {snapshot:cached!,stale:false};}
    return refresh(cached);
  })();
  try{return await pending;}finally{pending=null;}
}
