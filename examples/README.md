# 样例 agent

每个文件是一个**最小可跑**的 agent,演示一种接入方式的协议。
先拿它对着工具跑通,再把里面的样例逻辑换成你自己的 agent。

| 文件 | 接入方式 | 协议 |
|------|---------|------|
| `cli_agent.py` | 外部命令行 | stdin 读 `{"input"}`、stdout 写 `{"response"}`,一行一个 JSON |
| `library_agent.py` | 进程内库 | 暴露 `respond(history) -> str` |
| `http_stateless_agent.py` | HTTP无状态 | POST `{"messages"}` → `{"response"}`,每轮发完整历史 |
| `http_stateful_agent.py` | HTTP有状态 | POST `{"input","session_id"}` → `{"response","session_id"}` |

每个文件头部都写了它的完整协议、以及怎么在 `connect.md` 里配。

## 怎么用

1. `connect.md` 里填对应的接入类型和配置(照样例文件头部写的来)。
2. `hdl run <实验编号>` —— 工具会按这个协议驱动 agent。
3. 跑通后,把样例里的 `reply()` / `respond()` 换成你真 agent 的逻辑。

样例逻辑都是回显(把收到的话重复一遍),只为让你看清协议,不是真 agent。

## 你的 agent 接不上这四种协议怎么办

写一个小转接脚本:对工具这边说上面某一种协议,对内驱动你自己的 agent
(它有自己的命令行参数、自己的文件接口,都行)。这种转接代码是你 agent
专有的,放你自己这边,不进本工具 —— 工具只负责把这四种协议定清楚。
