const $=id=>document.getElementById(id);let busy=false;
const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
function facts(items){return items.map(([k,v])=>`<div class="fact"><span>${esc(k)}</span><span title="${esc(v)}">${esc(v)}</span></div>`).join('')}
function render(s){
 $('session').innerHTML=facts([['ID',s.session.id],['Turns',s.session.turns],['Messages',s.session.messages],['Max steps',s.session.max_steps],['Workspace',s.session.workspace]]);
 $('tools').innerHTML=s.tools.map(x=>`<span class="tag">${esc(x)}</span>`).join('');
 $('memory').innerHTML=facts([['Mode',s.memory.mode],['Project',s.memory.project||'—'],['Database',s.memory.database||'—']]);
 $('conversation').innerHTML=s.conversation.length?s.conversation.map(m=>`<div class="message ${m.role}"><div class="role">${m.role==='user'?'You':'Agent'}</div><div class="content">${esc(m.content)}</div></div>`).join(''):'<div class="empty">输入任务以开始会话。</div>';
 $('conversation').scrollTop=$('conversation').scrollHeight;
 const r=s.report;
 if(!r){$('report').className='empty';$('report').textContent='完成任务后显示';$('calls').innerHTML='暂无工具调用';$('memories').innerHTML='暂无召回记忆';return}
 $('report').className='report-grid';$('report').innerHTML=`<div class="metric"><small>Status</small><strong class="status-${esc(r.status)}">${esc(r.status)}</strong></div><div class="metric"><small>Steps</small><strong>${r.steps}</strong></div><div class="metric"><small>Changed</small><strong>${r.changed_files.length}</strong></div><div class="metric"><small>Verified</small><strong>${r.verification_commands.length}</strong></div>`;
 $('calls').className='';$('calls').innerHTML=r.tool_executions.length?r.tool_executions.map((x,i)=>`<details><summary>${i+1}. ${esc(x.name)} · ${x.ok?'OK':'ERROR'}</summary><pre>${esc(JSON.stringify({arguments:x.arguments,result:x.result,error:x.error},null,2))}</pre></details>`).join(''):'<div class="empty">本轮没有工具调用</div>';
 $('memories').className='';$('memories').innerHTML=r.retrieved_memories.length?r.retrieved_memories.map(x=>`<div class="memory-card">${esc(x)}</div>`).join(''):'<div class="empty">本轮没有召回记忆</div>';
 const diffs=r.tool_executions.filter(x=>x.result&&x.result.diff).map(x=>x.result.diff).join('\n');if(diffs)$('diff').textContent=diffs;
}
async function load(){const r=await fetch('/api/state');render(await r.json())}
async function send(e){e.preventDefault();const task=$('task').value.trim();if(!task||busy)return;busy=true;$('send').disabled=true;$('send').textContent='Agent 运行中…';try{const r=await fetch('/api/send',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({task})});const data=await r.json();if(!r.ok)throw Error(data.error||'request failed');$('task').value='';render(data);await diff()}catch(e){alert(e.message)}finally{busy=false;$('send').disabled=false;$('send').textContent='发送任务'}}
async function diff(){try{const r=await fetch('/api/diff');const d=await r.json();$('diff').textContent=r.ok?(d.diff||'暂无改动'):(d.error||'Diff 获取失败')}catch(e){$('diff').textContent=e.message}}
$('composer').addEventListener('submit',send);$('task').addEventListener('keydown',e=>{if(e.key==='Enter'&&e.ctrlKey)send(e)});$('refresh-diff').addEventListener('click',diff);load();diff();
