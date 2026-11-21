#!/data/data/com.termux/files/usr/bin/bash
cd "$(dirname "$0")"

if [ ! -f config.env ]; then
  echo "Not set up yet. Run:  bash setup.sh"
  exit 1
fi
source config.env

# Keep running when the screen is off
command -v termux-wake-lock >/dev/null && termux-wake-lock

echo "Watching $CITY every $((INTERVAL / 60)) min. Press Ctrl+C to stop."
while true; do
  echo "---- $(date '+%d-%m %H:%M')" | tee -a log.txt
  python check_dune.py 2>&1 | tee -a log.txt
  sleep "$INTERVAL"
done
