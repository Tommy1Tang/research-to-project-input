# Research to Project Input

**把业务调研材料，编译成经过语义校验、可逐条追溯、且带哈希基线的 AI 开发输入。**

一个给 AI 编码 Agent 用的「需求编译器 + 语义门禁」：业务调研先变成人可读的模型，
人工签字确认后，再编译成机器模型，然后从一个唯一事实源投影出统一 RDF 需求图、
BPMN 2.0 流程、OWL 本体和 8 份开发输入文档。任何一步都过不了闸门，就不许往下走。

```text
调研材料 ──▶ 人工确认的模型 ──▶ 唯一模型源 ──▶ RDF 需求图 ──▶ SHACL / OWL-RL / SPARQL 门禁
                                                                      │
                          开发输入 00-07 ◀── 人工二次确认 ◀── BPMN + OWL ─┘
```

<p>
<img alt="Python" src="https://img.shields.io/badge/Python-3.10%2B-3776AB?logo=python&logoColor=white">
<img alt="BPMN" src="https://img.shields.io/badge/BPMN-2.0%20%2F%20Camunda-FF6600">
<img alt="OWL" src="https://img.shields.io/badge/OWL-RL%20%2B%20SHACL-5C2D91">
<img alt="RDF" src="https://img.shields.io/badge/RDF-PROV--O-0B7285">
<img alt="self-test" src="https://img.shields.io/badge/self--test-passing-brightgreen">
<img alt="License" src="https://img.shields.io/badge/License-Apache--2.0-blue">
</p>

---

## English Overview

**Research to Project Input** is a state-controlled requirements pipeline for AI coding
agents. It converts raw business research (interviews, SOPs, process ledgers, spreadsheets)
into a traceable, semantically validated, and hash-baselined development input package.

**The problem it solves.** When an agent turns meeting notes straight into a PRD and code,
nothing distinguishes a confirmed business fact from a plausible guess made by the model, and
nobody can tell which source a requirement came from. The result is fast, confident, wrong code.

**The approach.** Three mechanisms, enforced by code rather than by prompt instructions:

1. **One canonical source.** A single `model-spec.json` is the only authoring source. The RDF
   requirements graph, BPMN, OWL, and `docs/input/00-07` are all *deterministic projections* of
   it — they can never disagree, because they can never be edited.
2. **Fail closed.** An 11-stage state machine with two mandatory human approval gates. Every
   transition is validated against recorded SHA-256 hashes. There is no `--allow-unapproved`
   bypass, and "continue", "just draft it", or "review later" is explicitly not approval.
3. **Semantic gating.** SHACL shape validation, OWL-RL deductive closure, and 6 competency
   SPARQL queries must pass *before* BPMN/OWL generation. Untraced process nodes, stateful
   entities without transitions, and open High blockers are hard errors, not warnings.

**Stack.** Python 3.10+ · rdflib · pySHACL · OWL-RL · PROV-O · BPMN 2.0 (Camunda-compatible) ·
OWL 2 · SHACL · SPARQL · JSON Schema. All runtime dependencies are vendored — the pipeline
runs fully offline with no `pip install`.

---

## 一、这个项目解决什么问题

### Why this exists

让 AI 直接读会议纪要然后写代码，是最省事、也最危险的路径。真正的成本不在生成，
而在于**没人分得清哪句是客户确认过的，哪句是模型自己编的**。等到代码写完，
追溯成本已经高到没人会去做。

```text
常见路径
  调研材料 ──▶ AI 总结 ──▶ PRD ──▶ 代码
                 ▲
                 └── 事实与推断混在一起，没有审核点，没有追溯，没有基线

本项目路径
  调研材料 ──▶ 人可读模型 ──▶ 人工签字 ──▶ 唯一机器模型 ──▶ 语义门禁 ──▶ 人工再签字 ──▶ 开发输入
                    ▲                            ▲                ▲
                批量台账格式                  哈希绑定           SHACL + 推理 + SPARQL
```

关键差别在于：**本项目把「不许跳过」写进了代码，而不是写进了提示词。**
提示词可以被说服，状态机不行。

### 它不做什么

明确划清边界，避免误解：

- ❌ 不是 AI 自动总结调研的摘要工具 —— 它要求人工在模型层签字。
- ❌ 不是 PRD 生成器 —— `docs/input/00-07` 是**开发需求输入**，PRD 是它的下游。
- ❌ 不是通用低代码平台 —— 它只负责「把需求变成可信的、可追溯的结构化模型」这一段。
- ❌ 不硬编码任何具体业务领域 —— 实验室、制造、金融只是示例，规则本身不假设行业。

