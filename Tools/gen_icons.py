# -*- coding: utf-8 -*-
"""Génère les icônes de la zone de notification (baleine bleue / baleine grise + .ico)."""
import io
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
OUT = BASE / "assets"
WHALE = (OUT / "whale_path.txt").read_text(encoding="utf-8").strip()

PEAK_COLOR = "#4D6BFE"
OFF_COLOR = "#8E99AE"


def render_svg(png_path, color, size=512):
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24">'
           f'<path fill="{color}" d="{WHALE}"/></svg>')
    from svglib.svglib import svg2rlg
    from reportlab.graphics import renderPM
    d = svg2rlg(io.StringIO(svg))
    s = size / 24.0
    d.scale(s, s)
    d.width = size
    d.height = size
    renderPM.drawToFile(d, str(png_path), fmt="PNG")


def fallback_render(png_path, color, size=512):
    from svgpath2mpl import parse_path
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.transforms as mtrans
    from matplotlib.figure import Figure
    from matplotlib.patches import PathPatch

    p = parse_path(WHALE)
    p = p.transformed(mtrans.Affine2D().scale(1, -1).translate(0, 24))  # SVG : y vers le bas
    fig = Figure(figsize=(size / 100, size / 100), dpi=100)
    ax = fig.add_axes([0, 0, 1, 1])
    ax.set_xlim(0, 24)
    ax.set_ylim(0, 24)
    ax.set_axis_off()
    ax.add_patch(PathPatch(p, facecolor=color, edgecolor="none"))
    fig.savefig(str(png_path), transparent=True)


def postprocess(src, dst_size, margin=0.82):
    from PIL import Image
    img = Image.open(src).convert("RGBA")
    bbox = img.split()[3].getbbox()  # découpe sur l'alpha
    img = img.crop(bbox)
    w, h = img.size
    scale = dst_size * margin / max(w, h)
    img = img.resize((max(1, round(w * scale)), max(1, round(h * scale))), Image.LANCZOS)
    canvas = Image.new("RGBA", (dst_size, dst_size), (0, 0, 0, 0))
    canvas.paste(img, ((dst_size - img.width) // 2, (dst_size - img.height) // 2), img)
    return canvas


def main():
    from PIL import Image
    for name, color in (("whale_peak", PEAK_COLOR), ("whale_offpeak", OFF_COLOR)):
        raw = OUT / f"_raw_{name}.png"
        try:
            render_svg(raw, color)
            how = "svglib"
        except Exception as e:
            print("svglib a échoué →", repr(e))
            fallback_render(raw, color)
            how = "matplotlib"
        big = postprocess(raw, 512)
        big.save(OUT / f"{name}.png")
        print(f"{name}.png OK ({how}, pixels visibles: {sum(1 for px in big.getdata() if px[3] > 0)})")
        raw.unlink(missing_ok=True)
    img = Image.open(OUT / "whale_peak.png").resize((256, 256), Image.LANCZOS)
    img.save(OUT / "whale.ico",
             sizes=[(256, 256), (64, 64), (48, 48), (32, 32), (24, 24), (16, 16)])
    print("whale.ico OK")


if __name__ == "__main__":
    main()
