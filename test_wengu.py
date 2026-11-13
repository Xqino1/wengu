"""温故的离线测试（不联网、不需要 Whisper）。
运行：uv run --with pytest --with pypdf --with python-pptx --with fpdf2 --with opencc-python-reimplemented pytest -q
"""
import json
import re

import wengu as w


def test_extract_urls():
    text = "看这个 https://www.youtube.com/watch?v=abc123，还有 https://youtu.be/xyz?si=1 和重复 https://www.youtube.com/watch?v=abc123"
    assert w.extract_urls(text) == ["https://www.youtube.com/watch?v=abc123", "https://youtu.be/xyz"]


def test_extract_urls_drops_timestamps_and_dedupes():
    md = ("[00:05](https://www.youtube.com/watch?v=Q7-mCKOzNUI&t=5s) 文字 "
          "[01:10](https://www.youtube.com/watch?v=Q7-mCKOzNUI&t=70s) "
          "https://www.youtube.com/watch_videos?video_ids=a%2Cb%2Cc&type=0")
    urls = w.extract_urls(md)
    assert urls[0] == "https://www.youtube.com/watch?v=Q7-mCKOzNUI"
    assert len(urls) == 2
    assert w.split_watch_videos(urls[1]) == [f"https://www.youtube.com/watch?v={v}" for v in "abc"]
    assert w.normalize_url("https://example.com/a?t=5") == "https://example.com/a?t=5"


def test_clipboard_with_own_review_pack_is_ignored(monkeypatch, tmp_path, capsys):
    pack = w.build_markdown([], [])
    assert w.OWN_MARK in pack

    class R:
        stdout = pack + "\n[00:05](https://www.youtube.com/watch?v=abc&t=5s)"

    monkeypatch.setattr(w.shutil, "which", lambda name: "/usr/bin/" + name)
    monkeypatch.setattr(w.subprocess, "run", lambda *a, **k: R())
    monkeypatch.setattr(w, "IN_DIR", tmp_path)
    monkeypatch.setattr(w.sys, "argv", ["wengu.py"])
    inputs = iter(["https://www.youtube.com/watch?v=new1", ""])
    monkeypatch.setattr("builtins.input", lambda *a: next(inputs))
    monkeypatch.setattr(w, "_more_pending", lambda *a, **k: False)
    text, confirmed = w.read_links()
    assert confirmed and w.extract_urls(text) == ["https://www.youtube.com/watch?v=new1"]
    assert "上次生成的复习包" in capsys.readouterr().out


def test_time_link():
    assert w.time_link("https://www.youtube.com/watch?v=abc", 754) == "[12:34](https://www.youtube.com/watch?v=abc&t=754s)"
    assert w.time_link("https://youtu.be/abc", 65) == "[01:05](https://youtu.be/abc?t=65)"
    assert w.time_link(None, 3700) == "[1:01:40]"


def test_parse_json3_auto_captions():
    data = {"events": [
        {"tStartMs": 0, "dDurationMs": 3000, "segs": [{"utf8": "today we"}, {"utf8": " talk about"}]},
        {"tStartMs": 1500, "aAppend": 1, "segs": [{"utf8": "\n"}]},
        {"tStartMs": 3000, "dDurationMs": 2000, "segs": [{"utf8": "enzyme kinetics"}]},
        {"tStartMs": 5000, "dDurationMs": 100},
    ]}
    segs = w.parse_json3(data)
    assert [s["text"] for s in segs] == ["today we talk about", "enzyme kinetics"]
    assert segs[1]["start"] == 3.0


def test_parse_vtt_rolling_duplicates():
    vtt = """WEBVTT

00:00:00.000 --> 00:00:02.000
today we <00:00:01.000><c>talk</c>

00:00:02.000 --> 00:00:04.000
today we talk
about enzyme &amp; kinetics

00:01:02.500 --> 00:01:04.000
about enzyme &amp; kinetics
this will be on the exam
"""
    segs = w.parse_vtt(vtt)
    assert [s["text"] for s in segs] == ["today we talk", "about enzyme & kinetics", "this will be on the exam"]
    assert segs[-1]["start"] == 62.5


def _tracks(url, ext="json3"):
    return [{"ext": ext, "url": url}]


def test_pick_subtitle_prefers_manual_then_original_auto():
    info = {"language": "en",
            "subtitles": {"live_chat": [{"ext": "json", "url": "x"}], "en": [{"ext": "vtt", "url": "manual-vtt"}, {"ext": "json3", "url": "manual-json3"}]},
            "automatic_captions": {"en-orig": _tracks("auto")}}
    kind, fmt = w.pick_subtitle(info)
    assert kind == "人工字幕（英语）" and fmt["url"] == "manual-json3"

    info2 = {"language": "en", "subtitles": {},
             "automatic_captions": {"fr": _tracks("translated"), "en-orig": _tracks("orig", "vtt")}}
    kind, fmt = w.pick_subtitle(info2)
    assert kind == "自动字幕（英语）" and fmt["url"] == "orig"

    assert w.pick_subtitle({"subtitles": {}, "automatic_captions": {}}) is None


def test_english_podcast_with_only_japanese_manual_subtitles_uses_english():
    # 11 月 13 日的 bug：英语播客只有日语人工字幕（给日本学生的翻译），旧版拿了日语
    info = {"language": None, "subtitles": {"ja": _tracks("ja-manual")},
            "automatic_captions": {"ja": _tracks("ja-translated"), "en-orig": _tracks("en-asr"), "en": _tracks("en-asr2")}}
    kind, fmt = w.pick_subtitle(info)
    assert kind == "自动字幕（英语）" and fmt["url"] == "en-asr"


def test_spoken_language_beats_what_the_uploader_labelled():
    # 视频标成日语，但语音识别听出来是英语：按声音来
    info = {"language": "ja", "subtitles": {"ja": _tracks("ja"), "en-GB": _tracks("en-gb"), "en": _tracks("en")},
            "automatic_captions": {"en-orig": _tracks("asr")}}
    kind, fmt = w.pick_subtitle(info)
    assert kind == "人工字幕（英语）" and fmt["url"] == "en"  # "en" 排在 "en-GB" 前面


def test_label_only_language_is_trusted_for_matching_tracks():
    info = {"language": "zh-CN", "subtitles": {"en": _tracks("en"), "zh-Hans": _tracks("zh")}, "automatic_captions": {}}
    kind, fmt = w.pick_subtitle(info)
    assert kind == "人工字幕（中文）" and fmt["url"] == "zh"
    # 标的是英语、只有日语人工字幕、没有语音识别：不拿翻译，交给语音识别
    assert w.pick_subtitle({"language": "en", "subtitles": {"ja": _tracks("ja")}, "automatic_captions": {}}) is None


