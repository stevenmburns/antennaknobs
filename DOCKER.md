# Running AntennaKNoBs with Docker

The full web workbench, one command, no Python environment:

```bash
docker run --rm -p 8000:8000 stevenmburns/antennaknobs:latest
```

Open **http://localhost:8000** — pick a design, drag a knob.

Images are published to Docker Hub on every release, tagged with the
release version and `latest`:

```bash
docker run --rm -p 8000:8000 stevenmburns/antennaknobs:0.34.0   # pin a version
```

## Or: docker compose (recommended)

The repo's [`compose.yaml`](compose.yaml) takes care of the port mapping
and mounts your design folder:

```bash
docker compose up
```

That's the whole file's job — you can also just download `compose.yaml`
alone; it pulls the published image, no repo checkout needed.

## Your own designs

The workbench's **"Your designs"** panel serves antenna files from
`~/.antennaknobs/designs`. In a container that folder is empty unless
you mount it — `compose.yaml` does this by default:

```yaml
volumes:
  - ~/.antennaknobs/designs:/root/.antennaknobs/designs
```

(or add `-v ~/.antennaknobs/designs:/root/.antennaknobs/designs` to
`docker run`). Files are shared with any local install: edit on either
side, refresh the browser. Designs still need your per-file OK before
they run (the UI prompts); on a single-user machine you can pre-trust
your own folder with `-e ANTENNAKNOBS_TRUST_USER_DESIGNS=1`.

## What's in the image — and what isn't

The image contains the workbench and the **momwire** engine (the
default, in-house MoM solver) — everything on the tin works. The
optional **NEC2 reference engine** (`pynec-accel`, which wraps the
GPLv2 `nec2++`) is *not* included, keeping the published image
MIT/BSD-only. Adding it is one layer:

```dockerfile
FROM stevenmburns/antennaknobs:latest
RUN pip install "pynec-accel>=1.7.4.post1"
```

```bash
docker build -t antennaknobs-nec2 . && docker run --rm -p 8000:8000 antennaknobs-nec2
```

(`compose.yaml` carries this as a commented-out alternate service —
uncomment and `docker compose up` builds it for you.)

## Developing antennaknobs itself with Docker

There's a second image for that: **`stevenmburns/antennaknobs-dev`** —
the full dev toolchain (Python 3.12, the C++ compiler momwire's
accelerator needs, Node 22 for the Vite frontend) with **no sources**.
Mount your checkout and follow the README's dev flow inside it:

```bash
git clone --recurse-submodules https://github.com/stevenmburns/antennaknobs
docker run -it --rm -v "$PWD/antennaknobs:/work" -w /work   -p 8000:8000 -p 5173:5173 stevenmburns/antennaknobs-dev
# inside: python -m venv .venv && . .venv/bin/activate
#         pip install -e ./momwire        # compiles the C++ accelerator
#         pip install -e ".[web]"
#         (cd src/antennaknobs/web/frontend && npm ci)
#         ... then uvicorn on 8000, vite dev on 5173 (README "Running it")
```

Built from [`Dockerfile.dev`](Dockerfile.dev); published manually and
rarely (the toolchain is stable), not on every release.

## Good to know

- **The container runs unlocked**, exactly like a local install: no
  login, no solve-size limits. Keep it on localhost or a network you
  control. If you re-host it on the open internet, turn on the shared
  instance's caps with `-e ANTENNAKNOBS_HOSTED=1`.
- **Platform**: `linux/amd64`. On Apple Silicon it runs under emulation
  (slower solves); a native install (`pip install "antennaknobs[web]"`)
  is the better path there.
- **Prefer no Docker?** The PyPI wheel ships the same browser UI — see
  [Install](README.md#install) in the README.
