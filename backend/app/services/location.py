"""场地租用业务规则：状态流转、字段校验、文件导入与筛选口径都收在这里。"""
from __future__ import annotations

import csv
import hashlib
import io
import json
import re
from datetime import datetime
from typing import Any

from app.store import store

MODULE = "location"
REQUIRED_FIELDS = ["场地编号", "场地名称", "场地类型"]
IMPORT_REQUIRED_FIELDS = ["场地名称", "场地类型", "可租时段"]
PUBLIC_FIELDS = ["场地编号", "场地名称", "场地类型", "所属区域", "可租时段", "场地费用", "对接联系人", "租用状态"]
STATUS_ORDER = ["待洽谈", "已签约", "使用中", "已退场"]
ACTION_RULES = {"签约场地": "已签约", "确认进场": "使用中", "办理退场": "已退场"}
NEGATIVE_ACTIONS = []
MAX_IMPORT_ROWS = 5000


class LocationService:
    def list_entries(
        self,
        *,
        keyword: str | None = None,
        name: str | None = None,
        location_type: str | None = None,
        status: str | None = None,
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        rows = self._filtered_rows(keyword=keyword, name=name, location_type=location_type, status=status)
        total = len(rows)
        start = max(page - 1, 0) * size
        return rows[start:start + size], total

    def export_entries(
        self,
        *,
        keyword: str | None = None,
        name: str | None = None,
        location_type: str | None = None,
        status: str | None = None,
    ) -> list[dict[str, Any]]:
        return [self._public_entry(row) for row in self._filtered_rows(
            keyword=keyword,
            name=name,
            location_type=location_type,
            status=status,
        )]

    def get_entry(self, entry_id: int) -> dict[str, Any] | None:
        return store.find(MODULE, entry_id)

    def create_entry(self, values: dict[str, Any]) -> tuple[dict[str, Any] | None, list[str]]:
        cleaned = self._clean_values(values)
        missing = [field for field in REQUIRED_FIELDS if not str(cleaned.get(field) or "").strip()]
        if missing:
            return None, missing
        entry = self._insert_entry(cleaned)
        return entry, []

    def import_content(
        self,
        *,
        filename: str,
        content: str,
        keyword: str | None = None,
        name: str | None = None,
        location_type: str | None = None,
        status: str | None = None,
        start_row: int = 0,
    ) -> dict[str, Any]:
        scope = self._scope(keyword=keyword, name=name, location_type=location_type, status=status)
        fingerprint = hashlib.sha256(f"{filename}\n{content}".encode("utf-8")).hexdigest()
        try:
            rows = self._parse_import_file(filename, content)
        except ValueError as exc:
            return {
                "ok": False,
                "message": f"文件无法导入：{exc}",
                "interrupted": False,
                "resume_from": None,
                "file_fingerprint": fingerprint,
                "scope": scope,
                "rows": [],
            }

        if start_row > len(rows):
            start_row = 0
        results: list[dict[str, Any]] = []
        created = 0
        duplicates = 0

        for row_number in range(start_row, len(rows)):
            raw_row = rows[row_number]
            try:
                entry, reason, duplicate = self._import_row(raw_row)
                result: dict[str, Any]
                if duplicate:
                    duplicates += 1
                    result = {"row": row_number + 1, "status": "duplicate", "reason": reason, "entry": entry}
                elif entry is None:
                    result = {"row": row_number + 1, "status": "failed", "reason": reason, "entry": None}
                else:
                    created += 1
                    result = {"row": row_number + 1, "status": "created", "reason": None, "entry": entry}
                results.append(result)
            except Exception as exc:  # 单行出现未预期错误时保留断点，前面已成功的行不回滚。
                results.append({"row": row_number + 1, "status": "failed", "reason": f"系统处理中断：{exc}", "entry": None})
                processed = row_number - start_row
                return {
                    "ok": False,
                    "message": f"第 {row_number + 1} 行处理中断，可从该行继续导入",
                    "total": len(rows),
                    "processed": processed,
                    "created": created,
                    "duplicates": duplicates,
                    "failed": 1,
                    "interrupted": True,
                    "resume_from": row_number,
                    "file_fingerprint": fingerprint,
                    "scope": scope,
                    "rows": self._visible_results(results),
                }

        failed = sum(1 for item in results if item["status"] == "failed")
        ok = failed == 0
        message = f"导入完成：新增 {created} 条，重复跳过 {duplicates} 条，失败 {failed} 条"
        completed = start_row == 0 and len(results) == len(rows)
        return {
            "ok": ok,
            "message": message,
            "total": len(rows),
            "processed": len(rows) - start_row,
            "created": created,
            "duplicates": duplicates,
            "failed": failed,
            "interrupted": False,
            "resume_from": None,
            "file_fingerprint": fingerprint,
            "scope": scope,
            "rows": results if completed else self._visible_results(results),
        }

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
        entry["租用状态"] = target
        entry["pending"] = target != STATUS_ORDER[-1]
        entry["abnormal"] = action in NEGATIVE_ACTIONS
        return entry, f"拍摄场地已{action}"

    def _filtered_rows(
        self,
        *,
        keyword: str | None = None,
        name: str | None = None,
        location_type: str | None = None,
        status: str | None = None,
    ) -> list[dict[str, Any]]:
        rows = store.rows(MODULE)
        if keyword:
            rows = [row for row in rows if keyword in str(row.get("场地编号", ""))]
        if name:
            rows = [row for row in rows if name in str(row.get("场地名称", ""))]
        if location_type:
            rows = [row for row in rows if location_type in str(row.get("场地类型", ""))]
        if status:
            rows = [row for row in rows if row.get("status") == status or row.get("租用状态") == status]
        return rows

    @staticmethod
    def _scope(**filters: str | None) -> dict[str, Any]:
        return {key: value for key, value in filters.items() if value}

    @staticmethod
    def _public_entry(row: dict[str, Any]) -> dict[str, Any]:
        entry = {field: row.get(field, "") for field in PUBLIC_FIELDS}
        entry["租用状态"] = row.get("租用状态") or row.get("status") or STATUS_ORDER[0]
        return entry

    @staticmethod
    def _visible_results(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
        visible = [item for item in results if item["status"] != "created"]
        return visible[:1000]

    @staticmethod
    def _parse_import_file(filename: str, content: str) -> list[dict[str, str]]:
        if not filename.strip():
            raise ValueError("文件名不能为空")
        if not content.strip():
            raise ValueError("文件内容为空")
        if len(content.encode("utf-8")) > 2 * 1024 * 1024:
            raise ValueError("文件不能超过 2 MB，请拆分后再导入")
        normalized_name = filename.lower()
        text = content.lstrip("﻿")
        is_json = normalized_name.endswith(".json") or text.lstrip().startswith(("{", "["))
        if is_json:
            try:
                payload = json.loads(text)
            except json.JSONDecodeError as exc:
                raise ValueError(f"JSON 格式错误：{exc.msg}") from exc
            if isinstance(payload, dict):
                payload = payload.get("items", [])
            if not isinstance(payload, list):
                raise ValueError("JSON 需为记录数组，或包含 items 数组")
            rows = []
            for item in payload:
                if not isinstance(item, dict):
                    raise ValueError("JSON 中每条记录都必须是对象")
                rows.append({
                    str(key).strip(): "" if value is None else str(value).strip()
                    for key, value in item.items()
                    if str(key).strip()
                })
        else:
            delimiter = "\t" if normalized_name.endswith(".tsv") else ","
            reader = csv.DictReader(io.StringIO(text), delimiter=delimiter)
            if not reader.fieldnames:
                raise ValueError("未找到表头")
            rows = [
                {key.strip(): value for key, value in row.items() if key and key.strip()}
                for row in reader
            ]
            rows = [row for row in rows if any(str(value).strip() for value in row.values())]

        if len(rows) > MAX_IMPORT_ROWS:
            raise ValueError(f"单次最多导入 {MAX_IMPORT_ROWS} 行，请拆分文件")
        return rows

    def _import_row(self, raw_row: dict[str, Any]) -> tuple[dict[str, Any] | None, str | None, bool]:
        values = self._clean_values(raw_row)
        missing = [field for field in IMPORT_REQUIRED_FIELDS if not str(values.get(field) or "").strip()]
        if missing:
            return None, f"缺少必填字段：{'、'.join(missing)}", False

        period_reason = self._validate_rental_period(str(values["可租时段"]))
        if period_reason:
            return None, period_reason, False

        duplicate = self._find_by_name(str(values["场地名称"]))
        if duplicate is not None:
            return self._public_entry(duplicate), f"场地名称「{values['场地名称']}」已存在，重复文件未重复登记", True

        if not str(values.get("场地编号") or "").strip():
            values["场地编号"] = self._next_location_code()
        elif self._find_by_code(str(values["场地编号"])) is not None:
            return None, f"场地编号「{values['场地编号']}」已存在", False

        return self._insert_entry(values), None, False

    def _insert_entry(self, values: dict[str, Any]) -> dict[str, Any]:
        rows = store.rows(MODULE)
        entry = {"id": max((int(row.get("id", 0)) for row in rows), default=0) + 1}
        entry.update({field: values.get(field, "") for field in PUBLIC_FIELDS if field != "租用状态"})
        entry["status"] = STATUS_ORDER[0]
        entry["租用状态"] = STATUS_ORDER[0]
        entry["pending"] = True
        entry["abnormal"] = False
        rows.append(entry)
        return entry

    @staticmethod
    def _clean_values(values: dict[str, Any]) -> dict[str, Any]:
        cleaned: dict[str, Any] = {}
        for field in PUBLIC_FIELDS:
            value = values.get(field)
            if value is None:
                cleaned[field] = ""
                continue
            text = str(value).strip()
            if field == "场地费用" and text:
                try:
                    cleaned[field] = float(text)
                    continue
                except ValueError:
                    pass
            cleaned[field] = text
        return cleaned

    def _next_location_code(self) -> str:
        numbers = []
        for row in store.rows(MODULE):
            match = re.search(r"(\d+)$", str(row.get("场地编号", "")))
            if match:
                numbers.append(int(match.group(1)))
        return f"LOCA-{max(numbers, default=0) + 1:04d}"

    def _find_by_name(self, name: str) -> dict[str, Any] | None:
        target = name.strip()
        for row in store.rows(MODULE):
            if str(row.get("场地名称", "")).strip() == target:
                return row
        return None

    def _find_by_code(self, code: str) -> dict[str, Any] | None:
        target = code.strip()
        for row in store.rows(MODULE):
            if str(row.get("场地编号", "")).strip() == target:
                return row
        return None

    @staticmethod
    def _validate_rental_period(period: str) -> str | None:
        text = period.strip()
        if not text:
            return "可租时段不能为空"
        normalized = re.sub(r"\s+", "", text)
        normalized = normalized.replace("—", "-").replace("–", "-").replace("～", "~").replace("至", "-")
        datetime_pattern = re.compile(r"^\d{4}[-/.]\d{1,2}[-/.]\d{1,2}[T\s]?\d{1,2}:\d{2}(?::\d{2})?$")
        common_periods = {"全天", "白天", "上午", "下午", "晚上"}

        if normalized in common_periods:
            return None

        if datetime_pattern.match(normalized.replace("/", "-")):
            try:
                datetime.fromisoformat(normalized.replace("/", "-"))
                return None
            except ValueError:
                return "可租时段的日期时间不存在"

        date_matches = re.findall(r"\d{4}[-/.]\d{1,2}[-/.]\d{1,2}", normalized)
        time_matches = re.findall(r"\d{1,2}:\d{2}(?::\d{2})?", normalized)
        if date_matches:
            try:
                dates = [datetime.strptime(value.replace("/", "-"), "%Y-%m-%d") for value in date_matches]
            except ValueError:
                return "可租时段的日期不存在"
            if len(dates) == 2 and dates[0] > dates[1]:
                return "可租时段的开始日期不能晚于结束日期"
            if len(dates) > 2:
                return "可租时段最多填写开始和结束两个日期"
        elif time_matches:
            dates = []
        else:
            return "可租时段格式不正确，请使用日期、日期区间或 HH:MM-HH:MM"

        if time_matches:
            if len(time_matches) != 2:
                return "可租时段需包含开始和结束两个时间"
            try:
                start = datetime.strptime(time_matches[0], "%H:%M:%S" if time_matches[0].count(":") == 2 else "%H:%M")
                end = datetime.strptime(time_matches[1], "%H:%M:%S" if time_matches[1].count(":") == 2 else "%H:%M")
            except ValueError:
                return "可租时段的时间不存在"
            if start >= end:
                return "可租时段的开始时间需早于结束时间"
        return None
