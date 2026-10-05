# -*- coding: utf-8 -*-
"""P2 阶段关系边元数据补全治理：
为 workbook/relations.xlsx 补全缺失的「时代(era)」与「书(book)」。
遵循安全写入规范（safe_save_workbook，BytesIO 封包 + 原子替换）。
保留原有 rel_id 与证据关联不变。
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import sqlite3
import openpyxl
import pipeline.relations as R
from pipeline.common import safe_save_workbook
DB_PATH = os.path.join(ROOT, "data", "index", "index.db")
WORKBOOK = os.path.join(ROOT, "workbook", "relations.xlsx")

def main():
    conn = sqlite3.connect(DB_PATH)
    def get_person(pid):
        r = conn.execute("SELECT trad_name, dynasty FROM persons WHERE id=?", (pid,)).fetchone()
        return r if r else (pid, "")

    def get_ev_book(uid):
        if not uid:
            return ""
        r = conn.execute(
            "SELECT c.book_id FROM sentences s JOIN chapters c ON c.id=s.chapter_id WHERE s.uid=?",
            (uid,)).fetchone()
        return r[0] if r else ""

    def get_person_books(pid):
        rows = conn.execute(
            "SELECT DISTINCT c.book_id FROM mentions m JOIN sentences s ON s.uid=m.sentence_uid "
            "JOIN chapters c ON c.id=s.chapter_id WHERE m.person_id=?",
            (pid,)).fetchall()
        return {r[0] for r in rows}

    wb = openpyxl.load_workbook(WORKBOOK)
    ws = wb["relations"] if "relations" in wb.sheetnames else wb.active
    headers = [c.value for c in ws[1]]
    era_col = headers.index("时代(era)") + 1
    book_col = headers.index("书(book)") + 1
    a_col = headers.index("person_a") + 1
    b_col = headers.index("person_b") + 1
    uid_col = headers.index("证据uid") + 1
    stat_col = headers.index("状态(status)") + 1

    updated_era = 0
    updated_book = 0

    for row_idx in range(2, ws.max_row + 1):
        stat = str(ws.cell(row=row_idx, column=stat_col).value or "active").strip()
        if stat != "active":
            continue
        a = str(ws.cell(row=row_idx, column=a_col).value or "").strip()
        b = str(ws.cell(row=row_idx, column=b_col).value or "").strip()
        uid = str(ws.cell(row=row_idx, column=uid_col).value or "").strip()
        cur_era = str(ws.cell(row=row_idx, column=era_col).value or "").strip()
        cur_book = str(ws.cell(row=row_idx, column=book_col).value or "").strip()

        na, da = get_person(a)
        nb, db = get_person(b)

        # 1. 时代补全
        if not cur_era:
            if da == db and da:
                new_era = da
            else:
                pair = (na, nb)
                if "司馬炎" in pair: new_era = "西晉"
                elif "秦始皇" in pair: new_era = "秦"
                elif "酈食其" in pair: new_era = "西漢"
                elif "胡遵" in pair: new_era = "西晉"
                elif "項燕" in pair: new_era = "秦末"
                elif "冒頓單于" in pair: new_era = "西漢"
                elif "商紂王" in pair: new_era = "商"
                elif "公孫糾" in pair: new_era = "春秋"
                else: new_era = da or db or ""
            if new_era:
                ws.cell(row=row_idx, column=era_col, value=new_era)
                updated_era += 1

        # 2. 书籍补全
        if not cur_book:
            ev_b = get_ev_book(uid)
            if ev_b:
                ws.cell(row=row_idx, column=book_col, value=ev_b)
                updated_book += 1
            else:
                ba = get_person_books(a)
                bb = get_person_books(b)
                inter = ba & bb
                if len(inter) == 1:
                    ws.cell(row=row_idx, column=book_col, value=list(inter)[0])
                    updated_book += 1
                # 若跨多书则保持为空

    safe_save_workbook(wb, WORKBOOK)
    conn.close()
    print("治理完成：补全时代(era) {} 处，补全书(book) {} 处。".format(updated_era, updated_book))

if __name__ == "__main__":
    main()
