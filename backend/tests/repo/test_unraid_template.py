"""The published Unraid template starts the unified image with safe defaults."""

from __future__ import annotations

from xml.etree import ElementTree

from tests.paths import REPO_ROOT


def _template() -> ElementTree.Element:
    return ElementTree.parse(REPO_ROOT / "templates/printstash-api.xml").getroot()


def _configs(kind: str) -> list[ElementTree.Element]:
    return _template().findall(f"Config[@Type='{kind}']")


def test_selects_the_unified_image() -> None:
    template = _template()

    assert template.findtext("Name") == "PrintStash"
    assert template.findtext("Repository") == "ghcr.io/xiao-villamor/printstash:latest"
    assert template.findtext("Network") == "bridge"
    assert template.findtext("TemplateURL", "").endswith(
        "/templates/printstash-api.xml"
    )
    assert not template.findtext("PostArgs")
    assert not (REPO_ROOT / "templates/printstash-frontend.xml").exists()


def test_exposes_only_the_web_port() -> None:
    assert [(item.get("Target"), item.text) for item in _configs("Port")] == [
        ("3000", "3000")
    ]
    assert _template().findtext("WebUI") == "http://[IP]:[PORT:3000]/"


def test_persists_the_data_parent() -> None:
    assert [
        (item.get("Target"), item.get("Default"), item.get("Mode"), item.text)
        for item in _configs("Path")
    ] == [
        ("/data", "/mnt/user/appdata/printstash", "rw", "/mnt/user/appdata/printstash")
    ]


def test_enables_first_run_without_a_blank_secret() -> None:
    variables = {item.get("Target"): item for item in _configs("Variable")}

    assert variables["VAULT_SETUP_MODE"].text == "trusted_network"
    assert "VAULT_JWT_SECRET" not in variables


def test_uses_unraid_file_identity() -> None:
    variables = {item.get("Target"): item for item in _configs("Variable")}

    assert variables["PUID"].text == "99"
    assert variables["PGID"].text == "100"


def test_restarts_the_supervised_container() -> None:
    variables = {item.get("Target"): item for item in _configs("Variable")}

    assert variables["VAULT_RESTART_ENABLED"].text == "true"
    assert _template().findtext("ExtraParams") == "--restart=unless-stopped"


def test_community_applications_profile_describes_one_container() -> None:
    profile = ElementTree.parse(REPO_ROOT / "ca_profile.xml").getroot()
    description = profile.findtext("Profile", "")

    assert "one container" in description
    assert "two-container users" in description
    assert "Install **PrintStash-API first**" not in description
