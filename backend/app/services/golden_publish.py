"""金记录发布领域服务：管理发布申请的受理、领取确认、正式发布与回滚衔接。

数据链路位置：主数据发布层，负责消费合并产物，把发布版本
扇出给订阅方并衔接版本回滚任务。发布批次的具体内容以领取时确认的
发布明细为准；正式发出的清单保留原金记录标识，后续更正只生成可识别
的新依据，不改写已发出的明细。
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.services.base import BaseModuleService
from app.services.golden_merge import recognized_group_state
from app.store import store


def _empty_group_state(group: str) -> dict[str, Any]:
    return {
        "候选组": group,
        "认可金记录": "",
        "认可合并任务ID": None,
        "认可合并任务": "",
        "更正确认号": "",
        "替代关系": [],
        "已合并产物": [],
    }


class GoldenPublishService(BaseModuleService):
    MODULE = "golden_publish"
    ENTITY = "发布批次"
    OPERATION_TERM = "入库"
    LIST_FIELDS = ["发布批次", "实体编码", "金记录数", "发布时间", "版本标识"]
    REQUIRED_FIELDS = ["发布批次", "实体编码", "金记录数"]
    STATUS_ORDER = ["待发布", "已发布", "已回滚"]
    ACTION_RULES = {"发布批次": "已发布", "回滚批次": "已回滚"}
    NEGATIVE_ACTIONS = ["回滚批次"]

    def run_action(self, entry_id: int, action: str) -> tuple[dict[str, Any] | None, str]:
        """动作分派：发布批次走领取确认后的正式发布，回滚走版本回滚。"""
        if action == "发布批次":
            result = self.release_version(entry_id)
            if not result.get("ok"):
                return None, str(result.get("message", "发布失败"))
            entry = store.find(self.MODULE, entry_id)
            return entry, (
                f"{self.ENTITY}已发布，版本 {result.get('version', '')}；"
                f"{result.get('核对说明', '')}"
            )
        if action == "回滚批次":
            result = self.rollback_version(entry_id, reason="手动回滚")
            if not result.get("ok"):
                return None, str(result.get("message", "回滚失败"))
            entry = store.find(self.MODULE, entry_id)
            return entry, f"{self.ENTITY}已回滚批次"
        return super().run_action(entry_id, action)

    # ---- 业务扩展：发布申请的领取确认与明细核对 ----

    def claim_application(self, entry_id: int) -> dict[str, Any]:
        """领取/续领发布申请：按合并侧当前认可结果确认发布明细。

        清单范围只取申请引用候选组的合并产物；同实体其他候选组后来完成
        的结果不进入。已正式发出的申请不允许再改动明细。
        """
        entry = store.find(self.MODULE, entry_id)
        if entry is None:
            return {"ok": False, "message": f"{self.ENTITY} {entry_id} 不存在或已归档"}
        if entry.get("status") != "待发布":
            return {"ok": False, "message": "申请已正式发出，发布明细不能改动"}
        group = str(entry.get("候选组", ""))
        if not group:
            return {"ok": False, "message": "申请未关联合并候选组，不能领取"}
        state = recognized_group_state(group)
        recognized = state["认可金记录"]
        if not recognized:
            return {"ok": False, "message": "合并侧尚无已合并产物，不能领取"}
        refs = [item for item in str(entry.get("引用金记录", "")).split(",") if item]
        confirmation = state["更正确认号"]
        confirm_type = "更正确认" if confirmation else "原确认"
        detail = {
            "金记录标识": recognized,
            "合并任务ID": state["认可合并任务ID"],
            "合并任务": state["认可合并任务"],
            "确认类型": confirm_type,
            "更正确认号": confirmation,
            "替代金记录": "" if recognized in refs else "、".join(refs),
        }
        entry["发布明细"] = [detail]
        entry["采用金记录"] = recognized
        entry["更正确认号"] = confirmation
        entry["领取状态"] = "已领取"
        entry["金记录数"] = "1"
        entry["pending"] = True
        return {
            "ok": True,
            "message": f"已领取发布明细：{recognized}（{confirm_type}）",
            "entry": entry,
        }

    def application_detail(self, entry_id: int) -> dict[str, Any] | None:
        """发布申请明细：原受理单约束的范围 + 合并侧当前认可状态。

        已发出的批次返回冻结的发布明细（保留原金记录标识）；未领取的
        申请展示合并侧当前认可的标识与更正确认号，供续领时核对。
        """
        entry = store.find(self.MODULE, entry_id)
        if entry is None:
            return None
        group = str(entry.get("候选组", ""))
        state = recognized_group_state(group) if group else _empty_group_state(group)
        refs = [item for item in str(entry.get("引用金记录", "")).split(",") if item]
        recognized = state["认可金记录"]
        return {
            "id": entry.get("id"),
            "申请编号": entry.get("申请编号", ""),
            "发布批次": entry.get("发布批次", ""),
            "status": entry.get("status", ""),
            "领取状态": entry.get("领取状态", "待领取"),
            "实体编码": entry.get("实体编码", ""),
            "候选组": group,
            "合并任务ID": entry.get("合并任务ID"),
            "引用金记录": refs,
            "发布明细": entry.get("发布明细") or [],
            "采用金记录": entry.get("采用金记录", ""),
            "更正确认号": entry.get("更正确认号", ""),
            "金记录数": entry.get("金记录数", ""),
            "发布时间": entry.get("发布时间", ""),
            "版本标识": entry.get("版本标识", ""),
            "核对说明": entry.get("核对说明", ""),
            "版本冲突": bool(recognized) and recognized not in refs,
            "合并侧": state,
            "可领取": entry.get("status") == "待发布",
            "已发出": entry.get("status") in ("已发布", "已回滚"),
        }

    def verify_details(self, entry: dict[str, Any]) -> str:
        """同步核对发布明细引用的金记录与合并侧实际产物。"""
        details = entry.get("发布明细") or []
        group = str(entry.get("候选组", ""))
        state = recognized_group_state(group) if group else _empty_group_state(group)
        artifacts = set(state.get("已合并产物") or [])
        notes: list[str] = []
        for item in details:
            golden = str(item.get("金记录标识", ""))
            if golden not in artifacts:
                notes.append(f"{golden} 不在合并产物中")
        recognized = str(state.get("认可金记录", ""))
        adopted = str(entry.get("采用金记录", ""))
        if recognized and adopted and recognized != adopted:
            notes.append(f"合并侧当前认可 {recognized}，本批仍按领取时确认的 {adopted} 发出")
        return "；".join(notes) if notes else "明细与合并产物核对一致"

    # ---- 业务扩展：金记录发布与分发衔接 ----

    def release_version(self, entry_id: int) -> dict[str, Any]:
        """发布金记录版本：以领取时确认的发布明细为准，同步核对合并产物。"""
        entry = store.find(self.MODULE, entry_id)
        if entry is None or entry.get("status") != "待发布":
            return {"ok": False, "message": "发布批次不在待发布状态"}
        if entry.get("领取状态") != "已领取":
            return {"ok": False, "message": "发布申请尚未领取确认，不能发布"}
        if not (entry.get("发布明细") or []):
            return {"ok": False, "message": "发布明细为空，不能发布"}
        check = self.verify_details(entry)
        now = datetime.now(timezone.utc).isoformat()
        version = f"pub-v{entry_id}-{now[:10]}"
        entry["发布时间"] = now
        entry["版本标识"] = version
        entry["核对说明"] = check
        entry["status"] = "已发布"
        entry["pending"] = False
        return {"ok": True, "version": version, "released_at": now, "核对说明": check}

    def fanout_to_subscribers(self, entry_id: int) -> list[int]:
        """把已发布版本扇出给全部生效订阅方，生成分发批次。"""
        entry = store.find(self.MODULE, entry_id)
        if entry is None or entry.get("status") != "已发布":
            return []
        tasks = store.rows("dist_task")
        created: list[int] = []
        for sub in store.rows("subscriber_mgr"):
            if sub.get("status") != "已生效":
                continue
            task_id = max((int(r.get("id", 0)) for r in tasks), default=0) + 1
            tasks.append({
                "id": task_id,
                "分发批次": f"dist-{entry_id}-{task_id}",
                "订阅方": sub.get("订阅方标识", ""),
                "记录范围": f"版本 {entry.get('版本标识', '')}",
                "分发状态": "排队中",
                "回执状态": "未回收",
                "status": "排队中",
                "pending": True,
                "abnormal": False,
            })
            created.append(task_id)
        return created

    def rollback_version(self, entry_id: int, reason: str) -> dict[str, Any]:
        """回滚发布版本并触发版本回滚任务。"""
        entry = store.find(self.MODULE, entry_id)
        if entry is None or entry.get("status") != "已发布":
            return {"ok": False, "message": "批次未发布，无法回滚"}
        entry["status"] = "已回滚"
        entry["abnormal"] = True
        rollbacks = store.rows("version_rollback")
        rb_id = max((int(r.get("id", 0)) for r in rollbacks), default=0) + 1
        rollbacks.append({
            "id": rb_id,
            "回滚任务": f"rb-{entry_id}-{rb_id}",
            "目标版本": entry.get("版本标识", ""),
            "回滚原因": reason,
            "执行状态": "待执行",
            "影响订阅方": "",
            "status": "待执行",
            "pending": True,
            "abnormal": True,
        })
        return {"ok": True, "rollback_id": rb_id, "message": "回滚任务已创建"}

    def consume_merge_output(self, entry_id: int) -> list[dict[str, Any]]:
        """读取申请候选组内的合并产物，作为发布输入。"""
        entry = store.find(self.MODULE, entry_id)
        if entry is None:
            return []
        group = entry.get("候选组", "")
        return [m for m in store.rows("golden_merge")
                if m.get("候选组") == group and m.get("status") == "已合并"]

    def emit_stats_snapshot(self, entry_id: int) -> int:
        """发布完成后向治理看板输黄金记录数快照。"""
        entry = store.find(self.MODULE, entry_id)
        if entry is None:
            return 0
        stats = store.rows("stats_overview")
        stat_id = max((int(r.get("id", 0)) for r in stats), default=0) + 1
        stats.append({
            "id": stat_id,
            "统计时间": datetime.now(timezone.utc).isoformat(),
            "实体编码": entry.get("实体编码", ""),
            "金记录数": str(entry.get("金记录数", "0")),
            "重复率": "0%",
            "分发延迟": "0",
            "status": "正常",
            "pending": False,
            "abnormal": False,
        })
        return stat_id

    def register_publish_lineage(self, entry_id: int) -> str | None:
        """登记发布批次到分发模块的血缘边。"""
        entry = store.find(self.MODULE, entry_id)
        if entry is None:
            return None
        edges = store.rows("lineage_graph")
        edge_id = max((int(r.get("id", 0)) for r in edges), default=0) + 1
        edges.append({
            "id": edge_id,
            "血缘边标识": f"edge-pub-{edge_id}",
            "上游节点": entry.get("发布批次", ""),
            "下游节点": "dist_task",
            "变换规则": "版本分发",
            "登记时间": datetime.now(timezone.utc).isoformat(),
            "status": "已登记",
            "pending": False,
            "abnormal": False,
        })
        return f"edge-pub-{edge_id}"
