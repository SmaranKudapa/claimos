import {getWorkflow} from '../lib/workflow';
import {publicProgress} from '../lib/workflow-model';
export async function GET(){
  try{const {snapshot,stale}=await getWorkflow();return Response.json({...publicProgress(snapshot,stale),automatic_refresh:Boolean(process.env.CLAIMOS_WORKFLOW_READ_KEY)},{headers:{'cache-control':'no-store'}});}
  catch{return Response.json({error:'workflow_unavailable',message:'Workflow records are temporarily unavailable. No progress has been inferred.'},{status:503,headers:{'cache-control':'no-store'}});}
}
