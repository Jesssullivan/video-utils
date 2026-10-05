import {readFileSync, writeFileSync} from 'node:fs';
import {pcen, PcenState} from '../xoxd-spectrogram/src/core/pcen.ts';
const d=JSON.parse(readFileSync(process.argv[2], 'utf8'));
const results=d.cases.map((c:any)=>{
 const rows=pcen(c.rows,c.cfg,c.params);
 const state=new PcenState(c.cfg,c.params);
 let delta=0;
 for(let t=0;t<c.rows.length;t++) {
  const out=state.step(c.rows[t]);
  for(let b=0;b<out.length;b++) delta=Math.max(delta,Math.abs(out[b]-rows[t][b]));
 }
 return {id:c.id,rows:rows.map(x=>Array.from(x)),streaming_batch_max_absolute_difference:delta};
});
writeFileSync(process.argv[3],JSON.stringify({runtime:Bun.version,results}));
