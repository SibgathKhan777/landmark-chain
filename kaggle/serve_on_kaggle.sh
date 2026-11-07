#!/usr/bin/env bash
# Start the Evon API on Kaggle (a temporary public address with a key). Reads your token from the environment; never stores it.
#   export KAGGLE_API_TOKEN=<your token>      then:   bash serve_on_kaggle.sh
set -u
cd "$(dirname "$0")/serve"
ID=$(python3 -c "import json;print(json.load(open('kernel-metadata.json'))['id'])")
if [ -z "${KAGGLE_API_TOKEN:-}" ] && [ ! -f "$HOME/.kaggle/access_token" ]; then
  echo "No Kaggle token found. Run:  export KAGGLE_API_TOKEN=<your token>   and try again."; exit 1
fi
command -v kaggle >/dev/null || { echo "kaggle CLI missing: pip install kaggle"; exit 1; }
kaggle kernels push -p . || { echo "Push failed. Copy the error above."; exit 1; }
echo
echo "Link: https://www.kaggle.com/code/$ID"
echo "Waiting for it to start. Loading the model takes about 5 minutes after that."
for i in $(seq 1 30); do
  sleep 30
  S=$(kaggle kernels status "$ID" 2>&1); echo "$(date +%H:%M:%S)  $S"
  case "$S" in *RUNNING*) break ;; *ERROR*|*COMPLETE*|*CANCEL*) echo "It stopped. Open the link and read the log."; exit 1 ;; esac
done
cat <<MSG

It is running. In about 5 to 8 minutes the log on the Kaggle page (open the link, then the Logs tab of the latest version) will show:
    COPY THESE TWO LINES INTO landmark/.env
Paste the two lines (LLM_BASE_URL=... and LLM_API_KEY=...) into /Users/sibgath/shitwork/landmark/.env and restart python live_call.py.
The address changes every run and it stops by itself after 3 hours. The log contains the key: do not share it.
MSG
