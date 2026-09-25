"""场地租用导入功能的端到端校验：直接对内存仓库跑，避免多次进程相互污染。"""
import io
import csv
import sys

sys.path.insert(0, ".")
from fastapi.testclient import TestClient

from app.main import app
from app.services import location as loc

client = TestClient(app)

HEADER = ["场地编号", "场地名称", "场地类型", "所属区域", "可租时段", "场地费用", "对接联系人", "租用状态"]


def csv_text(rows, header=None):
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(header or HEADER)
    for row in rows:
        writer.writerow(row)
    return buf.getvalue()


# 0. 基础接口与既有流程不受影响
assert client.get("/api/health").json()["ok"]
overview = client.get("/api/overview").json()
assert any(item["name"] == "location" for item in overview["modules"])
base = client.get("/api/location?size=200").json()["total"]
print("baseline:", base)

# 1. 模板：列与所选范围一致，带 BOM 方便 Excel 打开
r = client.get("/api/location/import-template")
assert r.status_code == 200 and r.text.startswith("﻿")
for column in HEADER:
    assert column in r.text
r = client.get("/api/location/import-template?场地类型=影棚")
assert "当前筛选范围" in r.text and "影棚" in r.text
print("template ok")

# 2. 混合导入：合法行落库，冲突行逐行给原因且不阻断其他行
content = csv_text([
    ["LOCA-NEW-1", "海边悬崖", "外景地", "青岛", "2026-10-01~2026-10-05", "8800", "张三", "待洽谈"],
    ["LOCA-NEW-2", "室内摄影棚", "影棚", "北京", "2026-11-01", "abc", "李四", "待洽谈"],
    ["LOCA-NEW-3", "", "影棚", "北京", "2026-11-01", "100", "李四", "待洽谈"],
    ["LOCA-NEW-4", "古堡庄园", "外景地", "天津", "2026/11/01", "100", "李四", "待洽谈"],
    ["LOCA-NEW-5", "江边码头", "外景地", "上海", "2026-12-01~2026-11-01", "100", "赵五", "待洽谈"],
    ["LOCA-0001", "重复编号场地", "影棚", "北京", "2026-11-01", "100", "李四", "待洽谈"],
    ["LOCA-NEW-99", "场地租用样例1", "影棚", "北京", "2026-11-01", "100", "李四", "待洽谈"],
    ["LOCA-NEW-6", "状态非法场地", "影棚", "北京", "2026-11-01", "100", "李四", "啥状态"],
    ["LOCA-NEW-7", "可签约场地", "影棚", "北京", "2026-11-02", "100", "李四", "已签约"],
])
d = client.post("/api/location/import", json={"filename": "t.csv", "content": content}).json()
assert d["total"] == 9 and d["created"] == 2 and d["conflicted"] == 7, d
reasons = [c["reason"] for c in d["conflicts"]]
expected = ["场地费用需为数字", "缺少场地名称", "YYYY-MM-DD", "起始日期不能晚于结束日期",
            "场地编号「LOCA-0001」已存在", "场地名称「场地租用样例1」已存在", "租用状态需为"]
for needle in expected:
    assert any(needle in reason for reason in reasons), (needle, reasons)
assert client.get("/api/location?size=200").json()["total"] == base + 2
# 行号可定位（表头第 1 行，费用错误在文件第 3 行）
assert d["conflicts"][0]["line"] == 3
print("mixed import ok")

# 3. 同一文件重复导入：不新增场地
d2 = client.post("/api/location/import", json={"filename": "t.csv", "content": content}).json()
assert d2["created"] == 0 and "未重复创建场地" in d2["message"]
assert client.get("/api/location?size=200").json()["total"] == base + 2
print("dedupe ok")

# 4. 按当前筛选范围导入：范围外的行记冲突
content2 = csv_text([
    ["LOCA-S-1", "江南园林A", "园林", "苏州", "2027-01-01", "100", "王", "待洽谈"],
    ["LOCA-S-2", "数字虚拟棚", "影棚", "横店", "2027-01-02", "100", "王", "待洽谈"],
    ["LOCA-S-3", "街景棚", "影棚", "上海", "2027-01-03", "100", "王", "待洽谈"],
])
d3 = client.post("/api/location/import", json={
    "filename": "s.csv", "content": content2, "scope": {"场地类型": "影棚"},
}).json()
assert d3["created"] == 2 and d3["conflicted"] == 1, d3
assert "与当前筛选范围不符" in d3["conflicts"][0]["reason"]
assert d3["scope"] == {"场地类型": "影棚"}
# 列表筛选同口径
listed = client.get("/api/location?场地类型=影棚&size=200").json()
assert all("影棚" in (item.get("场地类型") or "") for item in listed["items"])
print("scope import/list ok")

