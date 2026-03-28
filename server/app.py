"""
Local Proxy Server v4.0 - Single Process + Web Dashboard

1 CMD duy nhat:
- Flask server khoi dong NGAY (san sang nhan request)
- Chrome workers setup SONG SONG bang threads (khong can CMD rieng)
- Web dashboard tai http://server:5000/ de quan sat tat ca

Architecture:
  ┌──────────────────────────────────────────────────┐
  │ Single Process (server/app.py)                    │
  │  - Flask server (port 5000)                       │
  │  - Web Dashboard (/)                              │
  │  - Task queue (FIFO)                              │
  │  - N Chrome worker threads (setup song song)      │
  │  - KHOI DONG NGAY → Chrome setup phia sau         │
  └──────────────────────────────────────────────────┘

API:
  GET  /                            - Web Dashboard
  POST /api/fix/create-image-veo3   - Tao anh (xep hang doi)
  GET  /api/fix/task-status         - Poll ket qua
  GET  /api/status                  - Server status (JSON)
  GET  /api/workers                 - Worker stats (JSON)
  GET  /api/queue                   - Queue info (JSON)
"""
import sys
import os
import uuid
import json
import time
import threading
import traceback
from pathlib import Path

sys.stdout.reconfigure(encoding='utf-8', errors='replace')

TOOL_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(TOOL_DIR))

from flask import Flask, request, jsonify, Response

app = Flask(__name__)

# ============================================================
# Shared State
# ============================================================
tasks = {}
task_lock = threading.Lock()

task_queue = []
queue_lock = threading.Lock()

# Chrome Pool (init in main)
chrome_pool = None

# Server logs (cho dashboard)
server_logs = []
log_lock = threading.Lock()
MAX_LOGS = 200

stats = {
    'total_received': 0,
    'total_completed': 0,
    'total_failed': 0,
    'start_time': time.time(),
}


def server_log(msg: str, level: str = "INFO"):
    """Log + luu cho dashboard."""
    ts = time.strftime("%H:%M:%S")
    line = f"[{ts}] [{level}] {msg}"
    print(line)
    with log_lock:
        server_logs.append({"time": ts, "level": level, "msg": msg})
        if len(server_logs) > MAX_LOGS:
            server_logs.pop(0)


def _get_queue_position(task_id: str) -> int:
    if chrome_pool:
        for w in chrome_pool.workers:
            if w.current_task_id == task_id:
                return 0
    with queue_lock:
        try:
            return task_queue.index(task_id) + 1
        except ValueError:
            return -1


# ============================================================
# Web Dashboard
# ============================================================