def test_unknown_language_goes_to_speech_recognition_instead_of_guessing():
    info = {"subtitles": {"en": _tracks("en"), "ja": _tracks("ja")}, "automatic_captions": {}}
    assert w.spoken_language(info) == ""
    assert w.pick_subtitle(info) is None


def test_old_subtitle_cache_is_refetched_but_whisper_cache_is_kept(tmp_path, monkeypatch):
    monkeypatch.setattr(w, "CACHE_DIR", tmp_path)

    def ydl_called(*a, **k):
        raise RuntimeError("重新取了")

    monkeypatch.setattr(w, "run_ydl", ydl_called)
    url_old, url_asr, url_new = (f"https://www.youtube.com/watch?v={v}" for v in ("old", "asr", "new"))
    w.cache_save(w.cache_key("url", url_old), {"method": "人工字幕", "segments": [{"text": "こんにちは"}]})
    w.cache_save(w.cache_key("url", url_asr), {"method": "Whisper 转写", "segments": []})
    w.cache_save(w.cache_key("url", url_new), {"method": "人工字幕（英语）", "segments": []})
    try:
        w.process_online(url_old)
        raise AssertionError("旧缓存应该作废")
    except RuntimeError as e:
        assert "重新取了" in str(e)
    assert w.process_online(url_asr)["method"] == "Whisper 转写"
    assert w.process_online(url_new)["method"] == "人工字幕（英语）"


def test_format_segments_english_and_chinese():
    en = [{"start": 0, "end": 2, "text": "today we talk"}, {"start": 2, "end": 4, "text": "about enzymes"},
          {"start": 10, "end": 12, "text": "this will be on the exam"}]
    out = w.format_segments(en, "https://www.youtube.com/watch?v=abc")
    assert out.splitlines()[0] == "[00:00](https://www.youtube.com/watch?v=abc&t=0s) today we talk about enzymes."
    assert "[00:10](https://www.youtube.com/watch?v=abc&t=10s) this will be on the exam." in out

    cc = w.get_converter()
    zh = [{"start": 0, "end": 2, "text": "今天我們講"}, {"start": 2, "end": 3, "text": "酶動力學"},
          {"start": 3, "end": 4, "text": "点个关注" + "注" * 30}]
    out = w.format_segments(zh, None, cc)
    assert out.startswith("[00:00] 今天")
    assert "注注注注注注" not in out
    if cc:
        assert "酶动力学" in out


def test_paragraphs_break_at_sentence_end_and_drop_sound_tags():
    segs = [{"start": 0, "end": 1, "text": "[SQUEAKING] [RUSTLING] [CLICKING]"},
            {"start": 1, "end": 2, "text": "."}]
    words = "we write down the underlying"
    for k in range(30):  # 一句很长、中间没有句号的话
        segs.append({"start": 2 + k, "end": 3 + k, "text": f"{words} {k}"})
    segs.append({"start": 33, "end": 34, "text": "assumptions about preferences."})
    segs.append({"start": 34, "end": 35, "text": "Next point [LAUGHTER] here."})
    out = w.format_segments(segs, None)
    assert "SQUEAKING" not in out and "LAUGHTER" not in out
    assert not out.startswith("[00:00] .")
    paras = out.split("\n\n")
    assert len(paras) >= 2  # 太长时仍然会硬断段
    assert all(not re.search(r"underlying \d+\.$", p) for p in paras)  # 但不会在句子中间硬塞句号
    assert any(p.endswith("assumptions about preferences.") or "preferences. Next point here." in p for p in paras)


ITEMS = [
    {"kind": "视频", "title": "Lec 1: Intro/Supply & Demand?", "duration": 60,
     "source": "https://www.youtube.com/watch?v=a", "method": "人工字幕",
     "segments": [{"start": 0, "end": 2, "text": "Hello class."},
                  {"start": 30, "end": 33, "text": "This will be on the exam, so remember this."},
                  {"start": 50, "end": 53, "text": "As you can see on the board, this curve shifts."}]},
    {"kind": "PDF", "title": "notes", "source": "notes.pdf", "method": "文字提取", "length": "1 页",
     "pages": [{"n": 1, "text": "glycolysis is very important"}]},
]


def test_write_pack(tmp_path):
    folder = w.write_pack(ITEMS, [("x.ppt", "暂不支持")], tmp_path / "pack", None, "ECON 101")
    assert sorted(p.name for p in folder.iterdir()) == [
        "1_原文全文", "2_复习文档", "3_精读指引", "pack.json", "原文全文_合并版.md", "给AI的任务.md"]
    raw = sorted(p.name for p in (folder / "1_原文全文").iterdir())
    assert raw == ["S01_Lec 1 Intro Supply & Demand.md", "S02_notes.md"]
    lec = (folder / "1_原文全文" / raw[0]).read_text("utf-8")
    assert lec.startswith("# S1｜Lec 1") and "[00:00](https://www.youtube.com/watch?v=a&t=0s)" in lec
    task = (folder / "给AI的任务.md").read_text("utf-8")
    assert "ECON 101" in task and "2_复习文档" in task and "3_精读指引" in task and "x.ppt" in task
    assert "| S1 | 视频 |" in task and "{name}" not in task and "{toc}" not in task
    assert "Math in LaTeX" in task and "Output language" in task
    meta = json.loads((folder / "pack.json").read_text("utf-8"))
    assert [i["sid"] for i in meta["items"]] == ["S1", "S2"] and meta["failed"][0]["source"] == "x.ppt"
    assert w.OWN_MARK in (folder / "原文全文_合并版.md").read_text("utf-8")
    assert list((folder / "2_复习文档").iterdir()) == []


def test_scan_cues_marks_emphasis_and_visual_moments():
    cues = w.scan_cues(ITEMS)
    assert "共 3 处" in cues
    assert "[00:30](https://www.youtube.com/watch?v=a&t=30s)" in cues and "on the exam" in cues
    assert "[00:50](https://www.youtube.com/watch?v=a&t=50s)" in cues and "on the board" in cues
    assert "p.1" in cues and "very important" in cues
    assert "没有经过 AI 或人的判断" in cues


def _pack(tmp_path, monkeypatch):
    monkeypatch.setattr(w, "OUT_DIR", tmp_path)
    return w.write_pack(ITEMS, [], tmp_path / "p1", None, "课")


