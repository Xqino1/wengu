#!/bin/bash
# 温故一键安装（macOS）。做四件事：
#   1. 没有 uv 就安装 uv（Python 运行环境管理器，装在 ~/.local/bin，不需要管理员密码）
#   2. 把温故下载到 ~/温故（已有的「输入」「输出」不会被动）
#   3. 在桌面放一个「温故」启动图标
#   4. 启动
set -euo pipefail
REPO="Xqino1/wengu"
DEST="$HOME/温故"

if [ "$(uname)" != "Darwin" ]; then
  echo "温故目前只支持 Mac。"
  exit 1
fi

echo "① 准备运行环境…"
export PATH="$HOME/.local/bin:/opt/homebrew/bin:/usr/local/bin:$HOME/.homebrew/bin:$PATH"
if ! command -v uv >/dev/null 2>&1; then
  curl -LsSf https://astral.sh/uv/install.sh | sh
  export PATH="$HOME/.local/bin:$PATH"
fi

echo "② 下载温故到 $DEST …"
mkdir -p "$DEST"
curl -fsSL "https://github.com/$REPO/archive/refs/heads/main.tar.gz" | tar -xz -C "$DEST" --strip-components=1
chmod +x "$DEST/温故.command"

echo "③ 在桌面放启动图标…"
LAUNCH="$HOME/Desktop/温故.command"
printf '#!/bin/bash\nexec "%s/温故.command"\n' "$DEST" > "$LAUNCH"
chmod +x "$LAUNCH"

echo "④ 启动…（会弹出一个新的终端窗口，浏览器随后自动打开）"
open "$LAUNCH"
echo
echo "装好了。以后双击桌面上的「温故」就能打开。"
