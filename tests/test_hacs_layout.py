import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_hacs_companion_integration_layout_is_valid():
    integration_dir = ROOT / "custom_components" / "neohub_control"
    manifest_path = integration_dir / "manifest.json"

    assert (ROOT / "hacs.json").is_file()
    assert (integration_dir / "__init__.py").is_file()
    assert (integration_dir / "config_flow.py").is_file()
    assert (integration_dir / "strings.json").is_file()
    assert (integration_dir / "brand" / "icon.png").is_file()
    assert manifest_path.is_file()

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    required_keys = {
        "domain",
        "documentation",
        "issue_tracker",
        "codeowners",
        "name",
        "version",
    }

    assert required_keys <= set(manifest)
    assert manifest["domain"] == "neohub_control"
    assert manifest["config_flow"] is True


def test_hacs_companion_version_matches_addon_version():
    manifest = json.loads(
        (ROOT / "custom_components" / "neohub_control" / "manifest.json").read_text(encoding="utf-8")
    )
    addon_config_text = (ROOT / "addons" / "neohub_control" / "config.yaml").read_text(
        encoding="utf-8"
    )
    addon_version = next(
        line.split(":", 1)[1].strip().strip('"')
        for line in addon_config_text.splitlines()
        if line.startswith("version:")
    )

    assert manifest["version"] == addon_version