def test_pack_info_and_path_safety(tmp_path, monkeypatch):
    folder = _pack(tmp_path, monkeypatch)
    info = w.pack_info("p1")
    assert info["name"] == "课" and info["n_items"] == 2 and info["n_review"] == 0 and info["n_guide"] == 0
    assert [(e["kind"], e["auto"]) for e in info["extras"]] == [("guide", True)]
    assert [(i["has_review"], i["has_guide"]) for i in info["items"]] == [(False, False)] * 2
    assert w.list_packs()[0]["id"] == "p1"
    assert w.pack_file("p1", "1_原文全文/S02_notes.md").name == "S02_notes.md"
    (tmp_path / "secret.md").write_text("x", "utf-8")
    for bad in ("../secret.md", "pack.json", "1_原文全文/nope.md"):
        try:
            w.pack_file("p1", bad)
            assert False, bad
        except FileNotFoundError:
            pass
    for bad in ("..", "p1/1_原文全文", "nope"):
        try:
            w.pack_dir(bad)
            assert False, bad
        except FileNotFoundError:
            pass
    assert folder.exists()


def test_save_ai_doc_and_render(tmp_path, monkeypatch):
    _pack(tmp_path, monkeypatch)
    rel = w.save_ai_doc("p1", "review", "S2", "# S2 复习文档\n\n要点 S2 p.1")
    assert rel == "2_复习文档/S02_notes.md"
    assert w.save_ai_doc("p1", "guide", "00", "# 学习路线") == "3_精读指引/00_学习路线.md"
    info = w.pack_info("p1")
    assert info["n_review"] == 1 and info["n_guide"] == 0
    assert [i["has_review"] for i in info["items"]] == [False, True]
    assert {e["file"] for e in info["extras"]} == {"3_精读指引/00_学习路线.md", "3_精读指引/自动线索.md"}
    for args in (("review", "S9", "x"), ("review", "S1", "  ")):
        try:
            w.save_ai_doc("p1", *args)
            assert False
        except ValueError:
            pass
    html = w.render_md("[12:34](https://www.youtube.com/watch?v=a&t=754s) text <script>alert(1)</script>\n\n| a | b |\n|---|---|\n| 1 | 2 |")
    assert 'target="_blank"' in html and "<script>" not in html and "<table>" in html


def test_render_md_math_is_preserved_for_katex_and_money_is_not_math():
    src = ("MRS is $-\\frac{MU_x}{MU_y}$ and a_b_c stays.\n\n$$\nU(x, y) = \\sqrt{x \\cdot y}\n$$\n\n"
           "It costs $3 today and $5 tomorrow. Escaped \\$7. Also \\(a<b\\).")
    html = w.render_md(src, math=True)
    assert '<span class="math">-\\frac{MU_x}{MU_y}</span>' in html            # 下划线没被当成斜体
    assert '<span class="math math-d">U(x, y) = \\sqrt{x \\cdot y}</span>' in html
    assert '<span class="math">a&lt;b</span>' in html
    assert "$3 today and $5 tomorrow" in html and html.count('class="math') == 3
    assert "math" not in w.render_md("price is $3 and $x$ here", math=False)  # 原文全文不做公式排版


def test_update_pack_and_task_refresh(tmp_path, monkeypatch):
    folder = _pack(tmp_path, monkeypatch)
    (folder / "给AI的任务.md").write_text("旧版任务说明", "utf-8")
    info = w.update_pack("p1", {"name": " ECON 101 ", "group": "大一上", "pinned": True, "archived": "yes"})
    assert info["name"] == "ECON 101" and info["group"] == "大一上" and info["pinned"] is True and info["archived"] is False
    w.update_pack("p1", {"archived": True, "name": "  "})
    full = w.pack_info("p1")
    assert full["archived"] is True and full["name"] == "ECON 101" and (folder / "1_原文全文").is_dir()
    task = (folder / "给AI的任务.md").read_text("utf-8")          # 打开旧复习包时，任务说明自动换成最新的
    assert "ECON 101" in task and "Math in LaTeX" in task and "`1_原文全文/S02_notes.md`" in task


def test_process_all_with_job_reporter(tmp_path, monkeypatch):
    from fpdf import FPDF

    for name in ("IN_DIR", "OUT_DIR", "CACHE_DIR"):
        d = tmp_path / name
        d.mkdir()
        monkeypatch.setattr(w, name, d)
    monkeypatch.setattr(w, "DONE_DIR", w.IN_DIR / "已处理")
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Helvetica", size=12)
    pdf.cell(0, 10, "Marginal cost equals marginal revenue")
    pdf.output(str(w.IN_DIR / "handout.pdf"))
    (w.IN_DIR / "old.key").write_text("x")
    files, skipped = w.list_inputs()
    assert [p.name for p in files] == ["handout.pdf"] and skipped[0][0] == "old.key"

    def boom(url):
        raise RuntimeError("视频不存在")

    monkeypatch.setattr(w, "process_online", boom)
    monkeypatch.setattr(w, "expand_url", lambda u: [u])
    job = w.Job("课")
    items, failed = w.process_all(["https://www.youtube.com/watch?v=zzz"], files, skipped, job)
    snap = job.snapshot()
    assert [i["status"] for i in snap["items"]] == ["fail", "ok"]
    assert snap["items"][1]["label"] == "handout" and "1 页" in snap["items"][1]["detail"]
    assert len(items) == 1 and {f[0] for f in failed} == {"old.key", "https://www.youtube.com/watch?v=zzz"}
    assert (w.DONE_DIR / "handout.pdf").exists()


