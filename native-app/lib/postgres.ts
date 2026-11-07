import {neon,type NeonQueryFunction} from '@neondatabase/serverless';
import {randomUUID} from 'node:crypto';
import type {CaseRecord,Json,Receipt} from './domain';
import {RepositoryConflict,type Repository} from './repository';

export class PostgresStore implements Repository {
  private sql:NeonQueryFunction<false,false>;
  private versions=new WeakMap<CaseRecord,number>();
  private leases=new Map<string,string>();
  constructor(connection:string){this.sql=neon(connection);}
  async initialize(){
    await this.sql.transaction([
      this.sql`SELECT pg_advisory_xact_lock(69487261)`,
      this.sql`CREATE TABLE IF NOT EXISTS claimos_cases(id text PRIMARY KEY,data jsonb NOT NULL,version bigint NOT NULL DEFAULT 1,created_at timestamptz NOT NULL DEFAULT now(),updated_at timestamptz NOT NULL DEFAULT now())`,
      this.sql`CREATE TABLE IF NOT EXISTS claimos_settings(key text PRIMARY KEY,data jsonb NOT NULL)`,
      this.sql`CREATE TABLE IF NOT EXISTS claimos_leases(key text PRIMARY KEY,owner text NOT NULL,expires_at timestamptz NOT NULL)`
    ]);
  }
  async setting<T>(key:string):Promise<T|null>{const rows=await this.sql`SELECT data FROM claimos_settings WHERE key=${key}`;return rows[0]?.data as T??null;}
  async set(key:string,value:unknown){await this.sql`INSERT INTO claimos_settings(key,data) VALUES(${key},${JSON.stringify(value)}::jsonb) ON CONFLICT(key) DO UPDATE SET data=excluded.data`;}
  async ensureSetting<T>(key:string,value:T):Promise<T>{const rows=await this.sql`INSERT INTO claimos_settings(key,data) VALUES(${key},${JSON.stringify(value)}::jsonb) ON CONFLICT(key) DO UPDATE SET key=excluded.key RETURNING data`;return rows[0]!.data as T;}
  private decode(row:Record<string,unknown>){const record=row.data as CaseRecord;this.versions.set(record,Number(row.version));return record;}
  async get(id:string){const rows=await this.sql`SELECT data,version FROM claimos_cases WHERE id=${id}`;if(!rows[0])throw new Error('Case not found.');return this.decode(rows[0]);}
  async list(){const rows=await this.sql`SELECT data,version FROM claimos_cases ORDER BY created_at DESC,id DESC LIMIT 100`;return rows.map(row=>this.decode(row));}
  async save(record:CaseRecord){
    record.updatedAt=new Date().toISOString();const version=this.versions.get(record),owner=this.leases.get(record.id);
    const rows=version===undefined
      ?await this.sql`INSERT INTO claimos_cases(id,data) VALUES(${record.id},${JSON.stringify(record)}::jsonb) ON CONFLICT(id) DO NOTHING RETURNING version`
      :await this.sql`UPDATE claimos_cases SET data=${JSON.stringify(record)}::jsonb,version=version+1,updated_at=now() WHERE id=${record.id} AND version=${version} AND (${owner??null}::text IS NULL OR EXISTS(SELECT 1 FROM claimos_leases WHERE key=${record.id} AND owner=${owner??null} AND expires_at>clock_timestamp())) RETURNING version`;
    if(!rows[0])throw new RepositoryConflict('The case changed in another worker. Refresh before continuing.');this.versions.set(record,Number(rows[0].version));return record;
  }
  async receipt(record:CaseRecord,provider:Receipt['provider'],kind:string,data:Json){record.receipts.push({id:randomUUID(),provider,kind,at:new Date().toISOString(),data});await this.save(record);}
  async acquire(key:string,owner:string){const rows=await this.sql`INSERT INTO claimos_leases(key,owner,expires_at) VALUES(${key},${owner},clock_timestamp()+interval '5 minutes') ON CONFLICT(key) DO UPDATE SET owner=excluded.owner,expires_at=excluded.expires_at WHERE claimos_leases.expires_at<clock_timestamp() RETURNING owner`;if(!rows[0])return false;this.leases.set(key,owner);return true;}
  async release(key:string,owner:string){await this.sql`DELETE FROM claimos_leases WHERE key=${key} AND owner=${owner}`;if(this.leases.get(key)===owner)this.leases.delete(key);}
}
