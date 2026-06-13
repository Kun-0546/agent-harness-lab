"""多轮移植对等性 pinning 测试(v1.1 spec §0.2-2)。

把 Stack A(runner / simulator / workflow 栈)的多轮现行行为钉成 golden,
作为 PR2 把多轮循环移植进 v1 栈(auto.py _run_case_turns)时的对照基准:

【Stack A golden —— 移植后必须逐条保持】
- run_agent_session 的 max(1, max_turns) 封顶(runner.py:48);
- simulator 返回 None 即收尾(runner.py:52-53);
- transcript 的 turn 序号从 0 递增,entry 形状 {turn, user, agent}(runner.py:50);
- 缺省 max_turns=8,经 testset/case 路径(runner.py:91 `c.max_turns or 8`);
- stub_simulator 的两句固定追问序列(simulator.py:18-29;PR2 退役后由
  scaffold 默认 playbook 等价承接,序列内容即此处所钉);
- 收尾 token "结束"(simulator.py:93)—— 双语契约里中文 token 两代共有,先钉住;
- turn 中途异常 → CaseRun.error 非空、不中断后续 case(runner.py:96-98)——
  error 字段语义两代共有,先钉住。

【v1 新契约 —— PR2 已落地,本组已翻转为正式断言,被测改指 v1 实现】
- partial transcript 保留(spec §0.2-1):被测 = auto._run_case_turns(caller
  持有的 transcript 在 turn 中途异常后保留已收集轮次);Stack A 的丢弃行为
  (runner.py:45-56 / :96-98)不再是 golden;
- 收尾 token 双语 结束/END(spec §0.2-4):被测 = user_sim.make_role_play_simulator
  (Stack A 仅认"结束",英文 persona 下模型答 END 会收尾失效 —— v1 修复)。

Stack A 退役(PR9)后,本文件整组原地转为 v1 行为回归测试(被测函数从
runner / simulator 改指 auto.py 的 _run_case_turns 与 v1 化 simulator)。

注:run_agent_session 的 finally session.close() 有意不钉 —— PR2 把 close
所有权移交 dispatch 层(spec PR2 首条),钉了反而阻碍迁移。
"""
import contextlib
import io
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from agent_harness_lab import llm, user_sim
from agent_harness_lab.agentconn import AgentSession
from agent_harness_lab.auto import _run_case_turns
from agent_harness_lab.runner import run_agent_session, run_experiment
from agent_harness_lab.simulator import (
    Simulator,
    make_llm_simulator,
    stub_simulator,
)
from agent_harness_lab.testset import parse_sim_case
from agent_harness_lab.version import Version

# stub_simulator 两句固定追问的 golden 副本 —— 故意不 import 源常量,
# 源码改了序列这里必须红(pinning 的意义所在)。
_GOLDEN_FOLLOWUPS = [
    "这个能再具体点吗?给个数。",
    "那如果情况变了,你会怎么调整?",
]


class _FakeSession(AgentSession):
    """脚本化假 session:回显用户话;可指定从第几次 send 开始抛异常。"""

    def __init__(self, fail_on_call: int | None = None):
        self.received: list[str] = []
        self.closed = False
        self._fail_on_call = fail_on_call

    def send(self, user_text: str) -> str:
        call_no = len(self.received) + 1
        if self._fail_on_call is not None and call_no >= self._fail_on_call:
            raise RuntimeError(f"agent 在第 {call_no} 次 send 时崩了")
        self.received.append(user_text)
        return f"回应:{user_text}"

    def close(self) -> None:
        self.closed = True


class _FakeAdapter:
    """假 adapter:只为喂 run_experiment 的 per-case start。"""

    def __init__(self, fail_on_call: int | None = None):
        self.fail_on_call = fail_on_call
        self.sessions: list[_FakeSession] = []

    def start(self, sandbox) -> _FakeSession:
        sess = _FakeSession(fail_on_call=self.fail_on_call)
        self.sessions.append(sess)
        return sess


def _greedy_sim(transcript: list) -> str:
    """永不收尾的模拟器 —— 专测 max_turns 封顶。"""
    return f"追问 {len(transcript)}"


def _version(vid: str = "V1") -> Version:
    return Version(path=Path(f"{vid}.md"), version_id=vid,
                   is_baseline=True, what="基线版")


