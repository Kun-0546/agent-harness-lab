# Harness Design Loop · 设计方案 v0.4.1

> 这版做什么:把 v0.4 的原则落成可执行的结构。
> v0.4 的原则不变(§1)。改动:四种模式 → authority matrix + preset;锚点加第四个(红线);喊人触发 → 带阈值的可计算规则;calibration 独立成一等结构;provenance 分两层;新增 brief.md 与 review.md 两个人机入口;路线在 v2、v3 之间加一档 v2.5。
> 取代 v0.4 草稿。v0.3 的 §0–§5、§7(接入、评测、文件格式骨架)仍有效。
> 日期:2026-05-18。这是执行方案,不是实现 —— 仍不写代码。

> **当前实现状态(2026-05-19 更新)**:v2-minimal 已把本文里的 "Designer Agent" 这条收束为 **external coding agent authored workflow** —— HDL 不内置 Designer LLM,起草是外层 coding agent(Claude Code / Cursor / Codex)的活。代码层面以 `v2-minimal-spec.md` 为准;本文是长期产品架构,保留 Designer Agent 的概念词供后续 v2.5 / v3 / v4 阶段使用。

---

## 1. 原则(承自 v0.4,不变)

agent 操作闭环,人拥有锚点。

hdl 这个域没有免费的固定点:「这个 agent 作为产品更好了吗」是个判断,它的 ground truth 是人的产品判断。所以工具可以越来越自动,但锚点必须留在人手上。下面整份文档,都是在回答一件事:锚点具体是什么、长在哪、怎么不被绕过。

---

## 2. 四个锚点

v0.4 列了三个,这版加第四个。

1. **目标所有权** —— agent 可提议改目标,接受的是人。
2. **rubric / judge 校准权** —— 这套 proxy 还跟不跟得上你真正在乎的,由人定期校。
3. **结论解释权** —— compare 出的是证据,读成产品决策的是人。
4. **红线所有权**(新增)—— 哪些退化,无论总分怎么涨都不可接受。

红线不等于 goal,也不等于 rubric。goal 说「往哪走」,rubric 给维度打分,红线是 guardrail —— 「可以更主动,但不能变烦」「可以更深入,但不能啰嗦」「可以更像顾问,但不能机械套框架」这一类。它是人写的、人改的;agent 不能放宽红线。

红线跨实验稳定,住在 goal 层(`goal.md` 的一个 `## 红线` 段);brief.md 每次再问一遍「这次什么不能牺牲」,可往上补。

单列它的原因:它直接决定 §5 里 `critical_regression` 盯哪些维度 —— 把「某关键维度退化就喊人」从一句模糊的话,变成一份人指定的清单。

---

## 3. authority matrix —— 分工的底层模型

v0.4 §2 的三层权力(生成 / 执行 / 锚点)是粗分。落地用一张 per-stage 的 authority matrix:loop 的每个阶段,各挂一个 authority 值。

**阶段**(10 个):

```
goal  program  versions  cases  rubric  simulator  run  score  compare  keep_discard
```

**authority 取值**(5 档):

| 值 | 含义 |
|---|---|
| `human_owned` | 人写、人改,agent 不碰 |
| `agent_drafted_human_approved` | agent 起草,人逐项批准才生效 |
| `agent_drafted_human_sampled` | agent 起草,人抽查(不逐项) |
| `agent_drafted_human_interpreted` | agent 出草稿 / 结论,人做最终解释 |
| `agent_operated` | agent 自动执行,不停 |

§8 的两个入口是人在这张表上行使权力的界面:brief.md 是 `human_owned` 阶段的输入口,review.md 是 `*_human_approved / _sampled / _interpreted` 阶段的审核口。

---

## 4. 四种模式 = 四个 preset

**模式不硬编码成四档。** 底层是 §3 的 matrix;四种模式是四个常用 preset。MVP 实现这四个 preset,不开放完整矩阵编辑 —— 但文件格式把整张 matrix 留好,以后能开。(这是 v0.4 §10 的定稿。)

matrix 记在 program.md 里。人选一个 mode,preset 展开成完整 matrix;program.md 从 Mode 2 起由 Designer Agent 生成,matrix 随它一起被人审。

**Mode 2 · Agent-Drafted Lab** 的 preset:

```yaml
mode: agent_drafted
authority:
  goal:         human_owned
  program:      agent_drafted_human_approved   # 由 brief.md 经 Designer Agent 生成
  versions:     agent_drafted_human_approved
  cases:        agent_drafted_human_sampled
  rubric:       agent_drafted_human_approved
  simulator:    agent_drafted_human_approved
  run:          agent_operated
  score:        agent_operated
  compare:      agent_drafted_human_interpreted
  keep_discard: human_owned
```

四个 preset 的差别,就是这张表整体往「人」或往「agent」挪:

- **Mode 1 Manual** —— 除 run / score(本就机械)外全 `human_owned`。
- **Mode 2 Agent-Drafted** —— 见上。人写 brief,agent 起草整包,人审 anchor 后跑。
- **Mode 3 Agent-Operated** —— versions / cases / compare 往 `agent_operated` 挪,keep_discard 仍 `human_owned`,靠 §5 的喊人规则兜底。
- **Mode 4 Self-Improving** —— 加上「实验方法」本身可被 agent 改(见 §9 v4)。

> 一处修正:v0.4 §4 的 Mode 2 草稿把 `program` 标成 `human_owned`。这版改了 —— 引入 brief.md 之后,人写的是 brief,不是 program;program 由 Designer Agent 生成,所以是 `agent_drafted_human_approved`。

---

## 5. 喊人触发 —— 带阈值的可计算规则

v0.4 §5 的触发器是对的,但停在描述层。落代码前必须给阈值,否则会被实现成「报告里写句 warning」、并不真正拦 workflow。

分两类门 + 一个资源闸。

**锚点改动门**(agent 想动锚点 → 必须人批):rubric 被改、目标被改、红线被改。

**结果异常报警 + 资源闸**(可计算,给 schema):

```yaml
escalation:                    # Mode 3 操作协议的一部分,人批准一次;阈值可调
  score_spike:                 # 分数异常跳升
    enabled: true
    threshold: 1.0             # 单轮总分涨幅超过即喊人
  no_discrimination:           # 全高分但分不开
    enabled: true
    min_mean_score: 8.0
    max_delta_between_versions: 0.2
  critical_regression:         # 红线维度退化
    enabled: true
    dimensions: ["简洁性", "事实准确性", "安全边界"]   # ← 来自 §2 的红线
    threshold: -0.5
  judge_disagreement:          # 多 judge 分歧过大
    enabled: true
    min_judges: 3
    max_std: 0.8
  budget:                      # 资源闸
    max_rounds: 5
    max_cost_usd: 20
```

`critical_regression.dimensions` 不是随手写的 —— 它就是 §2 第四个锚点(红线)那份清单。红线锚点和这条规则是同一件事的两端:人那头声明,规则这头执行。

---

## 6. Calibration —— 独立的一等结构

**calibration set 不是测试集的一部分。** 两者职责不同:

- `experiments/NNN/测试集/` —— test cases,测「当前 agent 在当前实验目标上的表现」。
- `calibration/` —— 测「评测系统自己还可不可信」。

说白了:test cases 测 agent;calibration 测 judge / rubric / method;adversarial bad versions 测整个 evaluation harness。所以 calibration 单独成目录,workspace 级(一套评测系统跨实验共用):

```
calibration/
├── golden/                人判过的高价值案例 —— 校 judge 还懂不懂你的偏好
├── sentinel/              抓系统性退化的探针 —— 简单问题会不会过度展开,等等
└── adversarial_versions/  故意的坏版本 —— 测整个 harness 分不分得出好坏
```

三类都**冻结**,放在 agent 的优化够不到的地方(v0.4 §6):人来种,或做成固定库;不让跑评测的 agent 每轮现生。

**adversarial bad versions 不进 `experiments/NNN/versions/`。** 普通 versions(V1/V2/V3)是你真想比的候选;adversarial 是评测系统的探针。两者混在一起,报告会很乱。所以目录上分开(见上),compare 报告里也分两块:

```
候选对比 Candidate comparison
  V2 vs V1   总分 +0.5

Harness 自检 Harness sanity check
  Bad-AlwaysAsk      应输给 V1          —— 通过
  Bad-FrameworkSpam  应在「简洁性」失分 —— 未通过
```

Harness 自检没过,意味着这次实验的结论本身不可信 —— 比单看 V1/V2 那个 +0.5 更早、更强的信号。

---

## 7. Provenance —— 分两层

v0.4 §8 只说了 artifact 来源,不够。分两层。

**artifact provenance** —— 每个文件谁生成、谁批准。写进各 artifact 的 frontmatter:

```yaml
provenance:
  source: human | agent_drafted | agent_auto
  approved_by: <谁>            # source 为 agent_drafted 时必填
  approval_state: pending | approved
```

**run provenance** —— 这次结果是在什么评测配置下跑出来的。写进 `results/run-*.json`、`score-*.json`:

```yaml
run_provenance:
  judge_model: <模型>          judge_prompt: <版本>
  simulator_model: <模型>      simulator_prompt: <版本>
  run_mode: 模拟 | 回放 | 固定
  compare_mode: 对基线 | 线性迭代
  calibration_version: <calibration set 版本>
  authority_mode: <Mode 1–4 / 自定义 matrix>
```