DASHBOARD_HTML = """<!DOCTYPE html>
<html lang="vi">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Server Dashboard</title>
<style>
* { margin: 0; padding: 0; box-sizing: border-box; }
body { font-family: 'Segoe UI', Tahoma, sans-serif; background: #0f172a; color: #e2e8f0; }
.header { background: #1e293b; padding: 16px 24px; border-bottom: 1px solid #334155; display: flex; justify-content: space-between; align-items: center; }
.header h1 { font-size: 18px; color: #38bdf8; }
.header .status { font-size: 13px; color: #94a3b8; }
.header .status .dot { display: inline-block; width: 8px; height: 8px; border-radius: 50%; margin-right: 6px; }
.header .status .dot.green { background: #22c55e; box-shadow: 0 0 6px #22c55e; }
.header .status .dot.yellow { background: #eab308; box-shadow: 0 0 6px #eab308; }

.grid { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; padding: 16px; }
.card { background: #1e293b; border-radius: 8px; border: 1px solid #334155; overflow: hidden; }
.card-header { padding: 12px 16px; border-bottom: 1px solid #334155; font-size: 14px; font-weight: 600; color: #94a3b8; display: flex; justify-content: space-between; }
.card-body { padding: 12px 16px; }

.stats-row { display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; padding: 0 16px 16px; }
.stat-box { background: #1e293b; border-radius: 8px; border: 1px solid #334155; padding: 16px; text-align: center; }
.stat-box .num { font-size: 28px; font-weight: 700; }
.stat-box .label { font-size: 11px; color: #94a3b8; margin-top: 4px; text-transform: uppercase; letter-spacing: 1px; }
.num.blue { color: #38bdf8; }
.num.green { color: #22c55e; }
.num.orange { color: #f97316; }
.num.red { color: #ef4444; }

/* Workers */
.worker-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(200px, 1fr)); gap: 8px; }
.worker-card { background: #0f172a; border-radius: 6px; padding: 10px 12px; border: 1px solid #334155; }
.worker-card.ready { border-color: #22c55e40; }
.worker-card.busy { border-color: #f9731640; background: #1a1200; }
.worker-card.setup { border-color: #eab30840; }
.worker-card.down { border-color: #ef444440; opacity: 0.6; }
.worker-name { font-size: 13px; font-weight: 600; margin-bottom: 4px; }
.worker-status { font-size: 11px; padding: 2px 8px; border-radius: 10px; display: inline-block; margin-bottom: 4px; }
.worker-status.ready { background: #22c55e20; color: #22c55e; }
.worker-status.busy { background: #f9731620; color: #f97316; }
.worker-status.setup { background: #eab30820; color: #eab308; }
.worker-status.down { background: #ef444420; color: #ef4444; }
.worker-info { font-size: 11px; color: #64748b; line-height: 1.6; }
.worker-task { font-size: 11px; color: #f97316; margin-top: 4px; }

/* Queue */
.queue-item { display: flex; align-items: center; padding: 6px 0; border-bottom: 1px solid #1e293b; font-size: 12px; gap: 8px; }
.queue-item:last-child { border: none; }
.queue-pos { background: #334155; color: #94a3b8; width: 24px; height: 24px; border-radius: 50%; display: flex; align-items: center; justify-content: center; font-size: 11px; font-weight: 600; flex-shrink: 0; }
.queue-prompt { flex: 1; color: #cbd5e1; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.queue-vm { color: #64748b; font-size: 11px; flex-shrink: 0; }
.queue-time { color: #64748b; font-size: 11px; flex-shrink: 0; width: 40px; text-align: right; }
.queue-empty { color: #475569; font-size: 13px; text-align: center; padding: 20px; }

/* Processing */
.proc-item { display: flex; align-items: center; padding: 6px 0; font-size: 12px; gap: 8px; border-bottom: 1px solid #1e293b; }
.proc-item:last-child { border: none; }
.proc-worker { background: #f9731620; color: #f97316; padding: 2px 8px; border-radius: 10px; font-size: 11px; flex-shrink: 0; }
.proc-prompt { flex: 1; color: #cbd5e1; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }

/* Logs */
.log-area { max-height: 300px; overflow-y: auto; font-family: 'Cascadia Code', 'Consolas', monospace; font-size: 11px; line-height: 1.5; }
.log-line { padding: 1px 0; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.log-line .ts { color: #475569; }
.log-line.INFO .msg { color: #94a3b8; }
.log-line.OK .msg { color: #22c55e; }
.log-line.WARN .msg { color: #eab308; }
.log-line.ERROR .msg { color: #ef4444; }

.full-width { grid-column: 1 / -1; }

/* Setup Panel */
.setup-overlay { position: fixed; top: 0; left: 0; width: 100%; height: 100%; background: rgba(0,0,0,0.8); display: flex; align-items: center; justify-content: center; z-index: 1000; }
.setup-panel { background: #1e293b; border: 1px solid #334155; border-radius: 12px; padding: 32px; width: 420px; }
.setup-panel h2 { color: #38bdf8; margin-bottom: 24px; font-size: 20px; text-align: center; }
.setup-row { margin-bottom: 20px; }
.setup-row label { display: block; font-size: 13px; color: #94a3b8; margin-bottom: 8px; }
.setup-row select, .setup-row input { width: 100%; padding: 10px 14px; background: #0f172a; border: 1px solid #334155; border-radius: 6px; color: #e2e8f0; font-size: 14px; }
.setup-row .hint { font-size: 11px; color: #64748b; margin-top: 4px; }
.toggle-row { display: flex; align-items: center; justify-content: space-between; }
.toggle { position: relative; width: 48px; height: 26px; }
.toggle input { opacity: 0; width: 0; height: 0; }
.toggle .slider { position: absolute; top: 0; left: 0; right: 0; bottom: 0; background: #475569; border-radius: 13px; cursor: pointer; transition: 0.3s; }
.toggle .slider:before { content: ''; position: absolute; width: 20px; height: 20px; left: 3px; bottom: 3px; background: #e2e8f0; border-radius: 50%; transition: 0.3s; }
.toggle input:checked + .slider { background: #22c55e; }
.toggle input:checked + .slider:before { transform: translateX(22px); }
.btn-start { width: 100%; padding: 14px; background: #22c55e; color: #0f172a; border: none; border-radius: 8px; font-size: 16px; font-weight: 700; cursor: pointer; margin-top: 8px; }
.btn-start:hover { background: #16a34a; }
.btn-start:disabled { background: #475569; cursor: not-allowed; color: #94a3b8; }
</style>
</head>
<body>

<!-- Setup Panel (hien khi chua start) -->
<div class="setup-overlay" id="setup-overlay" style="display:none">
    <div class="setup-panel">
        <h2>Server Settings</h2>
        <div class="setup-row">
            <div class="toggle-row">
                <label style="margin:0">IPv6 Proxy</label>
                <label class="toggle">
                    <input type="checkbox" id="cfg-ipv6" checked>
                    <span class="slider"></span>
                </label>
            </div>
            <div class="hint">BAT: Moi Chrome dung IPv6 rieng (chong 403). TAT: Dung IPv4 chung.</div>
        </div>
        <div class="setup-row">
            <label>So luong Chrome</label>
            <select id="cfg-chrome">
                <option value="0">Tat ca (tu dong detect)</option>
                <option value="1">1 Chrome</option>
                <option value="2">2 Chrome</option>
                <option value="3">3 Chrome</option>
                <option value="4">4 Chrome</option>
                <option value="5">5 Chrome</option>
            </select>
            <div class="hint">Chon so Chrome workers chay song song</div>
        </div>
        <button class="btn-start" id="btn-start" onclick="startServer()">START SERVER</button>
    </div>
</div>

<div class="header">
    <h1>Chrome Server Dashboard</h1>
    <div class="status">
        <span class="dot green" id="dot"></span>
        <span id="uptime">-</span> &nbsp;|&nbsp; Auto-refresh 2s
    </div>
</div>

<div class="stats-row" style="padding-top:16px">
    <div class="stat-box">
        <div class="num blue" id="s-workers">-</div>
        <div class="label">Workers Ready</div>
    </div>
    <div class="stat-box">
        <div class="num orange" id="s-queue">-</div>
        <div class="label">In Queue</div>
    </div>
    <div class="stat-box">
        <div class="num green" id="s-completed">-</div>
        <div class="label">Completed</div>
    </div>
    <div class="stat-box">
        <div class="num red" id="s-failed">-</div>
        <div class="label">Failed</div>
    </div>
</div>

<div class="grid">
    <!-- Workers -->
    <div class="card">
        <div class="card-header">
            <span>Chrome Workers</span>
            <span id="worker-summary">-</span>
        </div>
        <div class="card-body">
            <div class="worker-grid" id="workers"></div>
        </div>
    </div>

    <!-- Queue + Processing -->
    <div class="card">
        <div class="card-header">
            <span>Queue & Processing</span>
            <span id="queue-summary">-</span>
        </div>
        <div class="card-body">
            <div id="processing"></div>
            <div id="queue"></div>
        </div>
    </div>

    <!-- Logs -->
    <div class="card full-width">
        <div class="card-header">
            <span>Server Logs</span>
            <span id="log-count">-</span>
        </div>
        <div class="card-body">
            <div class="log-area" id="logs"></div>
        </div>
    </div>
</div>

<script>
function fmt(s) { return s < 10 ? '0'+s : s; }

async function refresh() {
    try {
        const [status, workers, queue, logsResp] = await Promise.all([
            fetch('/api/status').then(r=>r.json()),
            fetch('/api/workers').then(r=>r.json()),
            fetch('/api/queue').then(r=>r.json()),
            fetch('/api/logs').then(r=>r.json()),
        ]);

        // Stats
        document.getElementById('s-workers').textContent = status.chrome_ready + '/' + status.chrome_count;
        document.getElementById('s-queue').textContent = status.queue_size;
        document.getElementById('s-completed').textContent = status.stats.total_completed;
        document.getElementById('s-failed').textContent = status.stats.total_failed;

        let h = Math.floor(status.stats.uptime_hours);
        let m = Math.floor((status.stats.uptime_hours - h) * 60);
        document.getElementById('uptime').textContent = 'Uptime: ' + h + 'h ' + fmt(m) + 'm | Received: ' + status.stats.total_received;

        // Dot color
        let dot = document.getElementById('dot');
        dot.className = 'dot ' + (status.chrome_ready > 0 ? 'green' : 'yellow');

        // Workers
        let wHtml = '';
        let wList = workers.workers || [];
        document.getElementById('worker-summary').textContent = workers.ready + ' ready / ' + workers.total + ' total';
        wList.forEach(w => {
            let cls = w.busy ? 'busy' : (w.ready ? 'ready' : (w.status === 'setting_up' ? 'setup' : 'down'));
            let statusText = w.busy ? 'BUSY' : (w.ready ? 'READY' : (w.status || 'DOWN'));
            wHtml += '<div class="worker-card ' + cls + '">';
            wHtml += '<div class="worker-name">Chrome-' + w.index + '</div>';
            wHtml += '<span class="worker-status ' + cls + '">' + statusText + '</span>';
            wHtml += '<div class="worker-info">';
            if (w.account) wHtml += w.account.split('@')[0] + '<br>';
            if (w.ipv6) wHtml += '<span style="color:#818cf8;font-size:10px">' + w.ipv6.substring(0,25) + '</span><br>';
            wHtml += 'Done: ' + w.completed + ' | Fail: ' + w.failed;
            wHtml += '</div>';
            if (w.current_task) wHtml += '<div class="worker-task">Task: ' + w.current_task + '</div>';
            if (w.last_error) wHtml += '<div class="worker-task" style="color:#ef4444">' + w.last_error.substring(0,40) + '</div>';
            wHtml += '</div>';
        });
        document.getElementById('workers').innerHTML = wHtml || '<div class="queue-empty">No workers</div>';

        // Processing + Queue
        let pHtml = '';
        (queue.processing || []).forEach(p => {
            pHtml += '<div class="proc-item">';
            pHtml += '<span class="proc-worker">Chrome-' + p.worker + '</span>';
            pHtml += '<span class="proc-prompt">' + (p.prompt_preview || p.taskId) + '</span>';
            pHtml += '<span class="queue-vm">' + p.vm_id + '</span>';
            pHtml += '</div>';
        });
        if (pHtml) pHtml = '<div style="margin-bottom:8px;font-size:11px;color:#f97316;font-weight:600">PROCESSING</div>' + pHtml;

        let qHtml = '';
        (queue.queue || []).forEach(q => {
            qHtml += '<div class="queue-item">';
            qHtml += '<span class="queue-pos">' + q.position + '</span>';
            qHtml += '<span class="queue-prompt">' + q.prompt_preview + '</span>';
            qHtml += '<span class="queue-vm">' + q.vm_id + '</span>';
            qHtml += '<span class="queue-time">' + q.wait_time + 's</span>';
            qHtml += '</div>';
        });

        document.getElementById('queue-summary').textContent = queue.processing.length + ' processing, ' + queue.queue_size + ' queued';
        document.getElementById('processing').innerHTML = pHtml;
        document.getElementById('queue').innerHTML = qHtml || '<div class="queue-empty">Queue empty - waiting for tasks</div>';

        // Logs
        let logList = logsResp.logs || [];
        let lHtml = '';
        logList.forEach(l => {
            lHtml += '<div class="log-line ' + l.level + '"><span class="ts">' + l.time + '</span> <span class="msg">' + l.msg.replace(/</g,'&lt;') + '</span></div>';
        });
        let logArea = document.getElementById('logs');
        let wasAtBottom = logArea.scrollTop + logArea.clientHeight >= logArea.scrollHeight - 20;
        logArea.innerHTML = lHtml;
        document.getElementById('log-count').textContent = logList.length + ' lines';
        if (wasAtBottom) logArea.scrollTop = logArea.scrollHeight;

    } catch(e) {
        console.error('Refresh error:', e);
    }
}

// Setup panel logic
async function checkSetup() {
    try {
        let s = await fetch('/api/settings').then(r=>r.json());
        if (!s.started) {
            document.getElementById('setup-overlay').style.display = 'flex';
            document.getElementById('cfg-ipv6').checked = s.use_ipv6;
            document.getElementById('cfg-chrome').value = s.chrome_count;
        } else {
            document.getElementById('setup-overlay').style.display = 'none';
        }
    } catch(e) {}
}

async function startServer() {
    let btn = document.getElementById('btn-start');
    btn.disabled = true;
    btn.textContent = 'DANG KHOI DONG...';

    let ipv6 = document.getElementById('cfg-ipv6').checked;
    let chrome = parseInt(document.getElementById('cfg-chrome').value);

    // Save settings
    await fetch('/api/settings', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({use_ipv6: ipv6, chrome_count: chrome})
    });

    // Start
    await fetch('/api/start', {method: 'POST'});
    document.getElementById('setup-overlay').style.display = 'none';
}

checkSetup();
refresh();
setInterval(refresh, 2000);
</script>
</body>
</html>"""


