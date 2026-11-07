# Evon v3.3 translation test on Kaggle (2x Tesla T4), through llama.cpp and a community 4-bit GGUF.
# The first try (transformers + bitsandbytes) failed: the 4-bit model did not fit in the two GPUs' 28 GB and the library refuses CPU offload.
# The second try failed at "cmake configure" when building llama.cpp from source on Kaggle. llama.cpp publishes ready-built Ubuntu CUDA 12.8
# binaries and Kaggle has CUDA 12.8, so this version downloads those instead (no compiling).
# Third try (this file now): the second run worked (about 0.5 s per translation) but Kannada was poor: 8 of 12 came back unchanged.
# This version adds examples to the prompt, a second route via English, a bigger 5-bit file, a warm-up call, automatic checks and 6 extra sentences.
# This script: download llama.cpp, download a 24.7 GB GGUF, start llama-server on the two T4s, run 12 sentences.
import json
import os
import subprocess
import sys
import time
import urllib.request

REPO, FILE = "luminenio/gnani-evon-v3.3-30B-A3B-GGUF", "gnani-evon-v3.3-30B-A3B-Q5_K_M.gguf"      # community conversion, not an official Gnani file
FALLBACK_FILE = "gnani-evon-v3.3-30B-A3B-Q4_K_M.gguf"                                                  # 24.7 GB: this one loaded and ran in the second try
WORK, OUT = "/tmp/work", "/kaggle/working"
os.makedirs(WORK, exist_ok=True)


def sh(cmd, cwd=None, check=True, tail=25):
    print(f"$ {cmd}", flush=True)
    r = subprocess.run(cmd, shell=True, cwd=cwd, capture_output=True, text=True)
    out = (r.stdout + r.stderr).strip().splitlines()
    failed = bool(check and r.returncode)
    print("\n".join(out[-(120 if failed else tail):]), flush=True)          # on failure show a lot: the real error is rarely in the last lines
    if failed:
        sys.exit(f"command failed ({r.returncode}): {cmd}")
    return r


# ------------------------------------------------------------------ 1. the machine
sh("nvidia-smi --query-gpu=name,memory.total --format=csv; free -g | head -2; nvcc --version | tail -2; cmake --version | head -1", check=False)

# ------------------------------------------------------------------ 2. llama-server: the ready-made Ubuntu CUDA 12.8 build (no compiling)
TAG = "b11934"                                                                      # a release that has these files (checked 2026-10-27)
BASE = f"https://github.com/ggml-org/llama.cpp/releases/download/{TAG}"
t0 = time.time()
BIN = f"{WORK}/llama"
if not os.path.exists(BIN):
    os.makedirs(BIN)
    for name in (f"llama-{TAG}-bin-ubuntu-cuda-12.8-x64.tar.gz", f"cudart-llama-{TAG}-bin-ubuntu-cuda-12.8-x64.tar.gz"):
        sh(f"curl -sSL -o {WORK}/{name} {BASE}/{name} && tar -xzf {WORK}/{name} -C {BIN}", tail=3)
found = subprocess.run(f"find {BIN} -name llama-server -type f", shell=True, capture_output=True, text=True).stdout.split()
if not found:
    sh(f"find {BIN} | head -40", check=False, tail=40)
    sys.exit("llama-server was not in the downloaded archive; the file list is above.")
SERVER = found[0]
os.chmod(SERVER, 0o755)
LIBDIR = os.path.dirname(SERVER)
os.environ["LD_LIBRARY_PATH"] = f"{LIBDIR}:" + os.environ.get("LD_LIBRARY_PATH", "")
print(f"llama-server at {SERVER}, ready in {time.time() - t0:.0f} s", flush=True)
sh(f"ldd {SERVER} | grep -i 'not found' ; {SERVER} --version 2>&1 | tail -3", check=False, tail=8)

# ------------------------------------------------------------------ 3. the model file
sh("pip install -q -U huggingface_hub", check=False, tail=2)
from huggingface_hub import hf_hub_download  # noqa: E402
os.environ["HF_HOME"] = "/tmp/hf"


