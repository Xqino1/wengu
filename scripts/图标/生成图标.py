"""温故图标（开发者用，朋友不需要运行）：一对中文引号「」框住一段话，中间那行被荧光笔划过。

用法：python3 scripts/图标/生成图标.py
  重新生成本文件夹里的三个 SVG，以及 温故.app/Contents/Resources/AppIcon.icns（需要 rsvg-convert 和 Pillow）。

苹果 macOS 图标网格：1024 画布，824 圆角方块居中（边距 100），连续曲率圆角 r=185.4。
方块外不放任何像素（macOS 26 会把出界的图标关进灰框），方块内不透明。"""
import sys

K = (1.52866483, 1.08849323, 0.86840689, 0.02718815, 0.63149399, 0.07491100, 0.37282392, 0.15452442)

def squircle(x, y, w, h, r):
    a, b, c, d, e, f, g, hh = (k * r for k in K)
    X, Y = x + w, y + h
    p = [f"M{x + a:.2f} {y:.2f}", f"L{X - a:.2f} {y:.2f}",
         f"C{X - b:.2f} {y:.2f} {X - c:.2f} {y + d:.2f} {X - e:.2f} {y + f:.2f}",
         f"C{X - g:.2f} {y + hh:.2f} {X - hh:.2f} {y + g:.2f} {X - f:.2f} {y + e:.2f}",
         f"C{X - d:.2f} {y + c:.2f} {X:.2f} {y + b:.2f} {X:.2f} {y + a:.2f}",
         f"L{X:.2f} {Y - a:.2f}",
         f"C{X:.2f} {Y - b:.2f} {X - d:.2f} {Y - c:.2f} {X - f:.2f} {Y - e:.2f}",
         f"C{X - hh:.2f} {Y - g:.2f} {X - g:.2f} {Y - hh:.2f} {X - e:.2f} {Y - f:.2f}",
         f"C{X - c:.2f} {Y - d:.2f} {X - b:.2f} {Y:.2f} {X - a:.2f} {Y:.2f}",
         f"L{x + a:.2f} {Y:.2f}",
         f"C{x + b:.2f} {Y:.2f} {x + c:.2f} {Y - d:.2f} {x + e:.2f} {Y - f:.2f}",
         f"C{x + g:.2f} {Y - hh:.2f} {x + hh:.2f} {Y - g:.2f} {x + f:.2f} {Y - e:.2f}",
         f"C{x + d:.2f} {Y - c:.2f} {x:.2f} {Y - b:.2f} {x:.2f} {Y - a:.2f}",
         f"L{x:.2f} {y + a:.2f}",
         f"C{x:.2f} {y + b:.2f} {x + d:.2f} {y + c:.2f} {x + f:.2f} {y + e:.2f}",
         f"C{x + hh:.2f} {y + g:.2f} {x + g:.2f} {y + hh:.2f} {x + e:.2f} {y + f:.2f}",
         f"C{x + c:.2f} {y + d:.2f} {x + b:.2f} {y:.2f} {x + a:.2f} {y:.2f}Z"]
    return "".join(p)

# 256 网格上的标志（定稿几何）
BR = '<path d="M32 32H96V52H52V96H32Z"/><path d="M224 224H160V204H204V160H224Z"/>'          # 「 」
LINES = '<path d="M76 88H180V104H76Z"/><path d="M76 176H140V192H76Z"/>'                       # 上下两行字
SWIPE = "M88.86 116H184L171.14 164H76Z"                                                   # 荧光笔一划（15°斜口）
MID = "M88 132H168V148H88Z"                                                               # 被划过的那行字
SMALL_SWIPE = "M80.07 104H188L167.93 179H60Z"                                             # 小尺寸版：更粗的一划

def mark_black(small=False):
    """单色版：「」+ 荧光笔一划（被划的字是镂空），小尺寸版去掉上下两行字。"""
    if small:
        return BR + f'<path fill-rule="evenodd" d="{SMALL_SWIPE} M92 134H156V150H92Z"/>'
    return BR + LINES + f'<path fill-rule="evenodd" d="{SWIPE} {MID}"/>'

def icon(small=False):
    """白底圆角方块（像温故的阅读页），墨色字，只有被引用的那行用荧光黄。"""
    t = squircle(100, 100, 824, 824, 185.4)
    k = 2.9 if small else 2.55
    ox, oy = 512 - 128 * k, 512 - 128 * k - 6
    if small:  # 16/32px：去掉上下两行字，荧光笔一划加粗
        g = (f'<g fill="#1D1D1F">{BR}</g><path fill="url(#h)" d="{SMALL_SWIPE}"/>'
             '<path fill="#1D1D1F" d="M92 134H156V150H92Z"/>')
    else:
        g = (f'<g fill="#1D1D1F">{BR}{LINES}</g>'
             f'<path fill="url(#h)" d="{SWIPE}"/><path fill="#1D1D1F" d="{MID}"/>')
    return f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1024 1024" width="1024" height="1024">
<title>温故</title>
<defs>
<linearGradient id="b" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#FFFFFF"/><stop offset="1" stop-color="#ECECEF"/></linearGradient>
<linearGradient id="h" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#FFE45C"/><stop offset="1" stop-color="#FFD21F"/></linearGradient>
<clipPath id="c"><path d="{t}"/></clipPath>
</defs>
<path d="{t}" fill="url(#b)"/>
<path d="{t}" fill="none" stroke="#00000014" stroke-width="6" clip-path="url(#c)"/>
<g transform="translate({ox:.2f} {oy:.2f}) scale({k})">{g}</g>
</svg>'''


if __name__ == "__main__":
    import io
    import subprocess
    from pathlib import Path

    here = Path(__file__).resolve().parent
    (here / "温故图标.svg").write_text(icon())
    (here / "温故图标-小尺寸.svg").write_text(icon(small=True))
    (here / "标志-单色.svg").write_text(
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 256 256" width="256" height="256"><title>温故</title>{mark_black()}</svg>')

    from PIL import Image

    def png(name, size):
        out = subprocess.run(["rsvg-convert", "-w", str(size), "-h", str(size), str(here / name)],
                             capture_output=True, check=True).stdout
        return Image.open(io.BytesIO(out)).convert("RGBA")

    small = [png("温故图标-小尺寸.svg", s) for s in (16, 32)]
    full = [png("温故图标.svg", s) for s in (64, 128, 256, 512)]
    icns = here.parent.parent / "温故.app" / "Contents" / "Resources" / "AppIcon.icns"
    png("温故图标.svg", 1024).save(icns, format="ICNS", append_images=small + full)
    print("已生成", icns)