@app.route('/')
def dashboard():
    """Web Dashboard."""
    return Response(DASHBOARD_HTML, mimetype='text/html')


@app.route('/api/logs')
def api_logs():
    """Server logs cho dashboard."""
    with log_lock:
        return jsonify({"logs": list(server_logs)})


# ============================================================
# API Endpoints (cho VMs - khong thay doi)
# ============================================================

@app.route('/api/fix/create-image-veo3', methods=['POST'])
def create_image():
    """Tao task sinh anh - xep vao hang doi."""
    try:
        data = request.get_json()
        if not data:
            return jsonify({"success": False, "error": "No JSON body"}), 400

        body_json = data.get('body_json')
        flow_auth_token = data.get('flow_auth_token', '')
        flow_url = data.get('flow_url', '')
        vm_id = data.get('vm_id', request.remote_addr or 'unknown')

        if not body_json:
            return jsonify({"success": False, "error": "Missing body_json"}), 400
        if not flow_auth_token:
            return jsonify({"success": False, "error": "Missing flow_auth_token"}), 400

        prompt = ""
        if 'requests' in body_json and body_json['requests']:
            prompt = body_json['requests'][0].get('prompt', '')
        if not prompt:
            return jsonify({"success": False, "error": "No prompt in body_json.requests[0].prompt"}), 400

        project_id = ""
        if body_json.get('clientContext', {}).get('projectId'):
            project_id = body_json['clientContext']['projectId']
        elif flow_url:
            parts = flow_url.split('/projects/')
            if len(parts) > 1:
                project_id = parts[1].split('/')[0]
        if not project_id:
            return jsonify({"success": False, "error": "No projectId found"}), 400

        req = body_json['requests'][0]
        model_name = req.get('imageModelName', 'GEM_PIX_2')
        aspect_ratio = req.get('imageAspectRatio', 'IMAGE_ASPECT_RATIO_LANDSCAPE')
        seed = req.get('seed', None)
        image_inputs = req.get('imageInputs', [])  # Reference images (media IDs)

        task_id = str(uuid.uuid4())
        with task_lock:
            tasks[task_id] = {
                'status': 'queued',
                'result': None,
                'error': None,
                'created_at': time.time(),
                'prompt': prompt,
                'project_id': project_id,
                'bearer_token': flow_auth_token,
                'model_name': model_name,
                'aspect_ratio': aspect_ratio,
                'seed': seed,
                'image_inputs': image_inputs,
                'vm_id': vm_id,
                'worker': None,
            }
            stats['total_received'] += 1

        with queue_lock:
            task_queue.append(task_id)
            queue_position = len(task_queue)

        ready = chrome_pool.total_ready() if chrome_pool else 0
        avail = chrome_pool.available_count() if chrome_pool else 0
        server_log(f"+Task {task_id[:8]}... | VM: {vm_id} | Pos: {queue_position} | Free: {avail}/{ready} | {prompt[:50]}...")

        return jsonify({
            "success": True,
            "taskId": task_id,
            "queue_position": queue_position,
        })

    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route('/api/fix/task-status', methods=['GET'])
