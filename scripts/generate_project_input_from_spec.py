from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Any, Iterable

from model_spec_lib import joined, load_spec, md, object_index, text_list, validate_spec


FILES = {
    "00": "00-项目概述.md",
    "01": "01-能力目录.md",
    "02": "02-领域模型.md",
    "03": "03-状态机.md",
    "04": "04-业务规则.md",
    "05": "05-流程模型.md",
    "06": "06-调研台账摘要.md",
    "07": "07-待确认问题.md",
}


def table(headers: list[str], rows: Iterable[Iterable[Any]]) -> str:
    output = [
        "| " + " | ".join(headers) + " |",
        "|" + "|".join("---" for _ in headers) + "|",
    ]
    output.extend("| " + " | ".join(md(cell) for cell in row) + " |" for row in rows)
    return "\n".join(output)


def bullets(values: Any, empty: str = "- 无") -> str:
    items = text_list(values)
    return "\n".join(f"- {item}" for item in items) if items else empty


def field(label: str, value: Any) -> str:
    """Render one `- **label**：value` bullet.

    The downstream agent-delivery-gate input contract parses these with
    `^\\s*[-*]\\s*\\*\\*<label>\\*\\*\\s*[：:]`, so the bold markers are
    load-bearing, not cosmetic: without them every capability is reported as
    missing its goal / trigger role / inputs / outputs.
    """
    return f"- **{label}**：{md(value)}"


def gherkin_lines(criteria: list[str]) -> str:
    """Expand one-line `Given …, When …, Then …` criteria into three lines.

    The canonical spec stores each acceptance criterion as a single line, but
    `assets/templates/project-input/01-能力目录.template.md` and the downstream
    contract checker both require the three Gherkin keywords to open their own
    line. Splitting here keeps `model-spec.json` untouched while emitting the
    prescribed shape.
    """
    out: list[str] = []
    for criterion in criteria:
        text = md(criterion).strip()
        match = re.match(
            r"^Given\b(.*?)[,，]\s*When\b(.*?)[,，]\s*Then\b(.*)$",
            text,
        )
        if match:
            out.extend(
                f"{keyword}{clause.rstrip(' ,，')}"
                for keyword, clause in zip(("Given", "When", "Then"), match.groups())
            )
        else:
            # Not the uniform three-clause shape; keep it verbatim rather than
            # mangling a criterion that was authored differently.
            out.append(text)
    return "\n".join(out)


def rule_id(value: Any) -> str:
    """Map a canonical spec rule_id onto its contract-mandated `RULE-` form.

    `agent-delivery-gate/references/prd-input-contract.md` forbids bare `R-`
    because it is a prefix of both `ROLE-` and `REL-`, which makes mechanical ID
    matching depend on regex branch order. `model-spec.json` is frozen upstream
    at `development_ready`, so the compliant prefix is asserted here, at the
    projection boundary, and the canonical spec keeps its internal `R-` ids.

    This is the single authority for the mapping: the projection helpers below
    and `validate_traceability.py` both call it, so the two can never disagree.
    """
    text = "" if value is None else str(value)
    return re.sub(r"(?<![A-Za-z0-9-])R-", "RULE-", text)


def rule_ref(value: Any) -> str:
    """Backwards-compatible alias; prefer :func:`rule_id`."""
    return rule_id(value)


def rule_refs(values: Any) -> str:
    return rule_id(joined(values))


def generated_header(
    spec: dict[str, Any],
    spec_path: Path,
    requirements_graph: Path,
    bpmn_dir: Path,
    owl_path: Path,
) -> str:
    meta = spec.get("meta", {})
    return f"""<!-- GENERATED: edit model-spec.json and regenerate; do not edit generated sections independently. -->

> 来源模型：`{spec_path.as_posix()}`
> 模型基线：`{meta.get("baseline_id", "")}`
> 模型版本：`{meta.get("model_version", "")}`
> 审核状态：`{meta.get("review_status", "")}`
> 统一需求图：`{requirements_graph.as_posix()}`
> BPMN 目录：`{bpmn_dir.as_posix()}`
> OWL 模型：`{owl_path.as_posix()}`

"""


