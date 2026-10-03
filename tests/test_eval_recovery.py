"""Offline harness regressions; no Codex/Claude/model process is launched."""

import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "eval"))
import run_eval as E
import run_inline as I


class EvalRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.stack = contextlib.ExitStack()
        self.addCleanup(self.stack.close)
        self.stack.enter_context(contextlib.redirect_stdout(io.StringIO()))
        self.stack.enter_context(contextlib.redirect_stderr(io.StringIO()))
        self.stack.enter_context(patch.object(E.subprocess, "run", side_effect=AssertionError("No model subprocess in tests")))
        self.stack.enter_context(patch.multiple(
            E, EVAL=self.root, RUNS_ROOT=self.root / "runs", RUNS=self.root / "runs" / "base",
            RESULTS=self.root / "results", SANDBOX=self.root / "sandbox", TASKS=self.root / "tasks.jsonl",
            OPT={"B": self.root / "optimizer.md", "C": self.root / "optimizer.md"},
            STEM="offline", JUDGE_SUFFIX="", JUDGE_TPL="Synthetic rubric", WRAPPER="",
        ))
        self.stack.enter_context(patch.multiple(
            I, EVAL=self.root, RUNS=self.root / "runs" / "inline", OPT_B=self.root / "optimizer.md",
            OPT_I=self.root / "optimizer.md", STEM="offline_inline", JUDGE_TPL="Synthetic rubric",
            WRAPPER="", PAIRS={"AI": "I", "BI": "I", "AB": "B"},
        ))
        self.stack.enter_context(patch.dict(E.CFG, E.CFG.copy(), clear=True))
        self.stack.enter_context(patch.dict(I.CFG, I.CFG.copy(), clear=True))
        (self.root / "optimizer.md").write_text("Synthetic optimizer")
        self.tasks = [
            {"id": f"T{i:02d}", "场景": "Synthetic", "raw_prompt": "Synthetic task",
             "期望要点": ["Synthetic"], "典型失败": "Synthetic failure"}
            for i in range(1, 21)
        ]
        E.TASKS.write_text("\n".join(json.dumps(t) for t in self.tasks))

    def optimizers(self):
        return [(lambda: E.phase_optimize(self.tasks[0], "B"), E.RUNS / "T01" / "opt_B"),
                (lambda: I.opt_B(self.tasks[0]), I.RUNS / "T01" / "opt_B")]

    @staticmethod
    def fake_model(prompt, model, effort, out, **kwargs):
        out.mkdir(parents=True, exist_ok=True)
        rec = {"failed": None, "exit": 0, "output": "```text\nSynthetic optimized task\n```"}
        (out / "result.json").write_text(json.dumps(rec))
        return rec

    def test_write_failure_is_recoverable_without_repeating_model_call(self):
        for optimize, out in self.optimizers():
            with self.subTest(out=out.name, parent=out.parent.parent.name):
                with patch.object(E, "codex_run", side_effect=self.fake_model) as run, \
                        patch.object(E, "safe_write", side_effect=OSError(28, "synthetic full disk")):
                    with self.assertRaises(OSError):
                        optimize()
                self.assertEqual(run.call_count, 1)
                self.assertTrue((out / "result.json").exists())
                self.assertFalse((out / "optimized_prompt.md").exists())
                with patch.object(E, "codex_run", side_effect=AssertionError("Recovery must reuse the result")):
                    optimize()
                self.assertEqual((out / "optimized_prompt.md").read_text(), "Synthetic optimized task")

    def test_truncated_artifact_is_rebuilt_from_successful_result(self):
        for optimize, out in self.optimizers():
            self.fake_model("", "", "", out)
            (out / "optimized_prompt.md").write_text("Synthetic opt")
            with patch.object(E, "codex_run", side_effect=AssertionError("No retry needed")):
                optimize()
            self.assertEqual((out / "optimized_prompt.md").read_text(), "Synthetic optimized task")

    def test_multibyte_truncated_artifact_is_rebuilt_without_model_call(self):
        for optimize, out in self.optimizers():
            with self.subTest(optimizer=out.parent.parent.name):
                self.fake_model("", "", "", out)
                prompt = out / "optimized_prompt.md"
                prompt.write_bytes("中文提示词".encode("utf-8")[:-1])
                with patch.object(E, "codex_run", side_effect=AssertionError("No retry needed")):
                    optimize()
                self.assertEqual(prompt.read_text(), "Synthetic optimized task")

    def test_intact_artifact_does_not_repeat_model_or_write(self):
        for optimize, out in self.optimizers():
            self.fake_model("", "", "", out)
            (out / "optimized_prompt.md").write_text("Synthetic optimized task")
            with patch.object(E, "codex_run") as run, patch.object(E, "safe_write") as write:
                optimize()
            run.assert_not_called()
            write.assert_not_called()

    def test_missing_optimizer_result_is_retried(self):
        for optimize, out in self.optimizers():
            with patch.object(E, "codex_run", side_effect=self.fake_model) as run:
                optimize()
            self.assertEqual(run.call_count, 1)
            self.assertEqual((out / "optimized_prompt.md").read_text(), "Synthetic optimized task")

    def test_failed_or_nonzero_optimizer_results_are_retried(self):
        for optimize, out in self.optimizers():
            for rec in ({"failed": {"reason": "synthetic"}, "exit": 0, "output": "stale"},
                        {"failed": None, "exit": 1, "output": "stale"},
                        {"failed": None, "exit": 0, "output": ""},
                        {"failed": None, "exit": 0, "output": "```text\n\n```"}):
                out.mkdir(parents=True, exist_ok=True)
                (out / "result.json").write_text(json.dumps(rec))
                with patch.object(E, "codex_run", side_effect=self.fake_model) as run:
                    optimize()
                self.assertEqual(run.call_count, 1)
                self.assertEqual((out / "optimized_prompt.md").read_text(), "Synthetic optimized task")

    def executors(self):
        return [
            (lambda: E.phase_execute(self.tasks[0], "B"), E.RUNS, "B"),
            (lambda: E.phase_execute(self.tasks[0], "C"), E.RUNS, "C"),
            (lambda: I.exec_cond(self.tasks[0], "B"), I.RUNS, "B"),
        ]

    def test_execution_refuses_stale_prompt_after_failed_or_missing_optimization(self):
        for execute, runs, cond in self.executors():
            out = runs / "T01" / f"opt_{cond}"
            out.mkdir(parents=True, exist_ok=True)
            (out / "optimized_prompt.md").write_text("STALE OPTIMIZED PROMPT")
            records = [
                {"failed": {"reason": "synthetic"}, "exit": 0, "output": "stale"},
                {"failed": None, "exit": 1, "output": "stale"},
                {"failed": None, "exit": 0, "output": ""},
                None,
            ]
            for rec in records:
                with self.subTest(runs=runs.name, condition=cond, record=rec):
                    if rec is None:
                        (out / "result.json").unlink()
                    else:
                        (out / "result.json").write_text(json.dumps(rec))
                    with patch.object(E, "codex_run") as run:
                        with self.assertRaises(RuntimeError):
                            execute()
                    run.assert_not_called()

    def test_execution_recovers_successful_optimizer_result_before_calling_model(self):
        for execute, runs, cond in self.executors():
            out = runs / "T01" / f"opt_{cond}"
            self.fake_model("", "", "", out)
            with patch.object(E, "codex_run", side_effect=self.fake_model) as run:
                execute()
            self.assertEqual(run.call_count, 1)
            self.assertTrue(run.call_args.args[0].endswith("Synthetic optimized task"))
            self.assertEqual(run.call_args.args[3], runs / "T01" / f"exec_{cond}")

    def seed_one_win(self, runs, pair, cfg, rubric, task=None):
        task = task or self.tasks[0]
        for condition in pair:
            folder = runs / task["id"] / f"exec_{condition}"
            folder.mkdir(parents=True, exist_ok=True)
            (folder / "result.json").write_text(json.dumps({
                "failed": None, "exit": 0, "output": "Synthetic output", "model": "offline", "usage": {},
            }))
        verdict = {key: "Y" for key in I.CRITS}
        verdict.update(
            _mapping={"X": pair[0], "Y": pair[1]}, _lenX=10, _lenY=10,
            _sig=E.pair_sig("Synthetic output", "Synthetic output", E.task_basis(task)),
            _judge_cfg=E.judge_cfg(cfg["judge_model"], cfg["judge_effort"], rubric),
        )
        folder = runs / task["id"] / f"judge_{pair}"
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "verdict.json").write_text(json.dumps(verdict))

    def test_main_subset_aggregate_keeps_twenty_task_denominator(self):
        runs = E.RUNS_ROOT / "sol_medium"
        self.seed_one_win(runs, "AB", E.CFG, E.JUDGE_TPL)
        with patch.object(sys, "argv", ["run_eval.py", "--phase", "aggregate", "--tasks", "T01"]), \
                patch.object(E, "config_lock"), patch.object(E, "codex_run") as run:
            E.main()
        run.assert_not_called()
        summary = json.loads((E.RESULTS / f"{E.STEM}.json").read_text())
        self.assertEqual(summary["AB"]["n"], 1)
        self.assertFalse(summary["gate"]["complete"])
        self.assertFalse(summary["gate"]["pass"])

    def test_inline_subset_aggregate_keeps_twenty_task_denominator(self):
        runs = E.RUNS_ROOT / "astra_inline"
        self.seed_one_win(runs, "AI", I.CFG, I.JUDGE_TPL)
        with patch.object(sys, "argv", ["run_inline.py", "--phase", "aggregate", "--tasks", "T01"]), \
                patch.object(E, "config_lock"), patch.object(E, "codex_run") as run:
            I.main()
        run.assert_not_called()
        summary = json.loads((E.RESULTS / f"{I.STEM}.json").read_text())
        self.assertEqual(summary["AI"]["n"], 1)
        self.assertFalse(summary["gate_inline"]["complete"])
        self.assertFalse(summary["gate_inline"]["pass"])

    def test_subset_aggregate_includes_valid_results_outside_selected_task(self):
        for module, variant, pair, gate in (
            (E, "sol_medium", "AB", "gate"),
            (I, "astra_inline", "AI", "gate_inline"),
        ):
            runs = E.RUNS_ROOT / variant
            for task in self.tasks:
                self.seed_one_win(runs, pair, module.CFG, module.JUDGE_TPL, task)
            with patch.object(sys, "argv", [module.__file__, "--phase", "aggregate", "--tasks", "T01"]), \
                    patch.object(E, "config_lock"), patch.object(E, "codex_run") as run:
                module.main()
            run.assert_not_called()
            summary = json.loads((E.RESULTS / f"{module.STEM}.json").read_text())
            self.assertEqual(summary[pair]["n"], 20)
            self.assertTrue(summary[gate]["complete"])
            self.assertTrue(summary[gate]["pass"])

    def test_failed_or_missing_execution_is_not_judged_or_counted(self):
        for module, pair, gate, judge in (
            (E, "AB", "gate", E.phase_judge),
            (I, "AI", "gate_inline", I.judge),
        ):
            for task in self.tasks:
                self.seed_one_win(module.RUNS, pair, module.CFG, module.JUDGE_TPL, task)
            last = self.tasks[-1]
            result = module.RUNS / last["id"] / f"exec_{pair[1]}" / "result.json"
            for state in ("failed", "nonzero", "missing"):
                with self.subTest(module=module.__name__, state=state):
                    if state == "missing":
                        result.unlink()
                    else:
                        result.write_text(json.dumps({"failed": state == "failed",
                                                      "exit": 1 if state == "nonzero" else 0,
                                                      "output": "Synthetic output"}))
                    with patch.object(E, "codex_run") as run:
                        with self.assertRaises((RuntimeError, FileNotFoundError)):
                            judge(last, pair)
                        module.aggregate(self.tasks)
                    run.assert_not_called()
                    summary = json.loads((E.RESULTS / f"{module.STEM}.json").read_text())
                    self.assertEqual(summary[pair]["n"], 19)
                    self.assertFalse(summary[gate]["complete"])
                    self.assertFalse(summary[gate]["pass"])

    def test_no_results_never_passes_gate(self):
        for module, gate in ((E, "gate"), (I, "gate_inline")):
            module.aggregate(self.tasks)
            summary = json.loads((E.RESULTS / f"{module.STEM}.json").read_text())
            self.assertFalse(summary[gate]["complete"])
            self.assertFalse(summary[gate]["pass"])

    def test_subset_all_limits_execution_but_aggregates_entire_task_set(self):
        for module, args, phases in (
            (E, ["run_eval.py", "--tasks", "T01", "--conds", "A,B", "--pairs", "AB"],
             ["phase_optimize", "phase_execute", "phase_judge"]),
            (I, ["run_inline.py", "--tasks", "T01"], ["opt_B", "exec_cond", "judge"]),
        ):
            with self.subTest(module=module.__name__), contextlib.ExitStack() as stack:
                stack.enter_context(patch.object(sys, "argv", args))
                stack.enter_context(patch.object(E, "config_lock"))
                aggregate = stack.enter_context(patch.object(module, "aggregate"))
                phase_mocks = []
                for name in phases:
                    fn = Mock(__name__=name)
                    stack.enter_context(patch.object(module, name, fn))
                    phase_mocks.append(fn)
                module.main()
            aggregate.assert_called_once_with(self.tasks)
            for fn in phase_mocks:
                self.assertGreater(fn.call_count, 0)
                self.assertTrue(all(call.args[0]["id"] == "T01" for call in fn.call_args_list))


if __name__ == "__main__":
    unittest.main()
