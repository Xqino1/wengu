#!/bin/bash
# 温故启动器：双击运行，会在浏览器里打开温故的页面。
cd "$(dirname "$0")" || exit 1
export PATH="$HOME/.local/bin:/opt/homebrew/bin:/usr/local/bin:$HOME/.homebrew/bin:$PATH"

if ! command -v uv >/dev/null 2>&1; then
  echo "第一次使用：正在安装运行环境（约 1 分钟）…"
  if ! curl -LsSf https://astral.sh/uv/install.sh | sh; then
    echo
    echo "运行环境没装上，多半是网络问题。检查网络后再双击一次。"
    read -n 1 -s -r -p "按任意键关闭窗口"
    exit 1
  fi
  export PATH="$HOME/.local/bin:$PATH"
fi

echo "正在启动温故…第一次启动要下载组件（约 1GB），可能需要几分钟，之后都是秒开。"
# 先顺手把 yt-dlp 更新到最新（YouTube 经常变）；没网就用现有版本启动
uv run --quiet -P yt-dlp wengu.py "$@" || uv run --quiet --offline wengu.py "$@"
status=$?
if [ $status -ne 0 ]; then
  echo
  echo "温故没能启动（错误码 $status）。把这个窗口截图，发给给你这个工具的人。"
  read -n 1 -s -r -p "按任意键关闭窗口"
fi
