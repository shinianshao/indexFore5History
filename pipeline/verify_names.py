# -*- coding: utf-8 -*-
"""人名阻断表候选的**语料实证**。

挖掘器能召回候选但精度不够（2 字窗口的字面证据最多到五六成准），
所以最终表必须由人定；但人定的每一条都要在语料里验过，否则就是死规则。

本脚本做三件事：
  1. 给出的人工候选表 → 逐条查语料出现次数（0 次的踢掉，说明我记错或不存在）
  2. 逐条查是否与词典里的地名写法冲突（冲突的踢掉，否则会误伤地名）
  3. 逐条查是否已在人物词典里（在的踢掉，那由「人名占用区间」闸门负责）
最后打印可直接粘进 build_places.py 的 NAME_BLOCK 列表。
"""
import glob
import os
import sys
from collections import Counter

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import load_json, CORPUS, norm, DICT, INDEX      # noqa: E402

try:
    from opencc import OpenCC
    _t2s = OpenCC("t2s").convert
except Exception:
    _t2s = None


def S(s):
    s = norm(s)
    return _t2s(s) if _t2s else s


# ---- 人工候选：以单字地名为姓氏的《史记》人物 ----
# 只收「姓+名」这种真正会与地名撞车的形态；国+谥+爵（赵襄子/秦昭王）不收，
# 那种读法本来就该算地名。
CAND = """
秦嘉 秦舞陽 秦開
魏冉 魏齊 魏豹 魏咎 魏勃 魏章 魏絳 魏尚 魏無忌 魏敬 魏侈 魏錡 魏武子
趙高 趙括 趙奢 趙盾 趙武 趙鞅 趙衰 趙朔 趙同 趙嬰齊 趙利 趙信 趙食其 趙破奴
韓信 韓非 韓說 韓嫣 韓厥 韓不信 韓安國 韓廣 韓增 韓王孫
周昌 周苛 周勃 周章 周市 周文 周舍 周亞夫 周青臣 周殷 周緤 周仁 周丘 周霸
周最 周生 周陽由 周無傷
曹參 曹沫 曹沬 曹咎 曹窋 曹襄 曹圉 曹無傷 曹時 曹宗
鄭袖 鄭安平 鄭當時 鄭國 鄭忠 鄭昌 鄭朱 鄭吉
衛青 衛綰 衛登 衛伉 衛不疑 衛滿
陳平 陳勝 陳餘 陳豨 陳嬰 陳恢 陳武 陳軫 陳完 陳賈 陳厲公 陳掌
吳廣 吳起 吳芮 吳臣 吳陽 吳娃 吳漢
蔡澤 蔡義 蔡賜 蔡兼 蔡姬
薛歐 薛澤 薛宣 薛況
商容 商均 商瞿 商鞅
殷通
燕噲
晉鄙 晉文
宋義 宋昌 宋襄 宋留 宋建 宋毋忌
魯句踐 魯仲連
唐眛 唐舉 唐蒙 唐厲
雍齒 雍廩
夏說 夏徵舒 夏無且 夏育
虢射 虢叔 虢仲 虢石父
紀信 紀成 紀通
虞卿 虞常
芮良夫
"""


def main():
    data = load_json(os.path.join(INDEX, "book-data.json"))
    place_forms = set()
    for p in data["places"]:
        place_forms.update(S(a) for a in p["aliases"])
        for a in p.get("aliasList", []):
            place_forms.add(S(a["w"]))
    person_forms = set()
    for p in data["persons"]:
        person_forms.update(S(a) for a in (p.get("aliases") or []))
        for a in p.get("aliasList", []):
            person_forms.add(S(a["w"]))
    char_places = set(S(p["name"]) for p in data["places"] if p.get("isChar"))

    # 语料计数（按简体归并；同时记繁体形式）
    raw_forms = set()
    for s in data["sentences"]:
        pass
    cnt = Counter()
    for path in sorted(glob.glob(os.path.join(CORPUS, "sj-*.json"))):
        doc = load_json(path)
        for para in doc["paragraphs"]:
            for s in para["sentences"]:
                t = norm(s["text"])
                for i in range(len(t) - 1):
                    if S(t[i]) in char_places:
                        # 键一律转简体：语料是繁体，候选表是简体，不转会全部查无
                        cnt[S(t[i:i + 2])] += 1
                        cnt[S(t[i:i + 3])] += 1

    cands = [w for w in CAND.split() if w]
    ok, drop_hit, drop_place, drop_person = [], [], [], []
    for w in sorted(set(cands)):
        sw = S(w)
        if sw in person_forms:
            drop_person.append(w)
            continue
        if len(sw) > 2 and sw in place_forms:
            drop_place.append(w)
            continue
        if cnt.get(sw, 0) == 0:
            drop_hit.append(w)
            continue
        ok.append((w, cnt[sw]))

    print("提交候选 %d 条" % len(set(cands)))
    print("  收下           %d 条" % len(ok))
    print("  已在人物词典   %d 条：%s" % (len(drop_person), " ".join(drop_person)))
    print("  与地名写法冲突 %d 条：%s" % (len(drop_place), " ".join(drop_place)))
    print("  语料查无       %d 条：%s" % (len(drop_hit), " ".join(drop_hit)))
    print()
    print("=== 收下的（按语料出现次数降序）===")
    for w, n in sorted(ok, key=lambda x: -x[1]):
        print("  %-8s %d" % (w, n))
    print()
    print("=== 可直接粘进 build_places.py 的 NAME_BLOCK ===")
    words = [w for w, _ in sorted(ok, key=lambda x: -x[1])]
    line, out = "    ", []
    for w in words:
        if len(line) + len(w) + 1 > 88:
            out.append(line.rstrip())
            line = "    "
        line += '"%s", ' % w
    out.append(line.rstrip().rstrip(","))
    print("NAME_BLOCK = (\n" + "\n".join(out) + "\n)")


if __name__ == "__main__":
    main()
