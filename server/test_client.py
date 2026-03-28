"""
Test Client - Gọi Local Proxy Server giống cách gọi nanoai.pics.

Usage:
    python server/test_client.py <bearer_token> <project_id> [prompt]

Ví dụ:
    python server/test_client.py ya29.xxx 03328467-9a64-436e-bed5-36847908d49a "A cute dog"

Flow:
1. POST /api/fix/create-image-veo3 → lấy taskId
2. GET /api/fix/task-status?taskId=xxx → poll cho đến khi xong
3. Lưu ảnh ra file
"""
import sys
import json
import time
import uuid
import base64
import requests
from pathlib import Path

sys.stdout.reconfigure(encoding='utf-8', errors='replace')

SERVER_URL = "http://127.0.0.1:5000"
OUTPUT_DIR = Path(__file__).parent / "test_output"
OUTPUT_DIR.mkdir(exist_ok=True)


def create_image_task(bearer_token: str, project_id: str, prompt: str,
                      model: str = "GEM_PIX_2") -> str:
    """
    Gửi request tạo ảnh - giống cách gọi nanoai.pics.

    Returns: taskId
    """
    url = f"{SERVER_URL}/api/fix/create-image-veo3"

    # Build body_json giống Google Flow API format
    flow_url = f"https://aisandbox-pa.googleapis.com/v1/projects/{project_id}/flowMedia:batchGenerateImages"

    body = {
        "body_json": {
            "clientContext": {
                "sessionId": f";{int(time.time() * 1000)}",
                "projectId": project_id,
                "tool": "PINHOLE"
            },
            "requests": [{
                "clientContext": {
                    "sessionId": f";{int(time.time() * 1000)}",
                    "projectId": project_id,
                    "tool": "PINHOLE"
                },
                "seed": __import__('random').randint(1, 999999),
                "imageModelName": model,
                "imageAspectRatio": "IMAGE_ASPECT_RATIO_LANDSCAPE",
                "prompt": prompt,
                "imageInputs": []
            }]
        },
        "flow_auth_token": bearer_token,
        "flow_url": flow_url
    }

    print(f"POST {url}")
    print(f"  Token: {bearer_token[:20]}...{bearer_token[-10:]}")
    print(f"  ProjectId: {project_id}")
    print(f"  Prompt: {prompt[:60]}...")
    print(f"  Model: {model}")
    print()

    resp = requests.post(url, json=body, timeout=30)
    data = resp.json()
    print(f"Response: {json.dumps(data, indent=2)}")

    if data.get('success'):
        return data['taskId']
    else:
        print(f"[ERROR] {data.get('error', 'Unknown error')}")
        return None


def poll_task(task_id: str, max_wait: int = 180) -> dict:
    """
    Poll task status - giống cách poll nanoai.pics.

    Returns: result dict khi xong, None khi timeout/error
    """
    url = f"{SERVER_URL}/api/fix/task-status?taskId={task_id}"
    print(f"\nPolling task: {task_id}")

    start = time.time()
    while time.time() - start < max_wait:
        elapsed = time.time() - start

        try:
            resp = requests.get(url, timeout=10)
            data = resp.json()

            if data.get('result'):
                print(f"\n[OK] Completed sau {elapsed:.1f}s!")
                return data['result']

            if data.get('error'):
                print(f"\n[ERROR] {data['error']}")
                return None

            status = data.get('status', 'unknown')
            if int(elapsed) % 5 == 0:
                print(f"  ... {status} ({elapsed:.0f}s)")

        except Exception as e:
            print(f"  Poll error: {e}")

        time.sleep(2)

    print(f"\n[TIMEOUT] {max_wait}s")
    return None


def save_images(result: dict):
    """Lưu ảnh từ kết quả."""
    if not result or 'media' not in result:
        print("[WARN] No media in result")
        return

    for i, item in enumerate(result['media']):
        gen_img = item.get('image', {}).get('generatedImage', {})
        encoded = gen_img.get('encodedImage', '')
        fife_url = gen_img.get('fifeUrl', '')
        seed = gen_img.get('seed', '')
        prompt = gen_img.get('prompt', '')

        if encoded:
            img_bytes = base64.b64decode(encoded)
            out_path = OUTPUT_DIR / f"client_result_{i+1}.png"
            with open(out_path, 'wb') as f:
                f.write(img_bytes)
            print(f"[IMG {i+1}] Saved: {out_path}")
            print(f"  Size: {len(img_bytes):,} bytes")
            print(f"  Seed: {seed}")
            print(f"  Prompt: {prompt[:60]}")
        elif fife_url:
            print(f"[IMG {i+1}] URL available: {fife_url[:80]}...")
            try:
                r = requests.get(fife_url, timeout=30)
                if r.status_code == 200:
                    out_path = OUTPUT_DIR / f"client_result_{i+1}.png"
                    with open(out_path, 'wb') as f:
                        f.write(r.content)
                    print(f"  Downloaded: {out_path} ({len(r.content):,} bytes)")
            except Exception as e:
                print(f"  Download error: {e}")
        else:
            print(f"[IMG {i+1}] No image data")


def main():
    # Parse args
    if len(sys.argv) < 3:
        print("Usage: python server/test_client.py <bearer_token> <project_id> [prompt]")
        print()
        print("Ví dụ:")
        print('  python server/test_client.py ya29.xxx 03328467-xxxx "A cute dog"')
        print()
        print("Trước tiên phải start server:")
        print("  python -m server.app")
        return

    bearer_token = sys.argv[1].strip()
    if bearer_token.startswith("Bearer "):
        bearer_token = bearer_token[7:]

    project_id = sys.argv[2].strip()
    prompt = sys.argv[3].strip() if len(sys.argv) > 3 else "A cute cartoon dog playing with a red ball in a green park"

    print("=" * 60)
    print("TEST CLIENT - Gọi Local Proxy Server")
    print("=" * 60)
    print()

    # 1. Check server
    try:
        status = requests.get(f"{SERVER_URL}/api/status", timeout=5).json()
        print(f"Server status: {json.dumps(status, indent=2)}")
        print()
    except Exception as e:
        print(f"[ERROR] Server không chạy! Start server trước:")
        print(f"  python -m server.app")
        print(f"  Error: {e}")
        return

    # 2. Create task
    task_id = create_image_task(bearer_token, project_id, prompt)
    if not task_id:
        return

    # 3. Poll
    result = poll_task(task_id)

    # 4. Save
    if result:
        print()
        save_images(result)
        print()
        print("=" * 60)
        print("THÀNH CÔNG!")
        print("=" * 60)


if __name__ == "__main__":
    main()
