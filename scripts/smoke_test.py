import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request

API_PORT = int(os.environ.get('ERMES_API_PORT', '8502'))
HEALTH_URL = f'http://127.0.0.1:{API_PORT}/health'
QUERY_URL = f'http://127.0.0.1:{API_PORT}/query'


def http_get(url, timeout=5):
    req = urllib.request.Request(url)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read().decode('utf-8'), resp.getcode()
    except Exception as e:
        return None, e


def http_post_json(url, payload, headers=None, timeout=15):
    data = json.dumps(payload).encode('utf-8')
    hdrs = { 'Content-Type': 'application/json' }
    if headers:
        hdrs.update(headers)
    req = urllib.request.Request(url, data=data, headers=hdrs, method='POST')
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read().decode('utf-8'), resp.getcode()
    except Exception as e:
        return None, e


def wait_for_health(url, wait_seconds=30):
    print(f"Checking health at {url} (waiting up to {wait_seconds}s)...")
    start = time.time()
    while time.time() - start < wait_seconds:
        body, status = http_get(url, timeout=5)
        if body and isinstance(body, str):
            print("Health response:")
            try:
                parsed = json.loads(body)
                print(json.dumps(parsed, indent=2, ensure_ascii=False))
            except Exception:
                print(body)
            return True
        else:
            time.sleep(1)
    print("Health check failed: no response")
    return False


def run_pytest(test_path):
    print(f"Running pytest: {test_path}")
    try:
        rc = subprocess.call([sys.executable, '-m', 'pytest', test_path, '-q'])
        print(f"pytest exit code: {rc}")
        return rc == 0
    except Exception as e:
        print(f"Error running pytest: {e}")
        return False


def run_query_sample(query_text, module_name):
    api_key = os.environ.get('ERMES_API_KEY')
    if not api_key:
        print("ERMES_API_KEY not set in environment — skipping API query. To test API set ERMES_API_KEY in environment.")
        return False
    payload = { 'query': query_text, 'module': module_name }
    print(f"Sending sample query to {QUERY_URL} with module={module_name}")
    body, status = http_post_json(QUERY_URL, payload, headers={'Authorization': f'Bearer {api_key}'})
    if body and isinstance(body, str):
        print("Query response:")
        try:
            print(json.dumps(json.loads(body), indent=2, ensure_ascii=False))
        except Exception:
            print(body)
        return True
    else:
        print("Query failed:", status)
        return False


if __name__ == '__main__':
    ok = wait_for_health(HEALTH_URL, wait_seconds=30)
    if not ok:
        print("Health endpoint unavailable — aborting smoke test.")
        sys.exit(2)

    # Run WinSarp unit tests
    run_pytest('tests/test_winsarp.py')

    # Try a sample query if API key is configured
    sample_query = 'Qual è la formula per azzerare le causali automatiche?'
    run_query_sample(sample_query, 'WinSarp')

    print('\nSmoke test completed.')