# 5. 中断后续传：从断点行继续，不重复已成功的行
content4 = csv_text([
    ["LOCA-R-10", "中断棚甲", "影棚", "北京", "2027-03-01", "100", "王", "待洽谈"],
    ["LOCA-R-11", "中断棚乙", "影棚", "北京", "2027-03-02", "100", "王", "待洽谈"],
    ["LOCA-R-12", "中断棚丙", "影棚", "北京", "2027-03-03", "100", "王", "待洽谈"],
])
original = loc.LocationService._persist_row
calls = {"n": 0}


def boom(self, batch, values):
    calls["n"] += 1
    if calls["n"] == 2:
        raise RuntimeError("模拟磁盘抖动")
    return original(self, batch, values)


loc.LocationService._persist_row = boom
d5 = client.post("/api/location/import", json={"filename": "r4.csv", "content": content4}).json()
assert d5["interrupted"] and d5["created"] == 1 and d5["next_index"] == 1 and d5["skipped"] == 2, d5
total_during = client.get("/api/location?size=200").json()["total"]
# 中断后再次上传同一文件：提示继续，不产生变化
d5b = client.post("/api/location/import", json={"filename": "r4.csv", "content": content4}).json()
assert "从断点继续" in d5b["message"] and d5b["interrupted"] and d5b["created"] == 1
assert client.get("/api/location?size=200").json()["total"] == total_during
# 续传：剩 2 行落库
loc.LocationService._persist_row = original
d6 = client.post("/api/location/import", json={
    "filename": "r4.csv", "content": content4, "resume": True,
}).json()
assert d6["created"] == 3 and d6["conflicted"] == 0 and not d6["interrupted"], d6
assert client.get("/api/location?size=200").json()["total"] == total_during + 2
# 完成后再续传：幂等提示
d7 = client.post("/api/location/import", json={
    "filename": "r4.csv", "content": content4, "resume": True,
}).json()
assert "已导入完成" in d7["message"] and d7["created"] == 3
print("resume ok")

# 6. 文件级错误（表头/空文件/编码）
msgs = [
    client.post("/api/location/import", json={"content": "场地编号,场地名称\nX,Y\n"}).json()["message"],
    client.post("/api/location/import", json={"content": "随便列\n1\n"}).json()["message"],
    client.post("/api/location/import", json={"content": ""}).json()["message"],
]
assert "表头缺少必需列" in msgs[0] and "无法识别" in msgs[1] and "导入文件为空" in msgs[2]
bad_encoding = client.post("/api/location/import", json={
    "content": "garbage",
})
# 纯文本无表头列时应给可读错误而非 500
assert bad_encoding.status_code == 200
print("file-level validation ok")

# 7. 文件内重复场地编号：第二条记冲突，只建一条
dup = csv_text([
    ["LOCA-D-1", "同号棚甲", "影棚", "北京", "2027-05-01", "100", "王", "待洽谈"],
    ["LOCA-D-1", "同号棚乙", "影棚", "北京", "2027-05-02", "100", "王", "待洽谈"],
])
dd = client.post("/api/location/import", json={"filename": "dup.csv", "content": dup}).json()
assert dd["created"] == 1 and dd["conflicted"] == 1 and "LOCA-D-1" in dd["conflicts"][0]["reason"]
print("in-file duplicate ok")

# 8. 原有签约 / 进场 / 退场流程照常，导入的场地也能流转
nid = client.get("/api/location?场地编号=LOCA-NEW-1&size=5").json()["items"][0]["id"]
for action, target in [("签约场地", "已签约"), ("确认进场", "使用中"), ("办理退场", "已退场")]:
    result = client.post(f"/api/location/{nid}/actions", json={"values": {"action": action}}).json()
    assert result["ok"] and result["entry"]["status"] == target
assert not client.post(f"/api/location/{nid}/actions", json={"values": {"action": "删除场地"}}).json()["ok"]
assert not client.post("/api/location/99999/actions", json={"values": {"action": "签约场地"}}).json()["ok"]
# 登记入口不受影响
created = client.post("/api/location", json={"values": {
    "场地编号": "LOCA-MANUAL-1", "场地名称": "手工登记棚", "场地类型": "影棚",
}}).json()
assert created["ok"] and created["entry"]["status"] == "待洽谈"
print("existing flows ok")

# 9. 导出沿用当前筛选范围
exported = client.get("/api/location/export?场地类型=影棚").json()
assert exported["scope"] == {"场地类型": "影棚"}
assert all("影棚" in (item.get("场地类型") or "") for item in exported["items"])
print("export scope ok")

print("\nALL TESTS PASSED")
