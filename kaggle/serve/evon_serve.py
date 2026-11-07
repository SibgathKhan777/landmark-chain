# Serve Evon v3.3 (community 4/5-bit GGUF) from a Kaggle notebook as an API with a key, through a temporary public tunnel.
# Based on the test run in ../kernel/evon_llamacpp.py, which worked (about 0.6 s per translation on two T4s, 5 minutes to load).
#
# It prints, in the Kaggle log, two lines to paste into landmark/.env:
#     LLM_BASE_URL=https://....trycloudflare.com
#     LLM_API_KEY=...
# The address changes every run. The log is private to your Kaggle account: do not share it, it contains the key.
# It stops by itself after MAX_HOURS to protect your weekly GPU quota. Check Kaggle's terms before using a tunnel from a notebook.
import json
import os
import re
import secrets
import subprocess
import sys
import threading
import time
import urllib.request

MAX_HOURS = 3
REPO, FILES = "luminenio/gnani-evon-v3.3-30B-A3B-GGUF", ("gnani-evon-v3.3-30B-A3B-Q5_K_M.gguf", "gnani-evon-v3.3-30B-A3B-Q4_K_M.gguf")
TAG = "b11934"                                                    # llama.cpp release with the Ubuntu CUDA 12.8 build (checked 2026-10-27)
WORK, KEY = "/tmp/work", secrets.token_urlsafe(24)
os.makedirs(WORK, exist_ok=True)
started = time.time()


def say(*a):
    print(*a, flush=True)


def sh(cmd, check=True, tail=15):
    say(f"$ {cmd}")
    r = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    out = (r.stdout + r.stderr).strip().splitlines()
    say("\n".join(out[-(100 if check and r.returncode else tail):]))
    if check and r.returncode:
        sys.exit(f"command failed ({r.returncode}): {cmd}")
    return r


# ---------------------------------------------------------------- llama-server (ready-made CUDA build) and the model
sh("nvidia-smi --query-gpu=name,memory.total --format=csv", check=False)
BIN = f"{WORK}/llama"
if not os.path.exists(BIN):
    os.makedirs(BIN)
    for name in (f"llama-{TAG}-bin-ubuntu-cuda-12.8-x64.tar.gz", f"cudart-llama-{TAG}-bin-ubuntu-cuda-12.8-x64.tar.gz"):
        sh(f"curl -sSL -o {WORK}/{name} https://github.com/ggml-org/llama.cpp/releases/download/{TAG}/{name} && tar -xzf {WORK}/{name} -C {BIN}", tail=3)
SERVER = subprocess.run(f"find {BIN} -name llama-server -type f", shell=True, capture_output=True, text=True).stdout.split()[0]
os.chmod(SERVER, 0o755)
os.environ["LD_LIBRARY_PATH"] = os.path.dirname(SERVER) + ":" + os.environ.get("LD_LIBRARY_PATH", "")
sh("pip install -q -U huggingface_hub", check=False, tail=2)
os.environ["HF_HOME"] = "/tmp/hf"
from huggingface_hub import hf_hub_download  # noqa: E402


def start_server(file):
    path = hf_hub_download(REPO, file)
    say(f"model file: {file} ({os.path.getsize(path) / 1e9:.1f} GB)")
    log = open("/kaggle/working/llama-server.log", "w")
    proc = subprocess.Popen([SERVER, "-m", path, "-ngl", "99", "-c", "2048", "-sm", "layer", "-ts", "1,1", "--host", "127.0.0.1", "--port", "8080",
                             "--jinja", "--chat-template-kwargs", '{"enable_thinking": false}', "--no-webui", "--api-key", KEY], stdout=log, stderr=subprocess.STDOUT)
    for _ in range(240):
        time.sleep(5)
        if proc.poll() is not None:
            return None
        try:
            if urllib.request.urlopen("http://127.0.0.1:8080/health", timeout=3).status == 200:
                return proc
        except Exception:
            pass
    proc.kill()
    return None


server = None
for f in FILES:
    server = start_server(f)
    if server:
        break
    say("did not start; log tail:\n" + open("/kaggle/working/llama-server.log").read()[-1500:])
if not server:
    sys.exit("llama-server did not start (see above).")
say(f"model loaded after {time.time() - started:.0f} s")

# ---------------------------------------------------------------- the temporary public address (cloudflared "quick tunnel": no account)
CF = f"{WORK}/cloudflared"
sh(f"curl -sSL -o {CF} https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64 && chmod +x {CF}", tail=3)
tunnel = subprocess.Popen([CF, "tunnel", "--url", "http://127.0.0.1:8080", "--no-autoupdate"], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
found = {}


def read_tunnel():
    for line in tunnel.stdout:
        m = re.search(r"https://[a-z0-9-]+\.trycloudflare\.com", line)
        if m and "url" not in found:
            found["url"] = m.group(0)


threading.Thread(target=read_tunnel, daemon=True).start()
for _ in range(60):
    if "url" in found:
        break
    time.sleep(1)
if "url" not in found:
    server.terminate()
    sys.exit("the tunnel did not give an address within 60 s.")
URL = found["url"]


def ask(text, tries=12):
    body = json.dumps({"messages": [{"role": "system", "content": "Translate the Hinglish message into English. Output only the translation."},
                                    {"role": "user", "content": text}], "temperature": 0, "max_tokens": 60}).encode()
    for i in range(tries):                                         # a new tunnel can take a few seconds to resolve
        try:
            req = urllib.request.Request(URL + "/v1/chat/completions", body, {"Content-Type": "application/json", "Authorization": f"Bearer {KEY}",
                                                                              "User-Agent": "landmark-chain/1.0"})
            t = time.time()
            r = json.load(urllib.request.urlopen(req, timeout=60))
            return r["choices"][0]["message"]["content"].strip(), round(time.time() - t, 2)
        except Exception as e:
            err = f"{type(e).__name__}: {e}"
            time.sleep(5)
    return None, err


answer, took = ask("seedha aao phir right le lo")
say("\nself-test through the public address:", answer, f"({took} s)" if answer else "")
if not answer:
    say("The model is running but the public address did not answer. Check Kaggle's rules on tunnels, or use a rented GPU instead.")
    server.terminate(); tunnel.terminate()
    sys.exit(1)
wrong_key = urllib.request.Request(URL + "/v1/chat/completions", b"{}", {"Content-Type": "application/json", "Authorization": "Bearer wrong", "User-Agent": "landmark-chain/1.0"})
try:
    urllib.request.urlopen(wrong_key, timeout=30)
    say("WARNING: the server answered with a wrong key. Do not use this address.")
except urllib.error.HTTPError as e:
    say(f"a wrong key is refused (HTTP {e.code}): good")

say("\n" + "=" * 70)
say("COPY THESE TWO LINES INTO landmark/.env, then restart  python live_call.py")
say(f"LLM_BASE_URL={URL}")
say(f"LLM_API_KEY={KEY}")
say("=" * 70)
say(f"Serving for up to {MAX_HOURS} hours. Stop it earlier from the Kaggle page (the session's Stop button).\n")

deadline = started + MAX_HOURS * 3600
while time.time() < deadline:
    time.sleep(300)
    if server.poll() is not None or tunnel.poll() is not None:
        say("the server or the tunnel stopped; ending.")
        break
    say(f"still serving, {round((deadline - time.time()) / 60)} minutes left")
server.terminate()
tunnel.terminate()
say("stopped.")
