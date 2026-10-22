#!/usr/bin/env bash
set -e

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$DIR"

PID_FILE="$DIR/server.pid"
LOG_FILE="$DIR/server.log"
ICON="$DIR/static/recipe-icon.svg"
VENV_PY="$DIR/.venv/bin/python"

get_pid() {
  if [ -f "$PID_FILE" ]; then
    local p
    p=$(cat "$PID_FILE" 2>/dev/null || true)
    if [ -n "$p" ] && kill -0 "$p" 2>/dev/null && ps -p "$p" -o cmd= | grep -q "server.py"; then
      echo "$p"
      return 0
    fi
  fi
  local p
  p=$(pgrep -f "python.*server\.py" | head -n 1)
  if [ -n "$p" ]; then
    echo "$p"
    return 0
  fi
  return 1
}

get_lan_ip() {
  local ip
  ip=$(hostname -I 2>/dev/null | awk '{print $1}')
  if [ -z "$ip" ]; then
    ip="127.0.0.1"
  fi
  echo "$ip"
}

start_server() {
  local pid
  if pid=$(get_pid); then
    notify-send -i "$ICON" "Recipe Helper Server" "Server is ALREADY running on port 8080 (PID $pid)!" 2>/dev/null || true
    xdg-open "http://localhost:8080" >/dev/null 2>&1 &
    return 0
  fi

  echo "Starting Recipe Helper Server..."
  nohup "$VENV_PY" server.py >> "$LOG_FILE" 2>&1 &
  local new_pid=$!
  echo "$new_pid" > "$PID_FILE"

  # Wait up to 6 seconds for port 8080 to respond
  local count=0
  local ready=0
  while [ $count -lt 12 ]; do
    if curl -s -m 1 http://localhost:8080 >/dev/null 2>&1; then
      ready=1
      break
    fi
    sleep 0.5
    count=$((count + 1))
  done

  local lan_ip
  lan_ip=$(get_lan_ip)
  if [ $ready -eq 1 ]; then
    notify-send -i "$ICON" "Recipe Helper Server" "Server Started Successfully! 🚀\nLocal: http://localhost:8080\nMobile: http://${lan_ip}:8080" 2>/dev/null || true
    xdg-open "http://localhost:8080" >/dev/null 2>&1 &
  else
    notify-send -i "$ICON" -u critical "Recipe Helper Server" "Server started (PID $new_pid) but port 8080 is taking longer to respond. Check server.log." 2>/dev/null || true
  fi
}

stop_server() {
  local pid
  if pid=$(get_pid); then
    echo "Stopping Recipe Helper Server (PID $pid)..."
    kill "$pid" 2>/dev/null || true
    local count=0
    while kill -0 "$pid" 2>/dev/null && [ $count -lt 6 ]; do
      sleep 0.5
      count=$((count + 1))
    done
    if kill -0 "$pid" 2>/dev/null; then
      kill -9 "$pid" 2>/dev/null || true
    fi
    rm -f "$PID_FILE"
    notify-send -i "$ICON" "Recipe Helper Server" "Server Stopped 🛑" 2>/dev/null || true
  else
    notify-send -i "$ICON" "Recipe Helper Server" "Server is not currently running." 2>/dev/null || true
  fi
}

restart_server() {
  stop_server
  sleep 1
  start_server
}

view_logs() {
  if which mate-terminal >/dev/null 2>&1; then
    mate-terminal --title="Recipe Helper Server Logs" -e "tail -f $LOG_FILE" &
  elif which x-terminal-emulator >/dev/null 2>&1; then
    x-terminal-emulator -e "tail -f $LOG_FILE" &
  else
    zenity --text-info --title="Recipe Helper Server Logs" --filename="$LOG_FILE" --width=700 --height=500 &
  fi
}

gui_action() {
  local pid
  local lan_ip
  lan_ip=$(get_lan_ip)

  if pid=$(get_pid); then
    local action
    action=$(zenity --list \
      --title="Recipe Helper Server (Active 🟢)" \
      --text="Server is currently RUNNING on PID $pid\n\n🌐 Local:  http://localhost:8080\n📱 Mobile: http://${lan_ip}:8080\n\nSelect an action:" \
      --column="Action" \
      "🛑 Stop Server" \
      "🌐 Open Web App (Browser)" \
      "🔄 Restart Server" \
      "📋 View Server Logs" \
      --width=450 --height=320 2>/dev/null || true)

    case "$action" in
      "🛑 Stop Server")
        stop_server
        ;;
      "🌐 Open Web App (Browser)")
        xdg-open "http://localhost:8080" >/dev/null 2>&1 &
        ;;
      "🔄 Restart Server")
        restart_server
        ;;
      "📋 View Server Logs")
        view_logs
        ;;
      *)
        exit 0
        ;;
    esac
  else
    start_server
  fi
}

case "$1" in
  start)
    start_server
    ;;
  stop)
    stop_server
    ;;
  restart)
    restart_server
    ;;
  status)
    if pid=$(get_pid); then
      echo "Server is running (PID: $pid)"
    else
      echo "Server is stopped"
    fi
    ;;
  logs)
    view_logs
    ;;
  *)
    gui_action
    ;;
esac
