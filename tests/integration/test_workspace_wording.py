from pathlib import Path


def test_no_legacy_workspace_or_role_wording_in_docs_and_batch_1_code() -> None:
    roots = [
        Path("AGENTS.md"),
        Path("README.md"),
        Path("PROJECT_BRIEF.md"),
        Path("CONTRIBUTING.md"),
        Path("SECURITY.md"),
        Path(".env.example"),
        Path("docs"),
        Path("apps"),
        Path("packages"),
        Path("supabase"),
    ]
    banned = ["ten" + "ant", "Ten" + "ant", "ten" + "ant_id", "Strate" + "gist", "strate" + "gist"]
    failures: list[str] = []

    for root in roots:
        paths = [root] if root.is_file() else list(root.rglob("*"))
        for path in paths:
            if path.is_dir() or path.suffix.lower() not in {".md", ".py", ".ts", ".tsx", ".sql", ".json", ".toml"}:
                continue
            text = path.read_text(encoding="utf-8")
            for term in banned:
                if term in text:
                    failures.append(f"{path}: contains {term}")

    assert failures == []


def test_batch_1_navigation_links_only_existing_batch_1_routes() -> None:
    layout_source = Path("apps/web/src/app/layout.tsx").read_text(encoding="utf-8")

    assert 'href: "/dashboard"' in layout_source
    assert 'href: "/products"' in layout_source
    assert 'href: "/products/new"' in layout_source
    assert 'href: "/approvals"' not in layout_source
