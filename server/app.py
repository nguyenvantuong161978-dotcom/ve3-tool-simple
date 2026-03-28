"""
Local Proxy Server - Multi-Chrome Queue System v3.0

v3.0: Multi-Process - Moi Chrome chay 1 CMD rieng
- Main CMD: Flask server + queue management (khoi dong NGAY, khong doi Chrome)
- N Worker CMDs: Moi Chrome 1 process rieng, setup song song
- Workers giao tiep voi server qua HTTP internal API

Architecture:
  ┌─────────────────────────────────────────────┐
  │ Main CMD (server/app.py)                     │
  │  - Flask server (port 5000)                  │
  │  - Task queue (FIFO)                         │
  │  - Worker registry                           │
  │  - KHOI DONG NGAY → san sang nhan request    │
  └──────────────┬──────────────────────────────┘
                 │ HTTP internal API
    ┌────────────┼────────────┬────────────┐
    ▼            ▼            ▼            ▼
  Worker-0    Worker-1    Worker-2    Worker-3
  (CMD rieng) (CMD rieng) (CMD rieng) (CMD rieng)
  Chrome-0    Chrome-1    Chrome-2    Chrome-3
  Port 19222  Port 19223  Port 19224  Port 19225

Internal API (cho workers):
  POST /internal/register       - Worker dang ky voi server
  GET  /internal/next-task      - Worker lay task tiep theo
  POST /internal/task-done      - Worker bao hoan thanh task
  GET  /internal/worker-config  - Worker lay config (account, ipv6)

External API (cho VMs - khong doi):
  POST /api/fix/create-image-veo3
  GET  /api/fix/task-status?taskId=xxx
  GET  /api/status
  GET  /api/queue
  GET  /api/workers
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

# Add parent directory to path for imports
TOOL_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(TOOL_DIR))

from flask import Flask, request, jsonify

app = Flask(__name__)

# ============================================================
# Shared Queue + Task Storage
# ============================================================
tasks = {}
task_lock = threading.Lock()

task_queue = []
queue_lock = threading.Lock()

# ============================================================
# Worker Registry (thay the ChromePool)
# ============================================================
# worker_id -> worker_info
workers = {}
worker_lock = threading.Lock()

# Stats
stats = {
    'total_received': 0,
    'total_completed': 0,
    'total_failed': 0,
    'start_time': time.time(),
}

# Server configs (doc tu Sheet)
server_configs = []


def _get_queue_position(task_id: str) -> int:
    """Tra ve vi tri trong queue (1-based). 0 = dang processing. -1 = khong trong queue."""
    with worker_lock:
        for wid, w in workers.items():
            if w.get('current_task_id') == task_id:
                return 0

    with queue_lock:
        try:
            return task_queue.index(task_id) + 1
        except ValueError:
            return -1


# ============================================================
# Internal API - Cho Workers
# ============================================================

@app.route('/internal/worker-config', methods=['GET'])
def worker_config():
    """
    Worker lay config cua minh (account, ipv6, chrome path, port).
    GET /internal/worker-config?index=0
    """
    index = int(request.args.get('index', -1))
    if index < 0:
        return jsonify({"error": "Missing index"}), 400

    cfg = server_configs[index] if index < len(server_configs) else {}

    from server.chrome_pool import CHROME_FOLDERS, BASE_PORT
    chrome_folders = CHROME_FOLDERS

    # Tim chrome folder cho index nay
    chrome_path = ""
    found_chromes = []
    for i, folder in enumerate(chrome_folders):
        chrome_dir = TOOL_DIR / folder
        chrome_exe = chrome_dir / "GoogleChromePortable.exe"
        if chrome_exe.exists():
            found_chromes.append({
                "index": i,
                "path": str(chrome_exe),
                "folder": folder,
                "port": BASE_PORT + i,
            })

    if index < len(found_chromes):
        chrome_info = found_chromes[index]
    else:
        return jsonify({"error": f"No Chrome found for index {index}"}), 404

    return jsonify({
        "index": index,
        "chrome_path": chrome_info["path"],
        "chrome_folder": chrome_info["folder"],
        "port": chrome_info["port"],
        "account": cfg.get("account"),
        "ipv6": cfg.get("ipv6", ""),
    })


@app.route('/internal/register', methods=['POST'])
def register_worker():
    """
    Worker dang ky voi server.
    POST /internal/register
    Body: { "index": 0, "account": "email", "port": 19222, "status": "ready" }
    """
    data = request.get_json()
    if not data:
        return jsonify({"error": "No JSON"}), 400

    index = data.get('index', -1)
    worker_id = f"chrome-{index}"

    with worker_lock:
        workers[worker_id] = {
            'index': index,
            'account': data.get('account', ''),
            'port': data.get('port', 0),
            'status': data.get('status', 'starting'),
            'ready': data.get('status') == 'ready',
            'busy': False,
            'current_task_id': None,
            'total_completed': data.get('total_completed', 0),
            'total_failed': data.get('total_failed', 0),
            'last_error': data.get('last_error', ''),
            'registered_at': time.time(),
            'last_heartbeat': time.time(),
        }

    status = data.get('status', 'starting')
    print(f"[WORKER] Chrome-{index} registered: {status} | Account: {data.get('account', '?')}")
    return jsonify({"success": True, "worker_id": worker_id})


@app.route('/internal/next-task', methods=['GET'])
def next_task():
    """
    Worker lay task tiep theo tu queue.
    GET /internal/next-task?worker_id=chrome-0
    """
    worker_id = request.args.get('worker_id', '')
    if not worker_id:
        return jsonify({"task": None, "error": "Missing worker_id"}), 400

    # Check worker registered
    with worker_lock:
        w = workers.get(worker_id)
        if not w or not w.get('ready'):
            return jsonify({"task": None})

    # Lay task tu queue
    task_id = None
    with queue_lock:
        if task_queue:
            task_id = task_queue.pop(0)

    if not task_id:
        return jsonify({"task": None})

    # Mark worker busy
    with worker_lock:
        if worker_id in workers:
            workers[worker_id]['busy'] = True
            workers[worker_id]['current_task_id'] = task_id

    # Update task status
    with task_lock:
        task = tasks.get(task_id)
        if task:
            task['status'] = 'processing'
            task['started_at'] = time.time()
            task['worker'] = w.get('index', -1)

    vm_id = task.get('vm_id', '?') if task else '?'
    prompt = task.get('prompt', '')[:50] if task else ''
    print(f"[DISPATCH] {worker_id} ← Task {task_id[:8]}... | VM: {vm_id} | Prompt: {prompt}...")

    return jsonify({
        "task": {
            "task_id": task_id,
            "bearer_token": task.get('bearer_token', ''),
            "project_id": task.get('project_id', ''),
            "prompt": task.get('prompt', ''),
            "model_name": task.get('model_name', 'GEM_PIX_2'),
            "aspect_ratio": task.get('aspect_ratio', 'IMAGE_ASPECT_RATIO_LANDSCAPE'),
            "seed": task.get('seed'),
            "vm_id": vm_id,
        }
    })


@app.route('/internal/task-done', methods=['POST'])
def task_done():
    """
    Worker bao hoan thanh hoac loi.
    POST /internal/task-done
    Body: { "worker_id": "chrome-0", "task_id": "xxx", "success": true, "result": {...} }
    """
    data = request.get_json()
    if not data:
        return jsonify({"error": "No JSON"}), 400

    worker_id = data.get('worker_id', '')
    task_id = data.get('task_id', '')
    success = data.get('success', False)
    result = data.get('result')
    error = data.get('error', '')

    # Update task
    with task_lock:
        task = tasks.get(task_id)
        if task:
            if success and result:
                task['status'] = 'completed'
                task['result'] = result
                task['completed_at'] = time.time()
                stats['total_completed'] += 1
            else:
                task['status'] = 'failed'
                task['error'] = error or 'Unknown error'
                stats['total_failed'] += 1

    # Update worker
    with worker_lock:
        w = workers.get(worker_id)
        if w:
            w['busy'] = False
            w['current_task_id'] = None
            w['last_heartbeat'] = time.time()
            if success:
                w['total_completed'] = w.get('total_completed', 0) + 1
                w['last_error'] = ''
            else:
                w['total_failed'] = w.get('total_failed', 0) + 1
                w['last_error'] = str(error)[:100]

    vm_id = ''
    with task_lock:
        t = tasks.get(task_id, {})
        vm_id = t.get('vm_id', '?')
        duration = time.time() - t.get('started_at', time.time())

    if success:
        print(f"[DONE] {worker_id} | Task {task_id[:8]}... | VM: {vm_id} | {duration:.1f}s | OK")
    else:
        print(f"[FAIL] {worker_id} | Task {task_id[:8]}... | VM: {vm_id} | {error[:80]}")

    return jsonify({"success": True})


@app.route('/internal/heartbeat', methods=['POST'])
def heartbeat():
    """Worker gui heartbeat de bao van song."""
    data = request.get_json() or {}
    worker_id = data.get('worker_id', '')
    with worker_lock:
        w = workers.get(worker_id)
        if w:
            w['last_heartbeat'] = time.time()
            # Update status neu co
            if 'status' in data:
                w['status'] = data['status']
                w['ready'] = data['status'] == 'ready'
    return jsonify({"ok": True})


# ============================================================
# External API - Cho VMs (khong thay doi)
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

        # Extract prompt
        prompt = ""
        if 'requests' in body_json and body_json['requests']:
            prompt = body_json['requests'][0].get('prompt', '')

        if not prompt:
            return jsonify({"success": False, "error": "No prompt in body_json.requests[0].prompt"}), 400

        # Extract project ID
        project_id = ""
        if body_json.get('clientContext', {}).get('projectId'):
            project_id = body_json['clientContext']['projectId']
        elif flow_url:
            parts = flow_url.split('/projects/')
            if len(parts) > 1:
                project_id = parts[1].split('/')[0]

        if not project_id:
            return jsonify({"success": False, "error": "No projectId found in body_json or flow_url"}), 400

        # Extract model + aspect ratio
        req = body_json['requests'][0]
        model_name = req.get('imageModelName', 'GEM_PIX_2')
        aspect_ratio = req.get('imageAspectRatio', 'IMAGE_ASPECT_RATIO_LANDSCAPE')
        seed = req.get('seed', None)

        # Tao task
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
                'vm_id': vm_id,
                'worker': None,
            }
            stats['total_received'] += 1

        with queue_lock:
            task_queue.append(task_id)
            queue_position = len(task_queue)

        # Log
        ready_count = sum(1 for w in workers.values() if w.get('ready'))
        avail_count = sum(1 for w in workers.values() if w.get('ready') and not w.get('busy'))
        print(f"[QUEUE] +Task {task_id[:8]}... | VM: {vm_id} | Pos: {queue_position} | Workers: {avail_count}/{ready_count} free | Prompt: {prompt[:50]}...")

        return jsonify({
            "success": True,
            "taskId": task_id,
            "queue_position": queue_position,
        })

    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route('/api/fix/task-status', methods=['GET'])
def task_status():
    """Poll task status."""
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
    """Server health check + queue info + worker stats."""
    uptime = time.time() - stats['start_time']

    with queue_lock:
        queue_size = len(task_queue)

    vm_tasks = {}
    with task_lock:
        for tid, t in tasks.items():
            vm = t.get('vm_id', '?')
            if t['status'] in ('queued', 'processing'):
                vm_tasks[vm] = vm_tasks.get(vm, 0) + 1

    with worker_lock:
        total_workers = len(workers)
        ready_workers = sum(1 for w in workers.values() if w.get('ready'))
        available_workers = sum(1 for w in workers.values() if w.get('ready') and not w.get('busy'))

        processing = []
        for wid, w in workers.items():
            if w.get('busy') and w.get('current_task_id'):
                processing.append({
                    "worker": w['index'],
                    "task": w['current_task_id'][:8] + "...",
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
            "uptime_hours": round(uptime / 3600, 1),
        },
    })


@app.route('/api/workers', methods=['GET'])
def workers_info():
    """Chi tiet tung Chrome worker."""
    with worker_lock:
        worker_list = [
            {
                "index": w['index'],
                "ready": w.get('ready', False),
                "busy": w.get('busy', False),
                "current_task": w['current_task_id'][:8] + "..." if w.get('current_task_id') else None,
                "account": w.get('account'),
                "completed": w.get('total_completed', 0),
                "failed": w.get('total_failed', 0),
                "last_error": w.get('last_error') or None,
                "status": w.get('status', '?'),
            }
            for wid, w in sorted(workers.items(), key=lambda x: x[1].get('index', 0))
        ]

    return jsonify({
        "total": len(worker_list),
        "ready": sum(1 for w in worker_list if w['ready']),
        "available": sum(1 for w in worker_list if w['ready'] and not w['busy']),
        "workers": worker_list,
    })


@app.route('/api/queue', methods=['GET'])
def queue_info():
    """Xem chi tiet hang doi."""
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
    with worker_lock:
        for wid, w in workers.items():
            if w.get('busy') and w.get('current_task_id'):
                with task_lock:
                    t = tasks.get(w['current_task_id'], {})
                processing.append({
                    "worker": w['index'],
                    "taskId": w['current_task_id'][:8] + "...",
                    "vm_id": t.get('vm_id', '?'),
                    "prompt_preview": t.get('prompt', '')[:60],
                })

    return jsonify({
        "queue_size": len(queue_items),
        "processing": processing,
        "queue": queue_items,
    })


# ============================================================
# Cleanup old tasks (giu toi da 1 gio)
# ============================================================

def cleanup_old_tasks():
    """Xoa tasks cu hon 1 gio."""
    while True:
        time.sleep(300)
        cutoff = time.time() - 3600
        with task_lock:
            old_ids = [tid for tid, t in tasks.items()
                       if t['created_at'] < cutoff and t['status'] in ('completed', 'failed')]
            for tid in old_ids:
                del tasks[tid]
        if old_ids:
            print(f"[CLEANUP] Removed {len(old_ids)} old tasks")


def check_dead_workers():
    """Check workers khong gui heartbeat > 60s → mark dead."""
    while True:
        time.sleep(30)
        now = time.time()
        with worker_lock:
            for wid, w in workers.items():
                if w.get('ready') and now - w.get('last_heartbeat', now) > 60:
                    w['ready'] = False
                    w['status'] = 'dead'
                    # Tra lai task neu dang xu ly
                    tid = w.get('current_task_id')
                    if tid:
                        w['current_task_id'] = None
                        w['busy'] = False
                        with queue_lock:
                            task_queue.insert(0, tid)  # Them lai dau queue
                        with task_lock:
                            t = tasks.get(tid)
                            if t:
                                t['status'] = 'queued'
                        print(f"[DEAD] {wid} died, task {tid[:8]}... returned to queue")


# ============================================================
# Main
# ============================================================

if __name__ == '__main__':
    print("=" * 60)
    print("  LOCAL PROXY SERVER v3.0 - Multi-Process Architecture")
    print("=" * 60)
    print()
    print("External API (cho VMs):")
    print("  POST /api/fix/create-image-veo3  - Tao anh (xep hang doi)")
    print("  GET  /api/fix/task-status         - Poll ket qua")
    print("  GET  /api/status                  - Server status")
    print("  GET  /api/workers                 - Chi tiet workers")
    print("  GET  /api/queue                   - Xem hang doi")
    print()
    print("Internal API (cho Chrome workers):")
    print("  GET  /internal/worker-config      - Lay config")
    print("  POST /internal/register           - Dang ky worker")
    print("  GET  /internal/next-task           - Lay task")
    print("  POST /internal/task-done           - Bao hoan thanh")
    print()

    # Start cleanup threads
    threading.Thread(target=cleanup_old_tasks, daemon=True).start()
    threading.Thread(target=check_dead_workers, daemon=True).start()

    # Doc configs tu Sheet (de worker-config endpoint tra ve)
    try:
        from server.chrome_pool import get_server_config
        print("[INIT] Doc cau hinh tu Google Sheet 'SERVER'...")
        server_configs = get_server_config()
        if server_configs:
            print(f"[INIT] Tim thay {len(server_configs)} accounts/IPv6")
        else:
            print("[INIT] Khong tim thay config → workers se dung Chrome da login san")
    except Exception as e:
        print(f"[INIT] Loi doc sheet: {e}")

    print()
    print("Server READY - dang cho workers dang ky...")
    print("Chay 'python server/worker.py --index N' de khoi dong worker")
    print()
    print(f"Server starting on http://0.0.0.0:5000")
    print("=" * 60)
    app.run(host='0.0.0.0', port=5000, debug=False, threaded=True)
