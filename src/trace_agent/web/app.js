const $ = id => document.getElementById(id);
const esc = value => String(value ?? '').replace(/[&<>"']/g, char => ({
  '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
}[char]));
let busy = false;
let lastEventId = 0;
let currentState = null;
let selectedTurn = null;

function facts(items) {
  return items.map(([key, value]) =>
    `<div class="fact"><span>${esc(key)}</span><span title="${esc(value)}">${esc(value)}</span></div>`
  ).join('');
}

function render(state) {
  currentState = state;
  $('session').innerHTML = facts([
    ['标识', state.session.id], ['已完成任务', state.session.turns],
    ['上下文消息', state.session.messages], ['单任务步数上限', state.session.max_steps],
    ['工作区', state.session.workspace]
  ]);
  $('tools').innerHTML = state.tools.map(item => `<span class="tag">${esc(item)}</span>`).join('');
  $('memory').innerHTML = facts([
    ['模式', state.memory.mode], ['项目', state.memory.project || '—'],
    ['数据库', state.memory.database || '—']
  ]);
  $('welcome').classList.toggle('hidden', state.conversation.length > 0);
  $('conversation').innerHTML = state.conversation.length
    ? state.conversation.map(message => `<div class="message ${message.role}"><div class="role">${message.role === 'user' ? 'You' : 'Agent'}</div><div class="content">${esc(message.content)}</div></div>`).join('')
    : '';
  $('conversation').scrollTop = $('conversation').scrollHeight;

  if (selectedTurn === null && state.report) selectedTurn = state.report.turn;
  $('reports').innerHTML = state.reports.length
    ? [...state.reports].reverse().map(report => `<button class="history-item ${selectedTurn === report.turn ? 'active' : ''}" data-turn="${report.turn}">第 ${report.turn} 轮 · ${esc(report.status)}<small>${esc(report.task)}</small></button>`).join('')
    : '<div class="empty">暂无任务</div>';
  $('reports').querySelectorAll('.history-item').forEach(button => {
    button.addEventListener('click', () => selectReport(Number(button.dataset.turn)));
  });
  const report = selectedTurn === null
    ? state.report
    : state.reports.find(item => item.turn === selectedTurn) || state.report;
  renderReport(report);
}

function renderReport(report) {
  if (!report) {
    $('report').className = 'empty'; $('report').textContent = '完成任务后显示';
    $('calls').innerHTML = '暂无工具调用'; $('memories').innerHTML = '暂无召回记忆';
    $('file-diffs').innerHTML = '暂无文件变更';
    return;
  }
  selectedTurn = report.turn;
  const verificationLabels = {
    verified: '已验证', failed: '验证失败', unverified: '尚未验证', not_required: '无需验证'
  };
  $('report').className = 'report-grid';
  $('report').innerHTML = `<div class="metric"><small>任务状态</small><strong class="status-${esc(report.status)}">${esc(report.status)}</strong></div><div class="metric"><small>执行步数</small><strong>${report.steps}</strong></div><div class="metric"><small>改动文件</small><strong>${report.changed_files.length}</strong></div><div class="metric"><small>验证状态</small><strong class="${esc(report.verification_status)}">${esc(verificationLabels[report.verification_status] || report.verification_status)}</strong></div>`;
  $('calls').innerHTML = report.tool_executions.length
    ? report.tool_executions.map((item, index) => `<details><summary>${index + 1}. ${esc(item.name)} · ${item.ok ? '成功' : '错误'} · ${Number(item.duration_ms || 0).toFixed(1)} ms</summary><pre>${esc(JSON.stringify({arguments: item.arguments, result: item.result, error: item.error}, null, 2))}</pre></details>`).join('')
    : '<div class="empty">本轮没有工具调用</div>';
  $('memories').innerHTML = report.memory_evidence?.length
    ? report.memory_evidence.map(renderMemoryEvidence).join('')
    : '<div class="empty">本轮没有召回长期记忆</div>';
  $('file-diffs').innerHTML = report.file_diffs.length
    ? report.file_diffs.map(item => `<details><summary>${esc(item.path)} · <span class="diff-count">+${item.additions}</span> / -${item.deletions}</summary><pre>${esc(item.diff)}</pre></details>`).join('')
    : '<div class="empty">本轮没有文件变更</div>';
}

function renderMemoryEvidence(memory) {
  const trace = (memory.trace || []).map((node, index) => {
    const relation = index > 0
      ? `<div class="trace-relation">↓ ${esc(node.relation || 'DERIVED_FROM')}</div>`
      : '';
    return `${relation}<div class="trace-node"><b>${esc(node.layer)}</b><span>${esc(node.node_type)}</span><p>${esc(node.content)}</p></div>`;
  }).join('');
  const entities = (memory.entities || []).map(entity =>
    `<span class="entity-chip">${esc(entity.type)} · ${esc(entity.name)}</span>`
  ).join('');
  return `<div class="memory-evidence"><div class="memory-head"><strong>${esc(memory.layer)} · ${esc(memory.node_type)}</strong><small>${memory.verified ? '已有验证证据' : '未验证'} · score ${Number(memory.score || 0).toFixed(3)}</small></div><div class="trace-chain">${trace}</div>${entities ? `<div class="entity-list">${entities}</div>` : ''}</div>`;
}

function selectReport(turn) {
  selectedTurn = turn;
  render(currentState);
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
  selectedTurn = null; setRunning(true); $('activity').innerHTML = '';
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
$('welcome').querySelectorAll('.suggestion').forEach(button => {
  button.addEventListener('click', () => {
    $('task').value = button.dataset.prompt;
    $('task').focus();
  });
});
load(); diff(); setInterval(pollEvents, 700);
