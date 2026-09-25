from pathlib import Path
f = Path('pipeline/build_dict.py')
t = f.read_text(encoding='utf-8')
old = "字孔和，北海人，占梦。"
new = "字孔和，北海人，佔夢。"
if old in t:
    t = t.replace(old, new, 1)
    f.write_text(t, encoding='utf-8')
    print("fixed")
else:
    print("not found")