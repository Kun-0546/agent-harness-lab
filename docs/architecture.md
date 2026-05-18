# Harness Design Loop · 架构

> 配合 `design-v0.3.md`（概念）看。design 讲「是什么」，这份讲「代码怎么切」。
> 日期：2026-05-17。

## 一条线：通用 core / 项目相关 edge

工具要通用 —— 能用在任何被测 agent 上，不绑死某个项目。做法是把代码切成两块，
中间一道接缝：

- **通用 core** —— 实验编排（跑/打分/比）、数据模型、命令行。只认接口，永远不
  知道被测的是哪个 agent。
- **项目相关 edge** —— 五个接口的具体实现（适配器）。允许知道接入细节。

被测项目对工具来说，只是「一份 goal.md ＋ 一个接入配置 ＋ 一组测试 case」，
不碰 core 一行。

## 五个接口（接缝在哪）

`harness_design_loop/interfaces/`：

| 接口 | 管什么 | design |
|---|---|---|
| `Connection` / `Session` | 够到被测 agent | §3.2 |
| `ConversationDriver` | 把 case 变成对话 | §3.3 |
| `Simulator` | 模拟模式下扮用户 | §3.3 |
| `Scorer` | 把对话打成分 | §3.3 |
| `Snapshotter` | 抓环境快照 | §3.1 |

跟具体项目相关的东西，只能住在这五个接口后面。

## 分工

| | 谁 | 哪些文件 |
|---|---|---|
| 通用脊梁 | 架构侧 | `interfaces/` · `core/` · `models.py` · `tests/` |
| 具体边缘 | 实现方 | `adapters/` |

core 是「绝对不能耦合」的那部分，由手上没有任何真实项目的一侧来写，保证它
generic by construction。适配器本来就该知道接入细节，交给实现方。

## 通用性怎么强制

光靠约定守不住。三道机制：

1. **core 对着假适配器跑通。** `tests/fakes.py` 是 in-memory 的假 Connection /
   Scorer 等。core 能在零真实 agent 下端到端跑通（`tests/test_core.py`），就证明
   它没耦合任何项目。
2. **契约测试即验收闸。** `tests/contracts.py` 是「任意一个 Connection / Scorer 都
   必须过」的通用用例。实现方的适配器「写完了」＝ 过契约测试。契约测试进 CI，
   红就是没完成。
3. **早期上两个不一样的 agent。** 一个 fixture 会让人不知不觉贴着它写；两个不像
   的（比如进程内库 ＋ HTTP API）都跑通，通用性才算证明。

## 数据怎么流

```
goal.md ─┐  (PM 写)
         │
实验 ────┤  program ＋ 测试集 ＋ rubric ＋ versions
         │
  跑 ────┤  每版本 × 每 case：open_connection → driver.run → Conversation
         │
  打分 ──┤  每 Conversation：scorer.score → ScoreCard   （只读对话，可重打）
         │
  比 ────┘  ScoreCards → compare → ComparisonReport
```

`跑` 产出对话并持久化，`打分` 只读对话。两步分开 —— Scorer 永不碰 Connection，
所以打分便宜、能换 rubric / 换模型重打。

## 现在到哪

骨架阶段已落地：五个接口、core 编排（run/score/compare）、假适配器、契约测试
脚手架（Connection ＋ Scorer 两个契约，core 对 fakes 的端到端测试）。

未做：适配器具体实现（实现方）· 另三个接口的契约 · 持久化格式 · 噪声/归因算法 ·
接线层（config → 适配器实例）· CLI 的 run/score/compare 命令 · CI。
