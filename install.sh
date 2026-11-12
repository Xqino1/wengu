#!/bin/bash
# 温故一键安装 / 更新（macOS）。装过再运行一次就是更新。做这几件事：
#   1. 没有 uv 就安装 uv（Python 运行环境管理器，装在 ~/.local/bin，不需要管理员密码）
#   2. 温故开着就先关掉（正在提取材料时不更新，免得白做）
#   3. 下载最新版到 ~/温故；上一版有、这一版没有的旧文件会删掉。「输入」「输出」和你自己放进去的文件不会动
#   4. 预先装好温故要用的组件（第一次约 1GB，之后打开就快了）
#   5. 把「温故」放进「应用程序」文件夹和桌面，第一次安装时加到程序坞（Dock）
#   6. 装了 Codex 的话，教它听懂「更新温故」
#   7. 打开温故
set -euo pipefail
REPO="Xqino1/wengu"
DEST="$HOME/温故"
SRC_APP="$DEST/温故.app"
BUNDLE_ID="io.github.xqino1.wengu"
SYS_APPS="${WENGU_SYS_APPS:-/Applications}"
LOCAL="http://127.0.0.1:8737"
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

# 发给本机的请求不走代理：有些梯子会把它也接管
STATE="$(curl -s --noproxy '*' --max-time 2 "$LOCAL/api/state" 2>/dev/null || true)"
if [ -n "$STATE" ]; then
  if grep -q '"status": *"running"' <<<"$STATE"; then
    echo "温故正在提取材料，这次先不更新（不然这次提取会白做）。"
    echo "等它跑完，或者在页面上点「停止」，再更新一次。"
    exit 1
  fi
  echo "   温故正开着，先关掉它（装完会重新打开）。"
  curl -s --noproxy '*' --max-time 3 -X POST -H 'X-Wengu: 1' "$LOCAL/api/quit" >/dev/null 2>&1 || true
  sleep 1
fi

echo "② 下载温故到 $DEST …"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
mkdir -p "$TMP/new"
curl -fsSL "https://github.com/$REPO/archive/refs/heads/main.tar.gz" | tar -xz -C "$TMP/new" --strip-components=1
if [ ! -f "$TMP/new/wengu.py" ] || [ ! -f "$TMP/new/温故.app/Contents/MacOS/wengu" ]; then
  echo "下载下来的温故不完整（少了 温故.app 或 wengu.py）。过几分钟再试一次；还不行就告诉发给你这个命令的人。"
  exit 1
fi
mkdir -p "$DEST/.cache"
# 清单记着这次装了哪些文件。下次更新时，上一版有、新版没有的文件就是旧文件，删掉；
# 不在清单里的（输入、输出、缓存、你自己放进去的）一律不碰
LIST="$DEST/.cache/安装清单.txt"
(cd "$TMP/new" && find . -type f | sed 's#^\./##' | LC_ALL=C sort) > "$TMP/list"
if [ -f "$LIST" ]; then
  LC_ALL=C sort "$LIST" > "$TMP/old"
  LC_ALL=C comm -23 "$TMP/old" "$TMP/list" | while IFS= read -r f; do
    case "$f" in "" | /* | *..* | 输入/* | 输出/* | .cache/*) continue ;; esac
    rm -f "$DEST/$f"
    d="$(dirname "$DEST/$f")"
    while [ "$d" != "$DEST" ] && rmdir "$d" 2>/dev/null; do d="$(dirname "$d")"; done
  done
fi
ditto "$TMP/new" "$DEST"
cp "$TMP/list" "$LIST"
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
  touch "$MARK"
fi

# Codex 的全局说明里写一小段，让它听懂「更新温故」。整段夹在两行标记之间：
# 每次安装都换成最新的那段，不会重复；不想要了，把这两行标记和中间的内容删掉就行
CODEX_DIR="${CODEX_HOME:-$HOME/.codex}"
if [ -d "$CODEX_DIR" ]; then
  echo "⑤ 教 Codex 听懂「更新温故」…"
  AG="$CODEX_DIR/AGENTS.md"
  [ -f "$CODEX_DIR/AGENTS.override.md" ] && AG="$CODEX_DIR/AGENTS.override.md"  # 有它时 Codex 只读它
  BEGIN="<!-- 温故：开始（温故安装程序写的，不需要了可以连同这两行标记整段删掉） -->"
  END="<!-- 温故：结束 -->"
  touch "$AG"
  awk -v b="$BEGIN" -v e="$END" '
    $0 == b { skip = 1; next }
    skip && $0 == e { skip = 0; next }
    skip { next }
    { line[++n] = $0 }
    END { while (n > 0 && line[n] == "") n--; for (i = 1; i <= n; i++) print line[i] }
  ' "$AG" > "$TMP/agents"
  {
    cat "$TMP/agents"
    if [ -s "$TMP/agents" ]; then echo; fi
    echo "$BEGIN"
    echo "## 温故（课程复习工具，装在 ~/温故）"
    echo "- 用户说「更新温故」时：在终端运行 \`curl -fsSL https://raw.githubusercontent.com/$REPO/main/install.sh | bash\`。它要联网，还要写「应用程序」和桌面，需要权限时向用户申请。跑完用一两句话告诉用户结果。"
    echo "- 如果输出说温故正在提取材料，就告诉用户等提取完再说一次「更新温故」。"
    echo "$END"
  } > "$AG"
fi

echo "⑥ 打开温故…（浏览器会自动打开页面）"
open "$APP"
echo
echo "装好了。「应用程序」、桌面和程序坞里都有「温故」，点哪个都行；用完在页面上点「退出温故」。"
if [ -d "$CODEX_DIR" ]; then echo "以后要更新，对 Codex 说「更新温故」。"; fi
