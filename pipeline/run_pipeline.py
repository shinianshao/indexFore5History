# -*- coding: utf-8 -*-
"""管线编排：按正确顺序跑完整条链路。

    build.py           抓取结果 → 提取正文、切句   (data/corpus/*.json)
    build_dict.py      生成人物词典与泛称规则      (data/dict/people.json)
    annotate.py        别名标注 → 检索索引         (data/index/*.json + web/*.js)
    annotate_pei.py    裴注标注 → 独立索引         (data/index/pei-data.json + web/pei-data.js)
                       不进正文 mentionCount / 泛称基线
    build_places.py    生成地名词典与邻字守卫      (data/dict/places.json)
    annotate_places.py 地名标注 → 就地并入索引     (data/index/*.json + web/*.js)
    check_trad.py      字面层守卫：产物与界面是否都停在正确的不动点上（不过就中断）

顺序有依赖，不要手工乱跑：
    annotate.py 产出的 book-data.json 是 annotate_places.py 的输入
    （地名层要把「人名占用区间」挖掉，所以必须先有人物层结果）。
    check_trad.py 必须**最后**跑——它查的是最终产物。
resolve.py 是**体检工具**，不在链路里，需要时单独跑。

用法：
    python run_pipeline.py            完整链路（人物层 + 地名层 + 字面层守卫）
    python run_pipeline.py --audit    再跑一次词典体检
    python run_pipeline.py place      只重跑地名层（改地名规则时用，人物层不动）
"""
import os
import subprocess
import sys

sys.stdout.reconfigure(encoding="utf-8")
PIPELINE = os.path.dirname(os.path.abspath(__file__))
STEPS = [
    ("切分语料", "build.py"),
    ("生成人物词典", "build_dict.py"),
    ("标注人物索引", "annotate.py"),
    ("标注裴注索引", "annotate_pei.py"),
    ("标注晉書舊史注", "annotate_js_note.py"),
    ("生成地名词典", "build_places.py"),
    ("标注地名索引", "annotate_places.py"),
    ("校验字面层", "check_trad.py"),
]
# 只重跑地名层：地名词典 + 地名标注 + 守卫。前提是 book-data.json 已由 annotate.py 生成过。
PLACE_STEPS = [("生成地名词典", "build_places.py"),
               ("标注地名索引", "annotate_places.py"),
               ("校验字面层", "check_trad.py")]


def run(name, script):
    print("[{}] {}".format(name, script))
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    proc = subprocess.run([sys.executable, os.path.join(PIPELINE, script)],
                          capture_output=True, text=True, encoding="utf-8",
                          errors="replace", env=env)
    if proc.stdout:
        print(proc.stdout.rstrip())
    if proc.returncode != 0:
        print((proc.stderr or "").rstrip())
        raise SystemExit("{} 失败，已中断".format(script))


def main():
    place_only = "place" in sys.argv
    for name, script in (PLACE_STEPS if place_only else STEPS):
        run(name, script)
    if "--audit" in sys.argv:
        run("词典体检", "resolve.py")
    print("管线完成")


if __name__ == "__main__":
    main()