---

## 二、三个核心设计决策

### 1. 单一事实源，只允许投影

`models/spec/model-spec.json` 是唯一可以被称为「源」的文件。其余产物全部是它的投影：

| 产物 | 形式 | 用途 |
|---|---|---|
| `requirements-graph.ttl` | 统一 RDF 需求图 | 把流程、实体、状态、规则、能力、证据、问题连成一张连通图 |
| `*.bpmn` | BPMN 2.0 + 完整 DI | 可在 Camunda Modeler 直接打开，画布可见 |
| `*.owl` | OWL 2 本体 | 领域类、对象属性、状态实例，含中文 IRI 与 `zh-CN` 标签 |
| `00-07-*.md` | 8 份开发输入 | 交给下游生成 PRD / Coding Task / 代码 / 测试 |

**生成物禁止手工修补。** 想改内容只有一条路：`reopen` 回到上游、改模型源、重新生成。
这条规则由 Hook 强制，而不是靠自觉 —— 因为手工改一个投影，正是让多个产物悄悄互相
矛盾的最快方式。

### 2. 失败关闭：讲「继续」不等于审批通过

11 个阶段构成严格的状态机，其中 **2 个是人工闸门**，`run-stage` 会直接拒绝跨越：

```text
initialized
  │ register-research
research_registered
  │ scaffold-review
modeling_scaffolded
  ┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓
  ┃  🔒 人工闸门 1：业务建模审核                  ┃
  ┃     对象 models/review/00-05 初版 Markdown   ┃
  ┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛
  │ approve --gate modeling --human-confirmed
modeling_review_approved
  │ validate-spec
spec_reviewed
  │ generate-graph
graph_generated
  │ validate-graph          ← SHACL + OWL-RL + 6 条 SPARQL
graph_validated
  │ generate-models
models_generated
  ┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓
  ┃  🔒 人工闸门 2：RDF / BPMN / OWL 正式模型审核 ┃
  ┃     对象图、验证报告、BPMN、OWL               ┃
  ┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛
  │ approve --gate models --human-confirmed
models_approved
  │ generate-input
development_input_generated
  │ finalize
development_ready          ← current_stage=development_ready 且 valid=true 才算就绪
```

代码层面的强制手段：

| 机制 | 实现位置 | 作用 |
|---|---|---|
| 阶段唯一 | `pipeline-definition.json` | 每个阶段只声明**一个**合法 `next_action` |
| 动作校验 | `pipeline_runner.py` | `--action` 与阶段期望不符即报错退出 |
| 闸门拒跳 | `pipeline_runner.py` | 人工闸门上调用 `run-stage` 直接抛 `PipelineError` |
| 无旁路 | 无此代码 | 不存在 `--allow-unapproved`，也不允许重新引入 |
| 人工声明 | `--human-confirmed` | AI 不得代替审核人提供该参数 |
| 防篡改 | `pipeline_guard.py` | `PreToolUse` Hook 按阶段拒绝直接写入受保护产物 |

### 3. 语义门禁：先证明模型自洽，再生成产物

图生成之后、BPMN/OWL 生成之前，必须通过三道校验。这是整个项目最核心的质量闸门：

| 校验 | 引擎 | 通过标准 |
|---|---|---|
| 规范投影比对 | rdflib 规范化图 | 需求图必须是 model-spec 的**精确**投影，逐三元组一致 |
| SHACL 约束 | pySHACL | `requirements-shapes.ttl` 全部 conforms |
| OWL-RL 推理 | OWL-RL 演绎闭包 | 一致性检查无冲突，输出 `inferred-graph.ttl` |
| 能力问题 | 6 条 SPARQL | 按 manifest 逐条满足声明的期望值 |

6 条 SPARQL 查询各自负责一类「静默失效」——这类问题不会报错，只会悄悄产出错误的需求：

| 查询 | 目标 | 期望 | 级别 |
|---|---|---|---|
| `QRY-GRAPH-001` | 没有证据、也没有待确认问题的流程节点 | empty | error |
| `QRY-GRAPH-002` | 有状态但没有任何状态迁移的实体 | empty | error |
| `QRY-GRAPH-003` | Must 级能力缺少节点引用或验收标准 | empty | error |
| `QRY-GRAPH-004` | 未关闭的 High 级阻塞问题 | empty_when_approved | review |
| `QRY-GRAPH-005` | 被多个流程节点复用的能力（复用性检查） | informational | info |
| `QRY-GRAPH-006` | 流程节点 → 能力/实体/规则的影响面地图 | informational | info |

