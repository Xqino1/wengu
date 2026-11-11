#!/bin/bash
# 温故一键安装（macOS）。做五件事：
#   1. 没有 uv 就安装 uv（Python 运行环境管理器，装在 ~/.local/bin，不需要管理员密码）
#   2. 把温故下载到 ~/温故（已有的「输入」「输出」不会被动）
#   3. 预先装好温故要用的组件（第一次约 1GB，之后打开就快了）
#   4. 在桌面放「温故」图标，并加到程序坞（Dock）
#   5. 打开温故
set -euo pipefail
REPO="Xqino1/wengu"
DEST="$HOME/温故"
APP="$DEST/温故.app"
BUNDLE_ID="io.github.xqino1.wengu"

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
chmod +x "$DEST/温故.command" "$APP/Contents/MacOS/wengu"

echo "③ 准备组件（第一次约 1GB，要几分钟；以后打开就快了）…"
if ! (cd "$DEST" && uv sync --script wengu.py); then
  echo "   组件这次没装完（多半是网络问题），第一次打开温故时会接着装。"
fi

echo "④ 在桌面和程序坞放「温故」图标…"
touch "$APP"  # 让系统重新读取图标
LSREG=/System/Library/Frameworks/CoreServices.framework/Frameworks/LaunchServices.framework/Support/lsregister
[ -x "$LSREG" ] && "$LSREG" -f "$APP" >/dev/null 2>&1 || true

# 桌面上放一份图标。它只是个开关，温故本体和复习包都在 ~/温故
DESK="$HOME/Desktop/温故.app"
if [ -e "$DESK" ] && ! grep -q "$BUNDLE_ID" "$DESK/Contents/Info.plist" 2>/dev/null; then
  echo "   桌面上已经有一个别的「温故.app」，没有替换它。"
else
  rm -rf "$DESK"
  ditto "$APP" "$DESK"
fi
# 旧版安装在桌面放的是「温故.command」，换成新图标后就不需要了
OLD="$HOME/Desktop/温故.command"
if [ -f "$OLD" ] && grep -q '温故/温故.command' "$OLD"; then
  rm -f "$OLD"
fi

# 程序坞：只在第一次安装时加。你自己拖走了，重装不会再加回来
MARK="$DEST/.cache/已加到程序坞"
if [ ! -f "$MARK" ]; then
  DOCK="$(defaults export com.apple.dock - 2>/dev/null || true)"
  if ! grep -q -e "$BUNDLE_ID" -e '温故/温故.app' -e '%E6%B8%A9%E6%95%85/%E6%B8%A9%E6%95%85.app' <<<"$DOCK"; then
    TILE="<dict><key>tile-data</key><dict><key>file-data</key><dict><key>_CFURLString</key><string>$APP</string><key>_CFURLStringType</key><integer>0</integer></dict></dict></dict>"
    if defaults write com.apple.dock persistent-apps -array-add "$TILE"; then
      killall Dock 2>/dev/null || true
    else
      echo "   没能加到程序坞。可以自己把桌面上的「温故」拖到程序坞里。"
    fi
  fi
  mkdir -p "$DEST/.cache"
  touch "$MARK"
fi

echo "⑤ 打开温故…（浏览器会自动打开页面）"
PING="$(curl -s --noproxy '*' --max-time 1 http://127.0.0.1:8737/api/ping 2>/dev/null || true)"
if grep -q '"wengu"' <<<"$PING"; then
  echo "   温故本来就开着。在页面上点「退出温故」，再点一次图标，就是刚装的新版。"
fi
open "$APP"
echo
echo "装好了。以后点桌面或程序坞里的「温故」就能打开；用完在页面上点「退出温故」。"
