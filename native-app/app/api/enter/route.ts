import {enter} from '@usenaive-sdk/app';
export async function POST(request:Request){return enter(request,process.env);}
