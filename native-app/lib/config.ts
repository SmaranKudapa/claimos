export function configuration(){
  const get=(name:string)=>process.env[name]||'';
  return {naiveKey:get('NAIVE_API_KEY'),monidKey:get('MONID_API_KEY'),mailKey:get('AGENTMAIL_API_KEY'),mailPodId:get('AGENTMAIL_POD_ID'),model:get('NAIVE_MODEL')||'vetta/auto',databaseUrl:get('NEON_DATABASE_URL'),operatorToken:'',port:4260};
}
export function readiness(){const c=configuration();return [{name:'Naïve',ready:Boolean(c.naiveKey),role:'Managed agents · sessions · native budgets'},{name:'Monid',ready:Boolean(c.monidKey),role:'Tool discovery · inspected execution · cost receipts'},{name:'AgentMail',ready:Boolean(c.mailKey),role:'Claim inbox · approved correspondence · replies'}];}