def _run_one(cases, simulator, fail_on_call=None):
    """跑单版本 run_experiment,吞掉进度打印,返回 (runs, adapter)。"""
    v = _version()
    adapter = _FakeAdapter(fail_on_call=fail_on_call)
    with contextlib.redirect_stdout(io.StringIO()):
        runs = run_experiment(
            [v], cases, simulator,
            adapters_map={v.version_id: adapter},
            sandboxes_map={v.version_id: None},
            snapshots_map={v.version_id: "snap-test"})
    return runs, adapter


def _write_case(dir_path: Path, name: str, opening: str,
                max_turns: str | None = None) -> Path:
    """写一个最小 case 文件(模拟模式),走 parse_sim_case 真实解析路径。"""
    lines = ["---", f"id: {name}"]
    if max_turns is not None:
        lines.append(f"max_turns: {max_turns}")
    lines += ["---", "", "## 起始输入", "", opening, ""]
    path = dir_path / f"{name}.md"
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


class TestTurnCapPinning(unittest.TestCase):
    """钉 max(1, max_turns) 封顶(runner.py:48)。"""

    def test_max_turns_caps_loop(self):
        sess = _FakeSession()
        tr = run_agent_session(sess, "开场", _greedy_sim, max_turns=3)
        self.assertEqual(len(tr), 3)

    def test_zero_max_turns_still_runs_one_turn(self):
        sess = _FakeSession()
        tr = run_agent_session(sess, "开场", _greedy_sim, max_turns=0)
        self.assertEqual(len(tr), 1)

    def test_negative_max_turns_still_runs_one_turn(self):
        sess = _FakeSession()
        tr = run_agent_session(sess, "开场", _greedy_sim, max_turns=-5)
        self.assertEqual(len(tr), 1)


class TestNoneEndsConversation(unittest.TestCase):
    """钉 simulator 返回 None 即收尾(runner.py:52-53)。"""

    def test_none_on_first_call_ends_after_one_turn(self):
        sess = _FakeSession()
        tr = run_agent_session(sess, "开场", lambda t: None, max_turns=8)
        self.assertEqual(len(tr), 1)

    def test_none_mid_conversation_ends_before_cap(self):
        sess = _FakeSession()
        sim = lambda t: "再来一轮" if len(t) < 2 else None  # noqa: E731
        tr = run_agent_session(sess, "开场", sim, max_turns=8)
        self.assertEqual(len(tr), 2)


class TestTurnNumbering(unittest.TestCase):
    """钉 transcript 形状:turn 序号从 0 递增,entry = {turn, user, agent}。"""

    def test_turn_numbers_increment_from_zero(self):
        sess = _FakeSession()
        tr = run_agent_session(sess, "开场", _greedy_sim, max_turns=4)
        self.assertEqual([e["turn"] for e in tr], [0, 1, 2, 3])

    def test_entry_shape_and_contents(self):
        sess = _FakeSession()
        tr = run_agent_session(sess, "帮我做个搬家计划", _greedy_sim, max_turns=2)
        self.assertEqual(set(tr[0].keys()), {"turn", "user", "agent"})
        # turn 0 = case 起始输入,agent 收到的就是这句
        self.assertEqual(tr[0]["user"], "帮我做个搬家计划")
        self.assertEqual(tr[0]["agent"], "回应:帮我做个搬家计划")
        # turn 1 的 user 来自 simulator 看完 turn 0 后的产出
        self.assertEqual(tr[1]["user"], "追问 1")

    def test_simulator_sees_transcript_including_current_turn(self):
        # simulator 每轮收到的 transcript 含刚结束的这一轮(长度 1,2,3),
        # 且末轮也会调一次 simulator(结果弃用)—— LLM 调用量对账要靠这条。
        seen: list[int] = []

        def sim(transcript: list) -> str:
            seen.append(len(transcript))
            return "继续"

        run_agent_session(_FakeSession(), "开场", sim, max_turns=3)
        self.assertEqual(seen, [1, 2, 3])


