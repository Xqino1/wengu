#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10,<3.13"
# dependencies = [
#   "yt-dlp[default]",
#   "deno",
#   "imageio-ffmpeg",
#   "markdown",
#   "pypdf",
#   "python-pptx",
#   "opencc-python-reimplemented",
#   "mlx-whisper; sys_platform == 'darwin' and platform_machine == 'arm64'",
#   "faster-whisper; sys_platform != 'darwin' or platform_machine != 'arm64'",
# ]
# ///
"""
温故 · 把课程视频、录音、PDF、PPT 变成能复习的材料

双击「温故.command」会在浏览器里打开界面：粘贴 YouTube 链接或拖入文件，点「开始提取」。
每次提取生成一个复习包文件夹：
  1_原文全文/   每份材料的完整文字，带时间戳 / 页码（程序直接生成）
  2_复习文档/   详细复习文档（由你自己的 AI 按「给AI的任务.md」写）
  3_精读指引/   哪些片段、哪些页必须亲自看（自动线索由程序生成，其余由 AI 写）

命令行用法（不开界面）：uv run wengu.py --cli
"""

from __future__ import annotations

import hashlib
import math
import html
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import threading
import time
import uuid
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
IN_DIR = ROOT / "输入"
OUT_DIR = ROOT / "输出"
CACHE_DIR = ROOT / ".cache"
DONE_DIR = IN_DIR / "已处理"

IS_APPLE_SILICON = sys.platform == "darwin" and platform.machine() == "arm64"
MLX_MODEL = "mlx-community/whisper-large-v3-turbo"
FW_MODEL = os.environ.get("WENGU_FW_MODEL", "small")  # 非 M 芯片电脑用的模型，越大越准越慢

MEDIA_EXT = {".mp4", ".mov", ".m4a", ".mp3", ".wav", ".webm", ".aac", ".flac", ".mkv", ".ogg", ".m4v"}
DOC_EXT = {".pdf", ".pptx"}
CONVERT_HINT = {".ppt": "PPTX 或 PDF", ".key": "PDF 或 PPTX", ".doc": "PDF", ".docx": "PDF", ".pages": "PDF"}

VERSION = "0.4.1"
PORT = 8737
SEC_RAW, SEC_REVIEW, SEC_GUIDE = "1_原文全文", "2_复习文档", "3_精读指引"
TASK_FILE = "给AI的任务.md"
CUES_FILE = "自动线索.md"
MERGED_FILE = "原文全文_合并版.md"

AI_TASK = """# Task for the AI · {name}

You are my exam-prep tutor. This folder was produced by 温故 (Wengu) from my course materials. For each material, write two documents: **Study Notes** and a **Viewing Guide**.
If you can write files, save them as Markdown in the folders named below. If you cannot, output the same structure in the chat, one material at a time.

## Output language

Use the language I name in my message. If I don't name one, write in the language of the course material itself (English lectures → English notes): that is the language of my exam. Always keep technical terms, definitions and formulas exactly as the course states them. If I ask for Chinese or bilingual output, keep every term in the original language and give the translation in parentheses the first time it appears. Translate the section headings below into the output language.

## What is in this folder

- `1_原文全文/` — one file per material, numbered S1, S2, … Each video paragraph starts with a timestamp (for YouTube it is a clickable link). PDFs are split by `p.N`, slide decks by `slide N`.
- `3_精读指引/自动线索.md` — positions flagged by keyword matching ("important", "on the exam", "look at this graph", …). Nobody has judged them; expect false hits and misses. Use them only as leads.
- The list of materials is at the end of this file.

## Rules (both documents)

1. **Source only.** Write only what the material says. If background knowledge is truly needed, put it in a clearly labelled "Added (not from the course)" note.
2. **Cite everything.** Every concept, formula, example and recommendation ends with its source. Video: copy the paragraph's timestamp link unchanged and prefix the material number, e.g. `S3 [12:34](https://…&t=754s)`; with no link write `S3 12:34`. PDF: `S5 p.12`. Slides: `S6 slide 7`. If you cannot cite it, leave it out.
3. **Never silently fix the transcript.** Video text comes from captions or speech recognition and contains wrong words and numbers. When a term, number or formula looks wrong, give the version you believe is right and flag it "possible transcription error — verify", with the source.
4. **Never guess what was on screen.** The transcript cannot see the board, graphs or slides. Where the lecturer says "look here", "this curve", "as you can see" and the words do not spell out the content, write "depends on visuals" and list that moment in the Viewing Guide.
5. **One material at a time.** Finish one before starting the next. Do not merge or skip. If you stop early, tell me which material you reached.
6. **Math in LaTeX.** Inline math as `$...$`, displayed equations as `$$...$$` on their own lines. Define each symbol the first time it appears. Never write formulas as plain text such as `MUx/MUy`. Write money as "3 dollars" (or `\\$3`) so it is not read as math.
7. **Depth and layout.** These are study notes, not an outline: someone who reads only this document should be able to answer exam questions on the material. For a 45-minute lecture expect roughly 1,500–3,000 words. One `###` heading per concept. Short paragraphs (five lines at most), bullet lists, a table whenever things are compared, derivations as displayed equations with one step per line. No walls of text.

## Document 1: Study Notes → `2_复习文档/`

One file per material, with the same filename as its transcript (e.g. `S03_….md`). Structure:

```
# S3 | <title> — Study Notes
## What this lecture is about          (3–5 sentences, and where it sits in the course)
## Concepts
### <Concept name>
**Definition.** in the course's own terms
**Derivation / reasoning.** every step, nothing skipped; displayed equations
**Example.** the lecturer's example, with its numbers
**Pitfalls.** only ones the lecturer mentioned
**Source.** S3 [12:34](…)
## Formula sheet                       (table: Formula | Symbols | When it applies | Source)
## Graphs and figures                  (axes and curves as described in words; mark "depends on visuals")
## What the lecturer stressed          (short verbatim quotes + source)
## Links to other materials            (what it builds on, what builds on it)
## Practice questions                  (5–8, including calculation or derivation questions; cite the source of each)
## Answers                             (worked, at the end of the file)
## To verify
```

After every material is done, write `2_复习文档/00_总览.md` (course overview): a topic map (topic → which materials), one formula sheet for the whole course, and the 15 most examinable points in order of importance, each with your reason and its source.

## Document 2: Viewing Guide → `3_精读指引/`

Purpose: tell me which parts I must watch or read myself, and which parts the Study Notes cover well enough. **It is not a summary.**

One file per material, same filename as its transcript. Structure:

```
# S3 | <title> — Viewing Guide
## Verdict: watch about X of Y minutes yourself
## Must watch                          (table, most important first)
   | Where (clickable timestamp range, or pages) | Length | What it covers | Why you must see it yourself |
## The Study Notes are enough for      (time ranges or pages + one line each)
## Safe to skip                        (chit-chat, logistics, repetition; with time ranges)
```

"Why you must see it yourself" must be one or more of these, named explicitly:

- **A Depends on visuals** — board derivation, a graph being drawn, a demo: the transcript lost information
- **B Stressed by the lecturer** — said to be important or examinable, or repeated
- **C Long derivation** — hard to follow from text alone
- **D Poor transcript** — many recognition errors or broken sentences here
- **E Foundation** — later materials build on it

For PDFs and slide decks use "Must read", "Skim", "Safe to skip" with pages, and give the same kind of reasons.

After every material is done, write `3_精读指引/00_学习路线.md` (study plan): the combined must-watch list ranked by importance with total time, and three plans — 3 hours, 1 day, 3 days — saying what to watch, what to read, and in what order.

## When you finish

Tell me how many materials you processed, which points most need my verification, and whether any material's transcript is too poor to rely on.

## Materials

{toc}
"""

URL_RE = re.compile(r"https?://[^\s　，。！？、“”‘’（）()<>【】\[\]]+")
END_PUNCT = "。！？!?….;；"
ANY_PUNCT = "，。！？；：、,.!?;:…）)」』”\"'"
JUNK_PHRASES = ("请不吝点赞", "订阅 转发 打赏", "明镜与点点", "字幕由", "Amara.org", "字幕志愿者")
REPEAT_RE = re.compile(r"(.{1,4}?)\1{5,}")
SOUND_TAG_RE = re.compile(r"\[[A-Z][A-Z ,'\-]+\]|♪+")  # [APPLAUSE] [SQUEAKING] 这类声音标注
CLOSERS = "\"'”’)）」』"


