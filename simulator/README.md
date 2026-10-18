# simulator/

The AutoDRIVE Simulator lives here. **It is not committed** — everything in
this directory except this file and `.gitkeep` is ignored by git.

```sh
./scripts/fetch_simulator.sh            # the build for your machine
./scripts/fetch_simulator.sh --check    # what is installed?
./scripts/fetch_simulator.sh --force    # download it again
```

That downloads the `2026-icra` **compete** build from the
[AutoDRIVE release](https://github.com/AutoDRIVE-Ecosystem/AutoDRIVE-RoboRacer-Sim-Racing/releases/tag/2026-icra)
— about 140 MB — and unpacks it into `simulator/autodrive_simulator/`.

## Why it is not in the repository, or the image

It is a 140 MB binary that changes per platform and per release. Committing it
would make cloning miserable; baking it into the Docker image would make every
rebuild carry it. Fetching it separately also means macOS and Windows teams can
run the *native* simulator on their host while the devkit stays in the
container — see [docs/01-setup.md §1.6](../docs/01-setup.md).

Because it arrives through the bind mount at `/hackathon/simulator`, fetching a
new build on the host is picked up by the container immediately. No rebuild.

## Running it directly

Most of the time you do not need to — `ros2 launch roboracer_referee
simulator.launch.py` starts it alongside the bridge, and `evaluate.sh` runs the
whole thing. When you do:

```sh
./scripts/run_simulator.sh              # with a window
./scripts/run_simulator.sh --headless   # -batchmode -nographics
./scripts/run_simulator.sh --host 127.0.0.1 --port 4567
```

Remember the simulator is the **client**: it dials out to the devkit bridge,
which has to be listening first. See
[docs/02-simulator.md](../docs/02-simulator.md).
