#!/usr/bin/env bash
# Push the Evon test to Kaggle, wait for it, and download the results. Reads your token from the environment; never stores it.
#   export KAGGLE_API_TOKEN=<your token>     (a fresh one, from Kaggle > Settings > API)
#   bash run_on_kaggle.sh
set -u
cd "$(dirname "$0")/kernel"
ID=$(python3 -c "import json;print(json.load(open('kernel-metadata.json'))['id'])")

if [ -z "${KAGGLE_API_TOKEN:-}" ] && [ ! -f "$HOME/.kaggle/access_token" ]; then
  echo "No Kaggle token found. Run:  export KAGGLE_API_TOKEN=<your token>   and try again."; exit 1
fi
command -v kaggle >/dev/null || { echo "kaggle CLI missing: pip install kaggle"; exit 1; }

echo "Pushing $ID ..."
kaggle kernels push -p . || { echo "Push failed. Copy the error above."; exit 1; }
echo
echo "Link: https://www.kaggle.com/code/$ID"
echo "Waiting for the run (the model download is 63.5 GB, so this takes a while). Checking every 60 s. Ctrl+C is safe; the run continues on Kaggle."

while true; do
  sleep 60
  S=$(kaggle kernels status "$ID" 2>&1)
  echo "$(date +%H:%M:%S)  $S"
  case "$S" in
    *COMPLETE*|*complete*) break ;;
    *ERROR*|*error*|*CANCEL*|*cancel*) echo "The run did not finish cleanly. Open the link above and read the log."; break ;;
  esac
done

mkdir -p out && kaggle kernels output "$ID" -p out && echo "Downloaded to $(pwd)/out (look for evon_results.json and the log)."
