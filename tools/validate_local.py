"""Local stand-in for the checks CI would run.

hassfest and the HACS action run on GitHub; this approximates the parts of
them that can be checked with no network at all, plus the cross-file
consistency that nothing else checks: actions registered against actions
described, exceptions raised against exceptions declared, the quality scale
against the pinned rule list, the versions against each other. Run it before
a push so the push is not the first verification.

    python tools/validate_local.py
"""

from __future__ import annotations

import ast
import json
import os
import re
import sys
from typing import Any

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
DOMAIN = "envisalink_field_programmer"
COMP = os.path.join(ROOT, "custom_components", DOMAIN)
PLATFORMS = ("alarm_control_panel", "binary_sensor", "sensor", "switch")
# Files that raise or re-raise for the user: platforms, services, setup.
EXCEPTION_SOURCES = (
    "__init__.py",
    "coordinator.py",
    "programming.py",
    "field_programming_services.py",
    *(f"{p}.py" for p in PLATFORMS),
)

# hassfest requires these for a custom integration.
REQUIRED_MANIFEST = [
    "domain",
    "name",
    "documentation",
    "codeowners",
    "iot_class",
    "version",
]
VALID_IOT_CLASS = {
    "assumed_state",
    "cloud_polling",
    "cloud_push",
    "local_polling",
    "local_push",
    "calculated",
}

# Pinned from developers.home-assistant.io/docs/core/integration-quality-scale/checklist
# (checked 2026-09-02: 54 rules, none new or deprecated). The list is pinned
# here on purpose: a quality_scale.yaml that is missing a rule reads as
# complete, and checking against the full list turns an omission into a
# failure.
ALL_RULES = {
    # Bronze
    "action-setup",
    "appropriate-polling",
    "brands",
    "common-modules",
    "config-flow-test-coverage",
    "config-flow",
    "dependency-transparency",
    "docs-actions",
    "docs-conditions",
    "docs-high-level-description",
    "docs-installation-instructions",
    "docs-removal-instructions",
    "docs-triggers",
    "entity-event-setup",
    "entity-unique-id",
    "has-entity-name",
    "runtime-data",
    "test-before-configure",
    "test-before-setup",
    "unique-config-entry",
    # Silver
    "action-exceptions",
    "config-entry-unloading",
    "docs-configuration-parameters",
    "docs-installation-parameters",
    "entity-unavailable",
    "integration-owner",
    "log-when-unavailable",
    "parallel-updates",
    "reauthentication-flow",
    "test-coverage",
    # Gold
    "devices",
    "diagnostics",
    "discovery-update-info",
    "discovery",
    "docs-data-update",
    "docs-examples",
    "docs-known-limitations",
    "docs-supported-devices",
    "docs-supported-functions",
    "docs-troubleshooting",
    "docs-use-cases",
    "dynamic-devices",
    "entity-category",
    "entity-device-class",
    "entity-disabled-by-default",
    "entity-translations",
    "exception-translations",
    "icon-translations",
    "reconfiguration-flow",
    "repair-issues",
    "stale-devices",
    # Platinum
    "async-dependency",
    "inject-websession",
    "strict-typing",
}

failures: list[str] = []
notes: list[str] = []


def read(*parts: str) -> str:
    with open(os.path.join(*parts), encoding="utf-8") as fh:
        return fh.read()


def read_json(*parts: str) -> Any:
    return json.loads(read(*parts))


def check(condition: bool, message: str) -> None:
    if not condition:
        failures.append(message)


def constants(source: str, prefix: str) -> dict[str, str]:
    """Module-level string assignments whose name starts with prefix."""
    found: dict[str, str] = {}
    for node in ast.parse(source).body:
        if not isinstance(node, (ast.Assign, ast.AnnAssign)):
            continue
        target = node.targets[0] if isinstance(node, ast.Assign) else node.target
        if (
            isinstance(target, ast.Name)
            and target.id.startswith(prefix)
            and isinstance(node.value, ast.Constant)
            and isinstance(node.value.value, str)
        ):
            found[target.id] = node.value.value
    return found


def pyproject_version() -> str | None:
    text = read(ROOT, "pyproject.toml")
    match = re.search(r'^\[project\][^\[]*?^version\s*=\s*"([^"]+)"', text, re.M | re.S)
    return match.group(1) if match else None


