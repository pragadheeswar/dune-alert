#!/data/data/com.termux/files/usr/bin/bash
# Usage:
#   bash setup.sh          -> install everything + configure
#   bash setup.sh config   -> only change token / city
cd "$(dirname "$0")"

if [ "$1" != "config" ]; then
  echo "== Installing Python and requests (this takes a minute) =="
  pkg install -y python || exit 1
  pip install requests || exit 1
fi

echo
echo "== Settings (saved only on this phone, never uploaded) =="
read -r -p "Paste your Telegram bot token: " TOKEN
read -r -p "Telegram chat ID [press Enter for 5425747398]: " CHAT
CHAT=${CHAT:-5425747398}

echo
echo "Which city to watch?"
echo "  1) Chennai"
echo "  2) Bengaluru (for testing - booking already open)"
read -r -p "Choose 1 or 2 [press Enter for 1]: " C
if [ "$C" = "2" ]; then CITY="bengaluru"; else CITY="chennai"; fi

read -r -p "Check every how many minutes? [press Enter for 5]: " MIN
MIN=${MIN:-5}

cat > config.env <<EOF
export TELEGRAM_BOT_TOKEN="$TOKEN"
export TELEGRAM_CHAT_ID="$CHAT"
export CITY="$CITY"
export INTERVAL=$((MIN * 60))
EOF

echo
echo "== Sending a test message to Telegram =="
source config.env
TEST_MODE=true python check_dune.py

echo
echo "Done! If you got the Telegram message, start the checker with:"
echo "   bash run.sh"
