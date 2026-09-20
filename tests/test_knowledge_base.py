from pathlib import Path

from modules.whatsapp_cs import knowledge_base


def test_load_knowledge_excludes_vault_metadata(monkeypatch, tmp_path: Path) -> None:
    knowledge_dir = tmp_path / "话术库"
    knowledge_dir.mkdir()
    (knowledge_dir / "service.md").write_text(
        "## Greeting\nUse the approved greeting.", encoding="utf-8"
    )

    (tmp_path / "README.md").write_text("Repository instructions", encoding="utf-8")
    (tmp_path / "DEV_LOG.md").write_text("Development notes", encoding="utf-8")
    (knowledge_dir / "_index.md").write_text("Navigation only", encoding="utf-8")
    hidden_dir = tmp_path / ".obsidian"
    hidden_dir.mkdir()
    (hidden_dir / "private.md").write_text("Workspace metadata", encoding="utf-8")

    monkeypatch.setattr(knowledge_base, "_check_embed_model", lambda: False)

    assert knowledge_base.load_knowledge(str(tmp_path)) == 1
    assert Path(knowledge_base._documents[0]["source"]).name == "service.md"