def test_server_rejects_foreign_requests_and_serves_state(tmp_path, monkeypatch):
    import threading
    import urllib.error
    import urllib.request
    from http.server import ThreadingHTTPServer

    for name in ("IN_DIR", "OUT_DIR", "CACHE_DIR"):
        d = tmp_path / name
        d.mkdir()
        monkeypatch.setattr(w, name, d)
    monkeypatch.setattr(w, "DONE_DIR", w.IN_DIR / "已处理")
    monkeypatch.setattr(w, "_job", None)
    w.write_pack(ITEMS, [], w.OUT_DIR / "p1", None, "课")
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), None)
    port = httpd.server_address[1]
    httpd.RequestHandlerClass = w.make_handler(port)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{port}"

    def call(path, data=None, headers=None):
        req = urllib.request.Request(base + path, data=data, headers=headers or {})
        try:
            with urllib.request.urlopen(req, timeout=5) as r:
                return r.status, json.loads(r.read())
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read())

    try:
        code, st = call("/api/state")
        assert code == 200 and st["packs"][0]["id"] == "p1" and st["job"] is None
        assert call("/api/state", headers={"Host": "evil.example"})[0] == 403          # DNS 重绑定
        assert call("/api/start", data=b"{}")[0] == 403                                # 别的网站发来的 POST
        code, body = call("/api/start", data=b'{"text": ""}', headers={"X-Wengu": "1"})
        assert code == 400 and "还没有材料" in body["error"]
        code, body = call("/api/upload?name=..%2F..%2Fevil.pdf", data=b"%PDF", headers={"X-Wengu": "1"})
        assert code == 200 and (w.IN_DIR / "evil.pdf").exists() and not (tmp_path / "evil.pdf").exists()
        code, doc = call("/api/doc?pack=p1&path=3_%E7%B2%BE%E8%AF%BB%E6%8C%87%E5%BC%95/%E8%87%AA%E5%8A%A8%E7%BA%BF%E7%B4%A2.md")
        assert code == 200 and "自动线索" in doc["title"]
        assert call("/api/doc?pack=p1&path=../p1/pack.json")[0] == 404
        code, body = call("/api/pack_update", data='{"id": "p1", "pinned": true}'.encode(), headers={"X-Wengu": "1"})
        assert code == 200 and body["pack"]["pinned"] is True
        assert call("/vendor/../wengu.py")[0] == 404 and call("/vendor/nope.js")[0] == 404
    finally:
        httpd.shutdown()
        httpd.server_close()


def test_extract_pptx(tmp_path):
    from pptx import Presentation
    from pptx.util import Inches

    prs = Presentation()
    s1 = prs.slides.add_slide(prs.slide_layouts[1])
    s1.shapes.title.text = "Enzyme Kinetics"
    s1.placeholders[1].text = "Michaelis-Menten equation"
    s1.notes_slide.notes_text_frame.text = "Will be on midterm"
    s2 = prs.slides.add_slide(prs.slide_layouts[5])
    tbl = s2.shapes.add_table(2, 2, Inches(1), Inches(2), Inches(4), Inches(1)).table
    tbl.cell(0, 0).text, tbl.cell(0, 1).text = "Km", "Vmax"
    p = tmp_path / "lecture.pptx"
    prs.save(p)

    slides = w.extract_pptx(p)
    assert slides[0]["n"] == 1 and "Michaelis-Menten" in slides[0]["text"]
    assert slides[0]["notes"] == "Will be on midterm"
    assert "Km | Vmax" in slides[1]["text"]
    body = w.format_pages(slides, "slide ")
    assert "### slide 1" in body and "> 演讲者备注：Will be on midterm" in body


def test_extract_pdf(tmp_path):
    from fpdf import FPDF

    pdf = FPDF()
    pdf.set_font("Helvetica", size=12)
    pdf.add_page()
    pdf.cell(0, 10, "Page one: glycolysis")
    pdf.add_page()  # 空白页
    p = tmp_path / "notes.pdf"
    pdf.output(str(p))

    pages = w.extract_pdf(p)
    assert len(pages) == 2 and "glycolysis" in pages[0]["text"] and pages[1]["text"] == ""
    body = w.format_pages(pages, "p.")
    assert "### p.1" in body and "可能是图片或扫描件" in body


def test_build_markdown():
    items = [
        {"kind": "视频", "title": "Lecture 3 | Enzymes", "author": "Prof X", "duration": 3125,
         "source": "https://www.youtube.com/watch?v=abc", "method": "自动字幕",
         "segments": [{"start": 0, "end": 2, "text": "hello class"}]},
        {"kind": "PDF", "title": "notes", "source": "notes.pdf", "method": "文字提取", "length": "2 页",
         "pages": [{"n": 1, "text": "glycolysis"}, {"n": 2, "text": ""}]},
    ]
    md = w.build_markdown(items, [("old.ppt", "暂不支持这种格式")])
    assert "| S1 | 视频 | Lecture 3 / Enzymes | 52:05 | 自动字幕 |" in md
    assert "## S2｜notes" in md and "### p.1" in md
    assert "## 没处理成功的" in md and "old.ppt" in md
    assert md.startswith(w.OWN_MARK) and "## 材料目录" in md


def test_split_watch_videos():
    url = ("https://www.youtube.com/watch_videos?video_ids=8ssjKR7nNck%2CuuY13aUtFUo%2C-Z35m38qLd4"
           "&type=0&title=MIT+14.01")
    assert w.split_watch_videos(url) == [
        "https://www.youtube.com/watch?v=8ssjKR7nNck",
        "https://www.youtube.com/watch?v=uuY13aUtFUo",
        "https://www.youtube.com/watch?v=-Z35m38qLd4",
    ]
    assert w.split_watch_videos("https://www.youtube.com/watch?v=abc") is None


def test_run_ydl_retries_with_browser_cookies(monkeypatch):
    import yt_dlp

    calls = []

    class FakeYDL:
        def __init__(self, opts):
            self.opts = opts

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def extract_info(self, url, download=False):
            browser = (self.opts.get("cookiesfrombrowser") or (None,))[0]
            calls.append(browser)
            if browser is None or browser == "chrome":
                raise Exception("ERROR: Sign in to confirm you're not a bot")
            if browser == "safari":
                raise Exception("ERROR: [Errno 1] Operation not permitted: Cookies.binarycookies")
            return {"title": "ok", "via": browser}

    monkeypatch.setattr(yt_dlp, "YoutubeDL", FakeYDL)
    monkeypatch.setattr(w, "_cookie_browser", None)
    monkeypatch.setattr(w, "BROWSERS", ["chrome", "safari", "edge"])
    info = w.run_ydl({}, lambda ydl: ydl.extract_info("u"))
    assert info["via"] == "edge" and calls == [None, "chrome", "safari", "edge"]
    # 第二次直接用记住的浏览器
    info = w.run_ydl({}, lambda ydl: ydl.extract_info("u"))
    assert calls[-1] == "edge"


def test_run_ydl_other_errors_not_retried(monkeypatch):
    import pytest
    import yt_dlp

    class FakeYDL:
        def __init__(self, opts):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def extract_info(self, url, download=False):
            raise Exception("Video unavailable")

    monkeypatch.setattr(yt_dlp, "YoutubeDL", FakeYDL)
    monkeypatch.setattr(w, "_cookie_browser", None)
    with pytest.raises(Exception, match="Video unavailable"):
        w.run_ydl({}, lambda ydl: ydl.extract_info("u"))


