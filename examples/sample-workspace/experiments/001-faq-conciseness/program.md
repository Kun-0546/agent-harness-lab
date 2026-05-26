# 实验 001-faq-conciseness · program

## 假设
把 FAQ-bot 的 system prompt 从 "DEFAULT verbose"(runtime 自带)换成
"STRICT concise"(由 `concise-prompt@0.1.0` harness package 安装),
会让回答更简洁;同一组 case 跑两版应该看到非平凡的 delta。

## 声明
- 环境:无(沙盒里跑,单文件 Python agent)
- 对话模式:模拟
- 状态:重置
- 评分:LLM 打 1-10(本 sample 用本地桩 stub_grader,可复现)
- 运行模式:人评
- 对比方式:对基线