def start(file, ngl):
    path = hf_hub_download(REPO, file)
    print(f"model file: {file} ({os.path.getsize(path) / 1e9:.1f} GB)", flush=True)
    log = open(f"{OUT}/llama-server.log", "w")
    proc = subprocess.Popen([SERVER, "-m", path, "-ngl", str(ngl), "-c", "2048", "-sm", "layer", "-ts", "1,1", "--host", "127.0.0.1", "--port", "8080",
                             "--jinja", "--chat-template-kwargs", '{"enable_thinking": false}', "--no-webui"], stdout=log, stderr=subprocess.STDOUT)
    for _ in range(240):                                    # up to 20 minutes to load
        time.sleep(5)
        if proc.poll() is not None:
            return None, file
        try:
            if urllib.request.urlopen("http://127.0.0.1:8080/health", timeout=3).status == 200:
                return proc, file
        except Exception:
            pass
    proc.kill()
    return None, file


t0 = time.time()
proc, used_file = start(FILE, 99)
if proc is None:
    print("first choice did not start; log tail:\n" + open(f"{OUT}/llama-server.log").read()[-1500:], flush=True)
    proc, used_file = start(FALLBACK_FILE, 99)
if proc is None:
    print(open(f"{OUT}/llama-server.log").read()[-3000:])
    sys.exit("llama-server did not start. The tail of its log is above and in llama-server.log.")
print(f"server ready after {time.time() - t0:.0f} s with {used_file}", flush=True)
sh(f"grep -i -E 'offloaded|model buffer|model size' {OUT}/llama-server.log | head -8", check=False)

# ------------------------------------------------------------------ 4. the translation test
def chat(messages, max_tokens=180):
    body = {"messages": messages, "temperature": 0, "max_tokens": max_tokens, "repeat_penalty": 1.1}
    req = urllib.request.Request("http://127.0.0.1:8080/v1/chat/completions", json.dumps(body).encode(), {"Content-Type": "application/json"})
    t = time.time()
    r = json.load(urllib.request.urlopen(req, timeout=300))
    msg = r["choices"][0]["message"]["content"] or ""
    if "</think>" in msg:
        msg = msg.split("</think>")[-1]
    return msg.strip(), round(time.time() - t, 2), r.get("usage", {}).get("completion_tokens") or 0


RULES = ("Translate exactly. Do not add, remove or guess information. Keep numbers, colours and names. Keep conditions (if, when, until), "
         "negations (do not) and questions as they are. Say who does what: a statement about someone else stays a statement. "
         "If a part is unclear, write [unclear] there. Output only the translation, never the original.")
# Examples (not from the test set). The Kannada lines were written by me and have NOT been reviewed by a native speaker.
EX = [("seedha aao phir left le lo", "Come straight, then turn left.", "ನೇರವಾಗಿ ಬನ್ನಿ, ನಂತರ ಎಡಕ್ಕೆ ತಿರುಗಿ."),
      ("jab petrol pump dikhe tab ruk jana", "When you see the petrol pump, stop.", "ಪೆಟ್ರೋಲ್ ಬಂಕ್ ಕಾಣಿಸಿದಾಗ ನಿಲ್ಲಿ."),
      ("yahan ruko mat, aage jao", "Do not stop here, go ahead.", "ಇಲ್ಲಿ ನಿಲ್ಲಬೇಡಿ, ಮುಂದೆ ಹೋಗಿ."),
      ("क्या मैं यहाँ रुकूँ", "Should I stop here?", "ನಾನು ಇಲ್ಲಿ ನಿಲ್ಲಬೇಕೇ?")]


def shots(idx):
    out = []
    for e in EX:
        out += [{"role": "user", "content": e[0]}, {"role": "assistant", "content": e[idx]}]
    return out


def hi_to_en(text):
    sysm = "You translate short phone-call messages between a customer and a delivery rider from Hindi or Hinglish into English. " + RULES
    return chat([{"role": "system", "content": sysm}] + shots(1) + [{"role": "user", "content": text}])


def hi_to_kn(text):
    sysm = ("You translate short phone-call messages between a customer and a delivery rider from Hindi or Hinglish into Kannada. "
            "Always answer in Kannada script (ಕನ್ನಡ), even when the message is written in Roman letters. Never copy the message. " + RULES)
    return chat([{"role": "system", "content": sysm}] + shots(2) + [{"role": "user", "content": text}])