def test_run_ydl_cookie_ok_but_other_error_is_reported(monkeypatch):
    """Chrome 已通过人机验证，但缺 Deno 拿不到格式：要记住 Chrome，并给出装 Deno 的提示，而不是继续试别的浏览器。"""
    import pytest
    import yt_dlp

    calls = []

    class FakeYDL:
        def __init__(self, opts):
            self.opts = opts

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def extract_info(self, url, download=False):
            browser = (self.opts.get("cookiesfrombrowser") or (None,))[0]
            calls.append(browser)
            if browser is None:
                raise Exception("ERROR: Sign in to confirm you're not a bot")
            raise Exception("ERROR: [youtube] x: Requested format is not available")

    monkeypatch.setattr(yt_dlp, "YoutubeDL", FakeYDL)
    monkeypatch.setattr(w, "_cookie_browser", None)
    monkeypatch.setattr(w, "BROWSERS", ["chrome", "safari"])
    with pytest.raises(RuntimeError, match="下载音频时 YouTube 的验证没通过"):
        w.run_ydl({}, lambda ydl: ydl.extract_info("u"))
    assert calls == [None, "chrome"] and w._cookie_browser == "chrome"


UI = (w.ROOT / "ui.html").read_text("utf-8")


def test_ui_only_calls_routes_the_server_has():
    src = (w.ROOT / "wengu.py").read_text("utf-8")
    routes = set(re.findall(r'"(/api/[a-z_]+)', UI)) | set(re.findall(r"`(/api/[a-z_]+)", UI))
    assert routes and all(f'"{r}"' in src for r in routes), sorted(r for r in routes if f'"{r}"' not in src)


def test_ui_works_offline():
    # 界面不依赖任何外部资源：样式、脚本、字体都在本机
    assert not re.search(r"""(?:src|href)=["']https?://|@import|url\(\s*["']?https?://""", UI)
    assert 'href="/vendor/katex/katex.min.css"' in UI and 'src="/vendor/katex/katex.min.js"' in UI


def test_ui_colours_and_fonts_go_through_tokens():
    # 颜色和字体只在开头的变量里写一次，深色 / 护眼模式才不会漏掉哪一处
    css = UI[UI.index("<style>"):UI.index("</style>")]
    rules = css[css.index("*,*::before"):]
    assert not re.search(r"#[0-9a-fA-F]{3,8}\b|rgba?\(", rules)
    assert not re.search(r"font-family:(?!\s*(?:var\(|inherit))", rules)
    assert "transition:all" not in css.replace(" ", "")


def test_ui_expects_this_version():
    # 页面每次请求现读，程序要重启才换新；页面靠这个版本号发现"程序还是旧的"，所以两边必须一起改
    assert re.search(r'const WANT = "([^"]+)"', UI).group(1) == w.VERSION


# ---------------- 桌面 / 程序坞图标（温故.app）----------------
import os
import plistlib
import socket
import subprocess
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread


APP = w.ROOT / "温故.app"
LAUNCHER = APP / "Contents" / "MacOS" / "wengu"


def test_app_bundle_is_well_formed():
    info = plistlib.loads((APP / "Contents" / "Info.plist").read_bytes())
    assert APP / "Contents" / "MacOS" / info["CFBundleExecutable"] == LAUNCHER
    assert os.access(LAUNCHER, os.X_OK)
    assert info["CFBundlePackageType"] == "APPL"
    assert info["CFBundleShortVersionString"] == w.VERSION
    icon = APP / "Contents" / "Resources" / (info["CFBundleIconFile"] + ".icns")
    assert icon.read_bytes()[:4] == b"icns"
    install = (w.ROOT / "install.sh").read_text("utf-8")
    assert info["CFBundleIdentifier"] in install
    for f in (LAUNCHER, w.ROOT / "install.sh", w.ROOT / "温故.command"):
        subprocess.run(["bash", "-n", str(f)], check=True)


def _free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


PING_SERVER = """
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer
class H(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200); self.end_headers(); self.wfile.write(b'{"app": "wengu"}')
    def log_message(self, *a): pass
HTTPServer(("127.0.0.1", int(sys.argv[1])), H).serve_forever()
"""

UV_MODES = {
    "serve": 'echo $$ > "$FAKE_PID"; exec python3 -c "$FAKE_SERVER" "$FAKE_PORT"\n',
    "die": 'echo "端口 8737 被别的程序占用了。关掉占用它的程序，或者重启电脑后再试。"; exit 1\n',
    "slow": 'echo $$ > "$FAKE_PID"; exec sleep 30\n',
}


def _run_launcher(tmp_path, uv_mode="serve", wait="20", button="", has_wengu=True):
    """在假的 macOS 环境里跑图标启动器：open / osascript / uv 都换成记录调用的替身。"""
    home = tmp_path / "home"
    (home / "温故").mkdir(parents=True)
    if has_wengu:
        (home / "温故" / "wengu.py").write_text("")
    fakes = home / ".local" / "bin"  # 启动器会把它放在 PATH 最前面
    fakes.mkdir(parents=True)
    calls = tmp_path / "calls.txt"
    calls.write_text("")
    for name, body in {
        "open": 'echo "open $*" >> "$FAKE_CALLS"\n',
        "osascript": 'cat >/dev/null; echo "osascript $*" >> "$FAKE_CALLS"; echo "$FAKE_BUTTON"\n',
        "uv": 'echo "uv $*" >> "$FAKE_CALLS"\n' + UV_MODES[uv_mode],
    }.items():
        (fakes / name).write_text("#!/bin/bash\n" + body)
        (fakes / name).chmod(0o755)
    port = _free_port()
    env = {k: v for k, v in os.environ.items() if "proxy" not in k.lower()}
    env.update(HOME=str(home), WENGU_URL=f"http://127.0.0.1:{port}/", WENGU_WAIT=wait,
               FAKE_CALLS=str(calls), FAKE_PID=str(tmp_path / "pid"), FAKE_PORT=str(port),
               FAKE_SERVER=PING_SERVER, FAKE_BUTTON=button)
    return env, port, calls, home


def _kill(tmp_path):
    pid = tmp_path / "pid"
    if pid.exists():
        try:
            os.kill(int(pid.read_text()), 9)
        except ProcessLookupError:
            pass


def test_launcher_opens_page_when_already_running(tmp_path):
    env, port, calls, _ = _run_launcher(tmp_path)

    class H(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b'{"app": "wengu"}')

        def log_message(self, *a):
            pass

    srv = ThreadingHTTPServer(("127.0.0.1", port), H)
    Thread(target=srv.serve_forever, daemon=True).start()
    try:
        r = subprocess.run(["bash", str(LAUNCHER)], env=env, timeout=20)
    finally:
        srv.shutdown()
    assert r.returncode == 0
    assert calls.read_text().split("\n")[0] == f"open http://127.0.0.1:{port}/"
    assert "uv " not in calls.read_text()