def generate_00(spec: dict[str, Any], header: str) -> str:
    meta = spec.get("meta", {})
    scope = spec.get("scope", {})
    role_rows = [
        (
            item.get("role_id"),
            item.get("name"),
            joined(item.get("responsibilities")),
            item.get("usage_frequency"),
            joined(item.get("evidence_ids")),
            item.get("notes"),
        )
        for item in spec.get("roles", [])
    ]
    scenario_rows = [
        (
            item.get("scenario_id"),
            item.get("name"),
            item.get("description"),
            joined(item.get("role_ids")),
            joined(item.get("process_ids")),
            item.get("priority"),
            joined(item.get("evidence_ids")),
            joined(item.get("question_ids")),
        )
        for item in spec.get("scenarios", [])
    ]
    constraints = scope.get("constraints", [])
    constraint_rows = [
        (
            item.get("dimension"),
            item.get("requirement"),
            item.get("source"),
            joined(item.get("evidence_ids")),
        )
        if isinstance(item, dict)
        else ("约束", item, "", "")
        for item in constraints
    ]
    metric_rows = [
        (
            item.get("metric"),
            item.get("target"),
            item.get("measurement"),
        )
        if isinstance(item, dict)
        else (item, "", "")
        for item in scope.get("success_metrics", [])
    ]
    return header + f"""# 项目概述

## 基本信息

{table(
    ["项目", "内容"],
    [
        ("项目 ID", meta.get("project_id")),
        ("项目名称", meta.get("project_name")),
        ("业务域", scope.get("business_domain")),
        ("项目阶段", meta.get("phase")),
        ("模型版本", meta.get("model_version")),
        ("模型审核人", meta.get("reviewer")),
        ("模型审核日期", meta.get("review_date")),
    ],
)}

## 业务目标

{bullets(scope.get("goals"))}

## 用户角色清单

{table(["role_id", "角色", "职责", "使用频率", "evidence_id", "备注"], role_rows)}

## 业务场景清单

{table(
    ["scenario_id", "场景名称", "场景描述", "发起角色 role_id", "关联流程 process_id", "优先级", "evidence_id", "question_id"],
    scenario_rows,
)}

## 本期包含

{bullets(scope.get("in_scope"))}

## 本期不包含

{bullets(scope.get("out_of_scope"))}

## 非功能与业务约束

{table(["维度", "要求", "来源", "evidence_id"], constraint_rows)}

## 成功度量指标

{table(["指标", "目标值", "度量方式"], metric_rows)}
"""