def main() -> int:
    manifest = read_json(COMP, "manifest.json")
    const_src = read(COMP, "const.py")
    strings = read_json(COMP, "strings.json")

    # ---------------------------------------------------------- manifest
    for key in REQUIRED_MANIFEST:
        check(key in manifest, f"manifest.json missing required key {key!r}")
    check(
        manifest.get("domain") == DOMAIN,
        f"manifest domain is {manifest.get('domain')!r}",
    )
    check(
        manifest.get("iot_class") in VALID_IOT_CLASS,
        f"manifest iot_class {manifest.get('iot_class')!r} is not a valid value",
    )
    check(
        isinstance(manifest.get("codeowners"), list)
        and all(c.startswith("@") for c in manifest["codeowners"]),
        "manifest codeowners entries must start with @",
    )
    keys = list(manifest)
    check(
        keys[:2] == ["domain", "name"] and keys[2:] == sorted(keys[2:]),
        "manifest keys must be domain, name, then alphabetical (hassfest MANIFEST)",
    )
    check(
        "quality_scale" not in manifest,
        "quality_scale in manifest.json: the badge is core-only, a custom "
        "integration builds to the rules and does not claim a tier",
    )
    # Every homeassistant.components import must be declared, one way or the other.
    declared_components = set(manifest.get("dependencies", [])) | set(
        manifest.get("after_dependencies", [])
    )
    used_components: set[str] = set()
    for f in os.listdir(COMP):
        if f.endswith(".py"):
            used_components |= set(
                re.findall(r"^from homeassistant\.components\.(\w+)", read(COMP, f), re.M)
            )
    # Entity platform bases are imported by every platform and never declared.
    used_components -= set(PLATFORMS) | {"diagnostics"}
    check(
        used_components <= declared_components,
        f"manifest does not declare imported components {sorted(used_components - declared_components)}",
    )

    project_version = pyproject_version()
    check(
        project_version == manifest.get("version"),
        f"pyproject version {project_version!r} != manifest version {manifest.get('version')!r}",
    )

    # ---------------------------------------------------------- hacs.json
    hacs = read_json(ROOT, "hacs.json")
    check("name" in hacs, "hacs.json must contain name")
    check(
        hacs.get("homeassistant", "0") >= "2025.2.0",
        "hacs.json homeassistant floor below 2025.2.0, where "
        "homeassistant.helpers.service_info.dhcp first exists (the config flow "
        "imports DhcpServiceInfo from it)",
    )

    # ---------------------------------------------------------- brand images
    # Home Assistant 2026.3 and later serve these from the integration itself,
    # falling back logo.png -> icon.png, so only the icon pair has to exist.
    brand = os.path.join(COMP, "brand")
    for name in ("icon.png", "icon@2x.png"):
        check(os.path.isfile(os.path.join(brand, name)), f"missing brand/{name}")
    for name in ("logo.png", "logo@2x.png"):
        if os.path.isfile(os.path.join(brand, name)):
            notes.append(f"brand/{name} present; check it is not another copy of the icon")

    # ---------------------------------------------------------- translations
    en = read_json(COMP, "translations", "en.json")
    check(
        strings == en,
        "strings.json and translations/en.json differ - copy strings.json over",
    )
    for flow in ("config", "options"):
        for step, spec in strings.get(flow, {}).get("step", {}).items():
            data = set(spec.get("data", {}))
            described = set(spec.get("data_description", {}))
            check(
                data == described,
                f"{flow}.{step}: data_description {sorted(data ^ described)} out of step with data",
            )

    # ------------------------------------------------- entity translations
    # Every entity name comes from a translation key, and every declared key
    # belongs to an entity. A key on neither side is a name that silently
    # falls back to the object id.
    entity_strings = strings.get("entity", {})
    for platform in PLATFORMS:
        used = set(
            re.findall(r'_attr_translation_key\s*=\s*"([^"]+)"', read(COMP, f"{platform}.py"))
        )
        declared_keys = set(entity_strings.get(platform, {}))
        check(
            used <= declared_keys,
            f"{platform}.py uses translation keys {sorted(used - declared_keys)} "
            "that strings.json does not declare",
        )
        check(
            declared_keys <= used,
            f"strings.json declares entity keys {sorted(declared_keys - used)} "
            f"that {platform}.py does not use",
        )
    check(
        set(entity_strings) <= set(PLATFORMS),
        f"strings.json entity section names non-platforms {sorted(set(entity_strings) - set(PLATFORMS))}",
    )

    # ---------------------------------------------------------- actions
    services_yaml = os.path.join(COMP, "services.yaml")
    check(os.path.isfile(services_yaml), "services.yaml is missing")
    service_consts = set(constants(const_src, "SERVICE_").values())
    check(bool(service_consts), "const.py names no SERVICE_ constants")
    try:
        import yaml

        services = yaml.safe_load(read(services_yaml)) or {}
        check(
            set(services) == service_consts,
            f"services.yaml declares {sorted(services)} but const.py names "
            f"{sorted(service_consts)}",
        )
        # Fields are described inline in services.yaml (no services section
        # in strings.json yet); when one appears the two must agree.
        if "services" in strings:
            for name, spec in services.items():
                yaml_fields = set((spec or {}).get("fields", {}))
                described = set(strings["services"].get(name, {}).get("fields", {}))
                check(
                    yaml_fields == described,
                    f"action {name}: services.yaml fields {sorted(yaml_fields)} != "
                    f"strings.json fields {sorted(described)}",
                )
        # README documents every field of every action.
        readme = read(ROOT, "README.md")
        for name, spec in services.items():
            check(
                f"`{DOMAIN}.{name}`" in readme,
                f"README does not document action {name}",
            )
            for field in (spec or {}).get("fields", {}):
                check(
                    f"| `{field}` |" in readme,
                    f"README does not document field {field!r} of action {name}",
                )
    except ImportError:
        notes.append("PyYAML not installed - services.yaml not parsed")

    # ---------------------------------------------------------- icons
    # Actions and the entities with no device class carry an icon; entities
    # whose device class already supplies one are deliberately absent, so an
    # entry here that strings.json does not know is a typo, not an override.
    icons_path = os.path.join(COMP, "icons.json")
    check(os.path.isfile(icons_path), "icons.json is missing")
    if os.path.isfile(icons_path):
        icons = read_json(COMP, "icons.json")
        check(
            set(icons.get("services", {})) == service_consts,
            f"icons.json gives icons for {sorted(icons.get('services', {}))} but "
            f"const.py names {sorted(service_consts)}",
        )
        for platform, keys in icons.get("entity", {}).items():
            declared_keys = set(strings.get("entity", {}).get(platform, {}))
            check(
                set(keys) <= declared_keys,
                f"icons.json {platform} keys {sorted(set(keys) - declared_keys)} "
                "are not entity translation keys",
            )

    # ---------------------------------------------------------- quality scale
    scale_path = os.path.join(COMP, "quality_scale.yaml")
    check(os.path.isfile(scale_path), "quality_scale.yaml is missing")
    if os.path.isfile(scale_path):
        try:
            import yaml

            declared = yaml.safe_load(read(scale_path)).get("rules", {})
            missing = ALL_RULES - set(declared)
            check(not missing, f"quality_scale.yaml does not mention {sorted(missing)}")
            unknown = set(declared) - ALL_RULES
            check(not unknown, f"quality_scale.yaml invents rules {sorted(unknown)}")
            for rule, value in sorted(declared.items()):
                if isinstance(value, dict):
                    check(
                        value.get("status") in {"done", "todo", "exempt"},
                        f"{rule}: status must be done/todo/exempt",
                    )
                    if value.get("status") != "done":
                        check(
                            bool(str(value.get("comment", "")).strip()),
                            f"{rule}: a non-done status needs a comment saying why",
                        )
                else:
                    check(value == "done", f"{rule}: bare value must be 'done'")
            todo = sorted(
                r for r, v in declared.items() if isinstance(v, dict) and v.get("status") == "todo"
            )
            if todo:
                notes.append(f"quality scale still todo: {', '.join(todo)}")
        except ImportError:
            notes.append("PyYAML not installed - quality_scale.yaml not parsed")

    # ------------------------------------------------- exception translations
    # Every translated exception the code raises is declared, and nothing
    # declared is unused.
    exc_re = re.compile(r'translation_domain=DOMAIN,\s*translation_key="([^"]+)"')
    raised: set[str] = set()
    for f in EXCEPTION_SOURCES:
        raised |= set(exc_re.findall(read(COMP, f)))
    declared_exc = set(strings.get("exceptions", {}))
    check(
        raised <= declared_exc,
        f"code raises undeclared exception keys {sorted(raised - declared_exc)}",
    )
    check(
        declared_exc <= raised,
        f"strings.json declares unused exceptions {sorted(declared_exc - raised)}",
    )
    # Setup and poll exceptions must carry a translation, not an f-string.
    for f in ("__init__.py", "coordinator.py"):
        source = read(COMP, f)
        for exc in ("ConfigEntryNotReady", "ConfigEntryAuthFailed", "UpdateFailed"):
            for match in re.finditer(rf"raise {exc}\((.*?)\) from", source, re.S):
                check(
                    "translation_key=" in match.group(1),
                    f"{f}: {exc} raised without a translation key",
                )

    # ----------------------------------------------------- issue translations
    issue_consts = set(constants(const_src, "ISSUE_").values())
    declared_issues = set(strings.get("issues", {}))
    check(
        issue_consts == declared_issues,
        f"const.py issues {sorted(issue_consts)} != strings.json issues {sorted(declared_issues)}",
    )

    # ------------------------------------------------------------ platforms
    init_src = read(COMP, "__init__.py")
    check("CONFIG_SCHEMA" in init_src, "__init__.py has async_setup but no CONFIG_SCHEMA")
    for platform in PLATFORMS:
        check(
            f"Platform.{platform.upper()}" in init_src,
            f"{platform}.py exists but Platform.{platform.upper()} is not forwarded",
        )
        source = read(COMP, f"{platform}.py")
        check(
            "PARALLEL_UPDATES" in source,
            f"{platform}.py does not set PARALLEL_UPDATES",
        )
        check(
            "hass.data[" not in source,
            f"{platform}.py reads hass.data; the coordinator is entry.runtime_data",
        )

    # ---------------------------------------------------------- syntax
    for dirpath, _dirs, files in os.walk(COMP):
        for f in files:
            if f.endswith(".py"):
                path = os.path.join(dirpath, f)
                try:
                    ast.parse(read(path))
                except SyntaxError as err:
                    failures.append(f"{f}: {err}")

    # ---------------------------------------------------------- report
    print(f"manifest {manifest.get('domain')} {manifest.get('version')}")
    for n in notes:
        print(f"  NOTE   {n}")
    for f in failures:
        print(f"  FAIL   {f}")
    if not failures:
        print("  all offline checks passed")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