def test_launcher_starts_wengu_in_background(tmp_path):
    env, port, calls, home = _run_launcher(tmp_path, "serve")
    try:
        t = time.time()
        r = subprocess.run(["bash", str(LAUNCHER)], env=env, timeout=30)
        assert r.returncode == 0 and time.time() - t < 15
        log = calls.read_text()
        assert "uv run --quiet -P yt-dlp wengu.py" in log
        assert "open " not in log and "osascript" not in log  # 页面由温故自己打开，不弹窗
        assert (home / "温故" / ".cache" / "启动记录.txt").exists()
    finally:
        _kill(tmp_path)


def test_launcher_explains_why_it_could_not_start(tmp_path):
    env, _, calls, home = _run_launcher(tmp_path, "die", button="用终端打开")
    r = subprocess.run(["bash", str(LAUNCHER)], env=env, timeout=30)
    log = calls.read_text()
    assert r.returncode == 1
    assert "uv run --quiet --offline wengu.py" in log  # 联网更新失败会改用现有版本再试一次
    assert "温故没能打开" in log and "端口 8737 被别的程序占用了" in log
    assert f"open -a Terminal {home}/温故/温故.command" in log


def test_launcher_tells_you_when_first_start_is_slow(tmp_path):
    env, _, calls, _ = _run_launcher(tmp_path, "slow", wait="2")
    try:
        r = subprocess.run(["bash", str(LAUNCHER)], env=env, timeout=30)
        assert r.returncode == 0
        assert "温故正在准备" in calls.read_text()
    finally:
        _kill(tmp_path)


def test_launcher_without_wengu_says_to_reinstall(tmp_path):
    env, _, calls, _ = _run_launcher(tmp_path, has_wengu=False)
    r = subprocess.run(["bash", str(LAUNCHER)], env=env, timeout=20)
    assert r.returncode == 1
    assert "找不到温故" in calls.read_text()
    assert "uv " not in calls.read_text()


# ---------------- 一行安装 / 更新（install.sh）----------------
import tarfile


class FakeMac:
    """在假的 macOS 里跑 install.sh：下载换成本地打包的源码，uv / defaults / open / 本机温故 等换成记录调用的替身。"""

    def __init__(self, tmp_path, sys_apps=True):
        self.tmp, self.home = tmp_path, tmp_path / "home"
        self.apps, self.dest = tmp_path / "Applications", tmp_path / "home" / "温故"
        self.calls, self.dock, self.tgz = tmp_path / "calls.txt", tmp_path / "dock.txt", tmp_path / "main.tar.gz"
        fakes = self.home / ".local" / "bin"
        fakes.mkdir(parents=True)
        (self.home / "Desktop").mkdir()
        if sys_apps:
            self.apps.mkdir()
        self.calls.write_text("")
        for name, body in {
            "uname": 'echo Darwin\n',
            "curl": ('case "$*" in *main.tar.gz*) cat "$FAKE_TGZ";; *api/state*) [ -n "$FAKE_STATE" ] && echo "$FAKE_STATE" || exit 7;;'
                     ' *api/quit*) echo "quit" >> "$FAKE_CALLS";; *) echo "curl $*" >> "$FAKE_CALLS"; exit 1;; esac\n'),
            "uv": 'echo "uv $*" >> "$FAKE_CALLS"\n',
            "defaults": 'case "$1" in export) cat "$FAKE_DOCK" 2>/dev/null;; write) echo "$5" >> "$FAKE_DOCK";; esac\n',
            "killall": 'echo "killall $*" >> "$FAKE_CALLS"\n',
            "open": 'echo "open $*" >> "$FAKE_CALLS"\n',
            "ditto": 'mkdir -p "$2" && cp -R "$1/." "$2/"\n',  # ditto 是合并复制
            "sleep": 'true\n',
        }.items():
            (fakes / name).write_text("#!/bin/bash\n" + body)
            (fakes / name).chmod(0o755)
        self.env = {k: v for k, v in os.environ.items() if "proxy" not in k.lower() and k != "CODEX_HOME"}
        self.env.update(HOME=str(self.home), PATH=f"{fakes}:/usr/bin:/bin", WENGU_SYS_APPS=str(self.apps),
                        FAKE_TGZ=str(self.tgz), FAKE_CALLS=str(self.calls), FAKE_DOCK=str(self.dock), FAKE_STATE="")
        self.release()

    def release(self, extra=None, drop=()):
        """把仓库打成 GitHub 那样的压缩包，可以多放或少放几个文件，模拟新旧版本。"""
        skip = {"输入", "输出", ".cache", "__pycache__", ".pytest_cache", ".git"}
        with tarfile.open(self.tgz, "w:gz") as t:
            for p in sorted(w.ROOT.rglob("*")):
                rel = p.relative_to(w.ROOT)
                if not skip & set(rel.parts) and p.is_file() and str(rel) not in drop:
                    t.add(p, f"wengu-main/{rel}")
            for rel, text in (extra or {}).items():
                f = self.tmp / "extra" / rel
                f.parent.mkdir(parents=True, exist_ok=True)
                f.write_text(text)
                t.add(f, f"wengu-main/{rel}")

    def install(self, state="", ok=True):
        self.env["FAKE_STATE"] = state
        r = subprocess.run(["bash", str(w.ROOT / "install.sh")], env=self.env, capture_output=True, text=True, timeout=60)
        assert (r.returncode == 0) == ok, r.stdout + r.stderr
        return r

    def log(self):
        return self.calls.read_text()


def test_install_puts_icon_in_applications_desktop_and_dock(tmp_path):
    mac = FakeMac(tmp_path)
    mac.install()
    app = mac.apps / "温故.app"
    for a in (app, mac.home / "Desktop" / "温故.app"):
        assert os.access(a / "Contents" / "MacOS" / "wengu", os.X_OK)
        assert (a / "Contents" / "Resources" / "AppIcon.icns").exists()
    assert (mac.dest / "wengu.py").exists() and os.access(mac.dest / "温故.command", os.X_OK)
    assert "uv sync --script wengu.py" in mac.log()          # 组件在安装时装好
    assert f"<string>{app}</string>" in mac.dock.read_text() and "killall Dock" in mac.log()
    assert mac.log().strip().endswith(f"open {app}")           # 最后打开的是「应用程序」里那份


def test_install_twice_does_not_add_a_second_dock_icon(tmp_path):
    mac = FakeMac(tmp_path)
    mac.install()
    mac.install()
    assert mac.dock.read_text().count("tile-data") == 1
    assert (mac.apps / "温故.app").exists() and (mac.home / "Desktop" / "温故.app").exists()


