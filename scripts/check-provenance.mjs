import { execFileSync } from 'node:child_process';
const expected='2026-11-07';
const format=new Intl.DateTimeFormat('en-CA',{timeZone:'America/Los_Angeles',year:'numeric',month:'2-digit',day:'2-digit'});
const entries=execFileSync('git',['log','--all','--format=%h|%aI|%cI'],{encoding:'utf8'}).trim().split('\n').filter(Boolean);
if(!entries.length)throw new Error('Repository has no feature commits.');
for(const entry of entries){const [hash,author,committer]=entry.split('|');if(format.format(new Date(author))!==expected||format.format(new Date(committer))!==expected)throw new Error(`Commit ${hash} is outside ${expected} Pacific time.`);}
console.log(`${entries.length} feature commits dated ${expected} America/Los_Angeles.`);
