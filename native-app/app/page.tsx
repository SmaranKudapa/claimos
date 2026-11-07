import {headers} from 'next/headers';
import {viewer,signInUrl} from '@usenaive-sdk/app';
export const dynamic='force-dynamic';
export default async function Page(){
  const incoming=await headers(),forwarded=new Headers();incoming.forEach((value,key)=>forwarded.set(key,value));
  const who=await viewer(new Request(`https://${incoming.get('x-forwarded-host')||incoming.get('host')||'claimos.invalid'}/`,{headers:forwarded}),process.env);
  if(!who)return <main style={{maxWidth:520,margin:'15vh auto',padding:32,fontFamily:'system-ui',lineHeight:1.7}}><h1>Claim OS</h1><p>Open your company workspace through Naïve.</p><a href={signInUrl(process.env)||"https://app.usenaive.ai/"}>Open in Naïve →</a></main>;
  return <iframe title="Claim OS company workspace" src="/workspace/index.html" style={{position:'fixed',inset:0,width:'100%',height:'100dvh',border:0}}/>;
}
