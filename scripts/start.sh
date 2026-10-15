#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

usage() {
  printf '用法：./scripts/start.sh [--docker] [--port 8765] [--submissions 路径]\n'
}

mode=trusted-local
port=8765
serve_args=()
while [ "$#" -gt 0 ]; do
  case "$1" in
    --docker) mode=docker; shift ;;
    --trusted-local) mode=trusted-local; shift ;;
    --port|--submissions)
      if [ "$#" -lt 2 ]; then usage >&2; exit 2; fi
      if [ "$1" = --port ]; then port=$2; fi
      serve_args+=("$1" "$2")
      shift 2
      ;;
    --port=*) port=${1#--port=}; serve_args+=("$1"); shift ;;
    -h|--help) usage; exit 0 ;;
    *) printf '不支持的参数：%s\n' "$1" >&2; usage >&2; exit 2 ;;
  esac
done
if ! [[ "$port" =~ ^[1-9][0-9]{0,4}$ ]] || [ "$port" -gt 65535 ]; then
  printf '端口须为 1–65535 之间的整数。\n' >&2
  exit 2
fi

if [ "$mode" = trusted-local ]; then
  printf '本地体验模式：自动准备依赖和构建，无需 Docker。\n'
  ./scripts/setup.sh --trusted-local
  serve_args+=(--trusted-local)
else
  printf 'Docker 模式：请先启动 Docker。\n'
  ./scripts/setup.sh
fi

# Refuse to replace an existing service or open an unrelated application on this port.
.venv/bin/python - "$port" <<'PY'
import socket, sys
with socket.socket() as sock:
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        sock.bind(('127.0.0.1', int(sys.argv[1])))
    except OSError:
        sys.exit(f'端口 {sys.argv[1]} 已被占用，请用 --port 8790 指定其他端口。')
PY

url="http://127.0.0.1:$port"
printf '\n启动完成后将打开 %s；按 Ctrl+C 停止服务。\n' "$url"
server_pid=
opener_pid=
cleanup() {
  if [ -n "$opener_pid" ]; then kill "$opener_pid" 2>/dev/null || true; fi
  if [ -n "$server_pid" ]; then kill "$server_pid" 2>/dev/null || true; fi
  if [ -n "$opener_pid" ]; then wait "$opener_pid" 2>/dev/null || true; fi
  if [ -n "$server_pid" ]; then wait "$server_pid" 2>/dev/null || true; fi
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
./scripts/run.sh ${serve_args[@]+"${serve_args[@]}"} &
server_pid=$!
.venv/bin/python - "$url" <<'PY' &
import json, sys, time, urllib.error, urllib.request, webbrowser
url = sys.argv[1]
for _ in range(120):
    try:
        with urllib.request.urlopen(url + '/api/state', timeout=1) as response:
            state = json.load(response)
        if state.get('frame', {}).get('engine') == 'rust':
            try:
                opened = webbrowser.open(url)
            except webbrowser.Error:
                opened = False
            if not opened:
                print(f'服务已就绪，请在浏览器中打开 {url}', flush=True)
            break
    except (OSError, ValueError, urllib.error.URLError):
        pass
    time.sleep(.5)
else:
    print(f'自动打开浏览器超时；请查看服务日志或手动访问 {url}。', flush=True)
PY
opener_pid=$!
wait "$server_pid"
