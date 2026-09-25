"""场地租用业务规则：状态流转、字段校验、筛选口径与文件导入都收在这里。"""
from __future__ import annotations

import csv
import hashlib
import io
import math
from datetime import date
from typing import Any

from app.store import store

MODULE = "location"
REQUIRED_FIELDS = ["场地编号", "场地名称", "场地类型"]
# 导入模板列：与列表展示列保持一致，导入生成的场地也按这些字段落库。
IMPORT_FIELDS = ["场地编号", "场地名称", "场地类型", "所属区域", "可租时段", "场地费用", "对接联系人", "租用状态"]
# 上传时强制校验的字段：表头缺少这三列直接判为文件级错误
REQUIRED_HEADERS = ["场地名称", "场地类型", "可租时段"]
STATUS_ORDER = ["待洽谈", "已签约", "使用中", "已退场"]
ACTION_RULES = {"签约场地": "已签约", "确认进场": "使用中", "办理退场": "已退场"}
NEGATIVE_ACTIONS = []

# 筛选范围入参 -> 行字段。前端按中文字段名传参，这里收敛成统一口径。
SCOPE_ALIASES = {
    "keyword": "场地编号",
    "场地编号": "场地编号",
    "场地名称": "场地名称",
    "场地类型": "场地类型",
    "status": "租用状态",
    "租用状态": "租用状态",
}


def _clean(value: Any) -> str:
    return str(value if value is not None else "").strip()


def _parse_available_window(value: str) -> tuple[bool, str]:
    """校验可租时段：支持单日「YYYY-MM-DD」与区间「YYYY-MM-DD~YYYY-MM-DD」。"""
    text = value.replace("～", "~").replace("至", "~").replace("—", "-").replace("－", "-")
    parts = [part.strip() for part in text.split("~", 1)]
    if len(parts) == 1:
        parts.append(parts[0])

    parsed: list[date] = []
    for part in parts:
        try:
            parsed.append(date.fromisoformat(part))
        except ValueError:
            return False, "可租时段需为 YYYY-MM-DD 或起止区间「YYYY-MM-DD~YYYY-MM-DD」"
    if parsed[0] > parsed[1]:
        return False, "可租时段起始日期不能晚于结束日期"
    return True, ""


def normalize_scope(raw: dict[str, Any] | None) -> dict[str, str]:
    """把列表/导入入参整理成「行字段 -> 关键字」的筛选范围，空条件直接丢弃。"""
    scope: dict[str, str] = {}
    for key, value in (raw or {}).items():
        text = _clean(value)
        field = SCOPE_ALIASES.get(key)
        if field and text:
            scope[field] = text
    return scope


def _matches_scope(row: dict[str, Any], scope: dict[str, str]) -> bool:
    return all(keyword in str(row.get(field, "") or "") for field, keyword in scope.items())


