"""git add/commit/pull/pushでdocs/・records/の変更を公開リポジトリへ反映する。

`git commit`の標準出力を文字列判定して成否を決めるのではなく、
`git diff --cached --quiet`の終了コード（差分なし=0）で「コミットすべき
変更があるか」を判定してから`git commit`を呼ぶ。
"""

from __future__ import annotations

import logging
import subprocess

from .config import REPO_ROOT

logger = logging.getLogger(__name__)


class PublishError(RuntimeError):
    pass


def _run(args: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(
        args, cwd=REPO_ROOT, capture_output=True, text=True, encoding="utf-8"
    )


def publish(commit_message: str) -> bool:
    """変更をコミットしてpushする。

    差分が無ければ何もせず`False`を返す（エラーではない＝同日の再実行や、
    生成結果が前回と同一だった場合の想定挙動）。git操作自体に失敗した場合は
    `PublishError`を送出する（無人実行のため、握りつぶさず必ずログに残す）。
    """
    add_result = _run(["git", "add", "-A"])
    if add_result.returncode != 0:
        raise PublishError(f"git add に失敗しました: {add_result.stderr}")

    diff_result = _run(["git", "diff", "--cached", "--quiet"])
    if diff_result.returncode == 0:
        logger.info("コミットする変更がありません。公開をスキップします。")
        return False

    commit_result = _run(["git", "commit", "-m", commit_message])
    if commit_result.returncode != 0:
        raise PublishError(f"git commit に失敗しました: {commit_result.stderr}")

    pull_result = _run(["git", "pull", "--ff-only"])
    if pull_result.returncode != 0:
        raise PublishError(
            "git pull --ff-only に失敗しました（リモートと履歴が乖離している"
            f"可能性があります）: {pull_result.stderr}"
        )

    push_result = _run(["git", "push"])
    if push_result.returncode != 0:
        raise PublishError(f"git push に失敗しました: {push_result.stderr}")

    logger.info("公開しました: %s", commit_message)
    return True
