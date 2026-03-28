"""
Local Proxy Server - Queue System cho nhieu VM

Flow:
1. Server khoi dong → mo Chrome → dang nhap Google → vao Flow → tao project → san sang
2. VM gui POST /api/fix/create-image-veo3 voi {body_json, flow_auth_token, flow_url}
3. Server xep vao hang doi (FIFO) → xu ly tung task mot
4. Chrome tao recaptchaToken → Google nhan token khach + captcha hop le → tao anh
5. VM poll GET /api/fix/task-status?taskId=xxx → nhan ket qua + vi tri queue

API Contract:
  POST /api/fix/create-image-veo3
    Body: { body_json: {...}, flow_auth_token: "ya29.xxx", flow_url: "https://..." }
    Response: { success: true, taskId: "uuid", queue_position: 3 }

  GET /api/fix/task-status?taskId=xxx
    Response: { success: true, status: "queued", queue_position: 2 }
    Response: { success: true, status: "processing" }
    Response: { success: true, result: { media: [...] } }

  GET /api/status
    Response: { status: "running", chrome_ready: true, queue_size: 5, ... }

  GET /api/queue
    Response: { queue: [{taskId, vm_id, prompt_preview, status, position}, ...] }
"""
import sys
import os
import uuid
import json
import time
import threading
import traceback
from pathlib import Path
from collections import OrderedDict

sys.stdout.reconfigure(encoding='utf-8', errors='replace')

# Add parent directory to path for imports
TOOL_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(TOOL_DIR))

from flask import Flask, request, jsonify
from server.chrome_session import ChromeSession

app = Flask(__name__)

# ============================================================
# Queue System - Xu ly tuan tu, tra ket qua dung noi
# ============================================================
# Task storage: taskId → task_data
tasks = {}  # OrderedDict-like behavior via insertion order (Python 3.7+)
task_lock = threading.Lock()

# Queue: danh sach task_id theo thu tu FIFO
task_queue = []  # List of task_ids waiting to be processed
queue_lock = threading.Lock()

# Chrome session (singleton)
chrome_session: ChromeSession = None
processing_task_id = None  # Task dang duoc xu ly

# Stats
stats = {
    'total_received': 0,
    'total_completed': 0,
    'total_failed': 0,
    'start_time': time.time(),
}


def get_chrome_session() -> ChromeSession:
    """Lazy init Chrome session."""
    global chrome_session
    if chrome_session is None:
        chrome_session = ChromeSession()
        chrome_session.setup()
    return chrome_session


def _get_queue_position(task_id: str) -> int:
    """Tra ve vi tri trong queue (1-based). 0 = dang processing. -1 = khong trong queue."""
    global processing_task_id
    if task_id == processing_task_id:
        return 0  # Dang xu ly
    with queue_lock:
        try:
            return task_queue.index(task_id) + 1
        except ValueError:
            return -1  # Khong trong queue (da xong hoac loi)


