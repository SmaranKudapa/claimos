import {resolveCompany,requireViewer,json,fail} from '../../../lib/gateway';
export const dynamic='force-dynamic';
export const runtime='nodejs';
export const maxDuration=60;
export async function POST(request:Request){try{await requireViewer(request,true);const company=await resolveCompany();await company.tick();return json(await company.status());}catch(error){return fail(error);}}
