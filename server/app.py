"""
Local Proxy Server - Multi-Chrome Queue System cho nhieu VM

v2.0: Multi-Chrome - Chay N Chrome song song (thay vi 1)
- Moi Chrome: 1 account rieng + 1 IPv6 rieng + 1 queue worker thread rieng
- 5 Chrome Portable: GoogleChromePortable, - Copy, - Copy (2), - Copy (3), - Copy (4)
- Account + IPv6 doc tu Google Sheet "SERVER" (col B = account, col C = IPv6)
- Shared queue: task vao queue chung, worker nao ranh se lay

Flow:
1. Server khoi dong → doc accounts tu Sheet SERVER → mo N Chrome → dang nhap → san sang
2. VM gui POST /api/fix/create-image-veo3 voi {body_json, flow_auth_token, flow_url}
3. Server xep vao hang doi FIFO → worker ranh lay task tu queue
4. Chrome tao recaptchaToken → Google nhan token khach + captcha hop le → tao anh
5. VM poll GET /api/fix/task-status?taskId=xxx → nhan ket qua

API Contract:
  POST /api/fix/create-image-veo3
    Body: { body_json: {...}, flow_auth_token: "ya29.xxx", flow_url: "https://..." }
    Response: { success: true, taskId: "uuid", queue_position: 3 }

  GET /api/fix/task-status?taskId=xxx
    Response: { success: true, status: "queued", queue_position: 2 }
    Response: { success: true, status: "processing" }
    Response: { success: true, result: { media: [...] } }

  GET /api/status
    Response: { status: "running", chrome_count: 5, chrome_ready: 3, queue_size: 10, ... }

  GET /api/queue
    Response: { queue: [{taskId, vm_id, prompt_preview, status, position}, ...] }

  GET /api/workers
    Response: { workers: [{index, ready, busy, account, completed, failed}, ...] }
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
# Task storage: taskId -> task_data
tasks = {}
task_lock = threading.Lock()

# Queue: list of task_ids (FIFO)
task_queue = []
queue_lock = threading.Lock()

# Chrome Pool (initialized in main)
chrome_pool = None

# Stats
stats = {
    'total_received': 0,
    'total_completed': 0,
    'total_failed': 0,
    'start_time': time.time(),
}


def _get_queue_position(task_id: str) -> int:
    """Tra ve vi tri trong queue (1-based). 0 = dang processing. -1 = khong trong queue."""
    # Check if any worker is processing this task
    if chrome_pool:
        for w in chrome_pool.workers:
            if w.current_task_id == task_id:
                return 0  # Dang xu ly

    with queue_lock:
        try:
            return task_queue.index(task_id) + 1
        except ValueError:
            return -1  # Khong trong queue (da xong hoac loi)


# ============================================================
# API Endpoints
# ============================================================

@app.route('/api/fix/create-image-veo3', methods=['POST'])
def create_image():
    """
    Tao task sinh anh - xep vao hang doi.

    Body JSON:
    {
        "body_json": {
            "clientContext": { "projectId": "uuid", ... },
            "requests": [{ "prompt": "...", "imageModelName": "GEM_PIX_2", ... }]
        },
        "flow_auth_token": "ya29.xxx",
        "flow_url": "https://aisandbox-pa.googleapis.com/v1/projects/{id}/flowMedia:batchGenerateImages",
        "vm_id": "TA6-T1"  // Optional: de biet task tu VM nao
    }
    """
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

        # Extract prompt tu body_json
        prompt = ""
        if 'requests' in body_json and body_json['requests']:
            prompt = body_json['requests'][0].get('prompt', '')

        if not prompt:
            return jsonify({"success": False, "error": "No prompt in body_json.requests[0].prompt"}), 400

        # Extract project ID tu body_json hoac flow_url
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

        # Tao task va xep vao queue
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
                'worker': None,  # Worker index se xu ly task nay
            }
            stats['total_received'] += 1

        with queue_lock:
            task_queue.append(task_id)
            queue_position = len(task_queue)

        # Log
        ready = chrome_pool.total_ready() if chrome_pool else 0
        avail = chrome_pool.available_count() if chrome_pool else 0
        print(f"[QUEUE] +Task {task_id[:8]}... | VM: {vm_id} | Pos: {queue_position} | Workers: {avail}/{ready} free | Prompt: {prompt[:50]}...")

        return jsonify({
            "success": True,
            "taskId": task_id,
            "queue_position": queue_position,
        })

    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route('/api/fix/task-status', methods=['GET'])
def task_status():
    """
    Poll task status + vi tri trong queue.

    GET /api/fix/task-status?taskId=xxx
    """
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
        # queued hoac processing
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

    # Danh sach VM dang co task
    vm_tasks = {}
    with task_lock:
        for tid, t in tasks.items():
            vm = t.get('vm_id', '?')
            if t['status'] in ('queued', 'processing'):
                vm_tasks[vm] = vm_tasks.get(vm, 0) + 1

    # Worker stats
    total_workers = len(chrome_pool.workers) if chrome_pool else 0
    ready_workers = chrome_pool.total_ready() if chrome_pool else 0
    available_workers = chrome_pool.available_count() if chrome_pool else 0

    # Processing tasks
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
            "uptime_hours": round(uptime / 3600, 1),
        },
    })


@app.route('/api/workers', methods=['GET'])
def workers_info():
    """Chi tiet tung Chrome worker."""
    if not chrome_pool:
        return jsonify({"workers": [], "error": "ChromePool not initialized"})

    return jsonify({
        "total": len(chrome_pool.workers),
        "ready": chrome_pool.total_ready(),
        "available": chrome_pool.available_count(),
        "workers": chrome_pool.get_stats(),
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

    # Processing tasks
    processing = []
    if chrome_pool:
        for w in chrome_pool.workers:
            if w.busy and w.current_task_id:
                with task_lock:
                    t = tasks.get(w.current_task_id, {})
                processing.append({
                    "worker": w.index,
                    "taskId": w.current_task_id[:8] + "...",
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
        time.sleep(300)  # Check moi 5 phut
        cutoff = time.time() - 3600
        with task_lock:
            old_ids = [tid for tid, t in tasks.items()
                       if t['created_at'] < cutoff and t['status'] in ('completed', 'failed')]
            for tid in old_ids:
                del tasks[tid]
        if old_ids:
            print(f"[CLEANUP] Removed {len(old_ids)} old tasks")


# ============================================================
# Main
# ============================================================

if __name__ == '__main__':
    print("=" * 60)
    print("  LOCAL PROXY SERVER - Multi-Chrome Queue System")
    print("=" * 60)
    print()
    print("Endpoints:")
    print("  POST /api/fix/create-image-veo3  - Tao anh (xep hang doi)")
    print("  GET  /api/fix/task-status         - Poll ket qua + vi tri queue")
    print("  GET  /api/status                  - Server status + queue info")
    print("  GET  /api/workers                 - Chi tiet tung Chrome worker")
    print("  GET  /api/queue                   - Xem chi tiet hang doi")
    print()

    # Start cleanup thread
    cleanup_thread = threading.Thread(target=cleanup_old_tasks, daemon=True)
    cleanup_thread.start()

    # ============================================================
    # Init Chrome Pool
    # ============================================================
    from server.chrome_pool import ChromePool, get_server_config

    print("[INIT] Doc cau hinh tu Google Sheet 'SERVER'...")
    server_configs = []
    try:
        server_configs = get_server_config()
        if server_configs:
            print(f"[INIT] Tim thay {len(server_configs)} accounts/IPv6")
        else:
            print("[INIT] Khong tim thay config trong sheet 'SERVER'")
            print("[INIT] Server se chay voi Chrome da dang nhap san")
    except Exception as e:
        print(f"[INIT] Loi doc sheet: {e}")
        print("[INIT] Server se chay voi Chrome da dang nhap san")

    print()
    print("[INIT] Khoi tao Chrome Pool...")
    chrome_pool = ChromePool()
    chrome_pool.init_workers(server_configs)

    if not chrome_pool.workers:
        print("[INIT] KHONG TIM THAY Chrome Portable nao!")
        print("[INIT] Can it nhat 1 folder: GoogleChromePortable/GoogleChromePortable.exe")
        print("[INIT] Server se chay nhung KHONG THE tao anh!")
    else:
        print()
        print(f"[INIT] Setup {len(chrome_pool.workers)} Chrome workers...")
        ready_count = chrome_pool.setup_all()

        if ready_count > 0:
            print()
            print(f"[INIT] {ready_count} Chrome workers READY!")
            # Start worker threads
            chrome_pool.start_workers(task_queue, queue_lock, tasks, task_lock, stats)
            print(f"[INIT] {ready_count} worker threads started!")
        else:
            print("[INIT] KHONG CO Chrome worker nao san sang!", )
            print("[INIT] Server se chay nhung KHONG THE tao anh!")

    print()
    print(f"Server starting on http://0.0.0.0:5000")
    print(f"Chrome workers: {chrome_pool.total_ready() if chrome_pool else 0}")
    print("=" * 60)
    app.run(host='0.0.0.0', port=5000, debug=False, threaded=True)