class LocationService:
    def list_entries(
        self,
        *,
        page: int = 1,
        size: int = 20,
        scope: dict[str, str] | None = None,
    ) -> tuple[list[dict[str, Any]], int]:
        rows = store.rows(MODULE)
        scope = scope or {}
        if scope:
            rows = [row for row in rows if _matches_scope(row, scope)]
        total = len(rows)
        start = max(page - 1, 0) * size
        return rows[start:start + size], total

    def get_entry(self, entry_id: int) -> dict[str, Any] | None:
        return store.find(MODULE, entry_id)

    def create_entry(self, values: dict[str, Any]) -> tuple[dict[str, Any] | None, list[str]]:
        missing = [field for field in REQUIRED_FIELDS if not _clean(values.get(field))]
        if missing:
            return None, missing
        rows = store.rows(MODULE)
        entry = {"id": store.next_id(MODULE)}
        entry.update({field: _clean(values.get(field)) for field in REQUIRED_FIELDS})
        entry["status"] = STATUS_ORDER[0]
        entry["pending"] = True
        entry["abnormal"] = False
        rows.append(entry)
        return entry, []

    def run_action(self, entry_id: int, action: str) -> tuple[dict[str, Any] | None, str]:
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"拍摄场地 {entry_id} 不存在或已归档"
        if action not in ACTION_RULES:
            return None, f"动作「{action}」不属于场地租用可执行范围"
        target = ACTION_RULES[action]
        if target not in STATUS_ORDER:
            return None, f"目标状态「{target}」不在允许的状态序列里"
        entry["status"] = target
        entry["pending"] = target != STATUS_ORDER[-1]
        entry["abnormal"] = action in NEGATIVE_ACTIONS
        return entry, f"拍摄场地已{action}"

    # ---- 文件导入 --------------------------------------------------------

    def parse_csv(self, content: bytes) -> tuple[list[dict[str, str]], str]:
        """解析导入文件（CSV）：表头必须覆盖展示列，列顺序不做要求。"""
        try:
            text = content.decode("utf-8-sig")
        except UnicodeDecodeError:
            return [], "文件不是 UTF-8 编码的 CSV，请用导出模板另存为 CSV（UTF-8）后重试"
        reader = csv.reader(io.StringIO(text))
        try:
            header = next(reader)
        except StopIteration:
            return [], "导入文件为空，请先下载导入模板填写场地数据"
        header = [_clean(cell) for cell in header]
        unknown = [cell for cell in header if cell and cell not in IMPORT_FIELDS]
        if unknown:
            return [], f"表头存在无法识别的列：{'、'.join(unknown)}"
        missing = [field for field in REQUIRED_HEADERS if field not in header]
        if missing:
            return [], f"表头缺少必需列：{'、'.join(missing)}"

        rows: list[dict[str, str]] = []
        for cells in reader:
            values = {
                header[index]: _clean(cells[index]) if index < len(cells) else ""
                for index in range(len(header))
                if header[index]
            }
            if not any(values.values()):
                continue
            # 模板里带筛选说明的注释行（首列以 # 开头）直接跳过
            if _clean(cells[0]).startswith("#"):
                continue
            rows.append(values)
        return rows, ""

    @staticmethod
    def fingerprint(content: bytes) -> str:
        return hashlib.sha256(content.replace(b"\xef\xbb\xbf", b"")).hexdigest()

    def import_rows(
        self,
        *,
        filename: str,
        content_text: str,
        raw_scope: dict[str, Any] | None = None,
        resume: bool = False,
    ) -> dict[str, Any]:
        """按当前筛选范围导入场地；冲突行只记录原因，中断后可从断点继续。"""
        content = content_text.encode("utf-8")
        digest = self.fingerprint(content)
        batches = store.import_batches(MODULE)
        previous = batches.get(digest)

        if previous is not None and not resume:
            # 已完成：整体仍算成功，只是本次没有新增；中断中：提示走续传
            summary = self._import_summary(
                previous,
                ok=True,
                message=(
                    "该文件此前导入中断，已保留进度，请从断点继续"
                    if previous["interrupted"]
                    else "同一文件已导入过，未重复创建场地；如需重跑请先调整文件内容"
                ),
            )
            if not previous["interrupted"]:
                # 累计计数是上次导入的成果，本次重传没有任何新增/冲突
                summary["created"] = 0
                summary["conflicted"] = 0
                summary["conflicts"] = []
            return summary

        if previous is not None and resume:
            return self._resume_batch(previous)

        rows, error = self.parse_csv(content)
        if error:
            return {"ok": False, "message": error, "conflicts": [], "interrupted": False}

        batch = {
            "filename": filename,
            "fingerprint": digest,
            "scope": normalize_scope(raw_scope),
            "rows": rows,
            "cursor": 0,
            "created": 0,
            "conflicts": [],
            "codes": {_clean(row.get("场地编号")) for row in store.rows(MODULE) if _clean(row.get("场地编号"))},
            "names": {_clean(row.get("场地名称")) for row in store.rows(MODULE) if _clean(row.get("场地名称"))},
            "interrupted": False,
        }
        batches[digest] = batch
        return self._run_batch(batch)

    def _resume_batch(self, batch: dict[str, Any]) -> dict[str, Any]:
        if not batch["interrupted"]:
            return self._import_summary(batch, ok=True, message="该文件已导入完成，没有需要继续的中断行")
        batch["interrupted"] = False
        return self._run_batch(batch)

    def _validate_row(self, values: dict[str, str], batch: dict[str, Any]) -> str:
        code = _clean(values.get("场地编号"))
        name = _clean(values.get("场地名称"))
        kind = _clean(values.get("场地类型"))
        window = _clean(values.get("可租时段"))

        if not code:
            return "缺少场地编号"
        if not name:
            return "缺少场地名称"
        if not kind:
            return "缺少场地类型"
        if not window:
            return "缺少可租时段"
        ok, reason = _parse_available_window(window)
        if not ok:
            return reason

        fee_text = _clean(values.get("场地费用"))
        if fee_text:
            try:
                fee = float(fee_text)
            except ValueError:
                return "场地费用需为数字"
            if not math.isfinite(fee) or fee < 0:
                return "场地费用需为不小于 0 的数字"

        status_text = _clean(values.get("租用状态"))
        if status_text and status_text not in STATUS_ORDER:
            return f"租用状态需为：{'、'.join(STATUS_ORDER)}"

        if batch["scope"] and not _matches_scope(values, batch["scope"]):
            conditions = "、".join(f"{field}含{keyword}" for field, keyword in batch["scope"].items())
            return f"与当前筛选范围不符（{conditions}）"
        if code in batch["codes"]:
            return f"场地编号「{code}」已存在，避免重复登记"
        if name in batch["names"]:
            return f"场地名称「{name}」已存在，避免重复登记"
        return ""

    def _run_batch(self, batch: dict[str, Any]) -> dict[str, Any]:
        rows = batch["rows"]
        try:
            while batch["cursor"] < len(rows):
                index = batch["cursor"]
                values = rows[index]
                line = index + 2  # 表头占第 1 行，数据从第 2 行开始
                reason = self._validate_row(values, batch)
                if reason:
                    batch["conflicts"].append({"line": line, "values": values, "reason": reason})
                else:
                    self._persist_row(batch, values)
                batch["cursor"] = index + 1
        except Exception as exc:  # 中断：保留进度，续传时从当前行重跑
            batch["interrupted"] = True
            return self._import_summary(batch, ok=False, message=f"导入在第 {batch['cursor'] + 2} 行中断：{exc}，可从断点继续")

        message = f"导入完成：新增 {batch['created']} 个场地，冲突 {len(batch['conflicts'])} 行"
        if batch["scope"]:
            message += "（仅导入符合当前筛选范围的行）"
        return self._import_summary(batch, ok=True, message=message)

    def _persist_row(self, batch: dict[str, Any], values: dict[str, str]) -> None:
        code = _clean(values.get("场地编号"))
        name = _clean(values.get("场地名称"))
        fee_text = _clean(values.get("场地费用"))
        status_text = _clean(values.get("租用状态")) or STATUS_ORDER[0]

        entry: dict[str, Any] = {"id": store.next_id(MODULE)}
        for field in IMPORT_FIELDS:
            entry[field] = _clean(values.get(field)) or None
        if fee_text:
            entry["场地费用"] = float(fee_text)
        entry["租用状态"] = status_text
        entry["status"] = status_text
        entry["pending"] = status_text != STATUS_ORDER[-1]
        entry["abnormal"] = False
        store.rows(MODULE).append(entry)

        batch["codes"].add(code)
        batch["names"].add(name)
        batch["created"] += 1

    def _import_summary(self, batch: dict[str, Any], *, ok: bool, message: str) -> dict[str, Any]:
        total = len(batch["rows"])
        cursor = batch["cursor"]
        return {
            "ok": ok,
            "message": message,
            "filename": batch["filename"],
            "fingerprint": batch["fingerprint"],
            "scope": batch["scope"],
            "total": total,
            "created": batch["created"],
            "conflicted": len(batch["conflicts"]),
            "skipped": max(total - cursor, 0) if batch["interrupted"] else 0,
            "interrupted": batch["interrupted"],
            "next_index": cursor if batch["interrupted"] else None,
            "conflicts": list(batch["conflicts"]),
        }
