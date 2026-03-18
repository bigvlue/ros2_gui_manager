# ROS2 GUI Manager

A single-file PyQt5 desktop tool for managing ROS2 workspaces, packages, and nodes — all from one window, without memorizing terminal commands.

![Python](https://img.shields.io/badge/Python-3.8%2B-blue)
![ROS2](https://img.shields.io/badge/ROS2-Humble%20%7C%20Iron%20%7C%20Jazzy-brightgreen)
![PyQt5](https://img.shields.io/badge/PyQt5-5.x-orange)
![Platform](https://img.shields.io/badge/Platform-Linux-lightgrey)

---

## Table of Contents

- [Requirements](#requirements)
- [Installation & Launch](#installation--launch)
- [UI Overview](#ui-overview)
- [Features](#features)
  - [Workspace Management](#workspace-management)
  - [Package Management](#package-management)
  - [Node Management](#node-management)
  - [Launch File Management](#launch-file-management)
  - [External Tool Integration](#external-tool-integration)
  - [Tabbed Terminal](#tabbed-terminal)
- [Configuration File](#configuration-file)
- [Architecture Overview](#architecture-overview)
- [Known Limitations](#known-limitations)

---

## Requirements

| Item | Minimum Version |
|------|----------------|
| OS | Ubuntu 20.04+ (Linux only) |
| Python | 3.8+ |
| ROS2 | Humble / Iron / Jazzy |
| PyQt5 | 5.x (auto-installed on first run if missing) |

> **Auto-install**: On first launch, if PyQt5 is not found, the tool prompts you to install it automatically via `pip`.  
> Manual install: `pip install PyQt5` or `sudo apt install python3-pyqt5`

---

## Installation & Launch

No installation required. Just run the single file.

```bash
# Run directly
python3 ros2_gui_manager.py

# Or grant execute permission and run
chmod +x ros2_gui_manager.py
./ros2_gui_manager.py
```

---

## UI Overview

```
┌─────────────────────────────────────────────────────────────┐
│  ◈ ROS2 GUI Manager   Distro [jazzy▾]  Workspace [~/ws▾]   │  ← Top Bar
│                                     Terminal  RViz2  rqt    │
├──────────────┬──────────────────────────────────────────────┤
│ PROJECT TREE │                                              │
│              │         Action Panel (context-sensitive)     │
│  📁 ros2_ws  │   (Workspace / Package / Node / Launch)      │
│  ├ 📦 pkg_a  │                                              │
│  │  🔵 node1 │                                              │
│  │  📜 launch│                                              │
│  └ 📦 pkg_b  │                                              │
│              │                                              │
│  [+ New] [Open]                                             │
├──────────────┴──────────────────────────────────────────────┤
│ OUTPUT  ● 🔵 pkg_a/node1  ■ pkg_b/node2                     │  ← Tabbed Terminal
│  $ colcon build ...                                         │
│  [✓  OK] exit code: 0                                       │
└─────────────────────────────────────────────────────────────┘
```

---

## Features

### Workspace Management

**Auto-detection**  
Scans `/opt/ros/` to detect installed ROS2 distributions automatically.  
Default selection priority: Jazzy → Humble → Iron.

**Create a New Workspace**  
Enter a name and location — the tool creates `<path>/<name>/src/` and registers it in the config.

**Open an Existing Workspace**  
When selecting a folder, the tool validates the presence of `src/` and `install/setup.bash`, displaying warnings if anything looks off.

**Build / Clean Actions**

| Action | Internal Command |
|--------|-----------------|
| Build Workspace | `colcon build --symlink-install` |
| Clean Workspace | Removes `build/` `install/` `log/` |
| Clean & Build | Clean followed by immediate rebuild |
| Source Workspace | Sources `install/setup.bash` into the current environment |

> **Symlink conflict auto-detection**: If `failed to create symbolic link` is detected in build output, a dialog automatically suggests running Clean & Build.

---

### Package Management

Select a workspace in the project tree, then use **Add Package** or the right-click context menu.

**Package Creation Options**

| Field | Details |
|-------|---------|
| Build type | `ament_python` or `ament_cmake` |
| Dependencies | Space-separated (e.g. `rclpy std_msgs`) |
| Internal command | `ros2 pkg create --build-type <type> --dependencies <deps> <name>` |

**Per-package Build / Clean**

- **Build Package**: Builds only the selected package via `colcon build --packages-select <pkg>`
- **Clean Package**: Removes only `build/<pkg>` and `install/<pkg>`, leaving the rest of the workspace intact

---

### Node Management

**Create a Node**  
Select a package, enter a node name, and the tool generates a ready-to-run Python node boilerplate.

Files created automatically:
- `src/<pkg>/<pkg>/<node_name>.py` — Python node with ROS2 Publisher template
- `src/<pkg>/<pkg>/__init__.py` — Package init file (if not present)
- `setup.py` — `console_scripts` entry point added automatically

Generated node template:
```python
class MyNode(Node):
    def __init__(self):
        super().__init__('my_node')
        self.publisher_ = self.create_publisher(String, 'topic', 10)
        self.timer = self.create_timer(0.5, self.timer_callback)
```

**Run a Node**  
Select a node in the tree → click **Run Node**:
1. A parameter dialog appears (`param:=value` format)
2. The node runs in a dedicated tab via `ros2 run <pkg> <node>`
3. Tab icon reflects the process state (`●` running / `■` stopped)

**Edit Source**  
Installed editors (VS Code, Gedit, Kate, etc.) are auto-detected and used to open the node source file.

---

### Launch File Management

`.py` and `.xml` launch files are displayed in the project tree under their respective packages.

**Run a Launch File**  
Before execution, the tool parses launch arguments and displays them in a dialog.

| File Format | Parsed Target |
|-------------|--------------|
| `.py` | `DeclareLaunchArgument(...)` |
| `.xml` | `<arg name="..." default="..."/>` |
| `.yaml` | Top-level key-value pairs |

Defaults are pre-filled and can be edited before launch.  
Internal command: `ros2 launch <pkg> <launch_file> [args...]`

---

### External Tool Integration

Toolbar buttons are activated once both a **Distro** and a **Workspace** are selected.

| Button | Action |
|--------|--------|
| Terminal | Opens a ROS2-sourced terminal (tries gnome-terminal → xterm → konsole) |
| RViz2 | Launches `rviz2` |
| rqt | Launches `rqt` |

---

### Tabbed Terminal

The bottom panel is a VS Code-style tabbed terminal.

- **OUTPUT tab**: Dedicated to build logs and general workspace commands
- **Node / Launch tabs**: Each running process gets its own tab

**Tab Icon Reference**

| Icon | Meaning |
|------|---------|
| `●` | Process running |
| `■` | Process exited |
| `🔵` | Python node |
| `⚙` | C++ node |
| `📜` | Launch file |

**Graceful Process Shutdown**  
Clicking the close button (X) on a running tab sends signals in sequence:

```
SIGINT → wait 3s → SIGTERM → wait 2s → SIGKILL
```

**Output Buffering**  
To prevent GUI freezes from high-frequency log output, a batched update strategy is used.

| Setting | Value |
|---------|-------|
| GUI update interval | 500 ms |
| Max buffer lines | 200 (older lines dropped on overflow) |
| Max lines per tab | 1,000 |

---

## Configuration File

The workspace list is persisted as a JSON file.

**Location**: `~/.config/ros2_gui_manager/config.json`

```json
{
  "workspaces": [
    "/home/user/ros2_ws",
    "/home/user/swarm_ws"
  ]
}
```

---

## Architecture Overview

```
ros2_gui_manager.py
│
├── _check_and_install_dependencies()   # PyQt5 auto-install on startup
│
├── Utilities
│   ├── get_ros2_distros()              # Scans /opt/ros/
│   ├── get_ros_env()                   # Sources distro setup.bash
│   └── get_ws_env()                    # Merges distro + workspace env
│
├── WorkerThread (QThread)              # General command runner
│                                       # Streams stdout in real time
│
├── NodeWorkerThread (QThread)          # Node / Launch process runner
│   ├── Batched output buffering (500ms flush)
│   └── kill_node()                     # SIGINT → SIGTERM → SIGKILL
│
├── NodeTemplates                       # Python node boilerplate generator
│
└── MainWindow (QMainWindow)
    ├── _make_topbar()                  # Distro / Workspace selector + tool buttons
    ├── _make_left_panel()              # PROJECT TREE (QTreeWidget)
    ├── _make_action_area()             # Context-sensitive action panel (QStackedWidget)
    │   ├── _page_workspace()
    │   ├── _page_package()
    │   ├── _page_node()
    │   └── _page_launch()
    ├── _make_output_panel()            # Tabbed terminal (QTabWidget)
    ├── _parse_node_params()            # Parses declare_parameter() calls
    ├── _parse_launch_params()          # Parses DeclareLaunchArgument / <arg>
    └── _apply_theme()                  # Auto dark / light theme from system palette
```

---

## Known Limitations

- **Linux only**: Relies on `/opt/ros/` paths and `bash`-based environment sourcing. Does not run on macOS or Windows.
- **Python nodes only**: Node boilerplate generation is Python-only. C++ nodes must be written manually after package creation.
- **One process per tab**: Each node run opens a new tab. Running the same node multiple times creates multiple tabs.
- **Launch argument parsing**: Complex conditional arguments (`IfCondition`, dynamically generated args, etc.) may not be parsed correctly.

---

## License

MIT