def generate_05(spec: dict[str, Any], header: str) -> str:
    role_index = object_index(spec, "roles")
    interface_index = object_index(spec, "interfaces")
    process_rows = []
    sections: list[str] = []
    for process in spec.get("processes", []):
        process_id = str(process["process_id"])
        nodes = process.get("nodes", [])
        flows = process.get("flows", [])
        previous: dict[str, list[str]] = {str(node["node_id"]): [] for node in nodes}
        following: dict[str, list[str]] = {str(node["node_id"]): [] for node in nodes}
        for flow in flows:
            previous[str(flow["target"])].append(str(flow["source"]))
            following[str(flow["source"])].append(str(flow["target"]))
        process_rows.append(
            (
                process_id,
                process.get("name"),
                process.get("trigger"),
                process.get("start_event"),
                process.get("end_result"),
                joined(process.get("role_ids")),
                joined(process.get("entity_ids")),
                joined(process.get("interface_ids")),
                joined(process.get("evidence_ids")),
                joined(process.get("question_ids")),
            )
        )
        node_rows = []
        for sequence, node in enumerate(nodes, start=1):
            node_id = str(node["node_id"])
            role = role_index.get(str(node.get("actor_role_id")), {})
            node_rows.append(
                (
                    node_id,
                    sequence,
                    node.get("name"),
                    node.get("type"),
                    node.get("participant_id"),
                    node.get("lane_id"),
                    joined(previous[node_id]),
                    joined(following[node_id]),
                    node.get("trigger"),
                    role.get("name") or node.get("actor_role_id"),
                    joined(node.get("inputs")),
                    joined(node.get("outputs")),
                    node.get("gateway_condition"),
                    joined(node.get("state_ids")),
                    joined(node.get("capability_ids")),
                    joined(node.get("interface_ids")),
                    rule_refs(node.get("rule_ids")),
                    joined(node.get("exception_ids")),
                    joined(node.get("evidence_ids")),
                    joined(node.get("question_ids")),
                )
            )
        flow_rows = [
            (
                flow.get("flow_id"),
                flow.get("source"),
                flow.get("target"),
                flow.get("name"),
                flow.get("condition"),
                rule_refs(flow.get("rule_ids")),
                joined(flow.get("exception_ids")),
                joined(flow.get("evidence_ids")),
                joined(flow.get("question_ids")),
            )
            for flow in flows
        ]
        exception_rows = [
            (
                item.get("exception_id"),
                item.get("trigger_node_id"),
                item.get("condition"),
                item.get("handling"),
                item.get("result_state"),
                item.get("recoverable"),
                item.get("audit_required"),
                joined(item.get("evidence_ids")),
                joined(item.get("question_ids")),
            )
            for item in process.get("exceptions", [])
        ]
        related_interface_ids = {
            ref
            for node in nodes
            for ref in text_list(node.get("interface_ids"))
        } | {
            str(item.get("interface_id"))
            for item in process.get("message_flows", [])
            if item.get("interface_id")
        }
        interface_rows = [
            (
                item.get("interface_id"),
                item.get("name"),
                item.get("direction"),
                f"{item.get('external_system', '')}/{item.get('owner', '')}",
                joined(item.get("node_ids")),
                item.get("message_object"),
                joined(item.get("payload_fields")),
                item.get("protocol_format"),
                item.get("failure_handling"),
                joined(item.get("evidence_ids")),
                joined(item.get("question_ids")),
            )
            for interface_id, item in interface_index.items()
            if interface_id in related_interface_ids or process_id in text_list(item.get("process_ids"))
        ]
        sections.append(
            f"""## {process_id} {process.get("name", "")}

来源 BPMN：`models/bpmn/{process_id}.bpmn`

### 流程节点清单

{table(
    ["node_id", "序号", "节点名称", "BPMN 元素类型", "Pool", "Lane", "前置节点", "后置节点", "触发事件", "执行角色", "输入", "输出", "网关条件", "状态变化 state_id", "关联能力 capability_id", "关联接口 interface_id", "关联规则 rule_id", "异常分支 exception_id", "evidence_id", "question_id"],
    node_rows,
)}

### 顺序流

{table(["flow_id", "源节点", "目标节点", "名称", "条件", "rule_id", "exception_id", "evidence_id", "question_id"], flow_rows)}

### 异常分支

{table(["exception_id", "触发节点 node_id", "异常条件", "处理方式", "异常后状态", "是否可恢复", "是否审计追踪", "evidence_id", "question_id"], exception_rows)}

### 外部接口

{table(["interface_id", "接口名称", "方向", "外部系统/责任方", "触发节点 node_id", "消息对象", "关键字段", "协议/格式", "失败处理", "evidence_id", "question_id"], interface_rows)}
"""
        )
    return header + f"""# 流程模型

## 流程清单

{table(["process_id", "流程名称", "触发条件", "起点事件", "终点结果", "涉及角色", "主要实体", "主要外部系统", "evidence_id", "question_id"], process_rows)}

{"".join(sections)}
"""