def task_status():
    task_id = request.args.get('taskId', '')
    if not task_id:
        return jsonify({"success": False, "error": "Missing taskId"}), 400

    with task_lock:
        task = tasks.get(task_id)
    if not task:
        return jsonify({"success": False, "error": "Task not found"}), 404

    if task['status'] == 'completed':
        return jsonify({"success": True, "result": task['result']})
    elif task['status'] == 'failed':
        return jsonify({"success": False, "error": task['error']})
    else:
        position = _get_queue_position(task_id)
        response = {"success": True, "status": task['status']}
        if position > 0:
            response["queue_position"] = position
        elif position == 0:
            response["status"] = "processing"
            response["worker"] = task.get('worker')
        return jsonify(response)


@app.route('/api/status', methods=['GET'])
def server_status():
    uptime = time.time() - stats['start_time']
    with queue_lock:
        queue_size = len(task_queue)

    vm_tasks = {}
    with task_lock:
        for tid, t in tasks.items():
            vm = t.get('vm_id', '?')
            if t['status'] in ('queued', 'processing'):
                vm_tasks[vm] = vm_tasks.get(vm, 0) + 1

    total_workers = len(chrome_pool.workers) if chrome_pool else 0
    ready_workers = chrome_pool.total_ready() if chrome_pool else 0
    available_workers = chrome_pool.available_count() if chrome_pool else 0

    processing = []
    if chrome_pool:
        for w in chrome_pool.workers:
            if w.busy and w.current_task_id:
                processing.append({
                    "worker": w.index,
                    "task": w.current_task_id[:8] + "...",
                })

    return jsonify({
        "status": "running",
        "chrome_count": total_workers,
        "chrome_ready": ready_workers,
        "chrome_available": available_workers,
        "queue_size": queue_size,
        "processing": processing,
        "vm_active": vm_tasks,
        "stats": {
            "total_received": stats['total_received'],
            "total_completed": stats['total_completed'],
            "total_failed": stats['total_failed'],
            "uptime_hours": round(uptime / 3600, 2),
        },
    })


