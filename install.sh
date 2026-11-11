#!/bin/bash
# 温故一键安装（macOS）。做五件事：
#   1. 没有 uv 就安装 uv（Python 运行环境管理器，装在 ~/.local/bin，不需要管理员密码）
#   2. 把温故下载到 ~/温故（已有的「输入」「输出」不会被动）
#   3. 预先装好温故要用的组件（第一次约 1GB，之后打开就快了）
#   4. 把「温故」放进「应用程序」文件夹和桌面，并加到程序坞（Dock）
#   5. 打开温故
set -euo pipefail
REPO="Xqino1/wengu"
DEST="$HOME/温故"
SRC_APP="$DEST/温故.app"
BUNDLE_ID="io.github.xqino1.wengu"
SYS_APPS="${WENGU_SYS_APPS:-/Applications}"
LSREG=/System/Library/Frameworks/CoreServices.framework/Frameworks/LaunchServices.framework/Support/lsregister

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
chmod +x "$DEST/温故.command" "$SRC_APP/Contents/MacOS/wengu"

echo "③ 准备组件（第一次约 1GB，要几分钟；以后打开就快了）…"
if ! (cd "$DEST" && uv sync --script wengu.py); then
  echo "   组件这次没装完（多半是网络问题），第一次打开温故时会接着装。"
fi

echo "④ 把「温故」放进应用程序、桌面和程序坞…"
# 把 温故.app 放一份到某个文件夹。那里已经有「温故」时，只替换我们自己放的（认 Bundle ID）。
# 每一份都只是个开关，温故本体和复习包都在 ~/温故。
place() {
  local dst="$1/温故.app"
  if [ -e "$dst" ] && ! grep -q "$BUNDLE_ID" "$dst/Contents/Info.plist" 2>/dev/null; then
    echo "   $1 里已经有一个别的「温故」，没有替换它。"
    return 1
  fi
  mkdir -p "$1" 2>/dev/null || true
  rm -rf "$dst" 2>/dev/null || true
  if ! ditto "$SRC_APP" "$dst" 2>/dev/null; then
    echo "   没能放进 $1。"
    return 1
  fi
  touch "$dst"  # 让系统重新读取图标
  if [ -x "$LSREG" ]; then "$LSREG" -f "$dst" >/dev/null 2>&1 || true; fi
}

# 应用程序：管理员账户能直接写 /Applications；不能写就放「个人文件夹/应用程序」，启动台和聚焦搜索一样找得到
APP="$SRC_APP"
if [ -w "$SYS_APPS" ] && place "$SYS_APPS"; then
  APP="$SYS_APPS/温故.app"
elif place "$HOME/Applications"; then
  APP="$HOME/Applications/温故.app"
fi

# 桌面
place "$HOME/Desktop" || echo "   可以自己从「应用程序」里把温故拖到桌面。"
# 旧版安装在桌面放的是「温故.command」，有了图标就不需要了
OLD="$HOME/Desktop/温故.command"
if [ -f "$OLD" ] && grep -q '温故/温故.command' "$OLD"; then
  rm -f "$OLD"
fi

# 程序坞：只在第一次安装时加。你自己拖走了，重装不会再加回来
MARK="$DEST/.cache/已加到程序坞"
if [ ! -f "$MARK" ]; then
  DOCK="$(defaults export com.apple.dock - 2>/dev/null || true)"
  if ! grep -q -e "$BUNDLE_ID" -e '温故.app' -e '%E6%B8%A9%E6%95%85.app' <<<"$DOCK"; then
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
echo "装好了。「应用程序」、桌面和程序坞里都有「温故」，点哪个都行；用完在页面上点「退出温故」。"
