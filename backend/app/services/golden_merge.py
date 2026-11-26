"""金记录合并领域服务：管理重复候选组按生还规则合并成金记录的任务与冲突处置。

数据链路位置：主数据加工层第三环，负责消费重复检测结果与复核结论，
把金记录派发给发布批次与交叉映射。
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.services.base import BaseModuleService
from app.store import store


def recognized_group_state(group: str) -> dict[str, Any]:
    """计算候选组在合并侧的当前认可结果：认可金记录、更正确认号与替代关系。

    认可规则：已确认更正（带更正确认号）的现行任务优先；否则取最早合并的
    现行任务——后来完成但尚未确认更正的合并不顶替原结果。
    """
    merged = [
        row for row in store.rows("golden_merge")
        if row.get("候选组") == group and row.get("status") == "已合并"
    ]
    current = [row for row in merged if row.get("现行标记", "现行") == "现行"]
    confirmed = [row for row in current if str(row.get("更正确认号", "")).strip()]
    if confirmed:
        recognized = max(confirmed, key=lambda row: int(row.get("id", 0)))
    elif current:
        recognized = min(current, key=lambda row: int(row.get("id", 0)))
    else:
        recognized = None
    replacements: list[dict[str, str]] = []
    for row in merged:
        if row.get("现行标记") != "已替代":
            continue
        confirmation = str(row.get("被更正确认号", ""))
        successor = next(
            (item for item in merged if item.get("更正确认号") == confirmation), None
        )
        replacements.append({
            "被替代金记录": str(row.get("合并结果", "")),
            "替代为金记录": str(successor.get("合并结果", "")) if successor else "",
            "更正确认号": confirmation,
        })
    return {
        "候选组": group,
        "认可金记录": str(recognized.get("合并结果", "")) if recognized else "",
        "认可合并任务ID": int(recognized["id"]) if recognized else None,
        "认可合并任务": str(recognized.get("合并任务", "")) if recognized else "",
        "更正确认号": str(recognized.get("更正确认号", "")) if recognized else "",
        "替代关系": replacements,
        "已合并产物": [str(row.get("合并结果", "")) for row in merged],
    }


class GoldenMergeService(BaseModuleService):
    MODULE = "golden_merge"
    ENTITY = "合并任务"
    OPERATION_TERM = "合并"
    LIST_FIELDS = ["合并任务", "实体编码", "候选组", "生还规则", "合并结果"]
    REQUIRED_FIELDS = ["合并任务", "实体编码", "候选组"]
    STATUS_ORDER = ["待合并", "已合并", "合并冲突"]
    ACTION_RULES = {"执行合并": "已合并", "转人工": "合并冲突"}
    NEGATIVE_ACTIONS = []

    def run_action(self, entry_id: int, action: str) -> tuple[dict[str, Any] | None, str]:
        """动作分派：执行合并产出金记录标识，确认更正登记候选组替代关系。"""
        if action == "执行合并":
            result = self.execute_with_survivor(entry_id)
            if not result.get("ok"):
                return None, str(result.get("message", "合并执行失败"))
            entry = store.find(self.MODULE, entry_id)
            return entry, f"{self.ENTITY}已执行合并，产出金记录 {result.get('golden_id', '')}"
        if action == "确认更正":
            result = self.confirm_correction(entry_id)
            if not result.get("ok"):
                return None, str(result.get("message", "更正确认失败"))
            entry = store.find(self.MODULE, entry_id)
            replaced = "、".join(result.get("替代金记录") or []) or "无"
            return entry, f"已登记更正确认号 {result.get('更正确认号', '')}，替代金记录：{replaced}"
        return super().run_action(entry_id, action)

    # ---- 业务扩展：金记录合并与发布衔接 ----

    def execute_with_survivor(self, entry_id: int) -> dict[str, Any]:
        """按生还规则执行合并，产出金记录标识。"""
        entry = store.find(self.MODULE, entry_id)
        if entry is None or entry.get("status") != "待合并":
            return {"ok": False, "message": "合并任务不在待合并状态"}
        rule = str(entry.get("生还规则", "最新优先"))
        golden_id = f"GR-{entry.get('实体编码')}-{entry_id:04d}"
        if rule == "置信度最高":
            golden_id += "-C"
        entry["合并结果"] = golden_id
        entry["现行标记"] = "现行"
        entry["status"] = "已合并"
        entry["pending"] = False
        return {"ok": True, "golden_id": golden_id, "survivor_rule": rule}

    def confirm_correction(self, entry_id: int) -> dict[str, Any]:
        """确认更正：把本任务结果登记为候选组的有效替代，生成更正确认号。

        同候选组其他现行结果被标记为已替代，发布申请据此识别版本冲突。
        """
        entry = store.find(self.MODULE, entry_id)
        if entry is None or entry.get("status") != "已合并":
            return {"ok": False, "message": "合并任务不在已合并状态，不能登记更正"}
        group = str(entry.get("候选组", ""))
        confirmation = f"COR-{entry_id:04d}"
        replaced: list[str] = []
        for other in store.rows(self.MODULE):
            if other is entry:
                continue
            if (
                other.get("候选组") == group
                and other.get("status") == "已合并"
                and other.get("现行标记", "现行") == "现行"
            ):
                other["现行标记"] = "已替代"
                other["被更正确认号"] = confirmation
                replaced.append(str(other.get("合并结果", "")))
        entry["现行标记"] = "现行"
        entry["更正确认号"] = confirmation
        return {"ok": True, "更正确认号": confirmation, "替代金记录": replaced}

    def resolve_conflict(self, entry_id: int, conclusion: str) -> str:
        """按复核结论解决合并冲突。"""
        entry = store.find(self.MODULE, entry_id)
        if entry is None or entry.get("status") != "合并冲突":
            return "任务不在冲突状态"
        if conclusion == "通过":
            entry["status"] = "已合并"
            entry["合并结果"] = f"GR-{entry.get('实体编码')}-{entry_id:04d}-R"
            entry["现行标记"] = "现行"
        else:
            entry["status"] = "待合并"
            entry["pending"] = True
        return f"冲突已按 {conclusion} 处理"

    def consume_review_results(self, entry_id: int) -> list[dict[str, Any]]:
        """读取合并复核队列的结论，回写冲突处理依据。"""
        entry = store.find(self.MODULE, entry_id)
        if entry is None:
            return []
        group = entry.get("候选组", "")
        return [r for r in store.rows("merge_review")
                if r.get("候选组") == group and r.get("status") in ("已通过", "已驳回")]

    def queue_publish(self, entry_id: int) -> dict[str, Any]:
        """提交发布申请：按合并任务幂等，重复提交只沿用原受理编号。

        申请登记引用的合并产物（候选组 + 金记录标识），清单范围由这笔
        申请决定；同实体其他候选组后来完成的结果不会进入。
        """
        entry = store.find(self.MODULE, entry_id)
        if entry is None or entry.get("status") != "已合并":
            return {"ok": False, "message": "任务未合并完成，不能提交发布申请"}
        golden_id = str(entry.get("合并结果", "")).strip()
        if not golden_id:
            return {"ok": False, "message": "合并任务还没有金记录标识，不能提交发布申请"}
        publishes = store.rows("golden_publish")
        for existing in publishes:
            if existing.get("合并任务ID") == entry_id and existing.get("status") in ("待发布", "已发布"):
                return {
                    "ok": True,
                    "reused": True,
                    "publish_id": existing.get("id"),
                    "申请编号": existing.get("申请编号", ""),
                    "message": f"该合并结果已受理，沿用原申请编号 {existing.get('申请编号', '')}",
                }
        publish_id = max((int(row.get("id", 0)) for row in publishes), default=0) + 1
        acceptance = f"PA-{publish_id:04d}"
        publishes.append({
            "id": publish_id,
            "发布批次": f"pub-{entry.get('实体编码', '')}-{publish_id}",
            "申请编号": acceptance,
            "实体编码": entry.get("实体编码", ""),
            "候选组": entry.get("候选组", ""),
            "合并任务ID": entry_id,
            "合并任务": entry.get("合并任务", ""),
            "引用金记录": golden_id,
            "领取状态": "待领取",
            "发布明细": [],
            "采用金记录": "",
            "更正确认号": "",
            "金记录数": "0",
            "发布时间": "",
            "版本标识": "",
            "status": "待发布",
            "pending": True,
            "abnormal": False,
        })
        return {
            "ok": True,
            "reused": False,
            "publish_id": publish_id,
            "申请编号": acceptance,
            "message": f"发布申请已受理，受理编号 {acceptance}",
        }

    def publish_applications(self, entry_id: int) -> dict[str, Any] | None:
        """按候选组列出发布申请：另一候选组的合并行看不到这笔申请。"""
        entry = store.find(self.MODULE, entry_id)
        if entry is None:
            return None
        group = str(entry.get("候选组", ""))
        state = recognized_group_state(group)
        recognized = state["认可金记录"]
        applications: list[dict[str, Any]] = []
        for row in store.rows("golden_publish"):
            if row.get("候选组") != group or row.get("合并任务ID") is None:
                continue
            refs = [item for item in str(row.get("引用金记录", "")).split(",") if item]
            applications.append({
                "id": row.get("id"),
                "申请编号": row.get("申请编号", ""),
                "发布批次": row.get("发布批次", ""),
                "status": row.get("status", ""),
                "领取状态": row.get("领取状态", "待领取"),
                "引用金记录": refs,
                "采用金记录": row.get("采用金记录", ""),
                "更正确认号": row.get("更正确认号", ""),
                "版本冲突": bool(recognized) and recognized not in refs,
            })
        return {
            "候选组": group,
            "合并任务ID": entry_id,
            "合并任务": entry.get("合并任务", ""),
            "合并结果": entry.get("合并结果", ""),
            "合并侧": state,
            "applications": applications,
        }

    def build_cross_map(self, entry_id: int, source_ids: list[str]) -> int:
        """为合并后的金记录建立源标识交叉映射。"""
        entry = store.find(self.MODULE, entry_id)
        if entry is None or entry.get("status") != "已合并":
            return 0
        golden_id = entry.get("合并结果", "")
        maps = store.rows("id_cross_map")
        mapped = 0
        for src in source_ids:
            map_id = max((int(r.get("id", 0)) for r in maps), default=0) + 1
            maps.append({
                "id": map_id,
                "映射批次": f"map-{entry_id}-{map_id}",
                "源系统标识": src,
                "金记录标识": golden_id,
                "映射置信度": "1.0",
                "映射状态": "已映射",
                "status": "已映射",
                "pending": False,
                "abnormal": False,
            })
            mapped += 1
        return mapped

    def record_lineage(self, entry_id: int) -> str | None:
        """登记合并任务到发布批次的血缘边。"""
        entry = store.find(self.MODULE, entry_id)
        if entry is None:
            return None
        edges = store.rows("lineage_graph")
        edge_id = max((int(r.get("id", 0)) for r in edges), default=0) + 1
        edges.append({
            "id": edge_id,
            "血缘边标识": f"edge-merge-{edge_id}",
            "上游节点": entry.get("合并任务", ""),
            "下游节点": "golden_publish",
            "变换规则": str(entry.get("生还规则", "最新优先")),
            "登记时间": datetime.now(timezone.utc).isoformat(),
            "status": "已登记",
            "pending": False,
            "abnormal": False,
        })
        return f"edge-merge-{edge_id}"