> `QRY-GRAPH-005` 是一个刻意设计的反重复开发机制：同一能力被多个流程引用时，
> 它们必须指向**同一个** `capability_id`，而不是每个流程各生成一份实现。

---

## 三、可追溯性：每个事实都能追到它的来源

### Provenance

统一需求图用 **PROV-O** 记录来源链，把生成的产物、模型元素、来源证据和责任人连起来：

```text
prov:Entity   调研证据 / model-spec.json / 生成的图
prov:Activity 生成、校验、审核活动
prov:Agent    审核人
```

因此以下问题都能在图查询里回答，而不是靠翻聊天记录：

- 这条业务规则，依据的是哪份证据？
- 这个流程节点，是谁在什么时候确认的？
- 如果这条规则要改，会影响哪些能力、实体和流程？

### 追溯与就绪判定

`development_ready` 不是「脚本跑完了」，而是一组硬性条件的合取：

- 无悬空或缺失的稳定 ID，无双向追溯不一致；
- 无不可达流程节点，每个异常分支在 BPMN 中都有真实路径；
- 每个有状态实体都关联状态机或待确认问题；
- 每条规则都关联输入、输出、触发条件与流程/实体；
- 已批准基线中不存在未关闭的 High 级阻塞问题；
- SHACL conforms，OWL-RL 一致性无违规，全部强制 SPARQL 达标；
- BPMN / OWL / `00-07` 均为精确投影，**零哈希漂移**。

---

## 四、确定性生成：同样的输入，字节级相同的输出

这是让「哈希基线」真正有意义的前提。项目为此做了三件事：

1. **RDF 规范化再序列化** —— 经 `to_canonical_graph()` 处理并排序后输出，
   消除空白节点编号和三元组顺序带来的不确定性。
2. **统一写入约定** —— 全部产物固定 UTF-8、`\n` 换行，不随平台变化。
3. **基线清单** —— `baseline-manifest.json` 记录所有产物的 SHA-256，
   `validate` 逐步复核；一旦漂移，任务不得被报告为完成。

副作用是：产物之间可以逐字节 diff，`reopen` 后的重新生成结果可验证，
「模型有没有被偷偷改过」成为一个可计算的问题。

### 中文建模不牺牲技术标识

项目要求在业务侧全面使用中文，同时保持技术标识稳定 —— 二者通过一层显式映射解耦：

| 类型 | XML ID / OWL IRI | 中文业务名称 | 稳定标识 |
|---|---|---|---|
| BPMN 节点 | `ND-IMPORT-TASK` | 导入工单 | XML `id` |
| BPMN 网关 | `GW-TASK-COMPLETE` | 任务数据是否完整 | XML `id` |
| OWL 类 | `#工单` | 工单 | `trace:稳定标识 = ENT-TEST-TASK` |
| OWL 对象属性 | `#工单_产生_处理结果` | 产生 | `trace:稳定标识 = REL-TASK-RESULT` |

下游代码和测试引用 ASCII 稳定标识；界面、图形与业务文档使用中文名称。
**W3C 标准 URI（`rdf:type`、`rdfs:subClassOf` 等）不改名**，只补充 `zh-CN` 显示标签。

---

## 五、30 秒验证

不需要任何 API Key、不需要联网、不需要 `pip install`（依赖已 vendored）。

```bash
git clone https://github.com/Tommy1Tang/research-to-project-input.git
cd research-to-project-input
python scripts/self_test.py
```

预期输出：

```text
PASS self-test: state machine, human gates, hooks, generation, semantic traceability,
High blockers, baseline, and drift detection
```

这个回归测试会在临时目录里跑完整条链路，并且**包含大量负向用例** ——
它不只断言「正常能跑通」，还会断言「该拦的必须拦住」（即 `expected=1` /
`expected=2` 的退出码断言，覆盖漂移、越权和旁路尝试）：

