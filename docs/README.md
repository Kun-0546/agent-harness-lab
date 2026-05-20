# docs

hdl 的文档。读哪个,看你要什么:

- **`file-formats.md`** —— v1 当前已实现的文件格式(工具实际读写的)。想知道现在怎么填 program / rubric / 测试集 / connect,看它。
- **`design-v0.3.md`** —— v1 的架构:三层模型、两个角色、四种接入、run / score / compare。file-formats.md 配它看。
- **`design-v0.4.1.md`** —— v2 及以后的产品方向(长期架构):agent 操作闭环、人拥有锚点;四模式、calibration、provenance、brief.md / review.md。
- **`v2-minimal-spec.md`** —— 当前 v2 分支(`v2-agent-drafted-lab`)的**实现切片**:把 `design-v0.4.1.md` 的 v2 那一档落成可建的细节 —— brief.md、external-agent authoring contract、review.md、集中式 provenance 的最小落地。代码层面以它为准。
- **`agent-authoring-guide.md`** —— 给**外层 coding agent**(Claude Code / Cursor / Codex)读的起草指南:你的角色、必读输入、要造的工件、不变量、起草前 checklist、命令清单。HDL 不调模型起草,这块由外层 agent 据本指南完成。
- **`archive/`** —— 已被取代的早期草稿(design-v0.1 / v0.2 / v0.4)和旧交接 note,留作记录。

一句话:`design-v0.3` + `file-formats` 是当前 v1;`design-v0.4.1` 是 v2+ 长期方向;`v2-minimal-spec` 是当前 v2 分支的实现切片;`agent-authoring-guide` 是给外层 agent 读的起草指南;`archive/` 是过去。