# ============================================================
# Queue Worker - Xu ly task tuan tu (1 thread duy nhat)
# ============================================================
def _queue_worker():
    """Worker thread xu ly queue. Chi 1 thread duy nhat chay ham nay."""
    global processing_task_id

    print("[QUEUE] Worker started - doi task...")

    while True:
        # Lay task tiep theo tu queue
        task_id = None
        with queue_lock:
            if task_queue:
                task_id = task_queue[0]  # Peek, chua remove

        if task_id is None:
            time.sleep(0.5)  # Khong co task, doi
            continue

        # Lay task data
        with task_lock:
            task = tasks.get(task_id)
        if not task:
            # Task bi xoa (cleanup), bo qua
            with queue_lock:
                if task_id in task_queue:
                    task_queue.remove(task_id)
            continue

        # Bat dau xu ly
        processing_task_id = task_id
        with task_lock:
            tasks[task_id]['status'] = 'processing'
            tasks[task_id]['started_at'] = time.time()

        vm_id = task.get('vm_id', '?')
        prompt_preview = task.get('prompt', '')[:50]
        queue_size = len(task_queue)
        print(f"[QUEUE] Processing: {task_id[:8]}... | VM: {vm_id} | Queue: {queue_size} | Prompt: {prompt_preview}...")

        try:
            session = get_chrome_session()
            if not session.ready:
                session.setup()
                if not session.ready:
                    raise RuntimeError("Chrome session not ready")

            # Tao anh
            result = session.generate_image(
                client_bearer_token=task['bearer_token'],
                client_project_id=task['project_id'],
                client_prompt=task['prompt'],
                model_name=task.get('model_name', 'GEM_PIX_2'),
                aspect_ratio=task.get('aspect_ratio', 'IMAGE_ASPECT_RATIO_LANDSCAPE'),
                seed=task.get('seed'),
            )

            with task_lock:
                if result and 'media' in result:
                    tasks[task_id]['status'] = 'completed'
                    tasks[task_id]['result'] = result
                    tasks[task_id]['completed_at'] = time.time()
                    stats['total_completed'] += 1
                    duration = time.time() - tasks[task_id].get('started_at', time.time())
                    print(f"[QUEUE] [OK] {task_id[:8]}... | VM: {vm_id} | {duration:.1f}s")
                elif result and 'error' in result:
                    tasks[task_id]['status'] = 'failed'
                    tasks[task_id]['error'] = result['error']
                    stats['total_failed'] += 1
                    print(f"[QUEUE] [FAIL] {task_id[:8]}... | VM: {vm_id} | {result['error'][:80]}")
                else:
                    tasks[task_id]['status'] = 'failed'
                    tasks[task_id]['error'] = 'No media in response'
                    stats['total_failed'] += 1
                    print(f"[QUEUE] [FAIL] {task_id[:8]}... | VM: {vm_id} | No media")

        except Exception as e:
            traceback.print_exc()
            with task_lock:
                tasks[task_id]['status'] = 'failed'
                tasks[task_id]['error'] = str(e)
                stats['total_failed'] += 1
            print(f"[QUEUE] [ERROR] {task_id[:8]}... | VM: {vm_id} | {str(e)[:80]}")

        finally:
            # Xoa khoi queue
            processing_task_id = None
            with queue_lock:
                if task_id in task_queue:
                    task_queue.remove(task_id)


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
            }
            stats['total_received'] += 1

        with queue_lock:
            task_queue.append(task_id)
            queue_position = len(task_queue)

        print(f"[QUEUE] +Task {task_id[:8]}... | VM: {vm_id} | Pos: {queue_position} | Prompt: {prompt[:50]}...")

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

    Response khi dang doi:
    { "success": true, "status": "queued", "queue_position": 3 }

    Response khi dang xu ly:
    { "success": true, "status": "processing" }

    Response khi xong:
    { "success": true, "result": { "media": [...] } }

    Response khi loi:
    { "success": false, "error": "..." }
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
        return jsonify(response)


@app.route('/api/status', methods=['GET'])
def server_status():
    """Server health check + queue info."""
    global chrome_session
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

    return jsonify({
        "status": "running",
        "chrome_ready": chrome_session is not None and chrome_session.ready,
        "queue_size": queue_size,
        "processing": processing_task_id[:8] + "..." if processing_task_id else None,
        "vm_active": vm_tasks,
        "stats": {
            "total_received": stats['total_received'],
            "total_completed": stats['total_completed'],
            "total_failed": stats['total_failed'],
            "uptime_hours": round(uptime / 3600, 1),
        },
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

    return jsonify({
        "queue_size": len(queue_items),
        "processing": processing_task_id[:8] + "..." if processing_task_id else None,
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
    print("LOCAL PROXY SERVER - Queue System")
    print("=" * 60)
    print()
    print("Endpoints:")
    print("  POST /api/fix/create-image-veo3  - Tao anh (xep hang doi)")
    print("  GET  /api/fix/task-status         - Poll ket qua + vi tri queue")
    print("  GET  /api/status                  - Server status + queue info")
    print("  GET  /api/queue                   - Xem chi tiet hang doi")
    print()

    # Start cleanup thread
    cleanup_thread = threading.Thread(target=cleanup_old_tasks, daemon=True)
    cleanup_thread.start()

    # Start queue worker (1 thread xu ly tuan tu)
    worker_thread = threading.Thread(target=_queue_worker, daemon=True)
    worker_thread.start()

    # Pre-init Chrome session
    print("[INIT] Khoi tao Chrome session...")
    try:
        chrome_session = ChromeSession()
        chrome_session.setup()
        print(f"[INIT] Chrome ready: {chrome_session.ready}")
    except Exception as e:
        print(f"[INIT] Chrome setup failed: {e}")
        print("[INIT] Server van chay - Chrome se duoc init khi co request dau tien")

    print()
    print("Server starting on http://0.0.0.0:5000")
    print("=" * 60)
    app.run(host='0.0.0.0', port=5000, debug=False, threaded=True)
