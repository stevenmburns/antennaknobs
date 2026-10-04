"""scripts/verify_fly_fleet.sh against a fake flyctl and curl (AK#405, #403).

The deploy workflows' "Verify fleet convergence" step runs this script after
`flyctl deploy`. With idle regions on `auto_stop_machines = 'suspend'`, a
machine that is suspended or stopped when the deploy lands is updated and
left stopped (see the script's header for Fly's words), so convergence is
"on the release image", whatever the state. A machine flyd reverted to the
old image (#403) must still fail, running or not.

Nothing here talks to Fly: `flyctl` and `curl` are shell stubs on PATH that
print recorded-shape JSON and a page.
"""

from __future__ import annotations

import json
import os
import shutil
import stat
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "verify_fly_fleet.sh"
REPO = "registry.fly.io/antennaknobs"
NEW = "deployment-01K6NEWNEWNEWNEWNEWNEWNEW00"
OLD = "deployment-01K6OLDOLDOLDOLDOLDOLDOLD00"

pytestmark = pytest.mark.skipif(
    shutil.which("bash") is None or shutil.which("jq") is None,
    reason="needs bash and jq, as the deploy runner has",
)


def _machine(mid: str, region: str, state: str, tag: str) -> dict:
    # The fields `flyctl machines list --json` prints that the script reads,
    # in its shape (image_ref is what the machine is on; config.image what
    # the last update asked for).
    return {
        "id": mid,
        "name": f"antennaknobs-{region}",
        "state": state,
        "region": region,
        "image_ref": {
            "registry": "registry.fly.io",
            "repository": "antennaknobs",
            "tag": tag,
            "digest": "sha256:" + ("0" * 64),
        },
        "config": {"image": f"{REPO}:{NEW}"},
    }


def _write(path: Path, text: str) -> None:
    path.write_text(text)
    path.chmod(path.stat().st_mode | stat.S_IXUSR)


def _run(tmp_path: Path, machines: list[dict]) -> subprocess.CompletedProcess:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    (tmp_path / "releases.json").write_text(
        json.dumps([{"ImageRef": f"{REPO}:{NEW}"}, {"ImageRef": f"{REPO}:{OLD}"}])
    )
    (tmp_path / "machines.json").write_text(json.dumps(machines))
    calls = tmp_path / "flyctl.calls"
    _write(
        bin_dir / "flyctl",
        f"""#!/usr/bin/env bash
echo "$*" >> {calls}
case "$1" in
  releases) cat {tmp_path / "releases.json"} ;;
  machines|machine) cat {tmp_path / "machines.json"} ;;
  *) echo "fake flyctl: unexpected $*" >&2; exit 2 ;;
esac
""",
    )
    _write(
        bin_dir / "curl",
        """#!/usr/bin/env bash
for a in "$@"; do last=$a; done
case "$last" in
  */) echo '<script src="/assets/index-abc123.js"></script>' ;;
  *) : ;;
esac
""",
    )
    env = {
        **os.environ,
        "PATH": f"{bin_dir}:{os.environ['PATH']}",
        "FLEET_SETTLE_SECONDS": "0",
    }
    out = subprocess.run(
        ["bash", str(SCRIPT), "antennaknobs", "https://app.example.test"],
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )
    # Only reads: the check never deploys, scales or touches a machine.
    for line in calls.read_text().splitlines():
        assert line.split()[0] in ("releases", "machines"), line
        assert "list" in line or line.startswith("releases"), line
    return out


def test_all_running_on_the_new_image_converges(tmp_path):
    out = _run(
        tmp_path,
        [
            _machine("e2865013be1d86", "sjc", "started", NEW),
            _machine("148e21ea7d4e89", "ams", "started", NEW),
            _machine("3d8d9e1b6e1d28", "nrt", "started", NEW),
        ],
    )
    assert out.returncode == 0, out.stdout + out.stderr
    assert f"fleet converged on {NEW}" in out.stdout


@pytest.mark.parametrize("state", ["suspended", "stopped"])
def test_an_idle_region_on_the_new_image_converges(tmp_path, state):
    out = _run(
        tmp_path,
        [
            _machine("e2865013be1d86", "sjc", "started", NEW),
            _machine("148e21ea7d4e89", "ams", state, NEW),
            _machine("3d8d9e1b6e1d28", "nrt", "stopped", NEW),
        ],
    )
    assert out.returncode == 0, out.stdout + out.stderr
    assert f"region=ams state={state}" in out.stdout


@pytest.mark.parametrize("state", ["started", "stopped", "suspended"])
def test_a_machine_reverted_to_the_old_image_fails(tmp_path, state):
    out = _run(
        tmp_path,
        [
            _machine("e2865013be1d86", "sjc", "started", NEW),
            _machine("148e21ea7d4e89", "ams", state, OLD),
        ],
    )
    assert out.returncode == 1
    assert "fleet did not converge" in out.stdout
    assert f"148e21ea7d4e89 (ams): state={state} image={OLD}" in out.stdout
    assert "e2865013be1d86 (sjc)" not in out.stdout.split("did not converge")[1]


def test_a_failed_machine_fails_even_on_the_new_image(tmp_path):
    out = _run(
        tmp_path,
        [
            _machine("e2865013be1d86", "sjc", "started", NEW),
            _machine("148e21ea7d4e89", "ams", "failed", NEW),
        ],
    )
    assert out.returncode == 1
    assert "148e21ea7d4e89 (ams): state=failed" in out.stdout


def test_no_machines_fails(tmp_path):
    out = _run(tmp_path, [])
    assert out.returncode == 1
    assert "lists no machines" in out.stdout
