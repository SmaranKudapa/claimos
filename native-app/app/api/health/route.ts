import {configuration,readiness} from '../../../lib/config';
import {requireViewer,json,fail} from '../../../lib/gateway';
export const dynamic='force-dynamic';
export const runtime='nodejs';
export async function GET(request:Request){try{await requireViewer(request);return json({providers:readiness(),requiresToken:false,storage:{provider:'Neon',configured:Boolean(configuration().databaseUrl)},runtime:'naive-native'});}catch(error){return fail(error);}}
