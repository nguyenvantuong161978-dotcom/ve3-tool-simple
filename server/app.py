"""
Local Proxy Server - Giống nanoai.pics

Flow:
1. Server khởi động → mở Chrome → đăng nhập Google → vào Flow → tạo project → sẵn sàng
2. Client gửi POST /api/fix/create-image-veo3 với {body_json, flow_auth_token, flow_url}
3. Server inject interceptor (thay bearer token + projectId) → paste prompt → Enter
4. Chrome tạo recaptchaToken → Google nhận token khách + captcha hợp lệ → tạo ảnh
5. Client poll GET /api/fix/task-status?taskId=xxx → nhận kết quả

API Contract (giống nanoai.pics):
  POST /api/fix/create-image-veo3
    Body: { body_json: {...}, flow_auth_token: "ya29.xxx", flow_url: "https://..." }
    Response: { success: true, taskId: "uuid" }

  GET /api/fix/task-status?taskId=xxx
    Response: { success: true, result: { media: [...] } }
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
from server.chrome_session import ChromeSession

app = Flask(__name__)

# ============================================================
# Task Manager - Quản lý tasks async
# ============================================================
tasks = {}  # taskId → { status, result, error, created_at }
task_lock = threading.Lock()

# Chrome session (singleton)
chrome_session: ChromeSession = None
chrome_lock = threading.Lock()  # Serialize image generation (1 Chrome = 1 task tại 1 thời điểm)


def get_chrome_session() -> ChromeSession:
    """Lazy init Chrome session."""
    global chrome_session
    if chrome_session is None:
        chrome_session = ChromeSession()
        chrome_session.setup()
    return chrome_session


# ============================================================
# API Endpoints
# ============================================================

@app.route('/api/fix/create-image-veo3', methods=['POST'])
def create_image():
    """
    Tạo task sinh ảnh - giống nanoai.pics.

    Body JSON:
    {
        "body_json": {
            "clientContext": { "projectId": "uuid", ... },
            "requests": [{ "prompt": "...", "imageModelName": "GEM_PIX_2", ... }]
        },
        "flow_auth_token": "ya29.xxx",
        "flow_url": "https://aisandbox-pa.googleapis.com/v1/projects/{id}/flowMedia:batchGenerateImages"
    }
    """
    try:
        data = request.get_json()
        if not data:
            return jsonify({"success": False, "error": "No JSON body"}), 400

        body_json = data.get('body_json')
        flow_auth_token = data.get('flow_auth_token', '')
        flow_url = data.get('flow_url', '')

        if not body_json:
            return jsonify({"success": False, "error": "Missing body_json"}), 400
        if not flow_auth_token:
            return jsonify({"success": False, "error": "Missing flow_auth_token"}), 400

        # Extract prompt từ body_json
        prompt = ""
        if 'requests' in body_json and body_json['requests']:
            prompt = body_json['requests'][0].get('prompt', '')

        if not prompt:
            return jsonify({"success": False, "error": "No prompt in body_json.requests[0].prompt"}), 400

        # Extract project ID từ body_json hoặc flow_url
        project_id = ""
        if body_json.get('clientContext', {}).get('projectId'):
            project_id = body_json['clientContext']['projectId']
        elif flow_url:
            # Parse từ URL: .../projects/{project_id}/flowMedia:...
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

        # Tạo task
        task_id = str(uuid.uuid4())
        with task_lock:
            tasks[task_id] = {
                'status': 'pending',
                'result': None,
                'error': None,
                'created_at': time.time(),
                'prompt': prompt,
                'project_id': project_id,
            }

        # Chạy task trong background thread
        thread = threading.Thread(
            target=_process_image_task,
            args=(task_id, flow_auth_token, project_id, prompt, model_name, aspect_ratio, seed),
            daemon=True
        )
        thread.start()

        return jsonify({"success": True, "taskId": task_id})

    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route('/api/fix/task-status', methods=['GET'])
def task_status():
    """
    Poll task status - giống nanoai.pics.

    GET /api/fix/task-status?taskId=xxx

    Response khi đang xử lý:
    { "success": true, "status": "processing" }

    Response khi xong:
    { "success": true, "result": { "media": [...] } }

    Response khi lỗi:
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
        return jsonify({"success": True, "status": task['status']})


