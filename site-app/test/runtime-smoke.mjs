import assert from 'node:assert/strict';
process.env.DATABASE_REST_URL='https://database.invalid';
process.env.DATABASE_SERVICE_KEY='runtime-test-only';
delete process.env.CLAIMOS_WORKFLOW_READ_KEY;
for(const name of ['filing','signup','stats','track','track-request','verdict','workflow']){
 const handler=await import(`../.build/api/${name}.js`);
 assert.ok(typeof handler.GET==='function'||typeof handler.POST==='function',name);
}
const filing=await import('../.build/api/filing.js');
assert.equal((await filing.GET(new Request('https://fixture.invalid/api/filing?county=Hendry'))).status,200);
const track=await import('../.build/api/track.js');
assert.equal((await track.GET(new Request('https://fixture.invalid/api/track'))).status,401);
console.log('All compiled API modules load in plain Node; filing and unauthenticated tracking responses verified.');