def generate_02(spec: dict[str, Any], header: str) -> str:
    entity_rows = [
        (
            item.get("entity_id"),
            item.get("name"),
            item.get("class_name"),
            item.get("parent_entity_id"),
            item.get("definition"),
            joined(item.get("synonyms")),
            item.get("identifier"),
            item.get("stateful"),
            item.get("core"),
            joined(item.get("evidence_ids")),
            joined(item.get("question_ids")),
            item.get("lifecycle"),
        )
        for item in spec.get("entities", [])
    ]
    relation_rows = [
        (
            item.get("relation_id"),
            item.get("source_entity_id"),
            item.get("name_en"),
            item.get("name_cn"),
            item.get("target_entity_id"),
            item.get("type"),
            item.get("cardinality"),
            item.get("required"),
            joined(item.get("process_ids")),
            joined(item.get("evidence_ids")),
            joined(item.get("question_ids")),
            item.get("description"),
        )
        for item in spec.get("relations", [])
    ]
    sections: list[str] = []
    for entity in spec.get("entities", []):
        attribute_rows = [
            (
                item.get("field_id"),
                item.get("name"),
                item.get("datatype"),
                item.get("required"),
                item.get("description"),
                item.get("constraint"),
            )
            for item in entity.get("attributes", [])
        ]
        sections.append(
            f"""### {entity.get("entity_id")} {entity.get("name")}

{table(
    ["项", "内容"],
    [
        ("Ontology 类名", entity.get("class_name")),
        ("上位类", entity.get("parent_entity_id")),
        ("业务定义", entity.get("definition")),
        ("同义词/别名", joined(entity.get("synonyms"))),
        ("唯一标识", entity.get("identifier")),
        ("来源流程", joined(entity.get("process_ids"))),
        ("来源节点", joined(entity.get("node_ids"))),
        ("证据来源", joined(entity.get("evidence_ids"))),
        ("待确认问题", joined(entity.get("question_ids"))),
    ],
)}

{table(["field_id", "字段", "类型", "必填", "说明", "约束"], attribute_rows)}
"""
        )
    return header + f"""# 领域模型

来源 OWL：`models/ontology/{spec.get("meta", {}).get("ontology_id", "ontology")}.owl`

## 实体清单

{table(["entity_id", "实体名称", "Ontology 类名", "上位类", "定义", "同义词/别名", "唯一标识", "是否有状态", "是否核心实体", "evidence_id", "question_id", "生命周期说明"], entity_rows)}

## 实体关系

{table(["relation_id", "源实体", "关系英文名", "关系中文名", "目标实体", "关系类型", "基数", "是否必需", "适用场景/流程", "evidence_id", "question_id", "说明"], relation_rows)}

## 核心实体属性

{"".join(sections)}
"""


def generate_03(spec: dict[str, Any], header: str) -> str:
    entity_index = object_index(spec, "entities")
    sections: list[str] = []
    for entity_id, entity in entity_index.items():
        entity_states = [item for item in spec.get("states", []) if item.get("entity_id") == entity_id]
        if not entity_states and not entity.get("stateful"):
            continue
        state_values: list[str] = []
        for item in entity_states:
            for state_name in (item.get("from_state"), item.get("to_state")):
                if state_name and state_name not in state_values:
                    state_values.append(str(state_name))
        transition_rows = [
            (
                item.get("state_id"),
                item.get("entity_id"),
                item.get("from_state"),
                item.get("to_state"),
                item.get("trigger"),
                item.get("node_id"),
                item.get("actor"),
                item.get("guard_condition"),
                rule_refs(item.get("guard_rule_ids")),
                joined(item.get("exception_ids")),
                bool(item.get("rollback_state")),
                item.get("rollback_state"),
                item.get("audit_required"),
                joined(item.get("evidence_ids")),
                joined(item.get("question_ids")),
            )
            for item in entity_states
        ]
        state_rows = [
            (
                value,
                value,
                "",
                not any(item.get("from_state") == value for item in entity_states),
                joined([
                    evidence_id
                    for item in entity_states
                    if value in {item.get("from_state"), item.get("to_state")}
                    for evidence_id in text_list(item.get("evidence_ids"))
                ]),
            )
            for value in state_values
        ]
        sections.append(
            f"""## {entity_id} {entity.get("name")}

### 状态清单

{table(["状态值", "状态名称", "说明", "是否终态", "evidence_id"], state_rows)}

### 状态转换表

{table(["state_id", "entity_id", "当前状态", "目标状态", "触发事件", "触发节点 node_id", "触发角色/系统", "前置条件", "关联 rule_id", "关联 exception_id", "可回退", "回退状态", "审计追踪", "evidence_id", "question_id"], transition_rows)}
"""
        )
    return header + "# 状态机\n\n" + "".join(sections)


