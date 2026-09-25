# -*- coding: utf-8 -*-
"""把 OWNER_FILL 写进 CHAPTER_OWNERS_SGZ 的空列表。"""
import importlib.util
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location(
    "fill", ROOT / "pipeline" / "_fill_sgz_owners.py"
)
fill = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fill)

bd = ROOT / "pipeline" / "build_dict.py"
text = bd.read_text(encoding="utf-8")
start = text.find("CHAPTER_OWNERS_SGZ = {")
if start < 0:
    raise SystemExit("no CHAPTER_OWNERS_SGZ")
end = text.find("\n}", start)
block = text[start:end]
new_block = block
for slug, pids in fill.OWNER_FILL.items():
    lit = ", ".join('"%s"' % p for p in pids)
    pat = re.compile(r'("%s":\s*)\[\s*\]' % re.escape(slug))
    if pat.search(new_block):
        new_block = pat.sub(
            lambda m: m.group(1) + "[" + lit + "]", new_block, count=1
        )
        print("filled", slug, len(pids))
    else:
        m2 = re.search(r'"%s":\s*\[([^\]]*)\]' % re.escape(slug), new_block)
        if m2 and m2.group(1).strip():
            print("skip nonempty", slug)
        else:
            print("MISS", slug)

bd.write_text(text[:start] + new_block + text[end:], encoding="utf-8")
t2 = bd.read_text(encoding="utf-8")
sec = t2[t2.find("CHAPTER_OWNERS_SGZ"):]
empty = []
for slug in fill.OWNER_FILL:
    m = re.search(r'"%s":\s*\[([^\]]*)\]' % re.escape(slug), sec)
    ok = m and m.group(1).strip()
    print("check", slug, "OK" if ok else "EMPTY")
    if not ok:
        empty.append(slug)
# also count all empty in section
for m in re.finditer(r'"(\d+)":\s*\[\s*\]', sec[: sec.find("\n}") + 2] if False else sec):
    # only within dict until next top-level assignment
    pass
end2 = sec.find("\nCHAPTER_RELATED") if "\nCHAPTER_RELATED" in sec else sec.find("\ndef ")
sec2 = sec[: end2 if end2 > 0 else sec.find("\n} ") + 2]
alls = re.findall(r'"(\d+)":\s*\[([^\]]*)\]', sec)
empty_all = [k for k, v in alls if not v.strip()]
print("remaining empty slugs in SGZ block:", empty_all)
if empty:
    raise SystemExit("still empty: " + ",".join(empty))
