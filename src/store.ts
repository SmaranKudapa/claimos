import { DatabaseSync } from 'node:sqlite';
import { mkdirSync,chmodSync } from 'node:fs';
import { dirname } from 'node:path';
import { randomUUID } from 'node:crypto';
import type {CaseRecord,Json,Receipt} from './domain.js';
import type {Repository} from './repository.js';

export class Store implements Repository {
  private leases=new Map<string,string>();
  db:DatabaseSync;
  constructor(path:string){mkdirSync(dirname(path),{recursive:true,mode:0o700});this.db=new DatabaseSync(path);chmodSync(path,0o600);this.db.exec('PRAGMA journal_mode=WAL; PRAGMA busy_timeout=5000; CREATE TABLE IF NOT EXISTS cases(id TEXT PRIMARY KEY,data TEXT NOT NULL); CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY,data TEXT NOT NULL);');}
  setting<T>(key:string):T|null{const row=this.db.prepare('SELECT data FROM settings WHERE key=?').get(key);return row?JSON.parse(String(row.data)) as T:null;}
  set(key:string,value:unknown){this.db.prepare('INSERT INTO settings VALUES(?,?) ON CONFLICT(key) DO UPDATE SET data=excluded.data').run(key,JSON.stringify(value));}
  ensureSetting<T>(key:string,value:T):T{const found=this.setting<T>(key);if(found!==null)return found;this.set(key,value);return value;}
  acquire(key:string,owner:string){if(this.leases.has(key))return false;this.leases.set(key,owner);return true;}
  release(key:string,owner:string){if(this.leases.get(key)===owner)this.leases.delete(key);}
  get(id:string):CaseRecord{const row=this.db.prepare('SELECT data FROM cases WHERE id=?').get(id);if(!row)throw new Error('Case not found.');return JSON.parse(String(row.data)) as CaseRecord;}
  list():CaseRecord[]{return this.db.prepare('SELECT data FROM cases ORDER BY rowid DESC LIMIT 100').all().map(row=>JSON.parse(String(row.data)) as CaseRecord);}
  save(c:CaseRecord){c.updatedAt=new Date().toISOString();this.db.prepare('INSERT INTO cases VALUES(?,?) ON CONFLICT(id) DO UPDATE SET data=excluded.data').run(c.id,JSON.stringify(c));return c;}
  receipt(c:CaseRecord,provider:Receipt['provider'],kind:string,data:Json){c.receipts.push({id:randomUUID(),provider,kind,at:new Date().toISOString(),data});this.save(c);}
  close(){this.db.close();}
}