@app.route('/api/workers', methods=['GET'])
def workers_info():
    if not chrome_pool:
        return jsonify({"workers": [], "total": 0, "ready": 0, "available": 0})

    return jsonify({
        "total": len(chrome_pool.workers),
        "ready": chrome_pool.total_ready(),
        "available": chrome_pool.available_count(),
        "workers": chrome_pool.get_stats(),
    })


@app.route('/api/queue', methods=['GET'])
def queue_info():
    queue_items = []
    with queue_lock:
        queue_copy = list(task_queue)

    for i, tid in enumerate(queue_copy):
        with task_lock:
            t = tasks.get(tid, {})
        queue_items.append({
            "position": i + 1,
            "taskId": tid[:8] + "...",
            "vm_id": t.get('vm_id', '?'),
            "prompt_preview": t.get('prompt', '')[:60],
            "status": t.get('status', '?'),
            "wait_time": round(time.time() - t.get('created_at', time.time()), 1),
        })

    processing = []
    if chrome_pool:
        for w in chrome_pool.workers:
            tid = w.current_task_id
            if w.busy and tid:
                with task_lock:
                    t = tasks.get(tid, {})
                processing.append({
                    "worker": w.index,
                    "taskId": tid[:8] + "...",
                    "vm_id": t.get('vm_id', '?'),
                    "prompt_preview": t.get('prompt', '')[:60],
                })

    return jsonify({
        "queue_size": len(queue_items),
        "processing": processing,
        "queue": queue_items,
    })


