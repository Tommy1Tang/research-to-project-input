from __future__ import annotations

import argparse
from pathlib import Path


FILES = {
    "00-建模范围.md": """# 建模范围

## 项目与阶段

## 建模目标

## 包含范围

## 不包含范围

## 审核人

""",
    "01-流程建模台账.md": """# 流程建模台账

| process_id | node_id | bpmn_element_type | pool | lane | node_name | actor | trigger | input | output | prev_node_id | next_node_id | gateway_condition | exception_id | interface_id | evidence_id | question_id |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|

""",
    "02-领域建模台账.md": """# 领域建模台账

## 实体 / Class

| entity_id | entity_name | ontology_class | parent_class | synonym | key_attributes | source_process_id | source_node_id | evidence_id | question_id |
|---|---|---|---|---|---|---|---|---|---|

## 关系 / ObjectProperty

| relation_id | source_entity_id | relation_name_en | relation_name_cn | target_entity_id | cardinality | source_process_id | evidence_id | question_id |
|---|---|---|---|---|---|---|---|---|

""",
    "03-状态与规则台账.md": """# 状态与规则台账

## 状态流转

| state_id | entity_id | from_state | trigger | to_state | actor | source_node_id | guard_rule_id | rollback_state | audit_required | evidence_id | question_id |
|---|---|---|---|---|---|---|---|---|---|---|---|

## 业务规则

| rule_id | rule_name | rule_type | process_id | node_id | entity_id | trigger | inputs | outputs | logic | exception_behavior | evidence_id | question_id |
|---|---|---|---|---|---|---|---|---|---|---|---|---|

""",
    "04-接口与消息台账.md": """# 接口与消息台账

| interface_id | external_system | process_id | node_id | direction | trigger | message_object | payload_fields | frequency | owner | failure_handling | evidence_id | question_id |
|---|---|---|---|---|---|---|---|---|---|---|---|---|

""",
    "05-证据与待确认问题.md": """# 证据与待确认问题

## 证据

| evidence_id | evidence_type | source | related_process_id | related_node_id | summary | file_or_link |
|---|---|---|---|---|---|---|

## 待确认问题

| question_id | question | category | related_process_id | related_node_id | current_assumption | blocking_level | owner | status |
|---|---|---|---|---|---|---|---|---|

""",
    "06-模型审核记录.md": """# 模型审核记录

| review_id | model_file | model_type | version | reviewer | review_date | conclusion | required_changes | approved_scope |
|---|---|---|---|---|---|---|---|---|

## 统一模型源编制

| baseline_id | model_version | model_spec_file | review_status | BPMN 审核结论 | OWL 审核结论 | 是否允许生成 00-07 |
|---|---|---|---|---|---|---|
| BASELINE-XXX | 0.1.0 | models/spec/model-spec.json | draft/reviewed/approved | | | 否 |

""",
}


def scaffold(output_dir: Path, overwrite: bool) -> list[Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    created: list[Path] = []
    for name, content in FILES.items():
        target = output_dir / name
        if target.exists() and not overwrite:
            continue
        target.write_text(content, encoding="utf-8", newline="\n")
        created.append(target)
    return created


def main() -> int:
    parser = argparse.ArgumentParser(description="Create modeling-review Markdown skeleton files.")
    parser.add_argument("--output", default="models/review", help="Output directory. Default: models/review")
    parser.add_argument("--overwrite", action="store_true", help="Overwrite existing files.")
    args = parser.parse_args()
    for path in scaffold(Path(args.output), args.overwrite):
        print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
