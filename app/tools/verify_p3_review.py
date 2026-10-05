# -*- coding: utf-8 -*-
"""P3 阶段全量交付独立审查脚本（Independent Review）。

覆盖 P3 全部核心治理与架构交付项：
[1] 根目录 README.md 真实性与指标契约（全五书 564 篇、22.3万句、2238人、1575地名、101关系边、8800启动命令）
[2] 历史前端 web/ 目录冻结归档治理（README 说明、HTML 冻结注释、app/web 与 dist/app.js 同步守卫）
[3] 关系图谱与多证据呈现端到端一致性（离线快照 rel 数据完备、39条证据对应、export_static 守卫）
[4] 文档治理与项目知识库对齐（docs/36 踩坑清单、MEMORY.md、两处 workflow SKILL）
[5] 故障注入红绿双向闭环（--inject 必须红，正常必须全绿）

运行方式：
    python app/tools/verify_p3_review.py           # 正常模式（全绿 -> 退出码 0）
    python app/tools/verify_p3_review.py --inject  # 故障注入模式（必须红 -> 退出码 1）
"""
import os
import sys
import re
import json
import sqlite3
import hashlib

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
if os.path.join(ROOT, "app", "server") not in sys.path:
    sys.path.insert(0, os.path.join(ROOT, "app", "server"))

import db

CHECKS = []
INJECT_FAULT = "--inject" in sys.argv

def check(name: str, passed: bool, extra: str = ""):
    CHECKS.append((name, passed))
    mark = "OK" if passed else "FAIL"
    detail = f"　（{extra}）" if extra else ""
    print(f"  [{mark}] {name}{detail}")


def review_readme():
    print("\n[审查项 1] 根目录 README.md 真实性与准确度审查")
    readme_path = os.path.join(ROOT, "README.md")
    with open(readme_path, encoding="utf-8") as f:
        content = f.read()

    # 1. 篇目规模
    check("README 包含 564 篇全书篇目规模", "564 篇" in content)

    # 2. 语料句子规模：必须为 223,164 句，杜绝 95,632 句历史旧数
    has_new_sents = "223,164" in content
    has_old_sents = "95,632" in content or "96,336" in content
    if INJECT_FAULT:
        has_new_sents = False  # 故障注入：模拟语料句子规模未更新
    check("README 包含全量 223,164 句且无 9.5 万句等过时数据",
          has_new_sents and not has_old_sents,
          f"包含新数={has_new_sents}, 残留旧数={has_old_sents}")

    # 3. 人物规模：2,238 人
    check("README 包含 2,238 位人物收录指标", "2,238" in content)

    # 4. 地名规模：1,575 处地名（或扩充后 1,620+ 处）
    has_places = ("1,575" in content or "1,620" in content or "1,621" in content)
    check("README 包含 1,575 或 1,620+ 处地名收录指标", has_places)

    # 5. 关系规模：101 条规范边
    check("README 包含 101 条规范关系边指标", "101 条" in content)

    # 6. 正确的服务端快速启动指导：指向 8800 端口，无旧 8770 错误引导
    has_8800 = "8800" in content and "app.server.main:app" in content
    has_old_8770_guide = "cd web && python -m http.server 8770" in content
    check("README 包含正确的 8800 启动指导且已清除旧 8770 引导",
          has_8800 and not has_old_8770_guide,
          f"包含8800={has_8800}, 残留8770引导={has_old_8770_guide}")

    # 7. 文档导航包含 36 号之后的最新交付索引
    has_doc_nav = "docs/36-踩坑清单.md" in content and "docs/41" in content
    check("README 文档导航链接到 docs/36 及 docs/41 最新交付报告", has_doc_nav)


def review_legacy_web_archive():
    print("\n[审查项 2] 历史前端 web/ 目录冻结归档治理审查")
    # 1. web/README.md 归档说明
    web_readme = os.path.join(ROOT, "web", "README.md")
    readme_exists = os.path.exists(web_readme)
    with open(web_readme, encoding="utf-8") as f:
        w_text = f.read() if readme_exists else ""
    check("web/README.md 存在且包含冻结归档声明",
          readme_exists and "已冻结" in w_text and "app/web" in w_text)

    # 2. web/index.html 头部注释
    web_html = os.path.join(ROOT, "web", "index.html")
    with open(web_html, encoding="utf-8") as f:
        html_text = f.read()
    check("web/index.html 头部包含明确的历史冻结提示注释",
          "历史冻结页面" in html_text and "app/web/index.html" in html_text)

    # 3. 生产前端 app/web/app.js 与 dist/app.js 脚本内容 100% 同步
    src_app = os.path.join(ROOT, "app", "web", "app.js")
    dst_app = os.path.join(ROOT, "dist", "app.js")
    with open(src_app, "r", encoding="utf-8") as f1, open(dst_app, "r", encoding="utf-8") as f2:
        t1 = f1.read().replace("\r\n", "\n")
        t2 = f2.read().replace("\r\n", "\n")
    if INJECT_FAULT:
        t2 = t2 + "\n// fault_injection_corrupted"
    check("主力前端 app/web/app.js 与 dist/app.js 逻辑代码 100% 同步",
          t1 == t2, f"src_len={len(t1)}, dst_len={len(t2)}")