@app.route('/api/status', methods=['GET'])
def server_status():
    """Server health check."""
    global chrome_session
    return jsonify({
        "status": "running",
        "chrome_ready": chrome_session is not None and chrome_session.ready,
        "pending_tasks": sum(1 for t in tasks.values() if t['status'] in ('pending', 'processing')),
        "completed_tasks": sum(1 for t in tasks.values() if t['status'] == 'completed'),
        "failed_tasks": sum(1 for t in tasks.values() if t['status'] == 'failed'),
    })


# ============================================================
# Task Processing
# ============================================================

def _process_image_task(task_id: str, bearer_token: str, project_id: str,
                        prompt: str, model_name: str, aspect_ratio: str, seed: int):
    """Xử lý task sinh ảnh trong background thread."""
    try:
        with task_lock:
            tasks[task_id]['status'] = 'processing'

        # Serialize Chrome access (chỉ 1 task tại 1 thời điểm)
        with chrome_lock:
            session = get_chrome_session()

            if not session.ready:
                # Thử setup lại
                session.setup()
                if not session.ready:
                    raise RuntimeError("Chrome session not ready")

            # Tạo ảnh
            result = session.generate_image(
                client_bearer_token=bearer_token,
                client_project_id=project_id,
                client_prompt=prompt,
                model_name=model_name,
                aspect_ratio=aspect_ratio,
                seed=seed,
            )

        with task_lock:
            if result and 'media' in result:
                tasks[task_id]['status'] = 'completed'
                tasks[task_id]['result'] = result
            elif result and 'error' in result:
                tasks[task_id]['status'] = 'failed'
                tasks[task_id]['error'] = result['error']
            else:
                tasks[task_id]['status'] = 'failed'
                tasks[task_id]['error'] = 'No media in response'

    except Exception as e:
        traceback.print_exc()
        with task_lock:
            tasks[task_id]['status'] = 'failed'
            tasks[task_id]['error'] = str(e)


# ============================================================
# Cleanup old tasks (giữ tối đa 1 giờ)
# ============================================================

def cleanup_old_tasks():
    """Xóa tasks cũ hơn 1 giờ."""
    while True:
        time.sleep(300)  # Check mỗi 5 phút
        cutoff = time.time() - 3600
        with task_lock:
            old_ids = [tid for tid, t in tasks.items() if t['created_at'] < cutoff]
            for tid in old_ids:
                del tasks[tid]
        if old_ids:
            print(f"[CLEANUP] Removed {len(old_ids)} old tasks")


# ============================================================
# Main
# ============================================================

if __name__ == '__main__':
    print("=" * 60)
    print("LOCAL PROXY SERVER - Giống nanoai.pics")
    print("=" * 60)
    print()
    print("Endpoints:")
    print("  POST /api/fix/create-image-veo3  - Tạo ảnh")
    print("  GET  /api/fix/task-status         - Poll kết quả")
    print("  GET  /api/status                  - Server status")
    print()

    # Start cleanup thread
    cleanup_thread = threading.Thread(target=cleanup_old_tasks, daemon=True)
    cleanup_thread.start()

    # Pre-init Chrome session
    print("[INIT] Khởi tạo Chrome session...")
    try:
        chrome_session = ChromeSession()
        chrome_session.setup()
        print(f"[INIT] Chrome ready: {chrome_session.ready}")
    except Exception as e:
        print(f"[INIT] Chrome setup failed: {e}")
        print("[INIT] Server vẫn chạy - Chrome sẽ được init khi có request đầu tiên")

    print()
    print("Server starting on http://0.0.0.0:5000")
    print("=" * 60)
    app.run(host='0.0.0.0', port=5000, debug=False, threaded=True)
