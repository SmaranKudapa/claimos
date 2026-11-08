import {filingGuide} from '../lib/filing';
export async function GET(req:Request){const guide=filingGuide(new URL(req.url).searchParams.get('county')||'');return Response.json(guide||{error:'unsupported_county',message:'Select Lee, Hendry or Bay to view the clerk’s instructions.'},{status:guide?200:400,headers:{'cache-control':'public, max-age=3600'}});}