def generate_04(spec: dict[str, Any], header: str) -> str:
    summary_rows = [
        (
            rule_ref(item.get("rule_id")),
            item.get("name"),
            item.get("type"),
            joined(item.get("capability_ids")),
            joined(item.get("process_ids")),
            joined(item.get("node_ids")),
            joined(item.get("entity_ids")),
            item.get("configurable"),
            item.get("dmn_candidate"),
            joined(item.get("evidence_ids")),
            joined(item.get("question_ids")),
        )
        for item in spec.get("rules", [])
    ]
    sections = []
    for item in spec.get("rules", []):
        input_rows = [
            (
                value.get("field"),
                value.get("source"),
                value.get("operator"),
                value.get("value"),
            )
            if isinstance(value, dict)
            else (value, "", "", "")
            for value in text_or_objects(item.get("inputs"))
        ]
        output_rows = [
            (
                value.get("field"),
                value.get("value"),
                value.get("description"),
            )
            if isinstance(value, dict)
            else (value, "", "")
            for value in text_or_objects(item.get("outputs"))
        ]
        sections.append(
            f"""### {rule_ref(item.get("rule_id"))} {item.get("name")}

{field("规则类型", item.get("type"))}
{field("关联能力", joined(item.get("capability_ids")))}
{field("关联流程", joined(item.get("process_ids")))}
{field("关联节点", joined(item.get("node_ids")))}
{field("关联实体", joined(item.get("entity_ids")))}
{field("触发时机", item.get("trigger"))}
{field("证据来源", joined(item.get("evidence_ids")))}
{field("待确认问题", joined(item.get("question_ids")))}

**输入条件**

{table(["条件字段", "来源", "运算符", "值/范围"], input_rows)}

**输出结果**

{table(["输出字段", "值/动作", "说明"], output_rows)}

**规则逻辑**

```text
{item.get("logic", "")}
```

**异常处理**：{md(item.get("exception_behavior"))}

**是否可配置**：{md(item.get("configurable"))}
"""
        )
    return header + f"""# 业务规则

## 规则总览

{table(["rule_id", "规则名称", "类型", "关联能力 capability_id", "关联流程 process_id", "关联节点 node_id", "关联实体 entity_id", "是否可配置", "是否 DMN 候选", "evidence_id", "question_id"], summary_rows)}

## 规则详细描述

{"".join(sections)}
"""


def text_or_objects(value: Any) -> list[Any]:
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


