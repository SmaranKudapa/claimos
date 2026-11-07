import {Company} from '../src/company.js';
import {PostgresStore} from '../src/postgres.js';
import {companyApi} from '../src/http.js';
import {configuration} from '../src/config.js';

let company:Promise<Company>|undefined;
async function hostedCompany(){
  if(!company)company=(async()=>{const store=new PostgresStore(configuration().databaseUrl);await store.initialize();return new Company(store);})().catch(error=>{company=undefined;throw error;});
  return company;
}
export default companyApi(hostedCompany,{hosted:true,configured:()=>Boolean(process.env.DATABASE_URL),config:()=>({...configuration(),databaseUrl:process.env.DATABASE_URL||'',operatorToken:process.env.CLAIMOS_OPERATOR_TOKEN||''})});
