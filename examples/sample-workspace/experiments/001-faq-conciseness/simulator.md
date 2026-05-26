# simulator

## 人设
一个普通用户,问完 FAQ 类问题后等回答即可,**不会**追问。

## 背景知识
对产品 FAQ 主题无先验背景。

## 追问策略
单轮即可 — 不追问。本 sample 用 stub_simulator(它在 agent 回应第一条
后返回 None 收尾),所以 simulator.md 文件主要为文档目的,内容不直接
影响 stub 行为。
