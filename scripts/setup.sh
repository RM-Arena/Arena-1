#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
setup_mode=${1:-docker}
if [ "$#" -gt 1 ] || { [ "$setup_mode" != docker ] && [ "$setup_mode" != --trusted-local ]; }; then
  printf '用法：./scripts/setup.sh [--trusted-local]\n' >&2
  exit 2
fi
required=(uv bun cargo)
if [ "$setup_mode" = docker ]; then required+=(docker); fi
for tool in "${required[@]}"; do
  if ! command -v "$tool" >/dev/null 2>&1; then
    printf '缺少 %s，请先安装后重试。\n' "$tool" >&2
    exit 1
  fi
done
uv sync --locked
bun install --frozen-lockfile
cargo build --release --manifest-path simulation/Cargo.toml
if [ "$setup_mode" = docker ]; then
  docker build -t rmuc-arena-policy:0.4 -f sandbox/Dockerfile .
fi
bun run build
printf '\n准备完成。\n'