# ============================================================
# Cleanup old tasks
# ============================================================

def cleanup_old_tasks():
    while True:
        time.sleep(300)
        cutoff = time.time() - 3600
        with task_lock:
            old_ids = [tid for tid, t in tasks.items()
                       if t['created_at'] < cutoff and t['status'] in ('completed', 'failed')]
            for tid in old_ids:
                del tasks[tid]
        if old_ids:
            server_log(f"Cleanup: removed {len(old_ids)} old tasks")


# ============================================================
# Main
# ============================================================

# ============================================================
# Server Settings (co the thay doi tu dashboard)
# ============================================================
server_settings = {
    'use_ipv6': True,       # Dung IPv6 cho Chrome (default: True)
    'chrome_count': 0,      # 0 = tat ca Chrome tim thay, >0 = gioi han so luong
    'started': False,       # Da bat dau setup chua
}
settings_lock = threading.Lock()


@app.route('/api/settings', methods=['GET'])
def get_settings():
    with settings_lock:
        return jsonify(server_settings)


@app.route('/api/settings', methods=['POST'])
def update_settings():
    data = request.get_json() or {}
    with settings_lock:
        if server_settings['started']:
            return jsonify({"error": "Server da bat dau, khong the thay doi"}), 400
        if 'use_ipv6' in data:
            server_settings['use_ipv6'] = bool(data['use_ipv6'])
        if 'chrome_count' in data:
            server_settings['chrome_count'] = max(0, int(data['chrome_count']))
    server_log(f"Settings updated: IPv6={server_settings['use_ipv6']}, Chrome={server_settings['chrome_count'] or 'ALL'}")
    return jsonify(server_settings)