def generate_01(spec: dict[str, Any], header: str) -> str:
    rows = [
        (
            item.get("capability_id"),
            item.get("name"),
            item.get("type"),
            item.get("priority"),
            joined(item.get("process_ids")),
            joined(item.get("node_ids")),
            joined(item.get("entity_ids")),
            rule_refs(item.get("rule_ids")),
            joined(item.get("state_ids")),
            joined(item.get("interface_ids")),
            len(text_list(item.get("node_ids"))) > 1,
            item.get("phase"),
            joined(item.get("evidence_ids")),
            joined(item.get("question_ids")),
            item.get("notes"),
        )
        for item in spec.get("capabilities", [])
    ]
    sections = []
    for item in spec.get("capabilities", []):
        normal_flow = "\n".join(
            f"{index}. {step}" for index, step in enumerate(text_list(item.get("normal_flow")), start=1)
        ) or "1. 无"
        exception_flow = bullets(item.get("exception_flow"))
        criteria = rule_ref(gherkin_lines(text_list(item.get("acceptance_criteria")))) or "待补充"
        sections.append(
            f"""### {item.get("capability_id")} {item.get("name")}

{field("业务目标", item.get("goal"))}
{field("触发角色", joined(item.get("role_ids")))}
{field("输入", joined(item.get("inputs")))}
{field("输出", joined(item.get("outputs")))}
{field("关联实体", joined(item.get("entity_ids")))}
{field("关联规则", rule_refs(item.get("rule_ids")))}
{field("关联状态", joined(item.get("state_ids")))}
{field("接口依赖", joined(item.get("interface_ids")))}
{field("来源节点", joined(item.get("node_ids")))}
{field("权限要求", item.get("permission_requirement"))}
{field("审计要求", item.get("audit_requirement"))}
{field("证据来源", joined(item.get("evidence_ids")))}
{field("待确认问题", joined(item.get("question_ids")))}

**正常流程**

{normal_flow}

**异常流程**

{exception_flow}

**验收标准**

```gherkin
{criteria}
```

**不包含**

{bullets(item.get("out_of_scope"))}
"""
        )
    return header + f"""# 能力目录

## 能力总览

{table(["capability_id", "能力名称", "类型", "优先级", "关联 process_id", "来源 node_id", "关联 entity_id", "关联 rule_id", "关联 state_id", "关联 interface_id", "是否复用", "阶段", "evidence_id", "question_id", "备注"], rows)}

## 能力详细描述

{"".join(sections)}
"""


def generate_06(spec: dict[str, Any], header: str) -> str:
    evidence_rows = [
        (
            item.get("evidence_id"),
            item.get("type"),
            item.get("source"),
            item.get("date"),
            item.get("provider"),
            joined(item.get("scenario_ids")),
            joined(item.get("process_ids")),
            joined(item.get("node_ids")),
            item.get("confidence"),
        )
        for item in spec.get("evidence", [])
    ]
    fact_rows = [
        (
            item.get("fact_id") or item.get("evidence_id"),
            item.get("summary"),
            item.get("evidence_id"),
            joined(item.get("scenario_ids")),
            joined(item.get("process_ids")),
            joined(item.get("node_ids")),
            joined(item.get("capability_ids")),
            rule_refs(item.get("rule_ids")),
            item.get("confidence"),
        )
        for item in spec.get("evidence", [])
    ]
    inference_rows = [
        (
            item.get("inference_id"),
            item.get("content"),
            item.get("basis"),
            item.get("impact"),
            joined(item.get("related_ids")),
            item.get("risk"),
            joined(item.get("question_ids")),
        )
        for item in spec.get("inferences", [])
    ]
    decision_rows = [
        (
            item.get("decision_id"),
            item.get("decision"),
            item.get("date"),
            item.get("owner"),
            joined(item.get("related_ids")),
            joined(item.get("evidence_ids")),
        )
        for item in spec.get("decisions", [])
    ]
    return header + f"""# 调研台账摘要

## 调研来源

{table(["evidence_id", "来源类型", "来源描述", "日期", "提供人/确认人", "关联 scenario_id", "关联 process_id", "关联 node_id", "可信度"], evidence_rows)}

## 关键业务事实

{table(["事实编号", "业务事实", "来源 evidence_id", "关联场景 scenario_id", "关联流程 process_id", "关联节点 node_id", "关联能力 capability_id", "关联规则 rule_id", "可信度"], fact_rows)}

## 推断项清单

{table(["编号", "推断内容", "推断依据", "影响范围", "关联对象", "风险", "待确认 question_id"], inference_rows)}

## 决策记录

{table(["decision_id", "决策", "日期", "责任人", "影响对象", "evidence_id"], decision_rows)}
"""