# ---------------- 小工具 ----------------
OWN_MARK = "# 温故 · 复习包"  # 自己生成的复习包里有大量时间戳链接，不能再当输入
DROP_PARAMS = {"t", "start", "si", "feature", "pp", "ab_channel"}


def normalize_url(u: str) -> str:
    """YouTube 链接去掉时间戳、分享追踪参数，同一个视频只算一条。"""
    from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

    if "youtube.com/" not in u and "youtu.be/" not in u:
        return u
    pr = urlparse(u)
    q = [(k, v) for k, v in parse_qsl(pr.query, keep_blank_values=True) if k not in DROP_PARAMS]
    return urlunparse(pr._replace(query=urlencode(q, safe=","), fragment=""))


def extract_urls(text: str) -> list[str]:
    seen, urls = set(), []
    for m in URL_RE.finditer(text or ""):
        u = normalize_url(m.group(0).rstrip(".,;:!?"))
        if u not in seen:
            seen.add(u)
            urls.append(u)
    return urls


def fmt_ts(sec: float) -> str:
    m, s = divmod(int(sec), 60)
    h, m = divmod(m, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"


def is_cjk(ch: str) -> bool:
    return "一" <= ch <= "鿿" or "぀" <= ch <= "ヿ" or "가" <= ch <= "힯"


def mostly_cjk(text: str) -> bool:
    letters = [c for c in text if c.isalpha()]
    return bool(letters) and sum(is_cjk(c) for c in letters) / len(letters) > 0.3


def time_link(base_url: str | None, sec: float) -> str:
    """YouTube 时间戳做成可点击的链接，点一下跳到视频对应位置。"""
    ts = fmt_ts(sec)
    if not base_url:
        return f"[{ts}]"
    s = int(sec)
    if "youtube.com/watch" in base_url:
        return f"[{ts}]({base_url}&t={s}s)"
    if "youtu.be/" in base_url:
        sep = "&" if "?" in base_url else "?"
        return f"[{ts}]({base_url}{sep}t={s})"
    return f"[{ts}]"


def get_converter():
    try:
        from opencc import OpenCC

        return OpenCC("t2s")
    except Exception:
        return None


def clean_text(t: str, cc=None) -> str:
    t = SOUND_TAG_RE.sub("", t or "").strip()
    if not any(c.isalnum() for c in t):
        return ""  # 只剩标点（比如 "."）就丢掉
    if cc and mostly_cjk(t):
        t = cc.convert(t)
    return REPEAT_RE.sub(r"\1", t)


def segment_paragraphs(segs: list[dict], cc=None, gap: float = 2.0) -> list[tuple[float, str]]:
    """把字幕/转写碎句合成段落，返回 (开始秒数, 文字)。中文段落约 160 字，英文约 600 字符。"""
    sample = " ".join(s.get("text", "") for s in segs[:50])
    cjk = mostly_cjk(sample)
    max_len = 160 if cjk else 600
    hard_len = int(max_len * 1.6)  # 一直等不到句号时的硬上限
    paras: list[tuple[float, list[str], bool]] = []  # (开始时间, 碎句, 是否在完整句子处断开)
    cur: list[str] = []
    cur_start, last_end, last_text = 0.0, None, None
    for sg in segs:
        t = clean_text(sg.get("text", ""), cc)
        if not t or t == last_text or any(j in t for j in JUNK_PHRASES):
            continue
        start = float(sg.get("start", 0.0))
        end = float(sg.get("end", start))
        if cur:
            size = sum(map(len, cur))
            paused = last_end is not None and start - last_end > gap
            # 中文转写碎句本身就是一句；英文要等到句号再断段，避免把一句话劈成两半
            sentence_end = cjk or cur[-1].rstrip(CLOSERS)[-1:] in END_PUNCT
            if paused or (size > max_len and sentence_end) or size > hard_len:
                paras.append((cur_start, cur, paused or sentence_end))
                cur = []
        if not cur:
            cur_start = start
        cur.append(t)
        last_end, last_text = end, t
    if cur:
        paras.append((cur_start, cur, True))

    out = []
    for st, parts, complete in paras:
        text = ""
        for i, p in enumerate(parts):
            if i == 0:
                text = p
                continue
            prev = text[-1]
            if is_cjk(prev) or is_cjk(p[0]):
                text += ("" if prev in ANY_PUNCT else "，") + p
            else:
                text += " " + p
        if complete and text and text[-1] not in END_PUNCT and text[-1] not in ANY_PUNCT:
            text += "。" if cjk else "."
        out.append((st, text))
    return out


def format_segments(segs: list[dict], base_url: str | None = None, cc=None, gap: float = 2.0) -> str:
    """带时间戳的段落文本；YouTube 的时间戳是可点击的链接。"""
    return "\n\n".join(f"{time_link(base_url, st)} {text}" for st, text in segment_paragraphs(segs, cc, gap))


# ---------------- 字幕 ----------------
def _ts(s: str) -> float:
    parts = s.split(":")
    sec = float(parts[-1])
    if len(parts) >= 2:
        sec += int(parts[-2]) * 60
    if len(parts) == 3:
        sec += int(parts[0]) * 3600
    return sec


def parse_json3(data: dict) -> list[dict]:
    segs = []
    for ev in data.get("events", []):
        if "segs" not in ev:
            continue
        text = "".join(s.get("utf8", "") for s in ev["segs"]).replace("\n", " ").strip()
        text = re.sub(r"\s+", " ", text)
        if not text:
            continue
        start = ev.get("tStartMs", 0) / 1000
        segs.append({"start": start, "end": start + ev.get("dDurationMs", 0) / 1000, "text": text})
    return segs


def parse_vtt(text: str) -> list[dict]:
    segs, last = [], None
    for block in re.split(r"\n\s*\n", text.replace("\r", "")):
        lines = block.strip().split("\n")
        for i, line in enumerate(lines):
            m = re.match(r"((?:\d+:)?\d{2}:\d{2}\.\d{3})\s+-->\s+((?:\d+:)?\d{2}:\d{2}\.\d{3})", line)
            if m:
                break
        else:
            continue
        start, end = _ts(m.group(1)), _ts(m.group(2))
        for line in lines[i + 1:]:
            t = html.unescape(re.sub(r"<[^>]+>", "", line)).strip()
            if t and t != last:  # 自动字幕会滚动重复上一行，去掉
                segs.append({"start": start, "end": end, "text": t})
                last = t
    return segs


LANG_NAMES = {"en": "英语", "zh": "中文", "ja": "日语", "ko": "韩语", "fr": "法语", "de": "德语", "es": "西班牙语",
              "pt": "葡萄牙语", "it": "意大利语", "ru": "俄语", "ar": "阿拉伯语", "hi": "印地语", "vi": "越南语"}


def spoken_language(info: dict) -> str:
    """视频里实际说的语言，如 "en"；判断不出时返回 ""。
    先看 YouTube 语音识别的原语言字幕轨（键名以 -orig 结尾，是按声音判断的）；没有才用视频标注的语言。
    标注是上传者自己填的，可能不准，比如给日本学生的英语听力视频标成日语。"""
    for k in info.get("automatic_captions") or {}:
        if k.endswith("-orig"):
            return k[: -len("-orig")].split("-")[0].lower()
    return (info.get("language") or "").split("-")[0].lower()


def pick_subtitle(info: dict) -> tuple[str, dict] | None:
    """只用和视频所说语言一致的字幕：人工字幕优先，其次原语言自动字幕。
    别的语言的字幕即使是人工的，也是翻译，拿来复习会和视频对不上；
    判断不出视频说什么语言时返回 None，交给语音识别（它按声音判断语言）。
    返回的说明带语言名，比如「人工字幕（英语）」，写进复习包的「文字来源」。"""
    lang = spoken_language(info)
    if not lang:
        return None
    name = LANG_NAMES.get(lang, lang)

    def best_fmt(tracks: list[dict]) -> dict | None:
        for ext in ("json3", "vtt"):
            for t in tracks:
                if t.get("ext") == ext and t.get("url"):
                    return t
        return None

    manual = {k: v for k, v in (info.get("subtitles") or {}).items() if k != "live_chat"}
    same = [k for k in manual if k.split("-")[0].lower() == lang]
    for k in sorted(same, key=lambda k: k.lower() != lang):  # "en" 排在 "en-GB" 前面
        f = best_fmt(manual[k])
        if f:
            return f"人工字幕（{name}）", f

    # 自动字幕里除了原语言那一轨，其余都是机器翻译，不用
    auto = info.get("automatic_captions") or {}
    order = [k for k in auto if k.endswith("-orig")] + [k for k in auto if k.lower() == lang]
    for k in order:
        f = best_fmt(auto[k])
        if f:
            return f"自动字幕（{name}）", f
    return None


# ---------------- 文档 ----------------
def extract_pdf(path: Path) -> list[dict]:
    from pypdf import PdfReader

    out = []
    for i, page in enumerate(PdfReader(str(path)).pages, 1):
        try:
            t = page.extract_text() or ""
        except Exception:
            t = ""
        t = re.sub(r"[ \t]+\n", "\n", t)
        t = re.sub(r"\n{3,}", "\n\n", t).strip()
        out.append({"n": i, "text": t})
    return out


def _shape_texts(shapes) -> list[str]:
    from pptx.enum.shapes import MSO_SHAPE_TYPE

    parts = []
    for sh in shapes:
        if sh.shape_type == MSO_SHAPE_TYPE.GROUP:
            parts += _shape_texts(sh.shapes)
            continue
        if getattr(sh, "has_text_frame", False) and sh.has_text_frame:
            t = "\n".join(p.text for p in sh.text_frame.paragraphs if p.text.strip())
            if t.strip():
                parts.append(t.strip())
        if getattr(sh, "has_table", False) and sh.has_table:
            for row in sh.table.rows:
                parts.append(" | ".join(c.text.strip() for c in row.cells))
    return parts


def extract_pptx(path: Path) -> list[dict]:
    from pptx import Presentation

    out = []
    for i, slide in enumerate(Presentation(str(path)).slides, 1):
        notes = ""
        if slide.has_notes_slide:
            notes = (slide.notes_slide.notes_text_frame.text or "").strip()
        out.append({"n": i, "text": "\n".join(_shape_texts(slide.shapes)).strip(), "notes": notes})
    return out


def format_pages(pages: list[dict], unit: str) -> str:
    """unit 是标题前缀：PDF 用 "p."，PPT 用 "slide "。"""
    blocks = []
    for p in pages:
        body = p["text"] or "（这一页没有可提取的文字，可能是图片或扫描件）"
        block = f"### {unit}{p['n']}\n\n{body}"
        if p.get("notes"):
            block += f"\n\n> 演讲者备注：{p['notes']}"
        blocks.append(block)
    return "\n\n".join(blocks)


# ---------------- 转写 ----------------
def transcribe(path: Path) -> list[dict]:
    if IS_APPLE_SILICON:
        import mlx_whisper

        res = mlx_whisper.transcribe(str(path), path_or_hf_repo=MLX_MODEL, verbose=False)
        return [{"start": s["start"], "end": s["end"], "text": s["text"]} for s in res.get("segments", [])]
    from faster_whisper import WhisperModel

    model = WhisperModel(FW_MODEL, device="cpu", compute_type="int8")
    segments, _ = model.transcribe(str(path), vad_filter=True)
    return [{"start": s.start, "end": s.end, "text": s.text} for s in segments]


def media_duration(segs: list[dict]) -> float:
    return segs[-1]["end"] if segs else 0


# ---------------- 缓存 ----------------
def cache_key(prefix: str, raw: str) -> str:
    return prefix + "_" + hashlib.md5(raw.encode("utf-8")).hexdigest()[:16]


def cache_load(key: str) -> dict | None:
    p = CACHE_DIR / f"{key}.json"
    if p.exists():
        try:
            return json.loads(p.read_text("utf-8"))
        except Exception:
            return None
    return None


def cache_save(key: str, data: dict) -> None:
    (CACHE_DIR / f"{key}.json").write_text(json.dumps(data, ensure_ascii=False), "utf-8")


# ---------------- 进度播报 / 外部工具 ----------------
_reporter = None  # 界面模式下指向当前任务，命令行模式为 None


def say(msg: str) -> None:
    if _reporter is not None:
        _reporter.note(msg)
    else:
        print(f"     {msg}", flush=True)


def setup_tools() -> None:
    """Deno 和 ffmpeg 都随依赖自动安装，这里只负责让它们能被找到，不需要 Homebrew。"""
    bindir = str(Path(sys.executable).parent)
    if bindir not in os.environ.get("PATH", "").split(os.pathsep):
        os.environ["PATH"] = bindir + os.pathsep + os.environ.get("PATH", "")
    if shutil.which("ffmpeg"):
        return
    try:
        import imageio_ffmpeg

        exe = Path(imageio_ffmpeg.get_ffmpeg_exe())
        shim = CACHE_DIR / "bin"
        shim.mkdir(parents=True, exist_ok=True)
        link = shim / "ffmpeg"
        if link.is_symlink() or link.exists():
            link.unlink()
        link.symlink_to(exe)
        os.environ["PATH"] = str(shim) + os.pathsep + os.environ["PATH"]
    except Exception:
        pass  # 有字幕的视频和 PDF / PPT 不需要 ffmpeg


# ---------------- YouTube 人机验证：借用浏览器登录状态 ----------------
BROWSERS = [b for b in [os.environ.get("WENGU_BROWSER")] if b] + ["chrome", "safari", "edge", "brave", "firefox"]
_cookie_browser: str | None = None  # 第一次成功后记住，后面直接用


class _QuietLogger:
    """不让 yt-dlp 自己往屏幕上刷英文报错，错误由我们统一用中文说明。"""

    def debug(self, msg):
        pass

    info = warning = error = debug


def _needs_cookies(err: Exception) -> bool:
    msg = str(err).lower()
    return "not a bot" in msg or "sign in to confirm" in msg


def _browser_unavailable(err: Exception) -> bool:
    msg = str(err).lower()
    return any(k in msg for k in ("cookies database", "operation not permitted", "could not find",
                                  "decrypt", "keychain", "keyring", "unsupported browser"))


def _friendly(err: Exception) -> Exception:
    msg = str(err)
    if "Requested format is not available" in msg or "n challenge" in msg:
        return RuntimeError("这个视频没有字幕，下载音频时 YouTube 的验证没通过。关掉温故再打开重试一次；还不行就把视频下载到本地，拖进来处理。")
    return err


def run_ydl(opts: dict, fn):
    """先不带 Cookie 跑；遇到人机验证，依次借用各浏览器的登录状态重试。"""
    global _cookie_browser
    import yt_dlp

    base = {"quiet": True, "no_warnings": True, "logger": _QuietLogger(), **opts}
    if _cookie_browser:
        base["cookiesfrombrowser"] = (_cookie_browser,)
    try:
        with yt_dlp.YoutubeDL(base) as ydl:
            return fn(ydl)
    except Exception as e:
        if _cookie_browser or not _needs_cookies(e):
            raise _friendly(e)
        say("YouTube 要求人机验证，正在借用浏览器的登录状态重试（Mac 如果弹出钥匙串提示，请点「始终允许」）…")
        last = e
        for b in BROWSERS:
            try:
                with yt_dlp.YoutubeDL({**base, "cookiesfrombrowser": (b,)}) as ydl:
                    out = fn(ydl)
                _cookie_browser = b
                say(f"已用 {b} 的登录状态通过验证，后面的视频都会直接用它")
                return out
            except Exception as e2:
                last = e2
                if _needs_cookies(e2) or _browser_unavailable(e2):
                    continue  # 这个浏览器不行，换下一个
                _cookie_browser = b  # 验证已经通过，是别的问题，直接如实报告
                raise _friendly(e2)
        raise RuntimeError(
            "YouTube 要求人机验证，借用浏览器登录状态也没成功。"
            "请确认 Chrome 里已登录 YouTube；如果开着代理，换个节点或关掉代理再试。"
            f"（最后的错误：{str(last)[:120]}）"
        )


def split_watch_videos(url: str) -> list[str] | None:
    """youtube.com/watch_videos?video_ids=a,b,c 这种临时合集，直接拆成单个视频。"""
    from urllib.parse import parse_qs, urlparse

    if "watch_videos" not in url:
        return None
    ids = parse_qs(urlparse(url).query).get("video_ids", [""])[0]
    vids = [v for v in ids.split(",") if v.strip()]
    return [f"https://www.youtube.com/watch?v={v.strip()}" for v in vids] or None


# ---------------- 处理各类材料 ----------------
def expand_url(url: str) -> list[str]:
    """播放列表展开成一条条视频链接。"""
    direct = split_watch_videos(url)
    if direct:
        return direct
    info = run_ydl({"extract_flat": "in_playlist", "skip_download": True},
                   lambda ydl: ydl.extract_info(url, download=False))
    if info.get("_type") == "playlist":
        out = []
        for e in info.get("entries") or []:
            if not e:
                continue
            u = e.get("url") or e.get("webpage_url") or ""
            if not u.startswith("http") and e.get("id"):
                u = f"https://www.youtube.com/watch?v={e['id']}"
            if u:
                out.append(u)
        return out
    return [url]


def process_online(url: str) -> dict:
    key = cache_key("url", url)
    cached = cache_load(key)
    # v0.4.1 之前选字幕不看语言，可能拿了别的语言的翻译字幕（比如英语播客拿到日语字幕）。
    # 那些缓存的说明是不带语言的「人工字幕」「自动字幕」：作废重取。语音识别的结果没问题，照用。
    if cached and cached.get("method") not in ("人工字幕", "自动字幕"):
        return cached

    def meta_and_subs(ydl):
        info = ydl.extract_info(url, download=False)
        segs, method = None, ""
        picked = pick_subtitle(info)
        if picked:
            kind, fmt = picked
            try:
                raw = ydl.urlopen(fmt["url"]).read().decode("utf-8", "replace")
                segs = parse_json3(json.loads(raw)) if fmt.get("ext") == "json3" else parse_vtt(raw)
                method = kind
            except Exception:
                segs = None
        return info, segs, method

    # 只取信息和字幕时不需要视频格式；即使格式拿不到，也照样把字幕取回来
    info, segs, method = run_ydl({"skip_download": True, "ignore_no_formats_error": True}, meta_and_subs)
    page_url = info.get("webpage_url") or url
    if not segs:
        stem = CACHE_DIR / key

        def download(ydl):
            info2 = ydl.extract_info(url, download=True)
            reqs = info2.get("requested_downloads") or [{}]
            return Path(reqs[0].get("filepath") or ydl.prepare_filename(info2))

        audio = run_ydl({"format": "bestaudio/best", "outtmpl": str(stem) + ".%(ext)s", "noprogress": True}, download)
        say("没有字幕，正在用语音识别转写（大约需要视频时长的五分之一；第一次会先下载约 1.6GB 的识别模型）…")
        segs = transcribe(audio)
        audio.unlink(missing_ok=True)
        method = "Whisper 转写"
    data = {
        "kind": "视频", "title": info.get("title") or url, "author": info.get("uploader") or "",
        "duration": info.get("duration") or media_duration(segs), "source": page_url,
        "method": method, "segments": segs,
    }
    cache_save(key, data)
    return data


def process_file(path: Path) -> dict:
    st = path.stat()
    key = cache_key("file", f"{path.name}|{st.st_size}|{st.st_mtime}")
    cached = cache_load(key)
    if cached:
        return cached
    ext = path.suffix.lower()
    if ext == ".pdf":
        pages = extract_pdf(path)
        data = {"kind": "PDF", "title": path.stem, "source": path.name, "method": "文字提取",
                "pages": pages, "length": f"{len(pages)} 页"}
    elif ext == ".pptx":
        slides = extract_pptx(path)
        data = {"kind": "PPT", "title": path.stem, "source": path.name, "method": "文字提取",
                "pages": slides, "length": f"{len(slides)} 张"}
    else:
        say("正在用语音识别转写（大约需要时长的五分之一；第一次会先下载约 1.6GB 的识别模型）…")
        segs = transcribe(path)
        data = {"kind": "视频/音频", "title": path.stem, "source": path.name, "method": "Whisper 转写",
                "duration": media_duration(segs), "segments": segs}
    cache_save(key, data)
    return data


def item_length(it: dict) -> str:
    if it.get("length"):
        return it["length"]
    return fmt_ts(it.get("duration") or 0)


def item_body(it: dict, cc=None) -> str:
    if "segments" in it:
        base = it["source"] if str(it.get("source", "")).startswith("http") else None
        return format_segments(it["segments"], base, cc) or "（没有识别到语音）"
    return format_pages(it.get("pages", []), "p." if it["kind"] == "PDF" else "slide ")


def toc_lines(items: list[dict]) -> list[str]:
    lines = ["| 编号 | 类型 | 标题 | 长度 | 文字来源 |", "|---|---|---|---|---|"]
    for i, it in enumerate(items, 1):
        title = it["title"].replace("|", "/")
        lines.append(f"| S{i} | {it['kind']} | {title} | {item_length(it)} | {it['method']} |")
    return lines


def item_lines(i: int, it: dict, cc=None, level: str = "##") -> list[str]:
    lines = [f"{level} S{i}｜{it['title']}", ""]
    if str(it.get("source", "")).startswith("http"):
        lines.append(f"- 链接：{it['source']}")
    else:
        lines.append(f"- 文件：{it['source']}")
    if it.get("author"):
        lines.append(f"- 作者/频道：{it['author']}")
    lines.append(f"- 长度：{item_length(it)}")
    lines.append(f"- 文字来源：{it['method']}")
    return lines + ["", item_body(it, cc)]


def failed_lines(failed: list[tuple[str, str]]) -> list[str]:
    if not failed:
        return []
    return ["", "---", "", "## 没处理成功的", ""] + [f"- {src}：{why}" for src, why in failed]


def build_markdown(items: list[dict], failed: list[tuple[str, str]], cc=None, name: str = "") -> str:
    """全部原文合并成一个文件（适合直接上传到 NotebookLM）。"""
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    lines = [
        f"{OWN_MARK}（{len(items)} 份材料，{now}）",
        "",
        *([f"课程 / 名称：{name}", ""] if name else []),
        "视频文字来自字幕或语音识别，可能有识别错误；PDF / PPT 是提取出来的文字。",
        "",
        "## 材料目录",
        "",
        *toc_lines(items),
        "",
        "---",
    ]
    for i, it in enumerate(items, 1):
        lines += [""] + item_lines(i, it, cc)
    lines += failed_lines(failed)
    return "\n".join(lines).strip() + "\n"


def safe_name(title: str, limit: int = 60) -> str:
    name = re.sub(r'[\\/:*?"<>|\n\r\t]+', " ", title).strip(" .")
    return re.sub(r"\s+", " ", name)[:limit].strip() or "材料"


# ---------------- 自动线索：不用 AI，按关键词标出值得回看的位置 ----------------
EMPHASIS_RE = re.compile(
    r"\b(on the (exam|midterm|final|test|quiz)|will be on|(very|really|super|most) important|importantly|"
    r"remember (this|that)|key (point|idea|insight|concept|takeaway|thing|lesson)|make sure (you|to)|don'?t forget|"
    r"crucial|critical(ly)?|the (main|big|central) (point|idea|lesson|takeaway)|you (need|have) to (know|understand|remember)|"
    r"pay attention|bottom line|take ?away|i want you to (know|understand|remember))\b"
    r"|重点|考试|会考|必考|务必|一定要(记|会|掌握|注意)|记住|划重点|易错|常考|核心(概念|思想)",
    re.I,
)
VISUAL_RE = re.compile(
    r"\b(look at|as you can see|you can see|on the board|(this|that|the) (graph|diagram|figure|curve|picture|chart|slide|table)|"
    r"let me (draw|write|show)|let'?s (draw|graph)|i'?ll draw|i'?m going to draw|draw(ing)? (a|the|this)|"
    r"shown here|over here|right here|this point here|up here|down here)\b"
    r"|看这里|看这个|这张图|如图|图上|图中|板书|画一下|画个|画出|这条线|这个点|黑板",
    re.I,
)


def _snippet(text: str, m: re.Match, width: int = 90) -> str:
    a, b = max(0, m.start() - width), min(len(text), m.end() + width)
    s = text[a:b].replace("\n", " ").strip()
    return ("…" if a > 0 else "") + s + ("…" if b < len(text) else "")


def scan_cues(items: list[dict], cc=None) -> str:
    """生成「自动线索.md」：老师的强调用语、需要看画面的时刻。纯关键词匹配，不做判断。"""
    out = [
        "# 自动线索",
        "",
        "程序按关键词标出的位置，**没有经过 AI 或人的判断**，会有误报和漏报。它的用处是提示从哪里看起：",
        "",
        "- **强调**：老师说了 important、on the exam、remember、重点、会考 之类的话",
        "- **看画面**：老师在指着板书、图表或幻灯片讲，文字稿里看不到画面内容",
        "",
    ]
    total = 0
    for i, it in enumerate(items, 1):
        emph, vis = [], []
        if "segments" in it:
            base = it["source"] if str(it.get("source", "")).startswith("http") else None
            for st, text in segment_paragraphs(it["segments"], cc):
                where = time_link(base, st)
                m = EMPHASIS_RE.search(text)
                if m:
                    emph.append(f"- {where} {_snippet(text, m)}")
                m = VISUAL_RE.search(text)
                if m:
                    vis.append(f"- {where} {_snippet(text, m)}")
        else:
            unit = "p." if it["kind"] == "PDF" else "slide "
            for pg in it.get("pages", []):
                m = EMPHASIS_RE.search(pg.get("text") or "")
                if m:
                    emph.append(f"- {unit}{pg['n']} {_snippet(pg['text'], m)}")
        out += [f"## S{i}｜{it['title']}", ""]
        if not emph and not vis:
            out += ["没有命中关键词。", ""]
            continue
        total += len(emph) + len(vis)
        if emph:
            out += [f"**强调（{len(emph)} 处）**", "", *emph, ""]
        if vis:
            out += [f"**看画面（{len(vis)} 处）**", "", *vis, ""]
    out.insert(2, f"共 {total} 处。")
    out.insert(3, "")
    return "\n".join(out).strip() + "\n"


# ---------------- 复习包：一个文件夹，三份产出 ----------------
def write_pack(items: list[dict], failed: list[tuple[str, str]], folder: Path, cc=None, name: str = "") -> Path:
    name = name or folder.name
    raw, review, guide = folder / SEC_RAW, folder / SEC_REVIEW, folder / SEC_GUIDE
    for d in (raw, review, guide):
        d.mkdir(parents=True, exist_ok=True)
    width = max(2, len(str(len(items))))
    meta = []
    for i, it in enumerate(items, 1):
        fname = f"S{i:0{width}d}_{safe_name(it['title'])}.md"
        (raw / fname).write_text("\n".join(item_lines(i, it, cc, "#")).strip() + "\n", "utf-8")
        meta.append({"sid": f"S{i}", "title": it["title"], "kind": it["kind"], "length": item_length(it),
                     "method": it["method"], "source": it.get("source", ""), "file": fname})
    (folder / MERGED_FILE).write_text(build_markdown(items, failed, cc, name), "utf-8")
    (guide / CUES_FILE).write_text(scan_cues(items, cc), "utf-8")
    info = {
        "name": name, "group": "", "pinned": False, "archived": False,
        "created": datetime.now().isoformat(timespec="minutes"), "version": VERSION,
        "items": meta, "failed": [{"source": a, "why": b} for a, b in failed],
    }
    (folder / TASK_FILE).write_text(task_text(info), "utf-8")
    (folder / "pack.json").write_text(json.dumps(info, ensure_ascii=False, indent=1), "utf-8")
    return folder


def task_text(meta: dict) -> str:
    rows = ["| No. | Type | Title | Length | Text source | File |", "|---|---|---|---|---|---|"]
    for it in meta.get("items", []):
        title = str(it["title"]).replace("|", "/")
        rows.append(f"| {it['sid']} | {it['kind']} | {title} | {it['length']} | {it['method']} | `{SEC_RAW}/{it['file']}` |")
    if meta.get("failed"):
        rows += ["", "Not extracted (ignore these):", ""] + [f"- {f['source']}: {f['why']}" for f in meta["failed"]]
    return AI_TASK.format(name=meta.get("name", ""), toc="\n".join(rows))


def new_pack_dir(name: str = "") -> Path:
    base = f"{safe_name(name, 40) if name else '复习包'}_{datetime.now():%m%d_%H%M}"
    folder, n = OUT_DIR / base, 2
    while folder.exists():
        folder, n = OUT_DIR / f"{base}_{n}", n + 1
    return folder


# ---------------- 收集输入、逐份处理 ----------------
def list_inputs() -> tuple[list[Path], list[tuple[str, str]]]:
    files, skipped = [], []
    for p in sorted(IN_DIR.iterdir()):
        if not p.is_file() or p.name.startswith("."):
            continue
        ext = p.suffix.lower()
        if ext in MEDIA_EXT or ext in DOC_EXT:
            files.append(p)
        elif ext in CONVERT_HINT:
            skipped.append((p.name, f"暂不支持这种格式，请导出为 {CONVERT_HINT[ext]} 后再放进来"))
        else:
            skipped.append((p.name, "不支持这种格式"))
    return files, skipped


class PrintReporter:
    """命令行模式：把进度打印出来。"""

    def plan(self, labels: list[str]) -> None:
        self.total = len(labels)
        self.labels = labels

    def start(self, i: int) -> None:
        print(f"[{i + 1}/{self.total}] {self.labels[i]}", flush=True)

    def ok(self, i: int, label: str, detail: str) -> None:
        print(f"     ✓ {label[:40]}（{detail}）", flush=True)

    def fail(self, i: int, why: str) -> None:
        print(f"     ✗ 失败：{why[:150]}", flush=True)

    def note(self, msg: str) -> None:
        print(f"     {msg}", flush=True)

    def cancelled(self) -> bool:
        return False


def process_all(urls: list[str], files: list[Path], skipped: list[tuple[str, str]], rep) -> tuple[list[dict], list[tuple[str, str]]]:
    """展开播放列表，逐份处理链接和文件。返回（成功的材料，失败清单）。"""
    items: list[dict] = []
    failed: list[tuple[str, str]] = list(skipped)
    expanded: list[str] = []
    for u in urls:
        try:
            got = expand_url(u)
            if len(got) > 1:
                rep.note(f"播放列表展开为 {len(got)} 个视频")
            expanded += got
        except Exception as e:
            failed.append((u, f"无法读取：{str(e)[:150]}"))
    seen: set[str] = set()
    expanded = [u for u in expanded if not (u in seen or seen.add(u))]

    rep.plan(expanded + [p.name for p in files])
    idx = -1
    for u in expanded:
        idx += 1
        if rep.cancelled():
            break
        rep.start(idx)
        try:
            it = process_online(u)
            items.append(it)
            rep.ok(idx, it["title"], f"{item_length(it)}，{it['method']}")
        except KeyboardInterrupt:
            print("\n已取消，先输出已完成的部分。")
            return items, failed
        except Exception as e:
            rep.fail(idx, str(e))
            failed.append((u, str(e)[:200]))

    DONE_DIR.mkdir(parents=True, exist_ok=True)
    for p in files:
        idx += 1
        if rep.cancelled():
            break
        rep.start(idx)
        try:
            it = process_file(p)
            items.append(it)
            shutil.move(str(p), DONE_DIR / p.name)
            rep.ok(idx, it["title"], f"{item_length(it)}，{it['method']}")
        except KeyboardInterrupt:
            print("\n已取消，先输出已完成的部分。")
            return items, failed
        except Exception as e:
            rep.fail(idx, str(e))
            failed.append((p.name, str(e)[:200]))
    return items, failed


# ---------------- 命令行模式 ----------------
def _more_pending(timeout: float = 0.4) -> bool:
    try:
        import select

        r, _, _ = select.select([sys.stdin], [], [], timeout)
        return bool(r)
    except Exception:
        return False


def read_links() -> tuple[str, bool]:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if args and Path(args[0]).exists():
        return Path(args[0]).read_text("utf-8"), False
    clip = ""
    if shutil.which("pbpaste"):
        clip = subprocess.run(["pbpaste"], capture_output=True, text=True).stdout
    if OWN_MARK in clip:
        print("（剪贴板里是上次生成的复习包，不把它当链接用。）")
        clip = ""
    if extract_urls(clip):
        return clip, False
    files_waiting = any(p.is_file() and not p.name.startswith(".") for p in IN_DIR.iterdir())
    print("剪贴板里没有链接。" + ("（「输入」文件夹里有文件，直接按回车也可以开始）" if files_waiting else ""))
    print("👉 把 YouTube 链接粘贴到这里（可以一次贴很多条），贴完按回车。")
    print("👉 看到「已收到 N 条」后，再按一次回车就开始。")
    lines: list[str] = []
    while True:
        try:
            line = input()
        except EOFError:
            break
        if not line.strip():
            if (extract_urls("\n".join(lines)) or files_waiting) and not _more_pending():
                break
            continue
        lines.append(line)
        if not _more_pending(0.15):
            print(f"   ✓ 已收到 {len(extract_urls(chr(10).join(lines)))} 条链接。继续粘贴，或直接按回车开始。")
    return "\n".join(lines), True


def main_cli() -> None:
    text, confirmed = read_links()
    urls = extract_urls(text)
    files, skipped = list_inputs()
    if not urls and not files:
        print("\n没有找到链接，「输入」文件夹里也没有可处理的文件。")
        for name, why in skipped:
            print(f"  - {name}：{why}")
        return

    def show(urls_: list[str]) -> None:
        print(f"\n识别到 {len(urls_)} 条链接、{len(files)} 个文件：")
        for u in urls_[:5]:
            print(f"   · {u[:100]}")
        if len(urls_) > 5:
            print(f"   · ……另外 {len(urls_) - 5} 条")
        for p in files[:5]:
            print(f"   · 文件：{p.name}")

    show(urls)
    if not confirmed:
        try:
            extra = input("👉 没问题就按回车开始；要换链接，直接在这里粘贴新链接再回车（Ctrl+C 取消）：")
        except EOFError:
            extra = ""
        new = extract_urls(extra)
        if new:
            urls = new  # 这一步粘贴了链接，就以新粘贴的为准
            show(urls)

    t0 = time.time()
    items, failed = process_all(urls, files, skipped, PrintReporter())
    if not items:
        print("\n没有成功处理的材料。")
        for src, why in failed:
            print(f"  - {src}：{why}")
        return
    folder = write_pack(items, failed, new_pack_dir(), get_converter())
    print("\n" + "=" * 40)
    print(f"完成：{len(items)} 份成功，{len(failed)} 份失败，用时 {(time.time() - t0) / 60:.1f} 分钟")
    print(f"复习包：{folder}")
    print(f"下一步：让你的 AI 打开这个文件夹，按「{TASK_FILE}」生成复习文档和精读指引。")
    if shutil.which("open"):
        subprocess.run(["open", str(folder)])


# ---------------- 界面模式：本机网页 ----------------
class Job:
    """一次提取任务。界面每秒来取一次 snapshot()。"""

    def __init__(self, name: str):
        self.id = uuid.uuid4().hex[:8]
        self.name = name
        self.status = "running"  # running / done / failed / cancelled
        self.items: list[dict] = []
        self.notes: list[str] = []
        self.pack: str | None = None
        self.error = ""
        self.t0 = time.time()
        self.t1: float | None = None
        self._cancel = False
        self._cur: int | None = None
        self._lock = threading.Lock()

    def plan(self, labels: list[str]) -> None:
        with self._lock:
            self.items = [{"label": x, "status": "wait", "detail": ""} for x in labels]

    def start(self, i: int) -> None:
        with self._lock:
            self._cur = i
            self.items[i]["status"] = "run"

    def ok(self, i: int, label: str, detail: str) -> None:
        with self._lock:
            self.items[i].update(status="ok", label=label, detail=detail)
            self._cur = None

    def fail(self, i: int, why: str) -> None:
        with self._lock:
            self.items[i].update(status="fail", detail=why[:300])
            self._cur = None

    def note(self, msg: str) -> None:
        with self._lock:
            if self._cur is not None:
                self.items[self._cur]["detail"] = msg
            else:
                self.notes = (self.notes + [msg])[-6:]

    def cancelled(self) -> bool:
        return self._cancel

    def snapshot(self) -> dict:
        with self._lock:
            return {
                "id": self.id, "name": self.name, "status": self.status, "items": [dict(x) for x in self.items],
                "notes": list(self.notes), "pack": self.pack, "error": self.error, "cancelling": self._cancel,
                "elapsed": int((self.t1 or time.time()) - self.t0),
            }


_job: Job | None = None
_job_lock = threading.Lock()


def _run_job(job: Job, urls: list[str]) -> None:
    global _reporter
    _reporter = job
    try:
        files, skipped = list_inputs()
        items, failed = process_all(urls, files, skipped, job)
        if items:
            folder = write_pack(items, failed, new_pack_dir(job.name), get_converter(), job.name)
            job.pack = folder.name
            job.status = "cancelled" if job.cancelled() else "done"
        else:
            job.status = "cancelled" if job.cancelled() else "failed"
            job.error = "没有一份材料处理成功。" + ("" if not failed else f"第一条原因：{failed[0][1]}")
    except Exception as e:  # 兜底：界面上要能看到出了什么事
        job.status = "failed"
        job.error = f"{type(e).__name__}: {str(e)[:300]}"
    finally:
        job.t1 = time.time()
        _reporter = None


def start_job(text: str, name: str) -> tuple[Job | None, str]:
    global _job
    with _job_lock:
        if _job and _job.status == "running":
            return None, "上一批还在处理，等它结束再开始。"
        urls = extract_urls(text)
        files, _ = list_inputs()
        if not urls and not files:
            return None, "还没有材料。粘贴链接，或者拖入文件。"
        _job = Job(name.strip())
        threading.Thread(target=_run_job, args=(_job, urls), daemon=True).start()
        return _job, ""


def pack_dir(pid: str) -> Path:
    root = OUT_DIR.resolve()
    p = (root / pid).resolve()
    if p.parent != root or not (p / "pack.json").is_file():
        raise FileNotFoundError(pid)
    return p


def pack_file(pid: str, rel: str) -> Path:
    base = pack_dir(pid)
    f = (base / rel).resolve()
    if base not in f.parents or f.suffix != ".md" or not f.is_file():
        raise FileNotFoundError(rel)
    return f


def _md_title(f: Path) -> str:
    try:
        with f.open(encoding="utf-8") as fh:
            for line in fh:
                if line.startswith("#"):
                    return line.lstrip("# ").strip()
    except Exception:
        pass
    return f.stem


def _section_files(base: Path, sec: str) -> list[dict]:
    d = base / sec
    if not d.is_dir():
        return []
    return [{"file": f"{sec}/{f.name}", "name": f.name, "title": _md_title(f), "auto": f.name == CUES_FILE}
            for f in sorted(d.glob("*.md"))]


def read_meta(base: Path) -> dict:
    return json.loads((base / "pack.json").read_text("utf-8"))


def pack_info(pid: str, full: bool = True) -> dict:
    base = pack_dir(pid)
    meta = read_meta(base)
    items = meta.get("items", [])
    names = {it["file"] for it in items}
    have = {sec: {f.name for f in (base / sec).glob("*.md")} if (base / sec).is_dir() else set()
            for sec in (SEC_REVIEW, SEC_GUIDE)}
    info = {"id": pid, "name": meta.get("name") or pid, "group": meta.get("group", ""),
            "pinned": bool(meta.get("pinned")), "archived": bool(meta.get("archived")),
            "created": meta.get("created", ""), "n_items": len(items),
            "n_review": len(have[SEC_REVIEW] & names), "n_guide": len(have[SEC_GUIDE] & names)}
    if not full:
        return info
    task = base / TASK_FILE  # 写作要求跟着程序版本走：旧复习包打开时自动换成最新的
    want = task_text(meta)
    if not task.exists() or task.read_text("utf-8") != want:
        task.write_text(want, "utf-8")
    extras = []
    for sec, kind in ((SEC_REVIEW, "review"), (SEC_GUIDE, "guide")):
        for f in sorted((base / sec).glob("*.md")) if (base / sec).is_dir() else []:
            if f.name not in names:
                extras.append({"file": f"{sec}/{f.name}", "title": _md_title(f), "kind": kind, "auto": f.name == CUES_FILE})
    merged = base / MERGED_FILE
    info.update(
        path=str(base), failed=meta.get("failed", []), extras=extras,
        items=[dict(it, has_review=it["file"] in have[SEC_REVIEW], has_guide=it["file"] in have[SEC_GUIDE]) for it in items],
        merged_chars=merged.stat().st_size if merged.exists() else 0,
        sections={"raw": SEC_RAW, "review": SEC_REVIEW, "guide": SEC_GUIDE}, task_file=TASK_FILE, merged_file=MERGED_FILE)
    return info


def update_pack(pid: str, changes: dict) -> dict:
    """改名、分组、置顶、归档。归档只是打个标记，文件不动。"""
    base = pack_dir(pid)
    meta = read_meta(base)
    if isinstance(changes.get("name"), str) and changes["name"].strip():
        meta["name"] = changes["name"].strip()[:80]
    if isinstance(changes.get("group"), str):
        meta["group"] = changes["group"].strip()[:40]
    for key in ("pinned", "archived"):
        if isinstance(changes.get(key), bool):
            meta[key] = changes[key]
    (base / "pack.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1), "utf-8")
    return pack_info(pid, full=False)


def list_packs() -> list[dict]:
    out = []
    if OUT_DIR.is_dir():
        for d in OUT_DIR.iterdir():
            if d.is_dir() and (d / "pack.json").is_file():
                try:
                    out.append(pack_info(d.name, full=False))
                except Exception:
                    continue
    return sorted(out, key=lambda x: x["created"], reverse=True)


# ---------------- 删除复习包 / 废纸篓 ----------------
# 删除只是把整个文件夹移进「输出/废纸篓」，放满 7 天才真正删掉，这之前随时能恢复。
# 这是温故唯一会真正删除文件的地方，而且只删用户自己在界面上删掉的复习包。
TRASH_DAYS = 7
TRASH_INFO = ".删除信息.json"   # 放在被删的复习包文件夹里：原来的文件夹名和删除时间


def trash_root() -> Path:
    return OUT_DIR / "废纸篓"


def _free_name(folder: Path) -> Path:
    base, n = folder, 2
    while folder.exists():
        folder, n = base.with_name(f"{base.name}_{n}"), n + 1
    return folder


def trash_dir(tid: str) -> Path:
    root = trash_root().resolve()
    p = (root / tid).resolve()
    if p.parent != root or not (p / "pack.json").is_file():
        raise FileNotFoundError(tid)
    return p


def _trash_info(d: Path) -> dict:
    try:
        info = json.loads((d / TRASH_INFO).read_text("utf-8"))
        return {"name": str(info["name"]), "deleted_at": float(info["deleted_at"])}
    except Exception:  # 说明文件丢了：按文件夹的修改时间算
        return {"name": d.name, "deleted_at": d.stat().st_mtime}


def delete_pack(pid: str) -> str:
    base = pack_dir(pid)
    trash_root().mkdir(parents=True, exist_ok=True)
    dest = _free_name(trash_root() / base.name)
    shutil.move(str(base), str(dest))
    (dest / TRASH_INFO).write_text(json.dumps({"name": base.name, "deleted_at": time.time()}, ensure_ascii=False), "utf-8")
    return dest.name


def restore_pack(tid: str) -> str:
    src = trash_dir(tid)
    name = Path(_trash_info(src)["name"]).name
    if not name or name.startswith(".") or name == trash_root().name:
        name = src.name
    dest = _free_name(OUT_DIR / name)
    (src / TRASH_INFO).unlink(missing_ok=True)
    shutil.move(str(src), str(dest))
    return dest.name


def _trashed() -> list[Path]:
    root = trash_root()
    return [d for d in root.iterdir() if d.is_dir() and (d / "pack.json").is_file()] if root.is_dir() else []


def purge_trash(tid: str = "", everything: bool = False, now: float | None = None) -> int:
    """彻底删除：指定的一个、全部，或者（都不指定时）放满 7 天的。返回删了几个。"""
    if tid:
        shutil.rmtree(trash_dir(tid))
        return 1
    now = time.time() if now is None else now
    gone = 0
    for d in _trashed():
        if everything or now - _trash_info(d)["deleted_at"] >= TRASH_DAYS * 86400:
            shutil.rmtree(d, ignore_errors=True)
            gone += 1
    return gone


def list_trash(now: float | None = None) -> list[dict]:
    now = time.time() if now is None else now
    purge_trash(now=now)
    out = []
    for d in _trashed():
        info = _trash_info(d)
        try:
            meta = read_meta(d)
        except Exception:
            meta = {}
        left = TRASH_DAYS * 86400 - (now - info["deleted_at"])
        out.append({"id": d.name, "name": meta.get("name") or info["name"], "n_items": len(meta.get("items", [])),
                    "deleted_at": datetime.fromtimestamp(info["deleted_at"]).isoformat(timespec="minutes"),
                    "days_left": max(1, math.ceil(left / 86400)), "_t": info["deleted_at"]})
    out.sort(key=lambda x: x["_t"], reverse=True)
    for x in out:
        del x["_t"]
    return out


_purged_at = 0.0


def trash_count() -> int:
    """给侧栏显示数量；顺便每 10 分钟清一次到期的（温故一直开着时也会按时清）。"""
    global _purged_at
    if time.time() - _purged_at > 600:
        _purged_at = time.time()
        purge_trash()
    return len(_trashed())


MATH_RE = re.compile(
    r"(?<!\\)\$\$(.+?)(?<!\\)\$\$"                                              # $$ … $$
    r"|\\\[(.+?)\\\]"                                                           # \[ … \]
    r"|\\\((.+?)\\\)"                                                           # \( … \)
    r"|(?<![\\$\w])\$(?=[^\s$])((?:\\.|[^$\\\n])+?)(?<=[^\s\\])\$(?![\d$])",    # $ … $（"$3 和 $5" 这种金额不算）
    re.S,
)


def render_md(text: str, math: bool = False) -> str:
    """Markdown → HTML。math=True 时把 LaTeX 公式原样留给页面上的 KaTeX 去排版。"""
    import html
    import markdown

    stash: list[str] = []

    def keep(m: re.Match) -> str:
        display = m.group(1) is not None or m.group(2) is not None
        tex = next(g for g in m.groups() if g is not None).strip()
        cls = "math math-d" if display else "math"
        stash.append(f'<span class="{cls}">{html.escape(tex)}</span>')
        return f"WGMATHX{len(stash) - 1}XEND"

    if math:
        text = MATH_RE.sub(keep, text)
    text = re.sub(r"<(?=[a-zA-Z/!?])", "&lt;", text)  # AI 写的文档里不允许夹带 HTML
    body = markdown.markdown(text, extensions=["tables", "fenced_code", "sane_lists"])
    body = re.sub(r"WGMATHX(\d+)XEND", lambda m: stash[int(m.group(1))], body)
    return body.replace("<a href=", '<a target="_blank" rel="noopener" href=')


def save_ai_doc(pid: str, section: str, sid: str, text: str) -> str:
    """把用户从网页版 AI 复制回来的内容存进复习包。"""
    base = pack_dir(pid)
    sec = {"review": SEC_REVIEW, "guide": SEC_GUIDE}[section]
    meta = read_meta(base)
    names = {it["sid"]: it["file"] for it in meta.get("items", [])}
    special = {"review": "00_总览.md", "guide": "00_学习路线.md"}
    fname = names.get(sid) or (special[section] if sid == "00" else None)
    if not fname or not text.strip():
        raise ValueError("缺少内容或材料编号")
    (base / sec).mkdir(exist_ok=True)
    (base / sec / fname).write_text(text.strip() + "\n", "utf-8")
    return f"{sec}/{fname}"


def make_handler(port: int):
    from http.server import BaseHTTPRequestHandler
    from urllib.parse import parse_qs, unquote, urlparse

    hosts = {f"127.0.0.1:{port}", f"localhost:{port}"}

    class Handler(BaseHTTPRequestHandler):
        # HTTP/1.0：每个请求用完就断开，本机之间没有性能问题，也不会有连接被占住的情况

        def log_message(self, *a):
            pass

        def _send(self, code: int, body: bytes, ctype: str) -> None:
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def _json(self, obj, code: int = 200) -> None:
            self._send(code, json.dumps(obj, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")

        def _guard(self, post: bool = False) -> bool:
            # 只接受本机浏览器对本页面的请求：挡掉别的网站借浏览器发来的请求
            if self.headers.get("Host") not in hosts or (post and self.headers.get("X-Wengu") != "1"):
                self._json({"error": "forbidden"}, 403)
                return False
            return True

        def do_GET(self):
            if not self._guard():
                return
            u = urlparse(self.path)
            q = {k: v[0] for k, v in parse_qs(u.query).items()}
            try:
                if u.path == "/":
                    self._send(200, (ROOT / "ui.html").read_bytes(), "text/html; charset=utf-8")
                elif u.path.startswith("/vendor/"):
                    base = (ROOT / "vendor").resolve()
                    f = (base / unquote(u.path[len("/vendor/"):])).resolve()
                    ctype = {".js": "text/javascript", ".css": "text/css", ".woff2": "font/woff2"}.get(f.suffix)
                    if base not in f.parents or not f.is_file() or not ctype:
                        raise FileNotFoundError(u.path)
                    self.send_response(200)
                    self.send_header("Content-Type", ctype)
                    self.send_header("Content-Length", str(f.stat().st_size))
                    self.send_header("Cache-Control", "max-age=86400")
                    self.end_headers()
                    self.wfile.write(f.read_bytes())
                elif u.path == "/favicon.ico":
                    self._send(204, b"", "image/x-icon")
                elif u.path == "/api/ping":
                    self._json({"app": "wengu", "version": VERSION})
                elif u.path == "/api/state":
                    files, skipped = list_inputs()
                    self._json({
                        "version": VERSION,
                        "inputs": [{"name": p.name, "size": p.stat().st_size, "ok": True} for p in files]
                                  + [{"name": n, "size": 0, "ok": False, "why": w} for n, w in skipped],
                        "job": _job.snapshot() if _job else None,
                        "packs": list_packs(),
                        "trash": trash_count(),
                    })
                elif u.path == "/api/pack":
                    self._json(pack_info(q.get("id", "")))
                elif u.path == "/api/trash":
                    self._json({"days": TRASH_DAYS, "items": list_trash()})
                elif u.path == "/api/doc":
                    f = pack_file(q.get("pack", ""), q.get("path", ""))
                    text = f.read_text("utf-8")
                    ai_written = f.parent.name in (SEC_REVIEW, SEC_GUIDE) and f.name != CUES_FILE
                    self._json({"title": _md_title(f), "html": render_md(text, math=ai_written), "text": text})
                else:
                    self._json({"error": "not found"}, 404)
            except (FileNotFoundError, KeyError):
                self._json({"error": "找不到这个文件，可能已经被移动或删除。"}, 404)
            except Exception as e:
                self._json({"error": str(e)[:300]}, 500)

        def do_POST(self):
            if not self._guard(post=True):
                return
            u = urlparse(self.path)
            q = {k: v[0] for k, v in parse_qs(u.query).items()}
            n = int(self.headers.get("Content-Length") or 0)
            try:
                if u.path == "/api/upload":
                    name = Path(unquote(q.get("name", ""))).name.strip()
                    if not name or name.startswith("."):
                        raise ValueError("文件名无效")
                    dest = IN_DIR / name
                    with dest.open("wb") as fh:
                        left = n
                        while left > 0:
                            chunk = self.rfile.read(min(left, 1 << 20))
                            if not chunk:
                                break
                            fh.write(chunk)
                            left -= len(chunk)
                    self._json({"ok": True, "name": name})
                    return
                body = json.loads(self.rfile.read(n) or b"{}")
                if u.path == "/api/start":
                    job, err = start_job(body.get("text", ""), body.get("name", ""))
                    self._json({"ok": bool(job), "error": err}, 200 if job else 400)
                elif u.path == "/api/cancel":
                    if _job and _job.status == "running":
                        _job._cancel = True
                    self._json({"ok": True})
                elif u.path == "/api/remove_input":
                    f = IN_DIR / Path(body.get("name", "")).name
                    if f.is_file() and f.parent == IN_DIR:
                        DONE_DIR.mkdir(parents=True, exist_ok=True)
                        shutil.move(str(f), DONE_DIR / f.name)  # 不删除，移到「已处理」
                    self._json({"ok": True})
                elif u.path == "/api/reveal":
                    target = pack_dir(body.get("pack", ""))
                    sub = body.get("sub", "")
                    if sub in (SEC_RAW, SEC_REVIEW, SEC_GUIDE):
                        target = target / sub
                    if shutil.which("open"):
                        subprocess.run(["open", str(target)])
                    self._json({"ok": True, "path": str(target)})
                elif u.path == "/api/pack_update":
                    self._json({"ok": True, "pack": update_pack(body.get("id", ""), body)})
                elif u.path == "/api/pack_delete":
                    self._json({"ok": True, "trash_id": delete_pack(body.get("id", ""))})
                elif u.path == "/api/trash_restore":
                    self._json({"ok": True, "pack": restore_pack(body.get("id", ""))})
                elif u.path == "/api/trash_purge":
                    if body.get("all") is True:
                        self._json({"ok": True, "gone": purge_trash(everything=True)})
                    elif body.get("id"):
                        self._json({"ok": True, "gone": purge_trash(tid=str(body["id"]))})
                    else:
                        raise FileNotFoundError("")
                elif u.path == "/api/save_doc":
                    rel = save_ai_doc(body.get("pack", ""), body.get("section", ""), body.get("sid", ""), body.get("text", ""))
                    self._json({"ok": True, "file": rel})
                elif u.path == "/api/quit":
                    self._json({"ok": True})
                    threading.Thread(target=self.server.shutdown, daemon=True).start()
                else:
                    self._json({"error": "not found"}, 404)
            except (FileNotFoundError, KeyError):
                self._json({"error": "找不到这个复习包，可能已经被移动或删除。"}, 404)
            except Exception as e:
                self._json({"error": str(e)[:300]}, 400)

    return Handler


def serve(open_browser: bool = True) -> None:
    import webbrowser
    from http.server import ThreadingHTTPServer
    from urllib.request import urlopen

    url = f"http://127.0.0.1:{PORT}/"
    try:  # 已经开着就不再开第二个，直接把页面调出来
        with urlopen(url + "api/ping", timeout=1) as r:
            if json.loads(r.read()).get("app") == "wengu":
                print("温故已经在运行，正在打开页面…")
                if open_browser:
                    webbrowser.open(url)
                return
    except Exception:
        pass
    try:
        httpd = ThreadingHTTPServer(("127.0.0.1", PORT), make_handler(PORT))
    except OSError:
        print(f"端口 {PORT} 被别的程序占用了。关掉占用它的程序，或者重启电脑后再试。")
        return
    print("=" * 46)
    print(f"  温故已启动：{url}")
    print("  浏览器会自动打开。用的时候别关这个窗口；")
    print("  用完在页面上点「退出温故」，或直接关掉这个窗口。")
    print("=" * 46, flush=True)
    if open_browser:
        threading.Timer(0.6, lambda: webbrowser.open(url)).start()
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()
        print("\n温故已退出，可以关闭这个窗口。")


def main() -> None:
    for d in (IN_DIR, OUT_DIR, CACHE_DIR):
        d.mkdir(parents=True, exist_ok=True)
    purge_trash()  # 废纸篓里放满 7 天的复习包
    setup_tools()
    if "--cli" in sys.argv:
        main_cli()
    else:
        serve(open_browser="--no-browser" not in sys.argv)


if __name__ == "__main__":
    main()