@app.route('/api/start', methods=['POST'])
def start_server_workers():
    """Bat dau setup Chrome workers (goi tu dashboard)."""
    with settings_lock:
        if server_settings['started']:
            return jsonify({"error": "Da bat dau roi"}), 400
        server_settings['started'] = True

    threading.Thread(target=_do_start_workers, daemon=True).start()
    return jsonify({"status": "starting"})


def _do_start_workers():
    """Setup Chrome workers (chay trong background thread)."""
    global chrome_pool

    from server.chrome_pool import ChromePool, get_server_config

    with settings_lock:
        use_ipv6 = server_settings['use_ipv6']
        chrome_count = server_settings['chrome_count']
        extra_ipv6 = server_settings.get('extra_ipv6', [])

    server_log("Doc cau hinh tu Google Sheet 'SERVER'...")
    server_configs = []
    try:
        server_configs = get_server_config()
        if server_configs:
            server_log(f"Tim thay {len(server_configs)} accounts/IPv6")
        else:
            server_log("Khong tim thay config trong sheet 'SERVER'")
    except Exception as e:
        server_log(f"Loi doc sheet: {e}", "ERROR")

    # Tat IPv6 neu user chon
    if not use_ipv6:
        server_log("IPv6: TAT - Chrome se dung IPv4", "WARN")
        for cfg in server_configs:
            cfg['ipv6'] = ""

    def pool_log(msg, level="INFO"):
        server_log(msg, level)

    chrome_pool = ChromePool(log_callback=pool_log)
    chrome_pool.init_workers(server_configs)

    # Them IPv6 bo sung tu GUI (neu co)
    if extra_ipv6 and use_ipv6:
        chrome_pool._ipv6_list.extend(extra_ipv6)
        server_log(f"[IPv6] Them {len(extra_ipv6)} IPv6 bo sung tu GUI (tong: {len(chrome_pool._ipv6_list)})")

    # Gioi han so Chrome neu user chon
    if chrome_count > 0 and len(chrome_pool.workers) > chrome_count:
        removed = len(chrome_pool.workers) - chrome_count
        chrome_pool.workers = chrome_pool.workers[:chrome_count]
        server_log(f"Gioi han: chi dung {chrome_count} Chrome (bo {removed})")

    if chrome_pool.workers:
        server_log(f"Setup {len(chrome_pool.workers)} Chrome workers SONG SONG...")

        def setup_worker_thread(worker):
            """Setup 1 worker trong thread rieng. Xong → start worker loop ngay."""
            from server.chrome_session import ChromeSession
            worker_name = f"Chrome-{worker.index}"
            try:
                pool_log(f"[{worker_name}] Bat dau setup...")
                if worker.account:
                    pool_log(f"[{worker_name}] Account: {worker.account['id']}")
                if worker.ipv6:
                    pool_log(f"[{worker_name}] IPv6: {worker.ipv6}")

                session = ChromeSession(
                    chrome_portable_path=worker.chrome_path,
                    port=worker.port,
                    ipv6=worker.ipv6,
                )
                if worker.account:
                    session._account = worker.account

                ok = session.setup()
                if ok:
                    worker.session = session
                    worker.ready = True
                    pool_log(f"[{worker_name}] READY! Project: {session.project_url}", "OK")

                    t = threading.Thread(
                        target=chrome_pool._worker_loop,
                        args=(worker, task_queue, queue_lock, tasks, task_lock, stats),
                        daemon=True,
                        name=f"ChromeWorker-{worker.index}",
                    )
                    t.start()
                    pool_log(f"[{worker_name}] Worker loop STARTED!", "OK")
                else:
                    pool_log(f"[{worker_name}] Setup FAILED!", "ERROR")
            except Exception as e:
                pool_log(f"[{worker_name}] Setup error: {e}", "ERROR")
                traceback.print_exc()

        for worker in chrome_pool.workers:
            t = threading.Thread(
                target=setup_worker_thread,
                args=(worker,),
                daemon=True,
                name=f"Setup-Chrome-{worker.index}",
            )
            t.start()
            time.sleep(1)
    else:
        server_log("Khong tim thay Chrome Portable nao!", "ERROR")


