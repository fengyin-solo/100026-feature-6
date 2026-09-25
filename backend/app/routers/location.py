"""场地租用接口：维护拍摄场地，覆盖导入、签约场地、确认进场、办理退场等动作。"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import JSONResponse

from app.schemas import (
    ActionResult,
    EntryPayload,
    LocationImportPayload,
    LocationImportResult,
    PageResult,
)
from app.services.location import LocationService

router = APIRouter(prefix="/api/location", tags=["场地租用"])

service = LocationService()

LIST_FIELDS = ["场地编号", "场地名称", "场地类型", "所属区域", "可租时段", "场地费用", "对接联系人", "租用状态"]
STATUSES = ["待洽谈", "已签约", "使用中", "已退场"]


@router.get("", response_model=PageResult[dict])
def list_entries(
    keyword: str | None = Query(default=None, description="按场地编号检索"),
    name: str | None = Query(default=None, description="按场地名称检索"),
    location_type: str | None = Query(default=None, description="按场地类型检索"),
    status: str | None = Query(default=None, description="待洽谈、已签约、使用中、已退场"),
    page: int = 1,
    size: int = 20,
) -> PageResult[dict]:
    """按场地编号、名称、类型与状态过滤场地租用列表；没有数据时返回空页，不报错。"""
    if size > 200:
        raise HTTPException(status_code=400, detail="每页最多 200 条，请缩小分页范围")
    items, total = service.list_entries(
        keyword=keyword,
        name=name,
        location_type=location_type,
        status=status,
        page=page,
        size=size,
    )
    return PageResult(items=items, total=total, page=page, size=size)


@router.post("/import", response_model=LocationImportResult)
def import_entries(payload: LocationImportPayload) -> LocationImportResult:
    """导入当前筛选范围对应的场地文件；逐行返回失败原因，单行失败不阻断其他行。"""
    result = service.import_content(
        filename=payload.filename,
        content=payload.content,
        keyword=payload.keyword,
        name=payload.name,
        location_type=payload.location_type,
        status=payload.status,
        start_row=payload.start_row,
    )
    return LocationImportResult(**result)


@router.get("/export")
def export_entries(
    keyword: str | None = Query(default=None, description="按场地编号检索"),
    name: str | None = Query(default=None, description="按场地名称检索"),
    location_type: str | None = Query(default=None, description="按场地类型检索"),
    status: str | None = Query(default=None, description="待洽谈、已签约、使用中、已退场"),
) -> JSONResponse:
    """导出当前筛选条件下的场地租用清单，字段与页面所选列保持一致。"""
    items = service.export_entries(
        keyword=keyword,
        name=name,
        location_type=location_type,
        status=status,
    )
    return JSONResponse(
        content={"module": "location", "total": len(items), "items": items},
        headers={"Content-Disposition": 'attachment; filename="location-export.json"'},
    )


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
