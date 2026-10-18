# `race_ws` — the racing workspace

A colcon workspace, bind-mounted into the container at `/hackathon/race_ws`.

```sh
cd /hackathon/race_ws
colcon build --symlink-install
source install/local_setup.bash
```

| Package | Yours? | What it is |
| --- | --- | --- |
| [`team_driver`](src/team_driver/) | **Yes** | Your entry. Start in [`team_driver/driver.py`](src/team_driver/team_driver/driver.py). It is wiring only — no driving logic ships with this repository. |
| [`roboracer_referee`](src/roboracer_referee/) | **Do not modify** | The judging environment: lap recording, penalties, result files, and the simulator launch. |

Two things this workspace does **not** contain:

- **The AutoDRIVE Devkit.** It is built into the image at `/sim_ws` from
  [`external/autodrive_devkit/`](../external/autodrive_devkit/), deliberately
  in its own overlay so that rebuilding this workspace can never shadow it.
  You may not modify it (rule 29).
- **The simulator.** It is a Unity binary in [`simulator/`](../simulator/),
  fetched by `./scripts/fetch_simulator.sh`.

`--symlink-install` means Python edits take effect without rebuilding. Rebuild
only after adding a file or changing `setup.py`.

> Building in the container writes `build/`, `install/` and `log/` as root
> through the bind mount, so deleting them from the host needs `sudo` — or just
> delete them from inside the container.

See [docs/04-algorithms.md](../docs/04-algorithms.md) and
[docs/05-evaluation.md](../docs/05-evaluation.md).
