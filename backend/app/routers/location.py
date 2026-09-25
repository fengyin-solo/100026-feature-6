"""场地租用接口：维护拍摄场地，覆盖签约、进场、退场动作，以及按当前筛选范围导入文件。"""
from __future__ import annotations

import csv
import io
from typing import Any
from urllib.parse import quote

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.schemas import ActionResult, EntryPayload, ImportResult, PageResult
from app.services.location import IMPORT_FIELDS, LocationService, normalize_scope

router = APIRouter(prefix="/api/location", tags=["场地租用"])

service = LocationService()

LIST_FIELDS = ["场地编号", "场地名称", "场地类型", "所属区域", "可租时段", "场地费用", "对接联系人", "租用状态"]
STATUSES = ["待洽谈", "已签约", "使用中", "已退场"]


class ImportPayload(BaseModel):
    """文件导入入参：文件名与 CSV 文本内容（前端读取本地文件后提交，无需 multipart 依赖）。"""

    filename: str = Field(default="场地租用导入.csv")
    content: str = Field(description="CSV 文件的文本内容（UTF-8）")
    scope: dict[str, str] = Field(default_factory=dict)
    resume: bool = False


@router.get("/import-template")
def download_template(
    场地编号: str | None = Query(default=None),
    场地名称: str | None = Query(default=None),
    场地类型: str | None = Query(default=None),
    status: str | None = Query(default=None),
) -> StreamingResponse:
    """下载导入模板：列与当前列表一致；带上筛选参数仅用于提示生成范围与所选范围相同。"""
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(IMPORT_FIELDS)
    scope = normalize_scope(
        {"场地编号": 场地编号, "场地名称": 场地名称, "场地类型": 场地类型, "租用状态": status}
    )
    if scope:
        conditions = "，".join(f"{field}含{keyword}" for field, keyword in scope.items())
        writer.writerow([f"# 当前筛选范围：{conditions}；导入时仅接收符合该范围的行"])
    data = "﻿" + buffer.getvalue()
    filename = quote("场地租用导入模板.csv")
    return StreamingResponse(
        io.BytesIO(data.encode("utf-8")),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{filename}"},
    )


@router.post("/import", response_model=ImportResult)
def import_entries(payload: ImportPayload) -> ImportResult:
    """按当前筛选结果范围导入场地：冲突行给出原因但不阻断其他行，同一文件不重复建场地。"""
    result = service.import_rows(
        filename=payload.filename,
        content_text=payload.content,
        raw_scope=payload.scope,
        resume=payload.resume,
    )
    return ImportResult(**result)


@router.get("", response_model=PageResult[dict])
def list_entries(
    keyword: str | None = Query(default=None, description="按场地编号检索"),
    status: str | None = Query(default=None, description="待洽谈、已签约、使用中、已退场"),
    场地编号: str | None = Query(default=None, description="按场地编号筛选"),
    场地名称: str | None = Query(default=None, description="按场地名称筛选"),
    场地类型: str | None = Query(default=None, description="按场地类型筛选"),
    page: int = 1,
    size: int = 20,
) -> PageResult[dict]:
    """按场地编号、名称、类型与状态过滤场地租用列表；没有数据时返回空页，不报错。"""
    if size > 200:
        raise HTTPException(status_code=400, detail="每页最多 200 条，请缩小分页范围")
    scope = normalize_scope(
        {"keyword": keyword, "status": status, "场地编号": 场地编号, "场地名称": 场地名称, "场地类型": 场地类型}
    )
    items, total = service.list_entries(scope=scope, page=page, size=size)
    return PageResult(items=items, total=total, page=page, size=size)


@router.get("/export")
def export_entries(
    keyword: str | None = Query(default=None),
    status: str | None = Query(default=None),
    场地编号: str | None = Query(default=None),
    场地名称: str | None = Query(default=None),
    场地类型: str | None = Query(default=None),
) -> dict[str, Any]:
    """导出场地租用清单：返回当前过滤条件下的全量数据，与页面所见范围一致。"""
    scope = normalize_scope(
        {"keyword": keyword, "status": status, "场地编号": 场地编号, "场地名称": 场地名称, "场地类型": 场地类型}
    )
    items, total = service.list_entries(scope=scope, page=1, size=10000)
    return {"module": "location", "scope": scope, "total": total, "items": items}


@router.get("/{entry_id}", response_model=dict)
def get_entry(entry_id: int) -> dict:
    """读取单条拍摄场地明细；不存在时给出可读的错误说明。"""
    entry = service.get_entry(entry_id)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"拍摄场地 {entry_id} 不存在或已归档")
    return entry


@router.post("", response_model=ActionResult)
def create_entry(payload: EntryPayload) -> ActionResult:
    """登记一条拍摄场地，缺字段时说明原因而不是静默丢弃。"""
    entry, missing = service.create_entry(payload.values)
    if missing:
        return ActionResult(ok=False, message=f"缺少必填字段：{'、'.join(missing)}")
    return ActionResult(ok=True, message="拍摄场地已登记", entry=entry)


@router.post("/{entry_id}/actions", response_model=ActionResult)
def run_action(entry_id: int, payload: EntryPayload) -> ActionResult:
    """对单条拍摄场地执行签约场地、确认进场、办理退场；不允许的动作会被拦下并说明原因。"""
    action = str(payload.values.get("action") or "").strip()
    entry, message = service.run_action(entry_id, action)
    if entry is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=entry)
