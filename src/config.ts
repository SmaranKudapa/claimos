import { existsSync,readFileSync } from 'node:fs';
import { parseEnv } from 'node:util';
import { resolve } from 'node:path';

export function configuration(){
  const path=resolve('.env');const file=existsSync(path)?parseEnv(readFileSync(path,'utf8')):{};
  const get=(name:string)=>process.env[name]||file[name]||'';
  return {naiveKey:get('NAIVE_API_KEY'),monidKey:get('MONID_API_KEY'),mailKey:get('AGENTMAIL_API_KEY'),mailPodId:get('AGENTMAIL_POD_ID'),model:get('NAIVE_MODEL')||'vetta/auto',databaseUrl:get('DATABASE_URL'),operatorToken:get('CLAIMOS_OPERATOR_TOKEN'),port:Number(get('PORT')||4260)};
}
export function readiness(){const c=configuration();return [{name:'Naïve',ready:Boolean(c.naiveKey),role:'Managed agents · sessions · native budgets'},{name:'Monid',ready:Boolean(c.monidKey),role:'Tool discovery · inspected execution · cost receipts'},{name:'AgentMail',ready:Boolean(c.mailKey),role:'Claim inbox · approved correspondence · replies'}];}
