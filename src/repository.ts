import type {CaseRecord,Json,Receipt} from './domain.js';

export class CaseBusyError extends Error {}
export class RepositoryConflict extends Error {}

export type Awaitable<T> = T|Promise<T>;
export interface Repository {
  setting<T>(key:string):Awaitable<T|null>;
  set(key:string,value:unknown):Awaitable<void>;
  ensureSetting<T>(key:string,value:T):Awaitable<T>;
  get(id:string):Awaitable<CaseRecord>;
  list():Awaitable<CaseRecord[]>;
  save(record:CaseRecord):Awaitable<CaseRecord>;
  receipt(record:CaseRecord,provider:Receipt['provider'],kind:string,data:Json):Awaitable<void>;
  acquire(key:string,owner:string):Awaitable<boolean>;
  release(key:string,owner:string):Awaitable<void>;
}
