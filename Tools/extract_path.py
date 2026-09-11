# -*- coding: utf-8 -*-
"""Extrait le chemin SVG officiel de la baleine depuis WhaleShape.swift (projet macOS)."""
import re
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
src = Path(sys.argv[1]).read_text(encoding="utf-8")
m = re.search(r'svgPathData = """(.*?)"""', src, re.S)
assert m, "chemin introuvable dans le fichier Swift"
path = " ".join(m.group(1).split())  # normalise les retours à la ligne en espaces
out = BASE / "assets" / "whale_path.txt"
out.write_text(path, encoding="utf-8")
print(f"path OK, {len(path)} caractères")
print("début:", path[:48])
print("fin:  ", path[-48:])
