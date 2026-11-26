"""统一资源接口：查询、导出、登记和动作按模块 key 分派到领域服务。"""
from __future__ import annotations

import csv
import io
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import StreamingResponse

from app.schemas import ActionPayload, ActionResult, EntryPayload, PageResult
from app.services import service_for

router = APIRouter(prefix="/api", tags=["业务资源"])


def require_service(module: str):
    service = service_for(module)
    if service is None:
        raise HTTPException(status_code=404, detail=f"未知业务模块：{module}")
    return service


@router.get("/{module}", response_model=PageResult[dict])
def list_entries(
    module: str,
    request: Request,
    keyword: str | None = Query(default=None),
    status: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    size: int = Query(default=20, ge=1, le=200),
) -> PageResult[dict]:
    service = require_service(module)
    filters = {
        key: value.strip()
        for key, value in request.query_params.items()
        if key in service.LIST_FIELDS and value.strip()
    }
    items, total = service.list_entries(
        filters=filters, keyword=keyword, status=status, page=page, size=size)
    return PageResult(items=items, total=total, page=page, size=size)


@router.get("/{module}/export")
def export_entries(
    module: str,
    request: Request,
    keyword: str | None = Query(default=None),
    status: str | None = Query(default=None),
) -> StreamingResponse:
    service = require_service(module)
    filters = {
        key: value.strip()
        for key, value in request.query_params.items()
        if key in service.LIST_FIELDS and value.strip()
    }
    items, _ = service.list_entries(
        filters=filters, keyword=keyword, status=status, page=1, size=1_000_000)
    output = io.StringIO()
    output.write("\ufeff")
    writer = csv.writer(output, lineterminator="\n")
    writer.writerow(["id", *service.LIST_FIELDS, "status"])
    for item in items:
        values = [item.get("id"), *(item.get(field, "") for field in service.LIST_FIELDS),
                  item.get("status", "")]
        writer.writerow([
            "'" + str(value) if str(value or "").startswith(("=", "+", "-", "@")) else value
            for value in values
        ])
    return StreamingResponse(
        iter([output.getvalue()]), media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{module}.csv"'},
    )


@router.get("/golden_merge/{entry_id}/publish_applications", response_model=dict)
def merge_publish_applications(entry_id: int) -> dict[str, Any]:
    """合并行的发布申请列表：按候选组归集，另一候选组看不到这笔申请。"""
    service = require_service("golden_merge")
    payload = service.publish_applications(entry_id)
    if payload is None:
        raise HTTPException(status_code=404, detail=f"合并任务 {entry_id} 不存在或已归档")
    return payload


@router.post("/golden_merge/{entry_id}/publish_application", response_model=ActionResult)
def submit_publish_application(entry_id: int) -> ActionResult:
    """提交发布申请：幂等受理，重复提交沿用原受理编号。"""
    service = require_service("golden_merge")
    result = service.queue_publish(entry_id)
    return ActionResult(
        ok=bool(result.get("ok")),
        message=str(result.get("message", "")),
        entry=result,
    )


@router.get("/golden_publish/{entry_id}/application", response_model=dict)
def publish_application_detail(entry_id: int) -> dict[str, Any]:
    """发布申请明细：原受理单约束的范围 + 合并侧当前认可状态。"""
    service = require_service("golden_publish")
    payload = service.application_detail(entry_id)
    if payload is None:
        raise HTTPException(status_code=404, detail=f"发布批次 {entry_id} 不存在或已归档")
    return payload


@router.post("/golden_publish/{entry_id}/claim", response_model=ActionResult)
def claim_publish_application(entry_id: int) -> ActionResult:
    """领取/续领发布申请：按合并侧当前认可结果确认发布明细。"""
    service = require_service("golden_publish")
    result = service.claim_application(entry_id)
    return ActionResult(
        ok=bool(result.get("ok")),
        message=str(result.get("message", "")),
        entry=result.get("entry") if result.get("ok") else None,
    )


@router.get("/{module}/{entry_id}", response_model=dict)
def get_entry(module: str, entry_id: int) -> dict[str, Any]:
    service = require_service(module)
    entry = service.get_entry(entry_id)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"{service.ENTITY} {entry_id} 不存在或已归档")
    return entry


@router.post("/{module}", response_model=ActionResult)
def create_entry(module: str, payload: EntryPayload) -> ActionResult:
    service = require_service(module)
    entry, missing = service.create_entry(payload.values)
    if missing:
        return ActionResult(ok=False, message=f"缺少必填字段：{'、'.join(missing)}")
    return ActionResult(ok=True, message=f"{service.ENTITY}已登记", entry=entry)


@router.post("/{module}/{entry_id}/actions", response_model=ActionResult)
def run_action(module: str, entry_id: int, payload: ActionPayload) -> ActionResult:
    service = require_service(module)
    entry, message = service.run_action(entry_id, payload.action.strip())
    return ActionResult(ok=entry is not None, message=message, entry=entry)