def test_install_without_admin_uses_personal_applications(tmp_path):
    mac = FakeMac(tmp_path, sys_apps=False)
    mac.install()
    app = mac.home / "Applications" / "温故.app"
    assert app.exists() and not mac.apps.exists()
    assert f"<string>{app}</string>" in mac.dock.read_text() and mac.log().strip().endswith(f"open {app}")


def test_install_leaves_other_things_on_the_desktop_alone(tmp_path):
    mac = FakeMac(tmp_path)
    mine = mac.home / "Desktop" / "温故.app" / "Contents"
    mine.mkdir(parents=True)
    (mine / "Info.plist").write_text("someone else's app")
    (mac.home / "Desktop" / "温故.command").write_text('#!/bin/bash\nexec "/Users/x/温故/温故.command"\n')
    mac.install()
    assert (mine / "Info.plist").read_text() == "someone else's app"
    assert not (mac.home / "Desktop" / "温故.command").exists()  # 旧版放的启动器换掉了
    assert (mac.apps / "温故.app").exists()


def test_update_removes_old_files_but_not_yours(tmp_path):
    mac = FakeMac(tmp_path)
    mac.release(extra={"旧功能.py": "old", "scripts/旧工具/跑.sh": "old"})
    mac.install()
    assert (mac.dest / "旧功能.py").exists()
    (mac.dest / "我的笔记.md").write_text("mine")
    (mac.dest / "输出" / "某门课").mkdir(parents=True)
    (mac.dest / "输出" / "某门课" / "a.md").write_text("pack")
    (mac.dest / ".cache" / "url_x.json").write_text("{}")
    mac.release()  # 新版没有那两个旧文件
    mac.install()
    assert not (mac.dest / "旧功能.py").exists()
    assert not (mac.dest / "scripts" / "旧工具").exists()       # 删空的文件夹也收掉
    assert (mac.dest / "scripts" / "发布到GitHub.command").exists()
    for kept in ("我的笔记.md", "输出/某门课/a.md", ".cache/url_x.json"):
        assert (mac.dest / kept).exists(), kept
    assert "旧功能.py" not in (mac.dest / ".cache" / "安装清单.txt").read_text()


def test_update_waits_while_wengu_is_extracting(tmp_path):
    mac = FakeMac(tmp_path)
    r = mac.install(state='{"version": "0.4.0", "job": {"status": "running"}}', ok=False)
    assert "正在提取材料" in r.stdout
    assert "quit" not in mac.log() and not mac.dest.exists()


def test_update_closes_running_wengu_then_reopens_it(tmp_path):
    mac = FakeMac(tmp_path)
    mac.install(state='{"version": "0.4.0", "job": {"status": "done"}}')
    log = mac.log().split("\n")
    assert log[0] == "quit" and log[-2] == f"open {mac.apps / '温故.app'}"


def test_install_teaches_codex_to_update(tmp_path):
    mac = FakeMac(tmp_path)
    codex = mac.home / ".codex"
    codex.mkdir()
    (codex / "AGENTS.md").write_text("# 我的规则\n- 说中文\n")
    mac.install()
    mac.install()  # 再装一次也只有一段
    text = (codex / "AGENTS.md").read_text()
    assert text.startswith("# 我的规则\n- 说中文\n\n<!-- 温故：开始")
    assert text.count("<!-- 温故：开始") == 1 and text.count("<!-- 温故：结束 -->") == 1
    assert "「更新温故」" in text and "/wengu/main/install.sh | bash" in text
    # 有 AGENTS.override.md 时 Codex 只读它，所以写进它
    (codex / "AGENTS.override.md").write_text("override\n")
    mac.install()
    assert "「更新温故」" in (codex / "AGENTS.override.md").read_text()


def test_install_without_codex_does_not_create_codex_files(tmp_path):
    mac = FakeMac(tmp_path)
    r = mac.install()
    assert not (mac.home / ".codex").exists() and "更新温故" not in r.stdout


def test_publish_refuses_to_publish_without_the_files_installs_need():
    # 发布脚本原样同步文件夹：少了文件就会从 GitHub 上删掉（11 月 12 日 温故.app 就这样被删过一次）
    script = (w.ROOT / "scripts" / "发布到GitHub.command").read_text("utf-8")
    required = re.search(r"REQUIRED=\(([^)]*)\)", script).group(1).split()
    install = (w.ROOT / "install.sh").read_text("utf-8")
    assert "wengu.py" in required and "温故.app/Contents/MacOS/wengu" in required
    for f in required:
        assert (w.ROOT / f).exists(), f
    assert script.index("REQUIRED=") < script.index("rsync ")
    assert '温故.app/Contents/MacOS/wengu" ]' in install  # 下载不完整就停


# ---------------- 删除复习包 / 7 天废纸篓 ----------------
import pytest


def _make_pack(out, folder, name="课", items=2):
    d = out / folder
    d.mkdir(parents=True)
    (d / "pack.json").write_text(json.dumps({"name": name, "created": "2026-11-13T02:00", "items": [{"sid": f"S{i}", "file": f"S{i}.md"} for i in range(items)]}, ensure_ascii=False))
    (d / "1_原文全文").mkdir()
    (d / "1_原文全文" / "S0.md").write_text("# S0")
    return d


@pytest.fixture
def out(tmp_path, monkeypatch):
    monkeypatch.setattr(w, "OUT_DIR", tmp_path / "输出")
    monkeypatch.setattr(w, "IN_DIR", tmp_path / "输入")
    (tmp_path / "输出").mkdir()
    (tmp_path / "输入").mkdir()
    return tmp_path / "输出"


def test_delete_moves_pack_to_trash_and_restore_brings_it_back(out):
    _make_pack(out, "复习包_1113_0229", "旧版播客", 1)
    tid = w.delete_pack("复习包_1113_0229")
    assert not (out / "复习包_1113_0229").exists()
    assert [p["id"] for p in w.list_packs()] == []                  # 列表里不再出现
    t = w.list_trash()
    assert [(x["id"], x["name"], x["n_items"], x["days_left"]) for x in t] == [(tid, "旧版播客", 1, 7)]
    assert (out / "废纸篓" / tid / "1_原文全文" / "S0.md").read_text() == "# S0"
    pid = w.restore_pack(tid)
    assert pid == "复习包_1113_0229" and (out / pid / "pack.json").exists()
    assert not (out / pid / w.TRASH_INFO).exists() and w.list_trash() == []