class TestDefaultMaxTurnsPinning(unittest.TestCase):
    """钉缺省 max_turns=8,经 testset/case 真实路径(runner.py:91)。"""

    def test_parse_sim_case_without_max_turns_is_none(self):
        with tempfile.TemporaryDirectory() as td:
            case = parse_sim_case(_write_case(Path(td), "D-01", "帮我做个搬家计划"))
        self.assertIsNone(case.max_turns)

    def test_run_experiment_defaults_to_eight_turns(self):
        with tempfile.TemporaryDirectory() as td:
            case = parse_sim_case(_write_case(Path(td), "D-01", "帮我做个搬家计划"))
        runs, _ = _run_one([case], _greedy_sim)
        self.assertEqual(len(runs), 1)
        self.assertEqual(len(runs[0].transcript), 8)

    def test_run_experiment_honors_explicit_max_turns(self):
        with tempfile.TemporaryDirectory() as td:
            case = parse_sim_case(
                _write_case(Path(td), "D-02", "帮我做个搬家计划", max_turns="3"))
        self.assertEqual(case.max_turns, 3)
        runs, _ = _run_one([case], _greedy_sim)
        self.assertEqual(len(runs[0].transcript), 3)


class TestStubSimulatorPinning(unittest.TestCase):
    """钉 stub_simulator 两句固定追问序列(simulator.py:18-29)。

    PR2 将退役这个硬编码 stub,由 scaffold 生成的默认 playbook 等价承接 ——
    届时本组测试改钉默认 playbook 的内容与收尾语义。
    """

    def test_exact_followup_sequence(self):
        one_turn = [{"turn": 0, "user": "开场", "agent": "回答"}]
        two_turns = one_turn + [{"turn": 1, "user": "追问", "agent": "回答2"}]
        self.assertEqual(stub_simulator(one_turn), _GOLDEN_FOLLOWUPS[0])
        self.assertEqual(stub_simulator(two_turns), _GOLDEN_FOLLOWUPS[1])

    def test_sequence_exhaustion_returns_none(self):
        three_turns = [{"turn": i, "user": "u", "agent": "a"} for i in range(3)]
        self.assertIsNone(stub_simulator(three_turns))

    def test_empty_transcript_gets_first_followup(self):
        # asked = max(0, len-1) 的防御边界:空 transcript 不炸,出第一句
        self.assertEqual(stub_simulator([]), _GOLDEN_FOLLOWUPS[0])

    def test_full_session_with_stub_is_three_turns(self):
        sess = _FakeSession()
        tr = run_agent_session(sess, "帮我做个搬家计划", stub_simulator, max_turns=8)
        self.assertEqual(len(tr), 3)
        self.assertEqual([e["user"] for e in tr],
                         ["帮我做个搬家计划"] + _GOLDEN_FOLLOWUPS)


class TestErrorRecordingCommonGround(unittest.TestCase):
    """turn 中途异常 → error 字段非空、不中断后续 case(runner.py:96-101)。

    error 字段语义是 Stack A 与 v1 partial-transcript 契约(spec §0.2-1)的
    共同点,作 golden 钉住;transcript 是否保留见下面的 future-contract 组。
    """

    def test_error_recorded_and_next_case_still_runs(self):
        with tempfile.TemporaryDirectory() as td:
            c1 = parse_sim_case(_write_case(Path(td), "D-01", "先崩的 case"))
            c2 = parse_sim_case(_write_case(Path(td), "D-02", "后面的 case"))
        runs, _ = _run_one([c1, c2], stub_simulator, fail_on_call=2)
        self.assertEqual(len(runs), 2)
        self.assertIn("第 2 次 send", runs[0].error)
        # 第二个 case 同样在第 2 次 send 崩 —— 但它确实被跑了(没被第一个拖死)
        self.assertIn("第 2 次 send", runs[1].error)

    def test_error_case_does_not_poison_clean_case(self):
        with tempfile.TemporaryDirectory() as td:
            case = parse_sim_case(_write_case(Path(td), "D-01", "正常 case"))
        runs, _ = _run_one([case], stub_simulator)
        self.assertEqual(runs[0].error, "")
        self.assertEqual(len(runs[0].transcript), 3)


class TestPartialTranscriptContract(unittest.TestCase):
    """【v1 新契约,golden=spec §0.2-1 —— PR2 已落地,已翻转为正式断言】

    turn 中途异常 → 已收集的部分 transcript 照常保留 + error 字段。被测改指
    v1 实现(auto._run_case_turns:caller 持有 transcript,异常不丢已收集
    轮次;auto._multiturn_case 据此落盘 partial transcript + error)。
    Stack A 的丢弃行为(runner.py:45-56 / :96-98)不再是 golden。
    """

    def test_partial_transcript_preserved_on_mid_session_exception(self):
        sess = _FakeSession(fail_on_call=2)
        transcript: list = []
        with self.assertRaises(RuntimeError):
            _run_case_turns(sess, "帮我做个搬家计划", stub_simulator, 8, transcript)
        # v1 契约:turn 0 已成功收集,必须保留在 caller 持有的 transcript 里
        self.assertEqual(len(transcript), 1)
        self.assertEqual(transcript[0]["turn"], 0)
        self.assertEqual(transcript[0]["user"], "帮我做个搬家计划")
        self.assertEqual(transcript[0]["agent"], "回应:帮我做个搬家计划")

    def test_clean_case_unaffected(self):
        sess = _FakeSession()
        tr = _run_case_turns(sess, "正常 case", stub_simulator, 8)
        self.assertEqual(len(tr), 3)  # 开场 + stub 两句追问后收尾


