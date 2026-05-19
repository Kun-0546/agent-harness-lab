# Harness Design Loop · 设计方案 v0.4

> 这版加什么：把实验的分工——人做什么、agent 做什么——做成一等设计对象。
> v0.3 的 §0–§5、§7 不变：接入、评测、三层目标、三个动作、文件结构照旧。
> 这版取代 v0.3 §6「两个模式」：两档扩成四档，并补上锚点、calibration、provenance。
> 日期：2026-05-18。先于文件格式细化和代码。一处未决见 §10。

---

## 0. 为什么要这版

v0.3 默认人手写整套实验文件——goal、program、versions、测试集、rubric、模拟器、connect。但这工具的长期价值，是让人少写、agent 多做，同时不失控。所以要先回答一个问题：实验闭环里，哪些能交给 agent，哪些必须留在人手上。

这版不改 v1 的活法。它把 v2 及以后的方向写清楚，让现在的决定知道自己往哪走。

---

## 1. 一条原则：agent 操作闭环，人拥有锚点

Karpathy 的 AutoResearch 能完全无人，是因为它的 ground truth 是 held-out loss——一个 agent 伪造不了的东西。

hdl 这个域没有这种免费的固定点。「这个 agent 作为产品更好了吗」是个判断，不是个测量。它的 ground truth 是人的产品判断。

所以一条硬原则：**hdl 可以越来越自动，但不能假装自己有一个无需人类锚点的 loss。** 把完整闭环交给 agent 独占，你得到的系统会很擅长把分数刷上去——分数还指不指向真东西，没人担保。这就是 v0.3 §2.1 已经点名的 Goodhart，搬到了整条循环的尺度上。

落到分工上：

```
agent 做实验      人定目标
agent 找证据      人校准尺子
agent 提建议      人解释结论
```

---

## 2. 实验权力分三层

把 agent 能拿的权、和人必须留的权，分开：

- **生成权**——agent 可以生成 versions、测试集、rubric 草案、模拟器、下一轮实验建议。
- **执行权**——agent 可以自动 run / score / compare / 汇总。
- **锚点权**——必须人拥有，或经人显式批准。见 §3。

生成权里「rubric 草案」要说清：agent 起草 rubric，但 rubric 要过 §6 的 golden 校准、再加人签字，才生效。生成 ≠ 拥有。

---

## 3. 三个不可让渡的锚点

- **目标所有权**——agent 可以提议改目标（目标本来就一直在动，见 v0.3 §2），但接受改动的是人。能改写自己目标的系统，等于没有目标。
- **rubric / judge 校准权**——rubric 是目标的操作化，judge 是 rubric 的执行者。这套 proxy 还跟不跟得上你真正在乎的东西，由人定期校（机制见 §6）。
- **结论解释权**——compare 出的是证据，不是结论。agent 可以报「V2 总分 +0.5、战略深度 +1.0、简洁性 -0.8」，可以建议「V2 更适合复杂咨询」；但「这个 trade-off 值不值」「默认上线还是只在复杂问题上用」，是人读出来的。

三者性质不同。目标所有权和解释权是**便宜的否决点**——agent 提、人否，日常成本低。rubric / judge 校准是**持续的活**。§6 的 calibration set 整套设计，存在的意义就是把这第三件的人力成本压到可承受——工程投入的重心在这。

---

## 4. 四种实验模式

「人参与多少」做成四个能直接选的档，比 v0.3 的「人评 / 自迭代」两档分得清。

**Mode 1 · Manual Lab**——人手写全部：goal、program、versions、测试集、rubric、connect。agent 只跑机械的 run / score / compare。适合早期调试、理解系统。项目现在最接近这一档。

**Mode 2 · Agent-Drafted Lab**——人写 goal + 实验意图（program）；agent 起草 versions、测试集、rubric、模拟器、compare 方案；人审核后再 run。它大幅减少人的工作量，又不失控。是 hdl 下一阶段最该做的方向。

**Mode 3 · Agent-Operated Lab**——人批准一次实验协议后，agent 自己生成版本、生成 case、跑、打分、比、提下一轮。但撞上触发条件必须喊人（见 §5）。中期较理想的形态。

**Mode 4 · Self-Improving Lab**——agent 不只优化被测 agent，也优化实验方法本身。有边界，见 §7。建立在 v1–v3 都稳之后。

---

## 5. Mode 3 的喊人触发

触发器分两类，机制不同。

**锚点改动门**（agent 想动锚点 → 必须批）：

- rubric 被修改
- 目标被修改

**结果异常报警**（结果不对劲 → 停下喊人）：

- 分数异常升高
- 所有版本都高分、但无区分度
- 某关键维度退化
- judge 分歧过大
- calibration set 失准

还要加一类**资源闸**：agent 跑了 N 轮、或花了 $X → 喊人。一个会自己生成版本、自己跑的 agent，质量没问题也可能烧光预算。

---

## 6. Calibration set——三类，冻结

