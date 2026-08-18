import os

from hostfront_manager.config import load_secrets_environment


def test_load_secrets_environment(tmp_path, monkeypatch):
    monkeypatch.delenv("HF_TEST_SECRET", raising=False)
    path = tmp_path / "secrets.env"
    path.write_text("HF_TEST_SECRET=value=with=equals\n")
    load_secrets_environment(path)
    assert os.environ["HF_TEST_SECRET"] == "value=with=equals"
