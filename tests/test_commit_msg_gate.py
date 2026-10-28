"""commit-msg 门禁的自测：真的能拦住该拦的提交。

**在临时克隆里跑**，绝不碰当前工作区（上一版在仓库里直接 commit 再
`git checkout -- .`，把未提交的 hook 改动一起还原了 —— 教训）。

    python -X utf8 tests/test_commit_msg_gate.py
"""
from __future__ import annotations

import pathlib
import shutil
import subprocess
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parent.parent


class Repo:
    def __init__(self, path: pathlib.Path):
        self.path = path

    def git(self, *args: str) -> subprocess.CompletedProcess:
        return subprocess.run(["git", *args], cwd=self.path, capture_output=True, text=True,
                              encoding="utf-8", errors="replace")

    def commit(self, msg: str) -> subprocess.CompletedProcess:
        f = self.path / ".git" / "_msg.txt"
        f.write_text(msg, encoding="utf-8", newline="\n")
        return self.git("commit", "-F", str(f))


def main() -> int:
    tmp = pathlib.Path(tempfile.mkdtemp(prefix="gate-selftest-"))
    repo_dir = tmp / "repo"
    r = subprocess.run(["git", "clone", "-q", "--no-hardlinks", str(ROOT), str(repo_dir)],
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    if r.returncode != 0:
        print("clone 失败:", r.stderr[:300])
        return 1

    # 关键：把**工作区**里的 .githooks / tests / scripts 复制进去（可能还没提交），
    # 否则克隆里 pre-commit 要跑的那些脚本根本不存在
    for rel in (".githooks", "tests", "scripts", "bugs", "docs"):
        src = ROOT / rel
        if not src.exists():
            continue
        # bugs / docs 要先删掉克隆里的旧版本：copytree 只合并、不删除，
        # 否则克隆里还留着 v0.1 那些没有状态前缀的旧目录，台账检查必红
        if (repo_dir / rel).exists():
            shutil.rmtree(repo_dir / rel, ignore_errors=True)
        shutil.copytree(src, repo_dir / rel)
    # README 也要用工作区版本（克隆里是 v0.1 的老 README，里面有死链）
    if (ROOT / "README.md").exists():
        shutil.copy(ROOT / "README.md", repo_dir / "README.md")
    # ruff 的配置在 pyproject.toml 里；不复制的话克隆会用默认规则集，
    # 于是 run.py 里那条抑制 E402 的注释被判成无用注释，自测全红
    for name in ("pyproject.toml", "requirements-dev.txt"):
        if (ROOT / name).exists():
            shutil.copy(ROOT / name, repo_dir / name)
    repo = Repo(repo_dir)
    repo.git("config", "core.hooksPath", ".githooks")
    repo.git("config", "user.email", "t@t")
    repo.git("config", "user.name", "t")
    # 把工作区里的 .githooks 提交进临时仓库：否则每个 case 后面的
    # `git reset --hard` 会把 hook 还原成老版本，测的就一直是旧门禁
    # 克隆里的 docs / bugs/README.md 必须按克隆自己的内容重新生成，
    # 否则「生成物一致」那条门禁会把测试本身判红（工作区与克隆的台账不完全一样）
    subprocess.run([sys.executable, "-X", "utf8", str(repo_dir / "scripts" / "build_docs.py")],
                   cwd=str(repo_dir), capture_output=True, text=True,
                   encoding="utf-8", errors="replace")
    repo.git("add", "-A", ".githooks", "tests", "scripts", "bugs", "docs", "README.md",
                  "pyproject.toml", "requirements-dev.txt")
    repo.git("commit", "-q", "--no-verify", "-m", "test: 装上门禁")

    results = []

    def case(name: str, files: dict[str, str], msg: str, want: int) -> None:
        for rel, text in files.items():
            p = repo_dir / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(text, encoding="utf-8", newline="\n")
        repo.git("add", "-A")
        got = repo.commit(msg)
        ok = (got.returncode == 0) == (want == 0)
        results.append(ok)
        print(f"{'OK  ' if ok else 'FAIL'}  {name}（期望{'通过' if want == 0 else '被拒'}，"
              f"实际 rc={got.returncode}）")
        if not ok:
            print("   ", (got.stderr or "").strip().replace("\n", " | ")[:200])
        # 回到干净状态（临时仓库里可以随便来）
        repo.git("reset", "-q", "--hard", "HEAD")
        repo.git("clean", "-qfd")

    case("改 bugs/ 却不写 BUG 编号",
         {"bugs/未修-05-choice-panel-not-polled/note.md": "x"},
         "docs: 随手改一下台账\n", want=1)
    case("改 bugs/ 漏写编号（改了 05、07 只写 05）",
         {"bugs/未修-05-choice-panel-not-polled/a.md": "x",
          "bugs/已修（实机验证）-07-mulligan-hand-unreadable/b.md": "y"},
         "docs(bugs): 改两条 (BUG 05)\n", want=1)
    case("改 bugs/ 编号一致",
         {"bugs/未修-05-choice-panel-not-polled/c.md": "x"},
         "docs(bugs): 改一条 (BUG 05)\n", want=0)
    case("修复类改 src/ 却不写 BUG 编号",
         {"src/hspy/_gate_probe.py": "# probe\n"},
         "fix: 改点代码\n\n现象 一\n触发条件 二\n日志 三\n", want=1)
    case("feat 改 src/ 可以不提编号",
         {"src/hspy/_gate_probe.py": "# probe\n"},
         "feat: 加个功能\n", want=0)
    case("改 tests/ 却不说覆盖什么",
         {"tests/_gate_probe.py": "# probe\n"},
         "test: 加个测试\n", want=1)
    case("改 tests/ 且写了「覆盖：」",
         {"tests/_gate_probe.py": "# probe\n"},
         "test: 加个测试\n\n覆盖：门的自测\n", want=0)
    case("fix 提交缺 现象/触发条件/日志",
         {"src/hspy/_gate_probe.py": "# probe\n"},
         "fix(engine): 修个东西 (BUG 05)\n", want=1)
    case("提交信息里编造 BUG 99",
         {"src/hspy/_gate_probe.py": "# probe\n"},
         "fix(engine): 修个东西 (BUG 99)\n\n现象 一\n触发条件 二\n日志 三\n", want=1)

    shutil.rmtree(tmp, ignore_errors=True)
    ok = all(results)
    print(f"\n{'全部通过' if ok else '有失败'}（{sum(results)}/{len(results)}）")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
