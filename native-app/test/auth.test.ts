import {test} from 'node:test';
import assert from 'node:assert/strict';
import {mintTicket,enter} from '@usenaive-sdk/app';
import {GET as health} from '../app/api/health/route';
import {POST as tick} from '../app/api/tick/route';
import {POST as mcp} from '../app/mcp/route';

process.env.NAIVE_APP_ID='app_native_fixture';process.env.DASHBOARD_TOKEN='test-only-dashboard-token';process.env.VETTA_MCP_TOKEN='test-only-mcp-token';
async function cookie(role:string|null='owner',app='app_native_fixture'){
  const ticket=await mintTicket('test-only-dashboard-token',{sub:'usr_fixture',email:null,role,org:'org_fixture',app,exp:Math.floor(Date.now()/1000)+120});
  const response=await enter(new Request('https://native-fixture.test/api/enter',{method:'POST',body:new URLSearchParams({ticket})}),process.env);
  return {response,cookie:response.headers.get('set-cookie')?.split(';')[0]||''};
}
test('native health and workflow execution require actual Studio authentication',async()=>{
  assert.equal((await health(new Request('https://native-fixture.test/api/health'))).status,401);
  assert.equal((await tick(new Request('https://native-fixture.test/api/tick',{method:'POST'}))).status,401);
  const session=await cookie();assert.equal(session.response.status,303);assert.ok(session.cookie);
  const response=await health(new Request('https://native-fixture.test/api/health',{headers:{cookie:session.cookie}}));assert.equal(response.status,200);const data=await response.json();assert.equal(data.providers.length,3);assert.equal(data.requiresToken,false);
  assert.equal((await health(new Request('https://native-fixture.test/api/health',{headers:{cookie:session.cookie+'invalid'}}))).status,401);
});
test('native app tickets are bound to the app and writes retain owner and origin checks',async()=>{
  assert.equal((await cookie('owner','app_other')).response.status,401);
  const member=await cookie('member');assert.equal((await tick(new Request('https://native-fixture.test/api/tick',{method:'POST',headers:{cookie:member.cookie}}))).status,403);
  const owner=await cookie();assert.equal((await tick(new Request('https://native-fixture.test/api/tick',{method:'POST',headers:{cookie:owner.cookie,origin:'https://untrusted.test'}}))).status,403);
});
test('native MCP is authenticated and exposes only bounded company operations',async()=>{
  const request=(authorized:boolean)=>new Request('https://native-fixture.test/mcp',{method:'POST',headers:{'content-type':'application/json',...(authorized?{authorization:'Bearer test-only-mcp-token'}:{})},body:JSON.stringify({jsonrpc:'2.0',id:1,method:'tools/list'})});
  assert.equal((await mcp(request(false))).status,401);const response=await mcp(request(true));assert.equal(response.status,200);const value=await response.json();assert.deepEqual(value.result.tools.map((tool:{name:string})=>tool.name),['claimos_summary','claimos_tick','claimos_case']);assert.equal(JSON.stringify(value).includes('test-only-mcp-token'),false);
});