_SIM_ENV = {
    "AHL_SIM_BASE_URL": "http://sim.invalid",
    "AHL_SIM_MODEL": "sim-model",
    "AHL_SIM_API_KEY": "sim-key",
}
_ONE_TURN = [{"turn": 0, "user": "开场", "agent": "回答"}]


def _llm_sim_reply(reply: str):
    """造一个 LLM 模拟器并让 mock 模型回 reply,返回模拟器的产出。"""
    cfg = Simulator(path=Path("simulator.md"),
                    persona="挑剔的用户", strategy="每轮要一个数字")
    with mock.patch.dict(os.environ, _SIM_ENV):
        sim = make_llm_simulator(cfg)
    with mock.patch("agent_harness_lab.llm.chat", return_value=reply):
        return sim(list(_ONE_TURN))


class TestLlmSimulatorEndTokenPinning(unittest.TestCase):
    """钉 LLM 模拟器收尾语义(simulator.py:91-95)。

    中文 token "结束" 是 v1 双语契约(结束/END)的共有一半,直接作 golden;
    英文 END 见下面的 future-contract 组。
    """

    def test_chinese_end_token_ends_conversation(self):
        self.assertIsNone(_llm_sim_reply("结束"))

    def test_chinese_end_token_matches_by_prefix(self):
        # startswith 语义:模型多嘴跟了后缀也照样收尾
        self.assertIsNone(_llm_sim_reply("结束。这轮聊透了"))

    def test_normal_reply_passes_through_stripped(self):
        self.assertEqual(_llm_sim_reply("  给个数字?  "), "给个数字?")

    def test_missing_key_raises_instead_of_faking(self):
        # 无 key 永不伪造追问:Stack A 形态是 make_llm_simulator 直接抛
        # RuntimeError(simulator.py:86-89);v1 形态改为 simulator_unconfigured
        # error 级 issue + 跳过派发(spec §0.1-2)—— 两代共同点是"绝不静默出假话"。
        cfg = Simulator(path=Path("simulator.md"),
                        persona="挑剔的用户", strategy="每轮要一个数字")
        env = dict(_SIM_ENV, AHL_SIM_API_KEY="")
        with mock.patch.dict(os.environ, env):
            with self.assertRaises(RuntimeError):
                make_llm_simulator(cfg)


def _v1_sim_reply(reply: str):
    """造一个 v1 role_play 模拟器并让 mock 模型回 reply,返回模拟器的产出。"""
    card = user_sim.PolicyCard(path=Path("policy.md"),
                               persona="a picky user", strategy="ask for a number")
    with mock.patch.dict(os.environ, _SIM_ENV):
        sim = user_sim.make_role_play_simulator(card)
    with mock.patch("agent_harness_lab.llm.chat", return_value=reply):
        return sim(list(_ONE_TURN))


class TestBilingualEndToken(unittest.TestCase):
    """【v1 新契约,golden=spec §0.2-4 —— PR2 已落地,已翻转为正式断言】

    收尾 token 双语:"结束" 与 "END" 任一开头即收尾。被测改指 v1 实现
    (user_sim.make_role_play_simulator)。Stack A 把 "END" 当普通追问原样
    返回的行为(英文 persona 下收尾失效的功能 bug)不再是 golden。
    """

    def test_english_end_token_ends_conversation(self):
        self.assertIsNone(_v1_sim_reply("END"))

    def test_english_end_token_matches_by_prefix(self):
        self.assertIsNone(_v1_sim_reply("END — we have covered enough."))

    def test_chinese_end_token_still_ends(self):
        self.assertIsNone(_v1_sim_reply("结束。这轮聊透了"))

    def test_normal_reply_passes_through_stripped(self):
        self.assertEqual(_v1_sim_reply("  give me a number?  "), "give me a number?")


if __name__ == "__main__":
    unittest.main()