def test_restore_does_not_overwrite_a_pack_with_the_same_folder_name(out):
    _make_pack(out, "复习包_1113_0229", "第一个")
    tid = w.delete_pack("复习包_1113_0229")
    _make_pack(out, "复习包_1113_0229", "后来同名的")
    pid = w.restore_pack(tid)
    assert pid == "复习包_1113_0229_2"
    assert {p["name"] for p in w.list_packs()} == {"第一个", "后来同名的"}


def test_deleting_two_packs_with_the_same_name_keeps_both_in_trash(out):
    _make_pack(out, "复习包_1113_0229")
    a = w.delete_pack("复习包_1113_0229")
    _make_pack(out, "复习包_1113_0229")
    b = w.delete_pack("复习包_1113_0229")
    assert a != b and len(w.list_trash()) == 2


def test_trash_empties_itself_after_seven_days(out):
    _make_pack(out, "A")
    _make_pack(out, "B")
    w.delete_pack("A")
    w.delete_pack("B")
    now = time.time()
    info = out / "废纸篓" / "A" / w.TRASH_INFO
    info.write_text(json.dumps({"name": "A", "deleted_at": now - 7 * 86400 - 1}))   # 放满 7 天
    left = w.list_trash(now=now)
    assert [x["id"] for x in left] == ["B"] and not (out / "废纸篓" / "A").exists()
    assert left[0]["days_left"] == 7


def test_purge_one_or_everything_and_nothing_outside_the_trash(out):
    _make_pack(out, "A")
    _make_pack(out, "B")
    _make_pack(out, "C")
    w.delete_pack("A")
    w.delete_pack("B")
    assert w.purge_trash(tid="A") == 1 and [x["id"] for x in w.list_trash()] == ["B"]
    assert w.purge_trash(everything=True) == 1 and w.list_trash() == []
    assert (out / "C" / "pack.json").exists()                          # 没删的复习包不受影响
    for bad in ("..", "../C", "C", "", "废纸篓"):
        with pytest.raises(FileNotFoundError):
            w.trash_dir(bad)
    with pytest.raises(FileNotFoundError):
        w.delete_pack("废纸篓")                                         # 废纸篓本身不是复习包


def test_trash_routes_are_guarded(out):
    import http.client
    port = _free_port()
    srv = ThreadingHTTPServer(("127.0.0.1", port), w.make_handler(port))
    Thread(target=srv.serve_forever, daemon=True).start()
    try:
        _make_pack(out, "A")

        def call(path, body=None, wengu=True):
            c = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
            hdr = {"Host": f"127.0.0.1:{port}"}
            if wengu:
                hdr["X-Wengu"] = "1"
            if body is None:
                c.request("GET", path, headers=hdr)
            else:
                c.request("POST", path, body=json.dumps(body), headers=hdr)
            r = c.getresponse()
            return r.status, json.loads(r.read() or b"{}")

        assert call("/api/pack_delete", {"id": "A"}, wengu=False)[0] == 403   # 别的网站借浏览器发来的请求挡掉
        assert (out / "A").exists()
        st, j = call("/api/pack_delete", {"id": "A"})
        assert st == 200 and j["trash_id"] == "A"
        st, j = call("/api/state")
        assert j["trash"] == 1
        st, j = call("/api/trash")
        assert j["days"] == 7 and [x["id"] for x in j["items"]] == ["A"]
        assert call("/api/trash_purge", {})[0] == 404                        # 没说删哪个：什么都不删
        st, j = call("/api/trash_restore", {"id": "A"})
        assert st == 200 and j["pack"] == "A" and (out / "A" / "pack.json").exists()
    finally:
        srv.shutdown()


def test_pack_lists_the_moments_each_review_cites(out):
    vid = {"kind": "视频", "title": "Lecture 2", "author": "", "duration": 3120, "source": "https://www.youtube.com/watch?v=abcdefgh",
           "method": "人工字幕（英语）", "segments": [{"start": 5, "end": 9, "text": "hi"}]}
    pdf = {"kind": "PDF", "title": "Slides", "length": "12 页", "pages": [{"n": 1, "text": "x"}], "method": "PDF 文字", "source": "slides.pdf"}
    folder = w.new_pack_dir("课")
    w.write_pack([vid, pdf], [], folder, None, "课")
    f = next((folder / w.SEC_RAW).glob("S01_*.md")).name
    (folder / w.SEC_REVIEW / f).write_text("See [02:15](u&t=135) and [10:42](u&t=642), again [02:15](u), late [1:59:59](u), text 03:00 is not a link\n", "utf-8")
    items = w.pack_info(folder.name)["items"]
    assert items[0]["secs"] == 3120 and items[0]["cites"] == [135, 642]   # 去重、排序，超出时长的不算
    assert items[1]["secs"] is None and items[1]["cites"] == []


def test_start_page_lines_come_from_your_own_transcripts(out):
    quotes = w.start_lines()                                                      # 还没有复习包：只有名言，每句都有出处、不重复
    assert len(quotes) >= 100 and all(x["by"] and "id" not in x for x in quotes)
    assert len({x["t"] for x in quotes}) == len(quotes) and "温故而知新，可以为师矣。" in [x["t"] for x in quotes]
    vid = {"kind": "视频", "title": "Lecture", "author": "", "duration": 600, "source": "https://www.youtube.com/watch?v=abcdefgh",
           "method": "人工字幕（英语）", "segments": [{"start": 5 + i * 30, "end": 30 + i * 30,
           "text": f"The standard error shrinks when the sample size number {i} grows. Short. This is the sentence about lecture {i}."} for i in range(20)]}
    base = w.new_pack_dir("课")
    w.write_pack([vid], [], base, None, "课")
    got = w.start_lines()
    lines = [x["t"] for x in got if "id" in x]                                     # 讲稿里的句子排在前面，名言跟在后面
    assert len(lines) >= 12 and all(16 <= len(x) <= 90 for x in lines) and len(got) == len(lines) + len(w.QUOTES)
    hit = next(x for x in got if "number 3 grows" in x["t"])                      # 每句带出处：点开回到原文那一秒
    assert (hit["id"], hit["name"], hit["sid"], hit["at"]) == (base.name, "课", "S1", 95)
    card = next(x for x in w.list_packs() if x["id"] == base.name)                # 复习包库的卡片：目录前几行和进度
    assert card["peek"] == [["S1", "Lecture"]] and card["marks"] == "0"
    assert not any("](" in x or "youtube" in x.lower() or x.startswith(("#", "-")) for x in lines)   # 没有链接、标题、元信息
    assert any("standard error" in x for x in lines) and "Short." not in lines
