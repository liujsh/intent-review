from intent_review.reviewers import clean_env


def test_clean_env_removes_nested_session_flags(monkeypatch):
    monkeypatch.setenv("CODEX_THREAD_ID", "parent")
    monkeypatch.setenv("CODEX_SANDBOX_NETWORK_DISABLED", "1")
    monkeypatch.setenv("CODEX_MANAGED_BY_NPM", "1")
    env = clean_env()
    assert "CODEX_THREAD_ID" not in env
    assert "CODEX_SANDBOX_NETWORK_DISABLED" not in env
    assert env["CODEX_MANAGED_BY_NPM"] == "1"
