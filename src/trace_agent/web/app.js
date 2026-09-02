const $ = id => document.getElementById(id);
const esc = value => String(value ?? '').replace(/[&<>"']/g, char => ({
  '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
}[char]));
let busy = false;
let lastEventId = 0;

function facts(items) {
  return items.map(([key, value]) =>
    `<div class="fact"><span>${esc(key)}</span><span title="${esc(value)}">${esc(value)}</span></div>`
  ).join('');
}

function render(state) {
  $('session').innerHTML = facts([
    ['ID', state.session.id], ['Turns', state.session.turns],
    ['Messages', state.session.messages], ['Max steps', state.session.max_steps],
    ['Workspace', state.session.workspace]
  ]);
  $('tools').innerHTML = state.tools.map(item => `<span class="tag">${esc(item)}</span>`).join('');
  $('memory').innerHTML = facts([
    ['Mode', state.memory.mode], ['Project', state.memory.project || '—'],
    ['Database', state.memory.database || '—']
  ]);
  $('conversation').innerHTML = state.conversation.length
    ? state.conversation.map(message => `<div class="message ${message.role}"><div class="role">${message.role === 'user' ? 'You' : 'Agent'}</div><div class="content">${esc(message.content)}</div></div>`).join('')
    : '<div class="empty">输入任务以开始会话。</div>';
  $('conversation').scrollTop = $('conversation').scrollHeight;

  const report = state.report;
  if (!report) {
    $('report').className = 'empty'; $('report').textContent = '完成任务后显示';
    $('calls').innerHTML = '暂无工具调用'; $('memories').innerHTML = '暂无召回记忆';
    return;
  }
  $('report').className = 'report-grid';
  $('report').innerHTML = `<div class="metric"><small>Status</small><strong class="status-${esc(report.status)}">${esc(report.status)}</strong></div><div class="metric"><small>Steps</small><strong>${report.steps}</strong></div><div class="metric"><small>Changed</small><strong>${report.changed_files.length}</strong></div><div class="metric"><small>Verified</small><strong>${report.verification_commands.length}</strong></div>`;
  $('calls').innerHTML = report.tool_executions.length
    ? report.tool_executions.map((item, index) => `<details><summary>${index + 1}. ${esc(item.name)} · ${item.ok ? 'OK' : 'ERROR'}</summary><pre>${esc(JSON.stringify({arguments: item.arguments, result: item.result, error: item.error}, null, 2))}</pre></details>`).join('')
    : '<div class="empty">本轮没有工具调用</div>';
  $('memories').innerHTML = report.retrieved_memories.length
    ? report.retrieved_memories.map(item => `<div class="memory-card">${esc(item)}</div>`).join('')
    : '<div class="empty">本轮没有召回记忆</div>';
  const diffs = report.tool_executions.filter(item => item.result?.diff).map(item => item.result.diff).join('\n');
  if (diffs) $('diff').textContent = diffs;
}

function setRunning(running) {
  busy = running;
  $('send').disabled = running;
  $('cancel').disabled = !running;
  $('send').textContent = running ? 'Agent 运行中…' : '发送任务';
  $('run-state').textContent = running ? '正在执行，可在右侧查看实时轨迹' : 'Enter 换行 · Ctrl+Enter 发送';
}

function appendEvents(events) {
  if (!events.length) return;
  if ($('activity').querySelector('.empty')) $('activity').innerHTML = '';
  for (const event of events) {
    lastEventId = Math.max(lastEventId, event.id);
    const node = document.createElement('div');
    node.className = `event ${event.kind}`;
    node.textContent = event.message;
    $('activity').appendChild(node);
  }
  $('activity').scrollTop = $('activity').scrollHeight;
}

async function pollEvents() {
  try {
    const response = await fetch(`/api/events?after=${lastEventId}`);
    const data = await response.json();
    appendEvents(data.events || []);
    if (busy) setRunning(data.running);
  } catch (_) {}
}

async function load() {
  const response = await fetch('/api/state');
  const state = await response.json();
  render(state); setRunning(state.session.running);
}

async function send(event) {
  event.preventDefault();
  const task = $('task').value.trim();
  if (!task || busy) return;
  setRunning(true); $('activity').innerHTML = '';
  try {
    const response = await fetch('/api/send', {
      method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({task})
    });
    const data = await response.json();
    if (!response.ok) throw Error(data.error || 'request failed');
    $('task').value = ''; render(data); await diff();
  } catch (error) {
    alert(error.message);
  } finally {
    setRunning(false); await pollEvents();
  }
}

async function cancel() {
  const response = await fetch('/api/cancel', {method: 'POST'});
  const data = await response.json();
  if (data.requested) $('run-state').textContent = '已请求停止，等待当前 API 或工具调用返回';
}

async function diff() {
  try {
    const response = await fetch('/api/diff');
    const data = await response.json();
    $('diff').textContent = response.ok ? (data.diff || '暂无改动') : (data.error || 'Diff 获取失败');
  } catch (error) { $('diff').textContent = error.message; }
}

$('composer').addEventListener('submit', send);
$('task').addEventListener('keydown', event => { if (event.key === 'Enter' && event.ctrlKey) send(event); });
$('cancel').addEventListener('click', cancel);
$('refresh-diff').addEventListener('click', diff);
load(); diff(); setInterval(pollEvents, 700);