def generate_07(spec: dict[str, Any], header: str) -> str:
    open_items = [item for item in spec.get("questions", []) if item.get("status") != "Closed"]
    closed_items = [item for item in spec.get("questions", []) if item.get("status") == "Closed"]
    rows = [
        (
            item.get("question_id"),
            joined(item.get("scenario_ids")),
            joined(item.get("process_ids")),
            joined(item.get("node_ids")),
            joined(item.get("capability_ids")),
            joined(item.get("prd_ids")),
            item.get("question"),
            item.get("category"),
            joined(item.get("impact")),
            item.get("current_assumption"),
            item.get("blocking_level"),
            item.get("mock_or_defer_strategy"),
            item.get("owner"),
            item.get("due_date"),
            item.get("status"),
        )
        for item in open_items
    ]
    closed_rows = [
        (
            item.get("question_id"),
            item.get("question"),
            item.get("resolution"),
            item.get("closed_date"),
            item.get("closed_by"),
            joined(item.get("impact")),
        )
        for item in closed_items
    ]
    high_sections = []
    for item in open_items:
        if item.get("blocking_level") != "High":
            continue
        high_sections.append(
            f"""### {item.get("question_id")} {item.get("question")}

- 当前假设：{md(item.get("current_assumption"))}
- 假设依据：{md(item.get("assumption_basis"))}
- 若假设不成立的影响：{md(joined(item.get("impact")))}
- Mock/暂缓策略：{md(item.get("mock_or_defer_strategy"))}
- 影响对象：{md(joined(item.get("related_ids") or item.get("capability_ids")))}
"""
        )
    return header + f"""# 待确认问题

## 问题清单

{table(["question_id", "scenario_id", "process_id", "node_id", "capability_id", "prd_id", "问题", "问题类型", "影响范围", "当前假设", "阻塞程度", "Mock/暂缓策略", "责任人", "期望关闭时间", "状态"], rows)}

## 高阻塞问题处理策略

{"".join(high_sections) or "无高阻塞未关闭问题。"}

## 已关闭问题

{table(["question_id", "问题", "关闭结论", "关闭时间", "确认人", "影响对象"], closed_rows)}
"""


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Generate populated docs/input/00-07 from canonical model-spec.json."
    )
    parser.add_argument("--spec", required=True, help="Path to model-spec.json.")
    parser.add_argument("--output", default="docs/input", help="Output directory.")
    parser.add_argument(
        "--requirements-graph",
        default="models/graph/requirements-graph.ttl",
        help="Validated unified requirements graph recorded in headers.",
    )
    parser.add_argument("--bpmn-dir", default="models/bpmn", help="BPMN source directory recorded in headers.")
    parser.add_argument("--owl", help="OWL source path recorded in headers.")
    parser.add_argument("--overwrite", action="store_true", help="Overwrite existing generated files.")
    args = parser.parse_args()

    spec_path = Path(args.spec)
    spec = load_spec(spec_path)
    errors = validate_spec(spec, require_approved=True)
    if errors:
        for error in errors:
            print(error, file=sys.stderr)
        return 1

    meta = spec.get("meta", {})
    requirements_graph = Path(args.requirements_graph)
    bpmn_dir = Path(args.bpmn_dir)
    owl_path = Path(args.owl or f"models/ontology/{meta.get('ontology_id', 'ontology')}.owl")
    header = generated_header(spec, spec_path, requirements_graph, bpmn_dir, owl_path)
    generators = {
        "00": generate_00,
        "01": generate_01,
        "02": generate_02,
        "03": generate_03,
        "04": generate_04,
        "05": generate_05,
        "06": generate_06,
        "07": generate_07,
    }

    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)
    for key in ("00", "05", "02", "03", "04", "01", "06", "07"):
        output = output_dir / FILES[key]
        if output.exists() and not args.overwrite:
            print(f"{output}: exists; use --overwrite", file=sys.stderr)
            return 1
        output.write_text(generators[key](spec, header), encoding="utf-8", newline="\n")
        print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