def en_to_kn(text):
    sysm = ("You translate short English phone-call messages between a customer and a delivery rider into Kannada, in Kannada script (ಕನ್ನಡ). "
            "Never copy the message. " + RULES)
    return chat([{"role": "system", "content": sysm}] + [m for e in EX for m in ({"role": "user", "content": e[1]}, {"role": "assistant", "content": e[2]})]
                + [{"role": "user", "content": text}])


def letters(text):
    kn = sum("\u0c80" <= c <= "\u0cff" for c in text)
    dv = sum("\u0900" <= c <= "\u097f" for c in text)
    la = sum(c.isascii() and c.isalpha() for c in text)
    return kn, dv, la


def flags(src, out, target, tokens):
    f = []
    if out.strip().lower() == src.strip().lower():
        f.append("COPIED_INPUT")
    kn, dv, la = letters(out)
    if target == "Kannada":
        if dv:
            f.append("HAS_DEVANAGARI")
        if la and la > kn * 0.2:
            f.append("HAS_LATIN")
        if not kn:
            f.append("NO_KANNADA")
    words = out.split()
    grams = [" ".join(words[i:i + 3]) for i in range(len(words) - 2)]
    if grams and max(grams.count(g) for g in grams) >= 4:
        f.append("REPEATING")
    if tokens >= 170:
        f.append("HIT_LENGTH_LIMIT")
    return f


SENTENCES = [   # the same 12 as before ...
    "सामने बिल्डिंग नंबर सिक्स सेवन नाइन है मेरा और आप सीधे देखो ब्लू कलर का बंदा दिखेगा ब्लू कलर का टी शर्ट दिखेगा वहाँ पे आ जाना",
    "भैया सीधे आ जाओ राइट ले लो फिर सामने बिल्डिंग दिखेगी वहाँ ठहरो मैं आ रहा हूँ",
    "भैया चाय पीकर आना",
    "building dikhne par right le lo",
    "agar building dikhe to wahan ruko",
    "driver seedha aa raha hai",
    "क्या मैं सीधे आ जाऊं",
    "right mat lena seedha aao",
    "दो गली बाद राइट ले लो",
    "आप वहाँ वेट कीजिए मैं फाइव मिनट में आ रहा हूँ",
    "bhaiya second gate right side wala, uske upar blue board hai",
    "ye mera number nahi hai, dusra number try karo",
    # ... plus 6 new ones that the examples do not cover
    "jab tak gate na dikhe seedha aao",
    "left mat lo seedha jao",
    "kya yahan ruk jaun",
    "do gali baad building ke samne ruko",
    "wo banda blue shirt mein hai",
    "bhaiya bahut traffic hai thoda late ho jaunga",
]

print("warm-up call (not counted) ...", flush=True)
chat([{"role": "user", "content": "namaste"}], max_tokens=8)

results = []
for i, s in enumerate(SENTENCES):
    row = {"said": s, "new_pattern": i >= 12}
    en, t_en, n_en = hi_to_en(s)
    row["English"] = {"text": en, "seconds": t_en, "tokens": n_en, "flags": flags(s, en, "English", n_en)}
    kn, t_kn, n_kn = hi_to_kn(s)
    row["Kannada_direct"] = {"text": kn, "seconds": t_kn, "tokens": n_kn, "flags": flags(s, kn, "Kannada", n_kn)}
    kn2, t2, n2 = en_to_kn(en)
    row["Kannada_via_English"] = {"text": kn2, "seconds": round(t_en + t2, 2), "tokens": n2, "flags": flags(en, kn2, "Kannada", n2)}
    results.append(row)
    print(f"{'NEW ' if row['new_pattern'] else ''}{s}")
    for k in ("English", "Kannada_direct", "Kannada_via_English"):
        print(f"  {k:20} {row[k]['seconds']:>5} s {row[k]['flags'] or ''}: {row[k]['text']}", flush=True)
    print(flush=True)

summary = {}
for k in ("English", "Kannada_direct", "Kannada_via_English"):
    secs = sorted(r[k]["seconds"] for r in results)
    summary[k] = {"median_s": secs[len(secs) // 2], "max_s": secs[-1], "with_flags": sum(bool(r[k]["flags"]) for r in results), "of": len(results)}
print("summary:", json.dumps(summary), flush=True)
json.dump({"model_file": used_file, "summary": summary, "results": results}, open(f"{OUT}/evon_results.json", "w"), ensure_ascii=False, indent=1)
proc.terminate()
print("done: evon_results.json saved", flush=True)