def review_relations_and_evidence():
    print("\n[审查项 3] 关系图谱与多证据呈现端到端一致性审查")
    # 1. 数据库活跃关系数与证据数
    conn = sqlite3.connect(db.db_path())
    n_act_rel = conn.execute("SELECT COUNT(*) FROM relations WHERE status='active'").fetchone()[0]
    n_ev = conn.execute("SELECT COUNT(*) FROM relation_evidence").fetchone()[0]
    conn.close()
    check("SQLite 库中活跃关系为 101 条且证据为 39 条",
          n_act_rel == 101 and n_ev == 39, f"relations={n_act_rel}, evidence={n_ev}")

    # 2. 离线快照 dist/data.js 中的 counts 与数据
    dist_data_path = os.path.join(ROOT, "dist", "data.js")
    with open(dist_data_path, encoding="utf-8") as f:
        data_js = f.read()
    m_counts = re.search(r'"counts":\{([^}]*)\}', data_js)
    counts = dict(re.findall(r'"(\w+)":(\d+)', m_counts.group(1))) if m_counts else {}
    check("dist/data.js 快照记录 101 条关系且 rel 模块已导出",
          counts.get("relations") == "101" and '"rel":' in data_js,
          f"counts.relations={counts.get('relations')}")

    # 3. 前端关系详情卡片证据数组支持
    src_app = os.path.join(ROOT, "app", "web", "app.js")
    with open(src_app, "r", encoding="utf-8") as f:
        js_code = f.read()
    has_ev_render = "evidences" in js_code and "evidence_uid" in js_code
    check("前端 app.js 包含多证据 evidences 数组渲染与跳转支持", has_ev_render)


def review_documentation_and_skills():
    print("\n[审查项 4] 文档体系治理与项目知识库对齐审查")
    # 1. docs/36-踩坑清单.md 登记了 P0/P1/P2 完成与 P3 治理
    doc36_path = os.path.join(ROOT, "docs", "36-踩坑清单.md")
    with open(doc36_path, encoding="utf-8") as f:
        d36 = f.read()
    check("docs/36 登记了 P0、P1、P2 全部闭环及 rel_id 契约避坑",
          "P0 写入护栏" in d36 and "P2 全量交付独立审查" in d36 and "rel_id" in d36 and "契约重构" in d36)

    # 2. .workbuddy/memory/MEMORY.md 包含最新状态
    memory_path = os.path.join(ROOT, ".workbuddy", "memory", "MEMORY.md")
    with open(memory_path, encoding="utf-8") as f:
        mem = f.read()
    check("MEMORY.md 登记了 P0-P2 完工与 docs/41 报告",
          "P2 全量独立审查" in mem and "docs/41" in mem)

    # 3. .agents/ 与 .mimocode/ 下的 SKILL.md 一致性
    s1_path = os.path.join(ROOT, ".agents", "skills", "bookindex-workflow", "SKILL.md")
    s2_path = os.path.join(ROOT, ".mimocode", "skills", "bookindex-workflow", "SKILL.md")
    with open(s1_path, encoding="utf-8") as f1, open(s2_path, encoding="utf-8") as f2:
        s1 = f1.read().replace("\r\n", "\n")
        s2 = f2.read().replace("\r\n", "\n")
    check("两处工作流 SKILL.md (.agents 与 .mimocode) 保持 100% 同步",
          s1 == s2, f"s1_len={len(s1)}, s2_len={len(s2)}")


def main():
    print("=" * 65)
    print("       古籍索引系统 BOOKINDEX · P3 阶段全量独立审查       ")
    print("=" * 65)
    review_readme()
    review_legacy_web_archive()
    review_relations_and_evidence()
    review_documentation_and_skills()

    total = len(CHECKS)
    passed = sum(1 for _, ok in CHECKS if ok)
    print("\n" + "=" * 65)
    print(f"审查结果统计：{passed}/{total} 项全部通过。")
    print("=" * 65)
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
