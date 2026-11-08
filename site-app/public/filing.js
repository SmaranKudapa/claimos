const select=document.querySelector('#filing-county'),status=document.querySelector('#filing-status'),root=document.querySelector('#filing-guide');
const node=(tag,text,cls)=>{const n=document.createElement(tag);n.textContent=text;if(cls)n.className=cls;return n;};
function link(text,url,cls='btn'){const a=node('a',text,cls);a.href=url;a.target='_blank';a.rel='noopener noreferrer';return a;}
let request=0;
async function load(){const current=++request;root.replaceChildren();if(!select.value){status.textContent='Choose a county to see its official filing destination and methods.';return;}status.textContent='Loading county filing instructions…';
 try{const r=await fetch('/api/filing?county='+encodeURIComponent(select.value));if(!r.ok)throw new Error();const d=await r.json();if(current!==request)return;
 const card=node('article','','filing-directory');card.append(node('span',`${d.county.toUpperCase()} COUNTY · OFFICIAL DESTINATION`,'label'),node('h2',d.destination),node('p',d.adapter));
 const facts=node('dl','','filing-facts');for(const [label,value]of [['How to submit',d.methods],['Where to send it',d.address],['Other physical delivery address',d.physical_address],['Filing fee',d.fee],['Deadline',d.deadline]]){const row=node('div','');row.append(node('dt',label));const dd=node('dd','');if(Array.isArray(value)){const ul=node('ul','');value.forEach(v=>ul.append(node('li',v)));dd.append(ul);}else dd.textContent=value;row.append(dd);facts.append(row);}card.append(facts);
 const actions=node('div','','pills');actions.append(link('Open official county instructions ↗',d.instructions_url),link('Get the DR-486 form ↗',d.form_url,'pill'),link('All official petition forms ↗',d.forms_url,'pill'));card.append(actions,node('p',d.evidence_exchange,'caption'));
 const ol=node('ol','','filing-sequence');d.steps.forEach(step=>ol.append(node('li',step)));card.append(node('h3','Before, during and after filing'),ol);root.append(card);status.textContent=`County source checked ${d.checked_at}. Confirm current instructions and case-specific requirements before submitting.`;history.replaceState(null,'','/filing?county='+encodeURIComponent(d.county));
 }catch{if(current===request)status.textContent='We could not load the guide. No filing method or deadline has been inferred.';}
}
const county=new URLSearchParams(location.search).get('county');if(county&&[...select.options].some(o=>o.value.toLowerCase()===county.toLowerCase()))select.value=[...select.options].find(o=>o.value.toLowerCase()===county.toLowerCase()).value;select.addEventListener('change',load);load();
