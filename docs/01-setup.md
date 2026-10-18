# 1. Setup

There are two pieces to install, and they are installed in different ways.

**The container** holds ROS 2 Humble, the AutoDRIVE Devkit, the reference
algorithms and the judging environment. You build it once from this repository.

**The AutoDRIVE Simulator** is a Unity binary — about 140 MB — that is not in
this repository and not in the image. One script downloads it.

Your code lives on your own machine and is mounted into the container at
`/hackathon`, so you edit files in your normal editor and nothing is lost when
the container stops.

---

## 1.1 Get the repository

```sh
git clone https://github.com/NTUDeepSpeed/Recruitment_Hackathon_2627.git ~/Recruitment_Hackathon_2627
cd ~/Recruitment_Hackathon_2627
git checkout track2
```

No `--recurse-submodules` on this branch and no submodules to forget: the
AutoDRIVE Devkit is committed into `external/autodrive_devkit/`. A ZIP download
works too, though a real clone is easier to submit from later.

---

## 1.2 Install Docker

### Windows 10/11

1. Install [Docker Desktop for Windows](https://www.docker.com/products/docker-desktop/).
2. Install WSL 2. Open **PowerShell as Administrator**:
   ```powershell
   wsl --install
   ```
   Reboot when it asks.
3. In Docker Desktop, go to **Settings → Resources → WSL integration**, enable
   your Ubuntu distro, and click **Apply & Restart**.
4. From then on, work in a WSL terminal:
   ```powershell
   wsl --set-default Ubuntu
   wsl ~
   ```

> Everything after this point happens **inside WSL**, not in PowerShell. If you
> run the scripts from PowerShell they will tell you so and stop.

> Cannot paste into the terminal? Right-click the window title → *Properties* →
> tick *Use Ctrl+Shift+C/V as Copy/Paste*.

### macOS

1. Install the Xcode command line tools if you have not already:
   ```sh
   xcode-select --install
   ```
2. Install [Docker Desktop for Mac](https://docs.docker.com/desktop/install/mac-install/)
   — pick the Apple Silicon or Intel build to match your machine.
3. Launch Docker Desktop and wait for the whale icon to stop animating.

Apple Silicon works, with one wrinkle: the simulator is a native macOS build and
runs on your Mac rather than in the container. See §1.6.

### Ubuntu / Debian Linux

1. Install [Docker Engine](https://docs.docker.com/engine/install/ubuntu/).
   Do **not** use Docker Desktop on Linux — it runs a VM you do not need and it
   is the usual reason a container cannot see a GPU.
2. Add yourself to the `docker` group so you do not need `sudo`:
   ```sh
   sudo usermod -aG docker "$USER"
   newgrp docker
   ```
   (Full instructions: [post-install steps](https://docs.docker.com/engine/install/linux-postinstall/).)
3. Check it works:
   ```sh
   docker run --rm hello-world
   ```

---

## 1.3 Fetch the simulator

```sh
./scripts/fetch_simulator.sh
```

It works out which build you need, downloads it from the AutoDRIVE release and
unpacks it into `simulator/`. That folder is in `.gitignore`: it is never
committed, and the script is how everyone — including the judges and CI — gets
the same binary.

```sh
./scripts/fetch_simulator.sh --check      # what is installed?
./scripts/fetch_simulator.sh --force      # download it again
./scripts/fetch_simulator.sh --platform macos
```

On Linux and WSL you want the Linux build, which is the default: it runs inside
the container and that is what a scored run drives. On macOS and Windows you
want the native build, which runs on your host — §1.6.

> The download is about 140 MB and the release carries no checksum, so the
> script's only integrity check is that what came back is a readable archive of
> roughly the right size. If it complains that the download is a few kilobytes,
> something on your network handed back a login page; try again, or fetch the
> URL it prints in a browser and unzip it into `simulator/` yourself.

---

## 1.4 Build the image

Pick the folder for your platform. The commands below use Linux; swap in
`macos` or `windows` as appropriate.

```sh
cd ~/Recruitment_Hackathon_2627
./install/linux/setup.sh
```

This takes **10 to 20 minutes** the first time: it pulls the ROS 2 Humble base
image and installs RViz, the devkit's dependencies and the graphics libraries
the simulator links against. Later builds are cached and take seconds.

If a build step fails, read the last few lines of output — the Dockerfile
checks its own work and says which step broke and why.
`./install/linux/setup.sh --no-cache` forces a clean rebuild.

> **ROS 2 Humble, not Jazzy.** That is deliberate: the official AutoDRIVE
> competition image is `ros:humble`, and the devkit's websocket stack only
> works on the versions that ship with it. Track 1 was Jazzy; this is not.

---

## 1.5 Start the container

```sh
./install/linux/run.sh
```

You land in a shell inside the container, at `/hackathon`. ROS is already
sourced.

For more terminals — and you will want three or four — open new host terminals
and run:

```sh
./install/linux/shell.sh
```

To shut everything down:

```sh
./install/linux/stop.sh
```

### Where the simulator window appears

| Platform | Where |
| --- | --- |
| Linux | Directly on your desktop, via the host X server |
| Windows / WSL | Directly on your desktop, via WSLg |
| macOS | On your Mac — the simulator runs natively, see §1.6 |

If nothing appears on Linux or WSL, fall back to the browser:

```sh
./install/linux/run.sh --novnc
```

and open <http://localhost:8080/vnc.html>.

You do not need a window at all to race. A scored run is headless.

### GPU

If an NVIDIA GPU is visible, `run.sh` attaches it automatically and falls back
to CPU-only if Docker cannot. Force it either way with `--gpu` or `--no-gpu`.

The GPU is there for **your** code — a learned policy, a planner — and for
rendering the simulator when you want to watch it. A scored run uses
`-batchmode -nographics`, which creates no graphics device at all, so judging
does not depend on it. The container is Python 3.10, so CUDA builds of PyTorch
and friends install and run; see [chapter 5](05-evaluation.md#58-judging-day).

---

## 1.6 Running the simulator on your host (macOS, Windows)

The container cannot run a native macOS or Windows simulator, so on those
platforms the simulator runs on your machine and the devkit runs in the
container. They talk over port 4567, which `docker-compose.yml` publishes.

**The direction of that connection is the opposite of what people expect, and
getting it backwards is the single most common setup failure.** The bridge
inside the container is the *server*: it listens on 4567. The simulator is the
*client*: you tell it where the bridge is and it dials out.

So the order is fixed:

1. Start the container and, inside it, the bridge:
   ```sh
   ros2 launch roboracer_referee simulator.launch.py simulator:=false rviz:=false
   ```
2. Then start the simulator on your host, by double-clicking it or:
   ```sh
   ./scripts/run_simulator.sh
   ```
3. In the simulator's **Menu Panel**, set the IP to `127.0.0.1` and the port to
   `4567`, and press **Connect**. Set the vehicle to **Autonomous**.

Topics appear the moment that connection lands. If they do not, nothing is
listening on 4567 — start the bridge first.

To score a run this way, tell `evaluate.sh` not to start a simulator of its own:

```sh
./scripts/evaluate.sh --team my_team --no-simulator
```

Linux and WSL users can do this too — it is a reasonable way to watch a run at
full graphics while everything else stays in the container — but the default
path, with both in the container, is simpler and is what judging uses.

---

## 1.7 Build the workspace and drive

Inside the container:

```sh
cd /hackathon/race_ws
colcon build --symlink-install
source install/local_setup.bash
```

`--symlink-install` means Python edits take effect without rebuilding. You only
need to re-run `colcon build` after adding a new file or changing `setup.py`.

Now, in two separate container shells:

```sh
# Terminal 1 — simulator and bridge
ros2 launch roboracer_referee simulator.launch.py

# Terminal 2 — your car
ros2 run team_driver driver
```

The car should set off — slowly, in a straight line, and into the first thing
in front of it. **That is correct.** The template in
[`race_ws/src/team_driver/team_driver/driver.py`](../race_ws/src/team_driver/team_driver/driver.py)
is wiring, not a driver: it has no steering logic at all. Seeing it move is how
you know the image, the bridge, the QoS settings and the workspace are all
working, and everything after that is yours to write — start with
[chapter 4](04-algorithms.md).

---

## 1.8 Check your environment is sane

```sh
./scripts/verify_judging_env.sh
```

This confirms the judging environment and the vendored devkit match the
official ones. Run it before you submit; an entry with a modified referee,
devkit or Dockerfile is not scored.

---

## 1.9 Troubleshooting

**Every topic is listed, but nothing ever publishes**
This is the one to know about. Check the socket:
```sh
netstat -tnp | grep 4567
```
*Nothing at all* — the simulator never reached the bridge. Is the bridge
running? Did you start the simulator first? Is the IP right?

*An `ESTABLISHED` connection and still no messages* — the TCP connection is up
but the Socket.IO handshake is not completing, which almost always means the
devkit's Python dependencies were replaced with newer ones. The pins in
`docker/devkit-requirements.txt` look absurdly old and are load-bearing; the
simulator advertises Engine.IO v4 in its handshake URL and then speaks v3
framing, so a modern `python-socketio` connects and then waits for ever.
Rebuild with `./install/<os>/setup.sh --no-cache`.

**`docker: command not found`, or "cannot connect to the Docker daemon"**
Docker Desktop is not running, or on Linux your user is not in the `docker`
group. On Windows, check Settings → Resources → WSL integration.

**`The AutoDRIVE Simulator is not installed`**
Run `./scripts/fetch_simulator.sh` on your **host**, not inside the container.
It lands in `simulator/`, which is bind-mounted, so the container sees it
immediately — no rebuild needed.

**The build fails at `apt-get` or `pip`**
Force a clean rebuild: `./install/linux/setup.sh --no-cache`. A half-cached
layer from an interrupted attempt is the usual cause.

**No simulator window**
Use `--novnc` and open <http://localhost:8080/vnc.html>. On Linux also check
`echo $DISPLAY` is set and try `xhost +local:root`. Remember you do not need a
window to race.

**The simulator prints pages of `Shader ... is not supported on this GPU`**
Normal and harmless in headless mode. `-nographics` means there is no GPU to
compile shaders for; the physics, the LiDAR and the lap timing are unaffected.
The ALSA and FMOD audio errors underneath them are the same story.

**The car does not move**
Check something is publishing:
```sh
ros2 topic hz /autodrive/roboracer_1/throttle_command
ros2 topic echo /autodrive/roboracer_1/throttle_command --once
```
No output means your driver node is not running or crashed — look at its
terminal. If it *is* publishing and the car still does not move, check that the
simulator is in **Autonomous** mode, not Manual.

**A topic exists, `ros2 topic info` shows a publisher, and `echo` shows nothing**
Quality-of-Service mismatch. The bridge publishes `RELIABLE` with a queue depth
of 1; a `BEST_EFFORT` subscriber — which is what people reach for with sensor
data — will never receive one message from it, silently. Use the profile in
`devkit_qos()` in
[`driver.py`](../race_ws/src/team_driver/team_driver/driver.py).

**`ros2: command not found` inside the container**
You are in a shell that did not source ROS. Exit and use
`./install/<os>/shell.sh`, or run `source /opt/ros/humble/setup.bash` by hand.

**`Package 'team_driver' not found`**
The workspace is not built or not sourced:
```sh
cd /hackathon/race_ws && colcon build --symlink-install && source install/local_setup.bash
```

**`Permission denied` deleting `race_ws/build` on the host**
The container builds as root through the bind mount. Delete them from inside
the container instead:
```sh
./install/linux/shell.sh 'rm -rf /hackathon/race_ws/build /hackathon/race_ws/install /hackathon/race_ws/log'
```

**A run fails to start with "address already in use"**
A bridge from a previous run is still holding port 4567.
`./scripts/evaluate.sh` cleans up after itself, but a run killed with Ctrl-C
partway through may not have. Inside the container:
```sh
pkill -f autodrive_bridge; pkill -f 'AutoDRIVE Simulator'
```

**Port 8080 is already in use**
```sh
NOVNC_PORT=8081 ./install/macos/run.sh
```

---

Next: **[2. The simulator](02-simulator.md)**