人类锚点不必是「天天写 case」。它可以压成一个小而冻结的集合：agent 自治地跑，持续拿这个集合做回归测，一分叉就喊人。这个集合分三类。

- **Golden cases**——人明确判过的高价值案例（明显好 / 明显差 / 长而空 / 短而中要害 / 看着专业其实误导）。校 judge 还懂不懂你的真实偏好。
- **Sentinel cases**——故意设计来抓系统性退化的（问题很简单，看会不会过度展开 / 用户假设是错的，看会不会盲从 / 要求很模糊，看会不会主动澄清 / 情绪很强，看会不会只讲道理不处理情绪）。
- **Adversarial bad versions**——故意放进去的坏版本（只会说空话 / 过度简短 / 永远先反问 / 过度自信 / 机械套框架）。评测系统要是分不出这些坏版本，说明实验方法本身不可信。这比单看 V1/V2 分数强。

**关键约束：这三类都冻结，放在 agent 的优化够不到的地方。** adversarial 尤其不能让跑评测的那个 agent 每轮现生——它会倾向只生成「自己 judge 已经抓得到」的坏版本，元测试永远绿、假安心。要人来种，或做成一个固定库。frozen 的字面意思就是：在优化器够不到的地方。

calibration set 还会随被测 agent 变强而失准——被测 agent 稳过某个 golden case 之后，那个 case 就不再有区分度。刷新它是人的活，不是一次性的。

---

## 7. 自我改进的边界（Mode 4）

「实验方法」拆两半，边界不一样。

**工具性——agent 可以自优化。** case 有没有区分度、评分方差大不大、judge 稳不稳、同版本重跑一不一致、成本降没降、compare 报告清不清楚、坏版本能不能被识别。这些有相对客观的反馈（「塞个坏版本，看方法抓不抓得到」本身就是个客观元测试），agent 可以自己改。

**有效性——不能自证。** 这个 rubric 真代表我的产品目标吗、这些 case 真代表真实用户吗、这个 judge 真懂我要的风格吗、这个版本真该上线吗。一旦 agent 同时能改 rubric、改 case、改 judge prompt、改版本、再决定留 / 丢，它就能把整个系统优化成「看起来分数很好」。

所以：实验方法可以自我改进，但必须被 §6 的 frozen calibration set、或人类偏好锚约束。往上走一层不会让锚点问题消失，只是把它挪高一层。

---

## 8. Provenance——来源要看得见

涉及目标、rubric、calibration 的改动，全部显式记录、可回滚。

再进一步：每个 artifact（version、测试集、rubric）带一个来源戳——人写的 / agent 起草人批的 / agent 全自动的。而且 compare 报告要把这个戳显示出来。

「V2 +0.5」这条证据，V2 和它用的 rubric 是人定的、还是 agent 自己生的，你对这 +0.5 的信任度完全不同。来源不能只躺在回滚日志里，要摆在你读结论的那张报告上。

---

## 9. 路线 v1–v4

四种模式按版本推进。每版的安全，靠的是上一版的地基。

**v1 · 可信手动 loop**（现在）——run / score / compare 可信；坏输入拒绝运行；V1/V2 真隔离；文档和代码一致；stub 和 real judge 分清楚。这一版别加自迭代。（run/score 跑前校验、compare_mode 兜底那轮，属于这一版。）

**v2 · agent 起草实验包**——人写 goal.md + program.md；agent 生成 versions/、测试集/、rubric.md、模拟器.md；人 review 后 run。这是最该做的下一步。**golden cases + adversarial bad versions 要在这一版就到位**——agent 一旦起草 rubric，「人 review」扛不住 review fatigue；golden 校准是让 v2 真安全的东西。（calibration 不放 v4：v2/v3 已经在动锚点，锚却拖到 v4 才装，顺序就反了。）

**v3 · agent 运行并提下一轮**——agent 自动跑、读 compare、提 V3、补 case、调 rubric 草案、提 keep / discard。所有涉及目标、rubric、calibration 的改动，显式记录、可回滚。

**v4 · agent 优化实验方法**——meta-evaluation、judge regression、escalation 规则成熟化，就是 §7 的「实验方法自优化」。建立在 v1–v3 都稳、calibration 已在位之上。

---

## 10. 一处未决

四种模式，是四个固定档，还是一张 per-stage 矩阵的四个预设？

把 loop 的每个阶段（起版本、起 case、rubric、跑、打分、判读留丢、迭代目标）各给一个档（agent 自主 / agent 起草人过关 / 人自己做），四种模式就是这张矩阵上的四个预设。

- **固定四档**：简单、好讲、好实现。
- **per-stage 矩阵 + 四预设**：更灵活——「我要 Mode 2，但 rubric 自己写」有位置——复杂度高一档。

倾向后者：它才接得上「人自己决定在哪里干预」。待定。

---

## 关系

取代 v0.3 §6，v0.3 其余部分仍有效。定稿后要同步：README 的「状态」段、file-formats.md 的「运行模式」字段。