```text
✓ 阶段状态机与合法转移
✓ 两个人工闸门的拒绝行为（未审批时 run-stage 必须失败）
✓ 未审批生成旁路阻断
✓ 统一需求图 / BPMN / OWL / 00-07 生成
✓ PROV-O 来源链、SHACL、SPARQL、OWL-RL 推理
✓ RDF 空白节点规范化与可重复哈希
✓ 中文名称、中文 IRI、zh-CN 标签、trace:稳定标识 的正向与负向门禁
✓ 控制 JSON / 控制 BPMN / 流水线 OWL / 状态模板一致性
✓ High 级阻塞问题、基线哈希与漂移检测
✓ PreToolUse 与 Stop Hook
```

也可以单独校验内置的完整示例模型：

```bash
python scripts/validate_model_spec.py assets/model-spec.example.json
# -> OK assets/model-spec.example.json
```

`assets/model-spec.example.json` 是一个字段完整的工单处理领域样例（已批准状态），
可以直接用来看清 `model-spec.json` 到底长什么样。

---

## 六、目录结构

```text
research-to-project-input/
├── SKILL.md                          AI 执行规则（强制控制模式、门禁边界）
├── README.md                         本文件：项目概览
├── docs/USAGE.md                     完整操作手册（逐条命令）
├── agents/openai.yaml                Agent 接入定义
│
├── references/                       契约层：把规则写成可校验的契约，而非散文
│   ├── pipeline-definition.json      可执行阶段契约（11 阶段 / 转移 / 门禁 / 不变量）
│   ├── pipeline-process.bpmn         流水线自身的 BPMN 流程视图（中文 + 完整 DI）
│   ├── pipeline-ontology.owl         流水线自身的 OWL 语义视图
│   ├── graph-engineering-contract.md 统一需求图与语义验证契约
│   ├── modeling-contract.md          建模 Markdown 契约
│   ├── model-spec-contract.md        唯一模型源契约
│   ├── bpmn-output-contract.md       BPMN 投影契约
│   ├── owl-output-contract.md        OWL 投影契约
│   ├── output-contract.md            00-07 输出契约
│   ├── workflow.md                   端到端追溯与就绪定义
│   └── pipeline-commands.md          命令与恢复流程
│
├── scripts/                          执行层：17 个 Python 模块
│   ├── pipeline_runner.py            状态机执行器（11 阶段、门禁、哈希、reopen）
│   ├── pipeline_guard.py             Codex Hook 守卫（PreToolUse / Stop）
│   ├── model_spec_lib.py             模型源加载、引用校验、中文门禁
│   ├── graph_runtime.py              离线 RDF 运行时装配（rdflib / pySHACL / OWL-RL）
│   ├── generate_requirements_graph.py 统一 RDF 需求图 + PROV-O 生成器
│   ├── generate_bpmn_from_spec.py    BPMN 2.0 + DI 生成器
│   ├── generate_owl_from_spec.py     OWL 2 生成器（中文 IRI + zh-CN 标签）
│   ├── generate_project_input_from_spec.py  00-07 生成器
│   ├── scaffold_modeling_review.py   生成建模 Markdown 台账骨架
│   ├── scaffold_project_input.py     按模板生成 00-07 骨架
│   ├── validate_graph_engineering.py SHACL + SPARQL + OWL-RL 门禁
│   ├── validate_traceability.py      端到端追溯与投影一致性
│   ├── validate_pipeline_control.py  控制模型四向一致性（JSON/BPMN/OWL/模板）
│   ├── validate_model_artifacts.py   BPMN / OWL 文件级校验
│   ├── create_baseline_manifest.py   SHA-256 基线清单
│   └── self_test.py                  全链路回归测试（含负向用例）
│
├── assets/
│   ├── model-spec.schema.json        模型源 JSON Schema
│   ├── model-spec.example.json       完整领域示例（工单处理）
│   ├── requirements-graph-ontology.ttl  需求图词汇与 OWL 公理
│   ├── requirements-shapes.ttl       SHACL 约束
│   ├── sparql/                       6 条能力问题查询 + manifest
│   └── templates/project-input/      00-07 模板
│
└── vendor/                           离线运行时（rdflib / pySHACL / OWL-RL 等）
```

---

## 七、技术栈

