import {setTimeout} from 'node:timers/promises';
import {configuration} from './config.js';
import {PostgresStore} from './postgres.js';
import {Company} from './company.js';

const config=configuration();if(!config.databaseUrl)throw new Error('Configure the Neon database for the company coordinator.');
const store=new PostgresStore(config.databaseUrl);await store.initialize();const company=new Company(store);
let stopping=false;for(const signal of ['SIGINT','SIGTERM'] as const)process.on(signal,()=>{stopping=true;});
console.log('Claim OS coordinator connected to Neon.');
while(!stopping){try{await company.tick();}catch{console.error('Coordinator cycle needs attention.');}if(!stopping)await setTimeout(5000);}
