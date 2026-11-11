#!/bin/bash
# 开发者用：把温故发布（或更新）到你的 GitHub。朋友不需要运行这个。
# 做法：把源码复制到 ~/projects/wengu（不带缓存、输入、输出），在那里提交并推送。
set -uo pipefail
SRC="$(cd "$(dirname "$0")/.." && pwd)"
DST="$HOME/projects/wengu"
export PATH="/opt/homebrew/bin:/usr/local/bin:$HOME/.homebrew/bin:$HOME/.local/bin:$PATH"
pause() { echo; read -n 1 -s -r -p "按任意键关闭窗口"; }

mkdir -p "$DST"
rsync -a --delete --exclude .git --exclude .cache --exclude 输入 --exclude 输出 --exclude 使用说明.md \
  --exclude .DS_Store --exclude __pycache__ --exclude .pytest_cache "$SRC/" "$DST/"
cd "$DST" || exit 1
[ -d .git ] || git init -q -b main

USER_NAME=""
if command -v gh >/dev/null 2>&1 && gh auth status >/dev/null 2>&1; then
  USER_NAME="$(gh api user -q .login 2>/dev/null)"
fi
if [ -z "$USER_NAME" ] && git remote get-url origin >/dev/null 2>&1; then
  USER_NAME="$(git remote get-url origin | sed -E 's#.*github\.com[:/]([^/]+)/.*#\1#')"
fi
if [ -z "$USER_NAME" ]; then
  read -r -p "你的 GitHub 用户名：" USER_NAME
fi
[ -n "$USER_NAME" ] || { echo "没有用户名，已取消。"; pause; exit 1; }

# 把安装地址里的占位符换成你的用户名（只改发布用的这份，不改桌面上的源码）
sed -i '' "s/__GITHUB_USER__/$USER_NAME/g" install.sh README.md 发给朋友.md

git add -A
if ! git diff --cached --quiet; then
  git commit -q -m "温故 $(grep -m1 '^VERSION' wengu.py | cut -d'"' -f2)：网页界面、三份产出、一行安装

Co-Authored-By: Claude Fable 5.2 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01CtnXVn8Eyy83uFC5R8igRs" || { echo "提交失败。"; pause; exit 1; }
fi

if ! git remote get-url origin >/dev/null 2>&1; then
  if command -v gh >/dev/null 2>&1 && gh auth status >/dev/null 2>&1; then
    gh repo create wengu --public --source . --remote origin --description "把课程视频、PDF、PPT 变成带出处的复习材料（本地运行）" \
      || { echo "创建仓库失败。"; pause; exit 1; }
  else
    echo
    echo "还没有 GitHub 仓库。现在去浏览器里建一个："
    echo "  1. 打开 https://github.com/new"
    echo "  2. Repository name 填 wengu，选 Public，其他都不勾，点 Create repository"
    open "https://github.com/new" 2>/dev/null
    read -r -p "建好后回到这里按回车…" _
    git remote add origin "https://github.com/$USER_NAME/wengu.git"
  fi
fi
git push -u origin main || { echo; echo "推送失败。多半是还没登录 GitHub：按上面的提示登录后，再双击运行一次。"; pause; exit 1; }

echo
echo "✅ 已发布：https://github.com/$USER_NAME/wengu"
echo
echo "下面这段话已经复制到剪贴板，直接发给朋友（让他粘贴给 ChatGPT）："
echo "------------------------------------------------------------"
sed -n '/^```text$/,/^```$/p' 发给朋友.md | sed '1d;$d' | tee >(pbcopy)
echo "------------------------------------------------------------"
pause
