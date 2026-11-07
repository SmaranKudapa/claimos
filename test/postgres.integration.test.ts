import {test} from 'node:test';
import assert from 'node:assert/strict';
import {randomUUID} from 'node:crypto';
import {neon} from '@neondatabase/serverless';
import {PostgresStore} from '../src/postgres.js';
import {RepositoryConflict} from '../src/repository.js';
import {newCase,parseInput} from '../src/domain.js';

test('Neon preserves case receipts and fences concurrent workers', {skip:!process.env.CLAIMOS_TEST_DATABASE_URL},async()=>{
  const connection=process.env.CLAIMOS_TEST_DATABASE_URL!,first=new PostgresStore(connection),second=new PostgresStore(connection),sql=neon(connection),key=`integration-${randomUUID()}`;
  await first.initialize();const record=newCase(parseInput({address:'Ephemeral database verification fixture',parcel:'TEST-NEON',county:'Lee County, Florida',brief:'Synthetic database verification; never contact or run agents.',sources:['https://www.leepa.org/']}));
  try{
    await first.save(record);const a=await first.get(record.id),b=await second.get(record.id);a.status='Receipt saved';await first.receipt(a,'Monid','integration.fixture',{runId:'test-only'});
    assert.equal((await second.get(record.id)).receipts[0]?.data.runId,'test-only');b.status='Stale update';await assert.rejects(second.save(b),RepositoryConflict);
    assert.equal(await first.acquire(key,'first'),true);assert.equal(await second.acquire(key,'second'),false);await second.release(key,'second');assert.equal(await second.acquire(key,'second'),false);await first.release(key,'first');assert.equal(await second.acquire(key,'second'),true);
    assert.equal(await first.acquire(record.id,'original'),true);const guarded=await first.get(record.id);await sql`UPDATE claimos_leases SET expires_at=clock_timestamp()-interval '1 second' WHERE key=${record.id}`;assert.equal(await second.acquire(record.id,'replacement'),true);await assert.rejects(first.save(guarded),RepositoryConflict);
  }finally{await sql`DELETE FROM claimos_cases WHERE id=${record.id}`;await sql`DELETE FROM claimos_leases WHERE key IN (${record.id},${key})`;}
});
