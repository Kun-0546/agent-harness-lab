# Harness Design Loop · 文件格式

> 本文描述 ahl **v1 当前已实现**的文件格式 —— 工具实际读写的。配合架构文档 `design-v0.3.md` 看。
> v2-minimal 已实现 brief.md、review.md、calibration/golden/ 的最小格式,见 `v2-minimal-spec.md`(§3 / §6 / §7);authority matrix、per-file provenance、calibration 校验闭环仍未实现,见 `design-v0.4.1.md`。
> 日期:2026-05-19,随代码更新。各格式都对着 `src/agent_harness_lab/` 的解析代码核过。

## 工作目录

`ahl init` 在工作目录根建 connect.md / goal.md / experiments/;`ahl new <名字>` 建一个实验:

```
<工作目录>/
├── goal.md                总目标(内部怎么写 = Goal Engineering 方法,待定)
├── connect.md             接入配置
└── experiments/
    └── <编号-名字>/
        ├── program.md     实验指令
        ├── rubric.md      评分维度 + 权重
        ├── simulator.md   模拟模式下扮用户的 agent
        ├── cases/         一个 case 一个 .md
        ├── harnesses/     一个 harness variant 一个 .md
        └── results/       run / score / compare 的产出
```

---

## connect.md

工作目录根一份。工具怎么连被测 agent(design-v0.3 §3.2 的四种接入方式)。

```
# connect

## 类型
外部命令行          # 进程内库 / 外部命令行 / HTTP无状态 / HTTP有状态

## 配置
命令:wsl python3 /path/to/agent.py
```

- 四种接入都已实现(见 examples/ 各一个样例)。外部命令行 = 子进程 + JSON 行:stdin 收 `{"input": ...}`,stdout 回 `{"response": ...}`。
- agent 在 WSL 里,命令写 `wsl ...`。
- **跨平台**:`命令:` 行是 shell 直接 exec 的命令。Python agent 解释器名 macOS / Linux 用 `python3`、Windows 用 `py`(Python Launcher);跨机器 handoff 时记得改对应解释器,或脚本加 shebang `#!/usr/bin/env python3` + `chmod +x` 再 `命令:./agent.py`(三平台都吃)。

---

## program.md

PM 交给 coding agent 的实验指令,一个实验一份。

```
# 实验 <编号-名字> · program

## 假设
<这次实验想验证什么>

## 声明
- 环境:<被测环境是什么 + 取的初始状态;无环境写"无">
- 对话模式:<模拟 / 回放 / 固定>
- 状态:<累积 / 重置>
- 评分:<评分器类型 + 打分粒度>
- 运行模式:<人评 / 自迭代>
- 对比方式:<对基线 / 线性迭代;可选,默认 对基线 —— 多版本 compare 怎么算 delta>

## 留/丢规则
<运行模式 = 自迭代时必填;人评留空>

## 喊人规则
<运行模式 = 自迭代时必填;人评留空>
```

---

## rubric.md

评分维度 + 权重,从 goal 推导。

```
# rubric

## <维度名>
权重: <0-1,所有维度之和 = 1;也可写百分数、和 = 100>
<这个维度衡量什么、怎么判高低分>
```

---

## simulator.md

模拟模式下扮用户的那个 agent。真 simulator 读它 + 调模型生成追问。

```
# simulator

## 人设
<simulator 扮谁>

## 背景知识
<它扮的人知道什么(可留空)>

## 追问策略
<怎么追问、什么时候收尾>
```

---

## cases/<case>.md

一个测试 case 一个文件。下面是「模拟」模式的格式;回放 / 固定模式的 case 形状不同,随后做。

```
---
id: D-01
type: D                 # 可选;分类标签
max_turns: 15           # 可选;对话轮次上限
depends_on:             # 可选;另一 case 的 id。已解析,但 run 暂未用它(占位、不生效)
---
## 起始输入
<开场那条用户消息>

## 完成标准
<可选;一个 checklist 或散文式判断要点>
```

---

## harnesses/<版本>.md

被测系统里摆出来对比的 harness variants,一个 variant 一个文件。一组里恰好一个标基线。

每个 variant 可以写自己的「类型」「配置」段,接到各自的 agent —— 比较两个不同 agent 时用;不写这两段就用全局 connect.md。

```
---
id: V1
基线: 是                # 是 / 否
---
## 这是什么
<这个版本是基线,还是相对基线改了什么>

## 类型
外部命令行              # 可选;不写则用全局 connect.md。四种接入同 connect.md

## 配置
命令:wsl python3 /path/to/this-version-agent.py
```

---

## results/

`run` / `score` / `compare` 的产出,工具写、PM 读:

- `run-<时间>.json` —— 一次 run 的对话(每条 = 版本 × case 的多轮 transcript)。
- `score-<时间>.json` —— 一次打分(每条 case 的各维度分 + 加权总分,带用的哪版 rubric、哪个评分器)。
- `compare-<时间>.md` —— 一次对比报告(版本总分、跟基线的差、哪个维度退化)。
