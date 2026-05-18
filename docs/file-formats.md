# Harness Design Loop · 文件格式

> 工具读写的所有文件格式。配合 `design-v0.3.md`(架构)看。
> 日期:2026-05-17,随代码更新。各格式都对着 `src/harness_design_loop/` 的解析代码核过。

## 工作目录

`hdl init` 在工作目录根建 connect.md / goal.md / experiments/;`hdl new <名字>` 建一个实验:

```
<工作目录>/
├── goal.md                总目标(内部怎么写 = Goal Engineering 方法,待定)
├── connect.md             接入配置
└── experiments/
    └── <编号-名字>/
        ├── program.md     实验指令
        ├── rubric.md      评分维度 + 权重
        ├── 模拟器.md      模拟模式下扮用户的 agent
        ├── 测试集/        一个 case 一个 .md
        ├── versions/      一个被测版本一个 .md
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

- 本期 run 只实现「外部命令行」:子进程 + JSON 通信(stdin 收 `{"input": ...}`,stdout 回 `{"response": ...}`)。
- agent 在 WSL 里,命令写 `wsl ...`。

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

## 模拟器.md

模拟模式下扮用户的那个 agent。真模拟器读它 + 调模型生成追问。

```
# 模拟器

## 人设
<模拟器扮谁>

## 背景知识
<它扮的人知道什么(可留空)>

## 追问策略
<怎么追问、什么时候收尾>
```

---

## 测试集/<case>.md

一个测试 case 一个文件。下面是「模拟」模式的格式;回放 / 固定模式的 case 形状不同,随后做。

```
---
id: D-01
type: D                 # 可选;分类标签
max_turns: 15           # 可选;对话轮次上限
depends_on:             # 可选;另一 case 的 id —— 初始上下文来自它跑完的对话
---
## 起始输入
<开场那条用户消息>

## 完成标准
<可选;一个 checklist 或散文式判断要点>
```

---

## versions/<版本>.md

被测系统里摆出来对比的版本,一个一个文件。一组里恰好一个标基线。

```
---
id: V1
基线: 是                # 是 / 否
---
## 这是什么
<这个版本是基线,还是相对基线改了什么>

## 接入配置
<这个版本怎么接:无环境写 model + system prompt + 参数,有环境写环境引用>
```

---

## results/

`run` / `score` / `compare` 的产出,工具写、PM 读:

- `run-<时间>.json` —— 一次 run 的对话(每条 = 版本 × case 的多轮 transcript)。
- `score-<时间>.json` —— 一次打分(每条 case 的各维度分 + 加权总分,带用的哪版 rubric、哪个评分器)。
- `compare-<时间>.md` —— 一次对比报告(版本总分、跟基线的差、哪个维度退化)。