为什么要 run provenance:同一个 V2 的 +0.5,用 stub grader 得到、用 GPT judge 得到、用人校准过的 judge 得到 —— 不是同一个证据等级。不记下来,读报告的人没法判断该多信它。

compare 报告头部带一段 provenance 摘要:

```
Versions:    V1 人写, V2 agent 起草·人已批
Cases:       agent 起草, 人抽查 5/20
Rubric:      agent 起草, 人已批, 基于 calibration-set-v3 校准
Judge:       gpt-xx, prompt v2, calibration 通过
Simulator:   本地桩
```

---

## 8. 两个人机入口

agent 多做之后,人和系统之间要有两个干净的界面,否则「人拥有锚点」只是嘴上说。

### brief.md —— 人的自然语言入口

不让用户直接写 program.md。program.md 带 假设 / 声明 / 留丢规则 / 喊人规则 / 运行模式 / 对话模式 / 对比方式 —— 对用户偏 DSL。

新增 `brief.md`,只问几个自然语言问题:

```
- 你想优化什么?
- 想验证哪个变化?
- 你最在意什么?
- 什么不能牺牲?          ← 喂 §2 的红线
- 希望怎么比较?
```

Designer Agent 据 brief.md 生成正式的 program.md / versions/ / 测试集/ / rubric.md / 模拟器.md。**brief.md 是人的入口,program.md 是系统执行协议** —— 两层分开。

### review.md —— Review Packet

agent 起草一整包之后,不能让人去翻五六个文件做 review。系统生成一个 `review.md`,只列人必须看的:

```
1  本次实验目标摘要
2  V1 / V2 的核心差异
3  rubric 维度与权重
4  不可牺牲项(红线)
5  case 覆盖地图
6  calibration / golden 是否通过
7  provenance 摘要
8  需要人批准的变更
```

这是「人拥有锚点」的产品化。没有它,人理论上握着锚点,实际会被文件淹没、退化成橡皮图章。

---

## 9. 路线 v1 / v2 / v2.5 / v3 / v4

每一档的安全,靠上一档的地基。

**v1 · Trusted Manual Loop**(当前)—— run / score / compare 可信;坏输入拒绝运行;版本隔离;文档与代码一致;stub / real judge 分清楚。当前在做的就是这个(含测试提的四点硬化)。

**v2 · Agent-Drafted Experiment Package** —— 人写 goal + brief;agent 生成 program / versions / cases / rubric / simulator 草案;人确认 anchor;再走现有 run / score / compare。
必须实现:brief.md、Designer Agent、artifact provenance、rubric approval state、golden cases。
**v2 的核心是「agent 起草实验包、人能校准 rubric」。不要在 v2 就堆 sentinel / adversarial / judge regression —— 那会把 v2 做成 v2+v3+v4 的混合体。**

**v2.5 · Calibration & Harness Sanity** —— 让评测系统知道自己的尺子有没有坏。
实现:sentinel cases、adversarial bad versions、calibration report、judge regression、bad-version detection。
摆在 v2 和 v3 之间:agent-operated(v3)必须站在「评测系统能自检」之上。

**v3 · Agent-Operated Loop** —— agent 自动跑实验、提下一轮,撞触发条件就喊人。
实现:escalation rules(§5)、resource gates、自动下一轮实验提案、keep/discard 提案、human approval checkpoints。

**v4 · Self-Improving Lab** —— agent 优化实验方法本身。
实现:method mutation、meta-evaluation、对区分度 / 成本 / 方差的优化、calibration-gated 的方法更新(方法改动要过 §6 的 frozen calibration 才生效)。

---

## 10. 从 v1 到 v2 的最小迁移

当前(v1)工作区:

```
goal.md  connect.md  experiments/NNN/{program.md, rubric.md, 模拟器.md, 测试集/, versions/, results/}
```

到 v2,最小变更:

- **+ `brief.md`** —— 每个实验一个,人写。
- **goal.md + `## 红线` 段** —— 标准的不可牺牲项。
- **program.md + authority matrix 字段** —— 取代单一的 `运行模式` 声明(§3 / §4)。
- **每个 artifact + provenance 头** —— frontmatter 里 `source / approved_by / approval_state`(§7)。
- **+ `calibration/` 目录** —— v2 先要 `golden/`;`sentinel/`、`adversarial_versions/` 留到 v2.5。
- **+ `review.md`** —— 每个实验一个,系统生成(§8)。

现有 run / score / compare 管线**不动**。v2 是在它前面接「起草 + 审」、后面接 provenance —— 中间那段可信的机械执行,原样保留。

---

## 关系

取代 v0.4 草稿。v0.3 的 §0–§5、§7 仍有效。README「状态」段、file-formats.md(`运行模式` 字段,以及新增的 brief.md / review.md / calibration/ 格式)待这版定稿后同步。