if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser(description="Chrome Server v4.0")
    parser.add_argument('--no-ipv6', action='store_true', help='Tat IPv6, dung IPv4')
    parser.add_argument('--chrome', type=int, default=0, help='So Chrome (0=tat ca)')
    parser.add_argument('--auto', action='store_true', help='Tu dong start (khong doi dashboard)')
    args = parser.parse_args()

    # Apply args to settings
    server_settings['use_ipv6'] = not args.no_ipv6
    server_settings['chrome_count'] = args.chrome

    print("=" * 60)
    print("  CHROME SERVER v4.0 - Single Process + Web Dashboard")
    print("=" * 60)
    print()
    print(f"  IPv6:   {'BAT' if server_settings['use_ipv6'] else 'TAT'}")
    print(f"  Chrome: {server_settings['chrome_count'] or 'TAT CA'}")
    print()

    # Start cleanup thread
    threading.Thread(target=cleanup_old_tasks, daemon=True).start()

    if args.auto:
        # Auto-start: khong can bam nut tren dashboard
        server_settings['started'] = True
        threading.Thread(target=_do_start_workers, daemon=True).start()
        print("  Auto-start: Chrome dang setup...")
    else:
        print("  Mo dashboard va bam START de bat dau!")

    print()
    print(f"  Dashboard: http://0.0.0.0:5000/")
    print()
    print("=" * 60)
    app.run(host='0.0.0.0', port=5000, debug=False, threaded=True)