| 领域 | 选型 | 在本项目中的作用 |
|---|---|---|
| 语义网 | rdflib 7.6 | RDF 图构建、规范化、精确投影比对 |
| 约束校验 | pySHACL 0.40 | 需求图结构约束的机器可判定校验 |
| 本体推理 | OWL-RL 7.6 | 演绎闭包与一致性检查 |
| 来源建模 | PROV-O | 证据 → 模型 → 产物 → 责任人 的追溯链 |
| 流程建模 | BPMN 2.0 / Camunda | 可被业务方直接打开审阅的流程产物 |
| 本体建模 | OWL 2 | 领域类、属性、状态实例的形式化表达 |
| 查询 | SPARQL 1.1 | 6 条能力问题，覆盖复用性与影响面分析 |
| 契约 | JSON Schema | 模型源的编辑器级校验 |
| 控制 | JSON + BPMN + OWL 四向一致 | 流水线定义自身也被校验，防止定义漂移 |
| 语言 | Python 3.10+ | 执行器、生成器、校验器，全部零第三方安装 |

---

## 八、工程规模

| 项目 | 数量 |
|---|---|
| Python 执行层 | 17 个模块 / 约 6,500 行 |
| 契约与规则文档 | 9 份 / 约 1,400 行 |
| 流水线阶段 | 11 个（含 2 个人工闸门） |
| SPARQL 能力问题 | 6 条 |
| 开发输入模板 | 8 份 |
| 回归测试 | 全链路，含大量负向断言 |
| 运行时依赖安装 | 0（全部 vendored，可离线运行） |

---

## 九、接入方式

在 Codex 中明确调用：

```text
$research-to-project-input
```

```text
使用 $research-to-project-input，将这些调研材料纳入需求流水线。
先检查当前状态，只执行允许的下一阶段，不要跨过人工审核门禁。
```

无论人工还是 AI 恢复任务，第一步永远是查状态、问下一步，而不是直接动手：

```bash
python scripts/pipeline_runner.py --project-root <project-root> status
python scripts/pipeline_runner.py --project-root <project-root> next
```

`next` 只会返回**当前唯一合法**的动作。完整命令、两个审批闸门的具体参数、
受控返工（`reopen`）与常见问题，见 **[docs/USAGE.md](docs/USAGE.md)**。

---

## 十、已知边界

诚实说明当前实现的范围与局限：

- **人工闸门依赖流程纪律。** `--human-confirmed` 是「人在回路」的声明，
  由协议约束；Agent 在缺少明确人工确认时不得提供该参数。
- **Hook 是额外防线，不是唯一防线。** Hook 需要宿主（Codex）信任后才生效；
  即使 Hook 未生效，Runner 的阶段校验和哈希校验仍然独立成立。
- **`model-spec.json` 目前由人与 AI 协作编制**，再经校验器把关，
  而不是由 Markdown 全自动编译 —— 这一步保留了刻意的设计自由度。
- **BPMN/OWL 面向业务可读性与追溯完整性优化**，而非面向可执行流程引擎部署。
- 项目文档以中文为主，因此领域词汇、IRI 与标签体系均围绕中文建模设计。

---

## 十一、许可

本项目采用 **Apache License 2.0** 授权，全文见 [LICENSE](LICENSE)。

```text
Copyright 2026 tommytang

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0
```

`vendor/` 目录中的第三方依赖保留其各自的原始许可证，均随包附带：

| 依赖 | 许可证 |
|---|---|
| rdflib 7.6 | BSD-3-Clause |
| pySHACL 0.40 | Apache-2.0 |
| OWL-RL 7.6 | W3C-20150513 |
| prettytable 3.18 | BSD-3-Clause |
| html5rdf 1.2.1 | MIT |
| pyparsing 3.3.2 | MIT |
| wcwidth 0.8.2 | MIT |
| packaging 26.2 | Apache-2.0 OR BSD-2-Clause |

详见各 `vendor/*.dist-info/` 目录中的 `LICENSE` 文件。

---

## 文档导航

| 文档 | 内容 |
|---|---|
| **README.md**（本文件） | 项目定位、架构决策、快速验证 |
| [docs/USAGE.md](docs/USAGE.md) | 完整操作手册：初始化、注册调研、审批、返工、验收 |
| [SKILL.md](SKILL.md) | AI 执行规则与强制控制模式 |
| [references/workflow.md](references/workflow.md) | 端到端追溯与开发就绪定义 |
| [references/pipeline-definition.json](references/pipeline-definition.json) | 可执行的阶段契约（唯一权威） |
| [LICENSE](LICENSE) | Apache License 2.0 全文 |

遇到规则冲突时，以 `SKILL.md`、`pipeline-definition.json` 和
`pipeline_runner.py` 的门禁结果为准。
