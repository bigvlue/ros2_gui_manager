#!/usr/bin/env python3
"""
ROS2 GUI Manager V1.0
A visual tool for managing ROS2 workspaces, packages, and nodes.
"""

import sys
import os
import platform
import signal
import threading
import subprocess
import shutil
import json
from pathlib import Path

IS_MAC = platform.system() == "Darwin"


def _get_bash():
    """사용 가능한 bash 경로 반환.
    macOS 기본 /bin/bash 는 v3.2로 ROS2 setup 스크립트 실행 불가.
    Homebrew bash(5.x)를 우선 사용."""
    if IS_MAC:
        for path in ["/opt/homebrew/bin/bash", "/usr/local/bin/bash"]:
            if Path(path).exists():
                return path
    return "bash"


BASH = _get_bash()


def _get_ros2_search_paths():
    """ROS2가 설치될 수 있는 후보 경로 목록"""
    paths = [Path("/opt/ros")]
    # RoboStack / conda: $CONDA_PREFIX/opt/ros/
    conda_prefix = os.environ.get("CONDA_PREFIX")
    if conda_prefix:
        paths.append(Path(conda_prefix) / "opt" / "ros")
    # Homebrew (Apple Silicon: /opt/homebrew, Intel: /usr/local)
    if IS_MAC:
        paths.append(Path("/opt/homebrew/opt/ros"))
        paths.append(Path("/usr/local/opt/ros"))
    return paths


def _find_setup_bash(distro):
    """distro에 맞는 setup.bash 경로 반환, 없으면 None"""
    for ros_path in _get_ros2_search_paths():
        setup = ros_path / distro / "setup.bash"
        if setup.exists():
            return str(setup)
    return None


# ─────────────────────────────────────────────
#  Startup Dependency Check
# ─────────────────────────────────────────────

def _check_and_install_dependencies():
    """PyQt5 등 필수 패키지 확인 → 없으면 설치 여부 묻고 자동 설치"""

    missing = []

    # PyQt5 체크
    try:
        import PyQt5
    except ImportError:
        missing.append("PyQt5")

    if not missing:
        return True  # 모두 설치됨

    print("=" * 52)
    print("  ROS2 GUI Manager - 의존성 확인")
    print("=" * 52)
    print(f"\n  다음 패키지가 설치되어 있지 않습니다:")
    for pkg in missing:
        print(f"    - {pkg}")
    print()

    answer = input("  지금 설치하시겠습니까? [Y/n]: ").strip().lower()
    if answer in ("", "y", "yes"):
        in_venv = sys.prefix != sys.base_prefix
        for pkg in missing:
            print(f"\n  [{pkg}] 설치 중...")
            if in_venv:
                # venv 안에서는 --break-system-packages 불필요
                result = subprocess.run(
                    [sys.executable, "-m", "pip", "install", pkg],
                    capture_output=False
                )
            else:
                # --break-system-packages: Ubuntu 23.04+ 대응
                result = subprocess.run(
                    [sys.executable, "-m", "pip", "install", pkg,
                     "--break-system-packages"],
                    capture_output=False
                )
                if result.returncode != 0:
                    result = subprocess.run(
                        [sys.executable, "-m", "pip", "install", pkg],
                        capture_output=False
                    )
            if result.returncode == 0:
                print(f"  [OK] {pkg} 설치 완료")
            else:
                print(f"  [ERROR] {pkg} 설치 실패")
                print(f"  수동 설치: pip install {pkg}")
                if platform.system() == "Darwin":
                    print(f"  또는:      brew install pyqt@5")
                else:
                    print(f"  또는:      sudo apt install python3-pyqt5")
                return False
        print("\n  설치 완료. 프로그램을 시작합니다...\n")
        return True
    else:
        print("\n  설치를 취소했습니다.")
        print("  수동 설치 후 다시 실행해주세요:")
        print("    pip install PyQt5")
        print("    또는: bash install.sh")
        return False


# 의존성 체크 먼저 실행 (PyQt5 import 전)
if __name__ == "__main__":
    if not _check_and_install_dependencies():
        sys.exit(1)

from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QSplitter, QTreeWidget, QTreeWidgetItem, QStackedWidget, QLabel,
    QPushButton, QComboBox, QLineEdit, QTextEdit, QPlainTextEdit, QFormLayout,
    QDialog, QDialogButtonBox, QFileDialog, QMessageBox, QGroupBox,
    QGridLayout, QFrame, QMenu, QScrollArea, QSizePolicy, QToolButton,
    QStatusBar, QTabWidget, QSpinBox
)
from PyQt5.QtCore import Qt, QThread, pyqtSignal, QSize, QTimer
from PyQt5.QtGui import QFont, QColor, QIcon, QTextCursor


# ─────────────────────────────────────────────
#  Utilities
# ─────────────────────────────────────────────

def get_ros2_distros():
    distros = set()
    for ros_path in _get_ros2_search_paths():
        if ros_path.exists():
            for d in ros_path.iterdir():
                if d.is_dir() and (d / "setup.bash").exists():
                    distros.add(d.name)
    # 이미 source된 환경 (AMENT_PREFIX_PATH 설정된 경우)
    if os.environ.get("ROS_DISTRO") and os.environ.get("AMENT_PREFIX_PATH"):
        distros.add(os.environ["ROS_DISTRO"])
    return sorted(distros)


def get_ros_env(distro):
    env = os.environ.copy()
    setup_script = _find_setup_bash(distro)
    if not setup_script:
        return env
    cmd = f"{BASH} -c 'source {setup_script} && env'"
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    for line in result.stdout.splitlines():
        if '=' in line:
            key, _, val = line.partition('=')
            env[key] = val
    return env


def get_ws_env(distro, workspace):
    env = get_ros_env(distro)
    setup = Path(workspace) / "install" / "setup.bash"
    if setup.exists():
        ros_setup = _find_setup_bash(distro)
        src = f"source {ros_setup} && " if ros_setup else ""
        cmd = f"{BASH} -c '{src}source {setup} && env'"
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
        for line in result.stdout.splitlines():
            if '=' in line:
                key, _, val = line.partition('=')
                env[key] = val
    return env


# ─────────────────────────────────────────────
#  Worker Thread
# ─────────────────────────────────────────────

class WorkerThread(QThread):
    output_signal = pyqtSignal(str)
    finished_signal = pyqtSignal(int)

    def __init__(self, cmd, env=None, cwd=None):
        super().__init__()
        self.cmd = cmd
        self.env = env
        self.cwd = str(cwd) if cwd else None

    def run(self):
        try:
            proc = subprocess.Popen(
                [BASH, "-c", self.cmd],
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                env=self.env, cwd=self.cwd,
                text=True, bufsize=1
            )
            for line in iter(proc.stdout.readline, ''):
                self.output_signal.emit(line.rstrip())
            proc.wait()
            self.finished_signal.emit(proc.returncode)
        except Exception as e:
            self.output_signal.emit(f"[ERROR] {e}")
            self.finished_signal.emit(1)



# ─────────────────────────────────────────────
#  Node Worker Thread (직접 프로세스 관리)
# ─────────────────────────────────────────────

# ─────────────────────────────────────────────
#  Node Worker Thread (버퍼링 + 배치 업데이트)
# ─────────────────────────────────────────────

MAX_TAB_LINES    = 1000  # 탭당 최대 표시 줄 수 (QPlainTextEdit 자동 관리)
FLUSH_INTERVAL_MS = 500  # GUI 업데이트 주기 (ms) - 빠른 출력 대응
MAX_BUF_LINES    = 200   # 버퍼 최대 줄 수 - 초과 시 오래된 줄 드롭

class NodeWorkerThread(QThread):
    # 배치 버퍼 전체를 한번에 emit
    batch_signal    = pyqtSignal(str)
    finished_signal = pyqtSignal(int)

    def __init__(self, cmd, env=None, cwd=None):
        super().__init__()
        self.cmd  = cmd
        self.env  = env
        self.cwd  = str(cwd) if cwd else None
        self.proc = None
        self._buf  = []
        self._lock = threading.Lock()

    def run(self):
        import time
        try:
            self.proc = subprocess.Popen(
                [BASH, "-c", self.cmd],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                env=self.env, cwd=self.cwd,
                text=True, bufsize=1,
                preexec_fn=os.setsid
            )

            last_flush = time.monotonic()

            for line in iter(self.proc.stdout.readline, ''):
                with self._lock:
                    self._buf.append(line.rstrip())
                    # 버퍼 초과 시 오래된 줄 드롭 (GUI 과부하 방지)
                    if len(self._buf) > MAX_BUF_LINES:
                        drop = len(self._buf) - MAX_BUF_LINES
                        del self._buf[:drop]

                now = time.monotonic()
                if now - last_flush >= FLUSH_INTERVAL_MS / 1000:
                    self._flush()
                    last_flush = now

            # 남은 버퍼 flush
            self._flush()
            self.proc.wait()
            self.finished_signal.emit(self.proc.returncode)

        except Exception as e:
            self.batch_signal.emit(f"[ERROR] {e}")
            self.finished_signal.emit(1)

    def _flush(self):
        with self._lock:
            if not self._buf:
                return
            batch = "\n".join(self._buf)
            self._buf.clear()
        self.batch_signal.emit(batch)

    def kill_node(self):
        """SIGINT → 3s → SIGTERM → 2s → SIGKILL 단계적 종료"""
        if not self.proc:
            return
        try:
            pgid = os.getpgid(self.proc.pid)
        except (ProcessLookupError, OSError):
            return

        def _do_kill():
            import time
            for sig, wait_sec in [(signal.SIGINT, 3), (signal.SIGTERM, 2), (signal.SIGKILL, 0)]:
                try:
                    if self.proc.poll() is not None:
                        break
                    os.killpg(pgid, sig)
                except (ProcessLookupError, OSError):
                    break
                if wait_sec:
                    deadline = time.time() + wait_sec
                    while time.time() < deadline:
                        if self.proc.poll() is not None:
                            break
                        time.sleep(0.1)
            try:
                self.proc.wait(timeout=1)
            except Exception:
                pass

        threading.Thread(target=_do_kill, daemon=True).start()


class NodeTemplates:

    @staticmethod
    def python_node(package_name, node_name):
        class_name = ''.join(w.capitalize() for w in node_name.split('_'))
        return f'''#!/usr/bin/env python3
"""
Node: {node_name}
Package: {package_name}
"""
import rclpy
from rclpy.node import Node
from std_msgs.msg import String


class {class_name}(Node):

    def __init__(self):
        super().__init__('{node_name}')
        self.publisher_ = self.create_publisher(String, 'topic', 10)
        self.timer = self.create_timer(0.5, self.timer_callback)
        self.i = 0
        self.get_logger().info(f'{class_name} node started.')

    def timer_callback(self):
        msg = String()
        msg.data = f'Hello from {node_name}: {{self.i}}'
        self.publisher_.publish(msg)
        self.get_logger().info(f'Publishing: "{{msg.data}}"')
        self.i += 1


def main(args=None):
    rclpy.init(args=args)
    node = {class_name}()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
'''

    @staticmethod
    def init_py():
        return "# ROS2 Python package\n"

    @staticmethod
    def update_setup_py(setup_py_path, pkg_name, node_name):
        if not setup_py_path.exists():
            return False
        content = setup_py_path.read_text()
        entry = f"            '{node_name} = {pkg_name}.{node_name}:main',"
        if f"'{node_name} =" in content:
            return True  # already exists
        target = "'console_scripts': ["
        if target in content:
            content = content.replace(target, f"{target}\n{entry}")
            setup_py_path.write_text(content)
            return True
        return False


# ─────────────────────────────────────────────
#  Divider
# ─────────────────────────────────────────────

def make_separator():
    line = QFrame()
    line.setFrameShape(QFrame.HLine)
    line.setFrameShadow(QFrame.Sunken)
    line.setStyleSheet("color: #2d2d44;")
    return line


# ─────────────────────────────────────────────
#  SSH Connection
# ─────────────────────────────────────────────

class ManualSpinBox(QSpinBox):
    """↑↓ 버튼 클릭 및 휠로 값이 바뀌어도 editingFinished를 발생시키지 않는 SpinBox.
    적용은 Enter 키 또는 외부 '적용' 버튼으로만 한다."""

    def stepBy(self, steps):
        """↑↓ 버튼 / 키보드 방향키: 값만 바꾸고 시그널 없음"""
        self.blockSignals(True)
        super().stepBy(steps)
        self.blockSignals(False)

    def wheelEvent(self, event):
        """마우스 휠: 스크롤 무시"""
        event.ignore()


class SSHConnection:
    """paramiko 기반 SSH 연결 래퍼"""

    def __init__(self, host, user, port=22, key_path=None, password=None):
        try:
            import paramiko
        except ImportError:
            raise ImportError(
                "paramiko 패키지가 필요합니다.\n"
                "설치:  pip install paramiko\n"
                "또는:  pip install paramiko --break-system-packages"
            )
        self.host = host
        self.user = user
        self.port = port
        self._client = paramiko.SSHClient()
        self._client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        connect_kwargs = {}
        if key_path and Path(key_path).expanduser().exists():
            connect_kwargs["key_filename"] = str(Path(key_path).expanduser())
        if password:
            connect_kwargs["password"] = password
        self._client.connect(host, port=port, username=user,
                             timeout=10, **connect_kwargs)
        self._sftp = None

    @property
    def id(self):
        return f"{self.user}@{self.host}:{self.port}"

    @property
    def label(self):
        return f"{self.user}@{self.host}"

    @property
    def sftp(self):
        if self._sftp is None:
            self._sftp = self._client.open_sftp()
        return self._sftp

    def exec(self, cmd):
        """명령 실행 → (stdout_str, returncode)"""
        _, stdout, _ = self._client.exec_command(cmd, get_pty=False)
        out = stdout.read().decode(errors="replace")
        rc = stdout.channel.recv_exit_status()
        return out, rc

    def open_channel(self, cmd):
        """스트리밍 실행용 채널 반환 (pty 포함)"""
        chan = self._client.get_transport().open_session()
        chan.get_pty()
        chan.exec_command(cmd)
        return chan

    def exists(self, path):
        try:
            self.sftp.stat(path)
            return True
        except Exception:
            return False

    def listdir_attr(self, path):
        """[(name, is_dir), ...]"""
        import stat as _stat
        try:
            attrs = self.sftp.listdir_attr(path)
            return [(a.filename, _stat.S_ISDIR(a.st_mode or 0)) for a in attrs]
        except Exception:
            return []

    def read_text(self, path):
        try:
            with self.sftp.open(path) as f:
                return f.read().decode(errors="replace")
        except Exception:
            return ""

    def get_ros2_distros(self):
        out, _ = self.exec("ls /opt/ros 2>/dev/null")
        distros = [d.strip() for d in out.splitlines() if d.strip()]
        out2, _ = self.exec("echo $ROS_DISTRO")
        rd = out2.strip()
        if rd and rd not in distros:
            distros.append(rd)
        return sorted(set(distros))

    def get_ros_env(self, distro):
        setup = f"/opt/ros/{distro}/setup.bash"
        out, _ = self.exec(f"bash -c 'source {setup} 2>/dev/null && env'")
        env = {}
        for line in out.splitlines():
            if "=" in line:
                k, _, v = line.partition("=")
                env[k] = v
        return env

    def close(self):
        try:
            if self._sftp:
                self._sftp.close()
            self._client.close()
        except Exception:
            pass


# ─────────────────────────────────────────────
#  Remote Worker Threads
# ─────────────────────────────────────────────

class RemoteWorkerThread(QThread):
    output_signal = pyqtSignal(str)
    finished_signal = pyqtSignal(int)

    def __init__(self, ssh: SSHConnection, cmd: str, cwd=None):
        super().__init__()
        self.ssh = ssh
        self.full_cmd = f"cd {cwd} && {cmd}" if cwd else cmd
        self._chan = None

    def run(self):
        try:
            self._chan = self.ssh.open_channel(self.full_cmd)
            buf = b""
            while not self._chan.exit_status_ready():
                if self._chan.recv_ready():
                    buf += self._chan.recv(4096)
                    while b"\n" in buf:
                        line, buf = buf.split(b"\n", 1)
                        self.output_signal.emit(line.decode(errors="replace").rstrip())
            # drain
            while self._chan.recv_ready():
                buf += self._chan.recv(4096)
            for line in buf.decode(errors="replace").splitlines():
                self.output_signal.emit(line.rstrip())
            rc = self._chan.recv_exit_status()
            self.finished_signal.emit(rc)
        except Exception as e:
            self.output_signal.emit(f"[ERROR] {e}")
            self.finished_signal.emit(1)


class RemoteNodeWorkerThread(QThread):
    batch_signal = pyqtSignal(str)
    finished_signal = pyqtSignal(int)

    def __init__(self, ssh: SSHConnection, cmd: str, cwd=None):
        super().__init__()
        self.ssh = ssh
        self.full_cmd = f"cd {cwd} && {cmd}" if cwd else cmd
        self._chan = None
        self._buf = []
        self._lock = threading.Lock()

    def stop(self):
        if self._chan:
            try:
                self._chan.close()
            except Exception:
                pass

    def run(self):
        import time
        try:
            self._chan = self.ssh.open_channel(self.full_cmd)
            last_flush = time.monotonic()
            while not self._chan.exit_status_ready():
                if self._chan.recv_ready():
                    data = self._chan.recv(4096).decode(errors="replace")
                    lines = data.splitlines()
                    with self._lock:
                        self._buf.extend(lines)
                        if len(self._buf) > MAX_BUF_LINES:
                            self._buf = self._buf[-MAX_BUF_LINES:]
                now = time.monotonic()
                if now - last_flush >= FLUSH_INTERVAL_MS / 1000:
                    with self._lock:
                        if self._buf:
                            self.batch_signal.emit("\n".join(self._buf))
                            self._buf.clear()
                    last_flush = now
                else:
                    time.sleep(0.05)
            while self._chan.recv_ready():
                data = self._chan.recv(4096).decode(errors="replace")
                with self._lock:
                    self._buf.extend(data.splitlines())
            with self._lock:
                if self._buf:
                    self.batch_signal.emit("\n".join(self._buf))
                    self._buf.clear()
            rc = self._chan.recv_exit_status()
            self.finished_signal.emit(rc)
        except Exception as e:
            self.batch_signal.emit(f"[ERROR] {e}")
            self.finished_signal.emit(1)


# ─────────────────────────────────────────────
#  SSH Connect Dialog
# ─────────────────────────────────────────────

def _parse_ssh_str(s: str) -> dict:
    """'ssh user@host', 'user@host', 'ssh user@host -p 2222', 'user@host:2222' 파싱"""
    import re
    s = s.strip()
    if s.startswith("ssh "):
        s = s[4:].strip()
    port = 22
    # -p 옵션
    m = re.search(r"-p\s+(\d+)", s)
    if m:
        port = int(m.group(1))
        s = re.sub(r"\s*-p\s+\d+", "", s).strip()
    # host:port 형식
    if "@" in s and ":" in s.split("@", 1)[1]:
        at_part = s.split("@", 1)[1]
        if ":" in at_part:
            host_part, port_str = at_part.rsplit(":", 1)
            try:
                port = int(port_str)
                s = s.split("@")[0] + "@" + host_part
            except ValueError:
                pass
    if "@" in s:
        user, host = s.split("@", 1)
    else:
        host = s
        user = os.environ.get("USER", "ubuntu")
    return {"host": host.strip(), "user": user.strip(), "port": port}


class SSHConnectDialog(QDialog):
    """간단한 SSH 연결 다이얼로그: 'ssh user@host' 한 줄 입력"""

    def __init__(self, parent=None, default_str=""):
        super().__init__(parent)
        self.setWindowTitle("SSH 원격 연결")
        self.setFixedSize(420, 180)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(24, 24, 24, 16)
        lay.setSpacing(12)

        hint = QLabel("SSH 연결 문자열을 입력하세요:")
        hint.setObjectName("info_label")
        lay.addWidget(hint)

        self.ssh_in = QLineEdit(default_str)
        self.ssh_in.setPlaceholderText("ssh pinky@192.168.4.1  또는  user@host -p 2222")
        self.ssh_in.setMinimumWidth(360)
        lay.addWidget(self.ssh_in)

        self.pwd_in = QLineEdit()
        self.pwd_in.setEchoMode(QLineEdit.Password)
        self.pwd_in.setPlaceholderText("Password  (키 인증 시 비워두세요)")
        lay.addWidget(self.pwd_in)

        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.button(QDialogButtonBox.Ok).setText("연결")
        btns.button(QDialogButtonBox.Cancel).setText("취소")
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        lay.addWidget(btns)

        self.ssh_in.returnPressed.connect(self.pwd_in.setFocus)
        self.pwd_in.returnPressed.connect(self.accept)

    def get_params(self) -> dict:
        params = _parse_ssh_str(self.ssh_in.text())
        params["password"] = self.pwd_in.text()
        params["key"] = "~/.ssh/id_rsa"
        return params


class RemoteBrowseDialog(QDialog):
    """SFTP 기반 원격 디렉토리 브라우저"""

    def __init__(self, ssh: "SSHConnection", parent=None):
        super().__init__(parent)
        self.ssh = ssh
        self.setWindowTitle(f"원격 폴더 선택  [{ssh.label}]")
        self.setMinimumSize(500, 420)
        self.selected_path = ""

        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 12, 12, 10)
        lay.setSpacing(8)

        # 경로 표시 + 네비게이션
        nav = QHBoxLayout()
        self.path_edit = QLineEdit()
        self.path_edit.setObjectName("bar_combo")
        self.path_edit.returnPressed.connect(self._go_to_path)
        b_go   = QPushButton("이동")
        b_go.setObjectName("action_default")
        b_go.setFixedWidth(50)
        b_go.clicked.connect(self._go_to_path)
        b_up   = QPushButton("↑")
        b_up.setObjectName("action_default")
        b_up.setFixedWidth(36)
        b_up.clicked.connect(self._go_up)
        b_home = QPushButton("~")
        b_home.setObjectName("action_default")
        b_home.setFixedWidth(36)
        b_home.clicked.connect(self._go_home)
        for w in [self.path_edit, b_go, b_up, b_home]:
            nav.addWidget(w)
        lay.addLayout(nav)

        from PyQt5.QtWidgets import QListWidget
        self.lst = QListWidget()
        self.lst.setObjectName("proj_tree")
        self.lst.itemDoubleClicked.connect(self._on_dbl_click)
        lay.addWidget(self.lst)

        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.button(QDialogButtonBox.Ok).setText("선택")
        btns.button(QDialogButtonBox.Cancel).setText("취소")
        btns.accepted.connect(self._on_select)
        btns.rejected.connect(self.reject)
        lay.addWidget(btns)

        # 홈 디렉토리에서 시작
        home_out, _ = ssh.exec("echo $HOME")
        home = home_out.strip() or "/"
        self._navigate(home)

    def _navigate(self, path: str):
        import posixpath
        path = path.rstrip("/") or "/"
        entries = self.ssh.listdir_attr(path)
        if entries is None:
            return
        self.current_path = path
        self.path_edit.setText(path)
        self.lst.clear()
        from PyQt5.QtWidgets import QListWidgetItem
        for name, is_dir in sorted(entries, key=lambda x: (not x[1], x[0].lower())):
            if name.startswith("."):
                continue
            if is_dir:
                item = QListWidgetItem(f"📁  {name}")
                item.setData(Qt.UserRole, posixpath.join(path, name))
                item.setData(Qt.UserRole + 1, True)
                self.lst.addItem(item)

    def _on_dbl_click(self, item):
        if item.data(Qt.UserRole + 1):
            self._navigate(item.data(Qt.UserRole))

    def _go_up(self):
        import posixpath
        parent = posixpath.dirname(self.current_path)
        self._navigate(parent or "/")

    def _go_home(self):
        home_out, _ = self.ssh.exec("echo $HOME")
        self._navigate(home_out.strip() or "/")

    def _go_to_path(self):
        self._navigate(self.path_edit.text().strip())

    def _on_select(self):
        sel = self.lst.selectedItems()
        if sel:
            self.selected_path = sel[0].data(Qt.UserRole)
        else:
            self.selected_path = self.current_path
        self.accept()


# ─────────────────────────────────────────────
#  Main Window
# ─────────────────────────────────────────────

class MainWindow(QMainWindow):

    def __init__(self):
        super().__init__()
        self.setWindowTitle("ROS2 GUI Manager")
        self.setMinimumSize(1280, 820)
        self.ros_env = None
        self.current_distro = None
        self.current_workspace = None
        self.worker = None
        self.node_tabs = {}   # tab_index → NodeWorkerThread
        self.ssh_connections: dict[str, SSHConnection] = {}  # id → SSHConnection
        self.current_ssh: SSHConnection | None = None        # None = local

        self._build_ui()
        self._apply_theme()
        self._detect_ros2()
        self._setup_bashrc_prompt()

    # ── UI Construction ───────────────────────

    def _build_ui(self):
        root = QWidget()
        self.setCentralWidget(root)
        root_layout = QVBoxLayout(root)
        root_layout.setSpacing(0)
        root_layout.setContentsMargins(0, 0, 0, 0)

        root_layout.addWidget(self._make_topbar())

        body = QSplitter(Qt.Horizontal)
        body.setHandleWidth(2)
        root_layout.addWidget(body, stretch=1)

        body.addWidget(self._make_left_panel())

        right = QSplitter(Qt.Vertical)
        right.setHandleWidth(2)
        body.addWidget(right)

        right.addWidget(self._make_action_area())
        right.addWidget(self._make_output_panel())

        body.setSizes([280, 1000])
        right.setSizes([560, 260])

        self.statusBar().showMessage("Ready  —  ROS2 GUI Manager")

    def _make_topbar(self):
        bar = QWidget()
        bar.setFixedHeight(52)
        bar.setObjectName("topbar")
        lay = QHBoxLayout(bar)
        lay.setContentsMargins(14, 0, 14, 0)
        lay.setSpacing(8)

        logo = QLabel("◈  ROS2 GUI Manager")
        logo.setObjectName("logo")
        lay.addWidget(logo)
        lay.addStretch()

        def _sep():
            s = QLabel("│")
            s.setObjectName("bar_sep")
            s.setFixedWidth(14)
            lay.addWidget(s)

        # ROS2 Distro
        distro_lbl = QLabel("ROS")
        distro_lbl.setObjectName("bar_label")
        self.distro_combo = QComboBox()
        self.distro_combo.setMinimumWidth(110)
        self.distro_combo.setMaximumWidth(160)
        self.distro_combo.setObjectName("bar_combo")
        self.distro_combo.currentTextChanged.connect(self._on_distro_changed)
        lay.addWidget(distro_lbl)
        lay.addWidget(self.distro_combo)

        _sep()

        # Workspace
        ws_lbl = QLabel("WS")
        ws_lbl.setObjectName("bar_label")
        self.ws_combo = QComboBox()
        self.ws_combo.setMinimumWidth(180)
        self.ws_combo.setMaximumWidth(320)
        self.ws_combo.setSizePolicy(
            self.ws_combo.sizePolicy().horizontalPolicy(),
            self.ws_combo.sizePolicy().verticalPolicy()
        )
        self.ws_combo.setObjectName("bar_combo")
        self.ws_combo.currentTextChanged.connect(self._on_workspace_changed)
        lay.addWidget(ws_lbl)
        lay.addWidget(self.ws_combo)

        _sep()

        # ROS_DOMAIN_ID
        domain_lbl = QLabel("ID")
        domain_lbl.setObjectName("bar_label")
        self.domain_spin = ManualSpinBox()
        self.domain_spin.setRange(0, 232)
        self.domain_spin.setFixedWidth(64)
        self.domain_spin.setObjectName("bar_combo")
        self.domain_spin.setValue(int(os.environ.get("ROS_DOMAIN_ID", "0")))
        # ↑↓ 화살표 클릭 시 즉시 반영 방지: 시그널 연결 없음
        # Enter 키 또는 적용 버튼으로만 반영
        self.domain_spin.editingFinished.connect(
            lambda: self._on_domain_id_changed(self.domain_spin.value())
        )

        domain_apply = QPushButton("적용")
        domain_apply.setObjectName("topbar_btn")
        domain_apply.setFixedWidth(44)
        domain_apply.clicked.connect(
            lambda: self._on_domain_id_changed(self.domain_spin.value())
        )

        lay.addWidget(domain_lbl)
        lay.addWidget(self.domain_spin)
        lay.addWidget(domain_apply)

        _sep()

        # SSH 연결 버튼 + 상태
        self.ssh_btn = QPushButton("SSH")
        self.ssh_btn.setObjectName("topbar_btn")
        self.ssh_btn.setMinimumWidth(56)
        self.ssh_btn.clicked.connect(self._manage_ssh)
        lay.addWidget(self.ssh_btn)

        self.ssh_status_lbl = QLabel("")
        self.ssh_status_lbl.setObjectName("ssh_status")
        lay.addWidget(self.ssh_status_lbl)

        _sep()

        # External tools
        self.tool_btns = []
        for label, slot in [("Terminal", self._open_terminal),
                             ("RViz2",   self._open_rviz),
                             ("rqt",     self._open_rqt)]:
            btn = QPushButton(label)
            btn.setObjectName("topbar_btn")
            btn.setMinimumWidth(58)
            btn.clicked.connect(slot)
            btn.setEnabled(False)
            lay.addWidget(btn)
            self.tool_btns.append(btn)

        return bar

    def _make_left_panel(self):
        panel = QWidget()
        panel.setObjectName("left_panel")
        lay = QVBoxLayout(panel)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        header = QLabel("  PROJECT TREE")
        header.setObjectName("section_header")
        header.setFixedHeight(36)
        lay.addWidget(header)

        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.setObjectName("proj_tree")
        self.tree.setContextMenuPolicy(Qt.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self._context_menu)
        self.tree.itemClicked.connect(self._on_item_clicked)
        lay.addWidget(self.tree, stretch=1)

        # Bottom quick-add buttons (2×2 grid)
        btn_area = QWidget()
        btn_area.setObjectName("tree_btn_area")
        btn_lay = QGridLayout(btn_area)
        btn_lay.setContentsMargins(8, 6, 8, 8)
        btn_lay.setSpacing(5)

        for col in range(2):
            btn_lay.setColumnStretch(col, 1)

        for (text, slot), (r, c) in zip(
            [("+ New WS",   self._create_workspace),
             ("Open WS",    self._open_workspace),
             ("+ Remote",   self._open_remote_workspace),
             ("+ Package",  self._create_package)],
            [(0,0),(0,1),(1,0),(1,1)]
        ):
            b = QPushButton(text)
            b.setObjectName("tree_add_btn")
            b.clicked.connect(slot)
            btn_lay.addWidget(b, r, c)

        lay.addWidget(btn_area)

        return panel

    def _make_action_area(self):
        self.stack = QStackedWidget()
        self.stack.setObjectName("action_stack")

        self.stack.addWidget(self._page_welcome())   # 0
        self.stack.addWidget(self._page_workspace()) # 1
        self.stack.addWidget(self._page_package())   # 2
        self.stack.addWidget(self._page_node())      # 3
        self.stack.addWidget(self._page_launch())    # 4

        return self.stack

    def _page_welcome(self):
        p = QWidget()
        lay = QVBoxLayout(p)
        lay.setAlignment(Qt.AlignCenter)
        lbl = QLabel("Select an item from the tree\nor create a new workspace")
        lbl.setAlignment(Qt.AlignCenter)
        lbl.setObjectName("welcome_hint")
        lay.addWidget(lbl)
        return p

    def _page_workspace(self):
        p = QWidget()
        lay = QVBoxLayout(p)
        lay.setContentsMargins(24, 20, 24, 20)
        lay.setSpacing(14)

        title = QLabel("[WS]  Workspace")
        title.setObjectName("page_title")
        lay.addWidget(title)

        self.ws_info_name = QLabel("Name: —")
        self.ws_info_path = QLabel("Path: —")
        self.ws_info_name.setObjectName("info_label")
        self.ws_info_path.setObjectName("info_label")
        lay.addWidget(self.ws_info_name)
        lay.addWidget(self.ws_info_path)
        lay.addWidget(make_separator())

        grid = QGridLayout()
        grid.setSpacing(10)

        actions = [
            ("Build Workspace",          "primary",  self._build_workspace),
            ("Clean & Build",            "primary",  self._clean_and_build),
            ("Source Workspace",         "default",  self._source_workspace),
            ("Open in Terminal",         "default",  self._open_ws_terminal),
            ("Clean (build/install/log)","danger",   self._clean_workspace),
        ]
        for i, (label, style, slot) in enumerate(actions):
            btn = QPushButton(label)
            btn.setObjectName(f"action_{style}")
            btn.clicked.connect(slot)
            grid.addWidget(btn, i // 2, i % 2)

        lay.addLayout(grid)
        lay.addStretch()
        return p

    def _page_package(self):
        p = QWidget()
        lay = QVBoxLayout(p)
        lay.setContentsMargins(24, 20, 24, 20)
        lay.setSpacing(14)

        title = QLabel("[PKG]  Package")
        title.setObjectName("page_title")
        lay.addWidget(title)

        self.pkg_info_name = QLabel("Name: —")
        self.pkg_info_path = QLabel("Path: —")
        self.pkg_info_name.setObjectName("info_label")
        self.pkg_info_path.setObjectName("info_label")
        lay.addWidget(self.pkg_info_name)
        lay.addWidget(self.pkg_info_path)
        lay.addWidget(make_separator())

        # Add node group
        group = QGroupBox("  Add New Node")
        group.setObjectName("card_group")
        g_lay = QFormLayout(group)
        g_lay.setSpacing(10)
        g_lay.setContentsMargins(14, 18, 14, 14)

        self.new_node_input = QLineEdit()
        self.new_node_input.setPlaceholderText("e.g. my_publisher")
        g_lay.addRow("Node name:", self.new_node_input)

        btn_add_node = QPushButton("＋  Create Node")
        btn_add_node.setObjectName("action_primary")
        btn_add_node.clicked.connect(self._create_node)
        g_lay.addRow("", btn_add_node)
        lay.addWidget(group)

        lay.addWidget(make_separator())

        grid = QGridLayout()
        grid.setSpacing(10)
        for i, (label, style, slot) in enumerate([
            ("Build Package",    "default", self._build_package),
            ("Clean Package",    "danger",  self._clean_package),
            ("Open in Terminal", "default", self._open_pkg_terminal),
        ]):
            btn = QPushButton(label)
            btn.setObjectName(f"action_{style}")
            btn.clicked.connect(slot)
            grid.addWidget(btn, i // 2, i % 2)
        lay.addLayout(grid)
        lay.addStretch()
        return p

    def _page_node(self):
        p = QWidget()
        lay = QVBoxLayout(p)
        lay.setContentsMargins(24, 20, 24, 20)
        lay.setSpacing(14)

        title = QLabel("[NODE]  Node")
        title.setObjectName("page_title")
        lay.addWidget(title)

        self.node_info_name = QLabel("Name: —")
        self.node_info_pkg  = QLabel("Package: —")
        self.node_info_name.setObjectName("info_label")
        self.node_info_pkg.setObjectName("info_label")
        lay.addWidget(self.node_info_name)
        lay.addWidget(self.node_info_pkg)
        lay.addWidget(make_separator())

        grid = QGridLayout()
        grid.setSpacing(10)
        for i, (label, style, slot) in enumerate([
            ("Run Node",    "primary", self._run_node),
            ("Edit Source", "default", self._edit_node),
        ]):
            btn = QPushButton(label)
            btn.setObjectName(f"action_{style}")
            btn.clicked.connect(slot)
            grid.addWidget(btn, 0, i)
        lay.addLayout(grid)
        lay.addStretch()
        return p

    def _page_launch(self):
        p = QWidget()
        lay = QVBoxLayout(p)
        lay.setContentsMargins(24, 20, 24, 20)
        lay.setSpacing(14)

        title = QLabel("[LAUNCH]  Launch File")
        title.setObjectName("page_title")
        lay.addWidget(title)

        self.launch_info_name = QLabel("File: —")
        self.launch_info_pkg  = QLabel("Package: —")
        self.launch_info_path = QLabel("Path: —")
        for lbl in [self.launch_info_name, self.launch_info_pkg, self.launch_info_path]:
            lbl.setObjectName("info_label")
            lay.addWidget(lbl)
        lay.addWidget(make_separator())

        grid = QGridLayout()
        grid.setSpacing(10)
        for i, (label, style, slot) in enumerate([
            ("Run Launch",   "primary", self._run_launch),
            ("Edit Source",  "default", self._edit_launch),
        ]):
            btn = QPushButton(label)
            btn.setObjectName(f"action_{style}")
            btn.setAutoDefault(False)
            btn.setDefault(False)
            btn.clicked.connect(slot)
            grid.addWidget(btn, 0, i)
        lay.addLayout(grid)
        lay.addStretch()
        return p

    def _make_output_panel(self):
        """VS Code 스타일 탭 터미널 패널"""
        panel = QWidget()
        panel.setObjectName("output_panel")
        lay = QVBoxLayout(panel)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        self.tab_widget = QTabWidget()
        self.tab_widget.setObjectName("terminal_tabs")
        self.tab_widget.setTabsClosable(True)
        self.tab_widget.tabCloseRequested.connect(self._on_tab_close_requested)
        lay.addWidget(self.tab_widget)

        # 첫 번째 탭 = OUTPUT (빌드/일반 로그)
        self.output = QPlainTextEdit()
        self.output.setReadOnly(True)
        self.output.setObjectName("output_text")
        self.output.setFont(QFont("Monospace", 10))
        self.output.setMaximumBlockCount(MAX_TAB_LINES)
        self.tab_widget.addTab(self.output, "OUTPUT")

        # 프로세스 상태 감시 타이머 (1초 간격)
        self.poll_timer = QTimer()
        self.poll_timer.setInterval(1000)
        self.poll_timer.timeout.connect(self._poll_node_processes)
        self.poll_timer.start()

        return panel

    def _poll_node_processes(self):
        """실행 중인 노드 프로세스 상태 주기적 체크"""
        for idx, worker in list(self.node_tabs.items()):
            if worker.proc and worker.proc.poll() is not None:
                # 프로세스 종료됨 → 탭 제목 업데이트
                tab_text = self.tab_widget.tabText(idx)
                if not tab_text.startswith("■ "):
                    base = tab_text.replace("● ", "")
                    self.tab_widget.setTabText(idx, f"■ {base}")

    def _on_tab_close_requested(self, index):
        """탭 닫기(X) 클릭 시"""
        tab_name   = self.tab_widget.tabText(index)
        worker     = self.node_tabs.get(index)
        is_running = worker and worker.proc and worker.proc.poll() is None

        # ── OUTPUT 탭 ────────────────────────────
        if index == 0:
            if QMessageBox.question(
                self, "탭 닫기",
                "OUTPUT 탭을 닫으면 빌드 로그가 사라집니다.\n정말 닫을까요?",
                QMessageBox.Yes | QMessageBox.No
            ) != QMessageBox.Yes:
                return
            self._close_tab(index)
            return

        # ── 노드/Launch 탭: 실행 중 ───────────────
        if is_running:
            answer = QMessageBox.question(
                self, "탭 닫기",
                f"'{tab_name}' 이 실행 중입니다.\n"
                f"프로세스에 종료 신호를 보낼까요?\n\n"
                f"출력창에서 [완료] 확인 후 탭이 자동으로 닫힙니다.",
                QMessageBox.Yes | QMessageBox.No
            )
            if answer != QMessageBox.Yes:
                # 탭의 출력창에 안내 메시지 표시
                tab_output = self.tab_widget.widget(index)
                if isinstance(tab_output, QPlainTextEdit):
                    tab_output.appendPlainText(
                        "\n─────────────────────────────────────\n"
                        "[안내] 노드가 실행 중입니다.\n"
                        "       출력창에서 [완료] 확인 후 X 버튼을 눌러 닫아주세요.\n"
                        "─────────────────────────────────────"
                    )
                self.tab_widget.setCurrentIndex(index)
                return

            # SIGINT 전송 + 출력창에 메시지 표시
            tab_output = self.tab_widget.widget(index)
            if isinstance(tab_output, QPlainTextEdit):
                tab_output.appendPlainText(
                    "\n─────────────────────────────────────\n"
                    "[종료 요청 중...] SIGINT 전송\n"
                    "─────────────────────────────────────"
                )

            # 종료 후 탭 자동 닫기: 별도 스레드에서 대기
            def _wait_and_close():
                import time
                deadline = time.time() + 5
                # SIGINT
                worker.kill_node()
                # 종료 대기 (최대 5초)
                while time.time() < deadline:
                    if worker.proc and worker.proc.poll() is not None:
                        break
                    time.sleep(0.2)
                # GUI 스레드에서 탭 닫기 (QTimer 단발 사용)
                QTimer.singleShot(300, lambda: self._close_tab_by_worker(worker))

            threading.Thread(target=_wait_and_close, daemon=True).start()
            return

        # ── 이미 종료된 탭 ────────────────────────
        # 출력창에 [완료] 텍스트 있는지 확인
        tab_output = self.tab_widget.widget(index)
        finished = True
        if isinstance(tab_output, QPlainTextEdit):
            content = tab_output.toPlainText()
            finished = "[완료]" in content or "[종료" in content or "✓" in content

        if not finished:
            answer = QMessageBox.question(
                self, "탭 닫기",
                f"'{tab_name}'\n"
                f"출력창에서 [완료] 가 확인되지 않았습니다.\n"
                f"그래도 닫을까요?",
                QMessageBox.Yes | QMessageBox.No
            )
            if answer != QMessageBox.Yes:
                return

        self._close_tab(index)

    def _close_tab_by_worker(self, worker):
        """worker 기준으로 탭 인덱스를 찾아 닫기"""
        for idx, w in list(self.node_tabs.items()):
            if w is worker:
                self._close_tab(idx)
                return

    def _close_tab(self, index):
        """탭 실제 제거 + 인덱스 재정리"""
        self.tab_widget.removeTab(index)

        # OUTPUT 탭 닫힌 경우 재생성
        if index == 0:
            self.output = QPlainTextEdit()
            self.output.setReadOnly(True)
            self.output.setObjectName("output_text")
            self.output.setFont(QFont("Monospace", 10))
            self.output.setMaximumBlockCount(MAX_TAB_LINES)
            self.tab_widget.insertTab(0, self.output, "OUTPUT")
            self.tab_widget.setCurrentIndex(0)

        # 탭 인덱스 재정리
        new_tabs = {}
        for old_idx, w in self.node_tabs.items():
            new_idx = old_idx if old_idx < index else old_idx - 1
            if old_idx != index:
                new_tabs[new_idx] = w
        self.node_tabs = new_tabs


    # ── Theme ─────────────────────────────────

    def _is_dark_system(self):
        """시스템 팔레트로 다크/라이트 감지"""
        bg = QApplication.palette().color(QApplication.palette().Window)
        return bg.lightness() < 128

    def _apply_theme(self):
        """시스템 테마를 따르되 버튼/텍스트/트리가 잘 보이도록 최소 보정"""
        dark = self._is_dark_system()

        # 시스템 팔레트 기준 색상
        if dark:
            fg          = "#e0e0e0"   # 기본 텍스트
            fg_dim      = "#a0a0a0"   # 보조 텍스트
            fg_accent   = "#6ab0f5"   # 강조 (파랑)
            fg_danger   = "#f47a7a"   # 위험 (빨강)
            bg_btn      = "#3a3a3a"   # 버튼 배경
            bg_btn_h    = "#4a4a4a"   # 버튼 hover
            border      = "#555555"   # 테두리
            bg_primary  = "#1e3a6e"   # primary 버튼 배경
            bg_prim_h   = "#2a4e8e"
            bg_danger   = "#5a1a1a"
            bg_danger_h = "#6e2020"
            tree_sel    = "#1e3a5e"
            tree_sel_fg = "#6ab0f5"
            tree_hover  = "#2a2a2a"
            tab_sel_top = "#6ab0f5"
            tab_fg_sel  = "#6ab0f5"
            tab_fg      = "#888888"
            out_fg      = "#90d090"   # 출력창 텍스트
        else:
            fg          = "#1a1a1a"
            fg_dim      = "#606060"
            fg_accent   = "#1a56db"
            fg_danger   = "#c0002a"
            bg_btn      = "#e8e8e8"
            bg_btn_h    = "#d8d8d8"
            border      = "#b0b0b0"
            bg_primary  = "#1a56db"
            bg_prim_h   = "#1440b0"
            bg_danger   = "#fff0f0"
            bg_danger_h = "#ffe0e0"
            tree_sel    = "#c8daff"
            tree_sel_fg = "#1a1a8e"
            tree_hover  = "#e8e8ff"
            tab_sel_top = "#1a56db"
            tab_fg_sel  = "#1a56db"
            tab_fg      = "#606060"
            out_fg      = "#1a6e1a"

        self.setStyleSheet(f"""
/* ══ 기본 폰트 ══════════════════════════════════════ */
QWidget {{ font-size: 13px; }}

/* ══ 탑바 ═══════════════════════════════════════════ */
#topbar      {{ border-bottom: 1px solid {border}; }}
#logo        {{ font-size: 14px; font-weight: 700;
                letter-spacing: 0.5px; color: {fg_accent}; }}
#bar_label   {{ color: {fg_dim}; font-size: 12px; font-weight: 600; }}
#bar_sep     {{ color: {border}; font-size: 16px; padding: 0; }}
#ssh_status  {{ color: {fg_accent}; font-size: 12px; font-weight: 600;
                padding: 0 4px; }}

/* ══ 콤보박스 & 스핀박스 ════════════════════════════ */
QComboBox, QSpinBox {{
    color: {fg}; background: {bg_btn};
    border: 1px solid {border}; border-radius: 5px;
    padding: 3px 8px; font-size: 13px;
    min-height: 26px;
}}
QComboBox:hover, QSpinBox:hover {{ border-color: {fg_accent}; }}
QComboBox::drop-down {{
    border: none; width: 20px;
}}
QComboBox QAbstractItemView {{
    color: {fg}; background: {bg_btn};
    border: 1px solid {border}; border-radius: 4px;
    selection-background-color: {tree_sel};
    selection-color: {tree_sel_fg};
    padding: 2px;
}}
QSpinBox::up-button, QSpinBox::down-button {{
    width: 16px; border: none; background: transparent;
}}

/* ══ 툴바 버튼 ══════════════════════════════════════ */
#topbar_btn {{
    background: {bg_btn}; color: {fg};
    border: 1px solid {border}; border-radius: 5px;
    padding: 4px 10px; font-size: 12px;
    min-height: 26px;
}}
#topbar_btn:hover    {{ background: {bg_btn_h}; color: {fg_accent};
                        border-color: {fg_accent}; }}
#topbar_btn:disabled {{ background: transparent; color: {fg_dim};
                        border-color: {border}; }}

/* ══ 좌측 패널 ══════════════════════════════════════ */
#section_header {{
    color: {fg_dim}; font-size: 11px; font-weight: 700;
    letter-spacing: 1px; padding-left: 12px;
    border-bottom: 1px solid {border};
}}

/* ══ 프로젝트 트리 ══════════════════════════════════ */
#proj_tree {{
    color: {fg}; border: none; font-size: 13px;
    outline: none; padding: 2px 0;
}}
#proj_tree::item               {{ padding: 4px 6px; border-radius: 4px; }}
#proj_tree::item:hover         {{ background: {tree_hover}; }}
#proj_tree::item:selected      {{ background: {tree_sel};
                                  color: {tree_sel_fg}; }}

/* ══ 트리 하단 버튼 (2×2 그리드) ═══════════════════ */
#tree_btn_area               {{ border-top: 1px solid {border}; }}
#tree_add_btn {{
    color: {fg}; background: transparent;
    border: 1px solid {border}; border-radius: 5px;
    padding: 5px 4px; font-size: 12px; min-height: 28px;
}}
#tree_add_btn:hover {{ color: {fg_accent}; border-color: {fg_accent};
                       background: {tree_hover}; }}

/* ══ 액션 패널 페이지 ══════════════════════════════ */
#page_title   {{ font-size: 17px; font-weight: 700;
                 color: {fg_accent}; padding-bottom: 2px; }}
#info_label   {{ color: {fg_dim}; font-size: 12px; }}
#welcome_hint {{ color: {fg_dim}; font-size: 14px; }}

/* ── 액션 버튼 ─────────────────────────────────── */
#action_primary {{
    background: {bg_primary}; color: #ffffff;
    border: none; border-radius: 6px;
    padding: 8px 14px; font-size: 13px; font-weight: 600;
    min-height: 36px;
}}
#action_primary:hover {{ background: {bg_prim_h}; }}

#action_default {{
    background: {bg_btn}; color: {fg};
    border: 1px solid {border}; border-radius: 6px;
    padding: 8px 14px; font-size: 13px;
    min-height: 36px;
}}
#action_default:hover {{ background: {bg_btn_h}; }}

#action_danger {{
    background: {bg_danger}; color: {fg_danger};
    border: 1px solid {fg_danger}; border-radius: 6px;
    padding: 8px 14px; font-size: 13px;
    min-height: 36px;
}}
#action_danger:hover {{ background: {bg_danger_h}; }}

/* ══ 그룹박스 ═══════════════════════════════════════ */
QGroupBox, #card_group {{
    border: 1px solid {border}; border-radius: 7px;
    margin-top: 10px; padding-top: 14px;
    font-size: 12px; font-weight: 700;
}}
QGroupBox::title, #card_group::title {{
    subcontrol-origin: margin; subcontrol-position: top left;
    left: 10px; top: -1px;
    padding: 0 5px; color: {fg_dim};
}}

/* ══ 입력창 ═════════════════════════════════════════ */
QLineEdit {{
    color: {fg}; background: {bg_btn};
    border: 1px solid {border}; border-radius: 5px;
    padding: 5px 10px; font-size: 13px; min-height: 26px;
}}
QLineEdit:focus {{ border-color: {fg_accent}; }}
QLineEdit:read-only {{ color: {fg_dim}; }}

/* ══ 다이얼로그 ═════════════════════════════════════ */
QDialog {{ font-size: 13px; }}
QDialogButtonBox QPushButton {{
    min-width: 80px; padding: 6px 14px;
    border: 1px solid {border}; border-radius: 5px;
    background: {bg_btn}; color: {fg};
    font-size: 13px; min-height: 30px;
}}
QDialogButtonBox QPushButton:hover {{ background: {bg_btn_h}; }}

/* ══ 스크롤바 ═══════════════════════════════════════ */
QScrollBar:vertical {{
    width: 8px; background: transparent; margin: 0;
}}
QScrollBar::handle:vertical {{
    background: {border}; border-radius: 4px; min-height: 24px;
}}
QScrollBar::handle:vertical:hover {{ background: {fg_dim}; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
QScrollBar:horizontal {{
    height: 8px; background: transparent; margin: 0;
}}
QScrollBar::handle:horizontal {{
    background: {border}; border-radius: 4px; min-width: 24px;
}}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{ width: 0; }}

/* ══ 탭 터미널 ══════════════════════════════════════ */
#terminal_tabs QTabBar::tab {{
    color: {tab_fg};
    border: 1px solid {border}; border-bottom: none;
    padding: 5px 24px 5px 12px;
    font-size: 12px; min-width: 110px;
}}
#terminal_tabs QTabBar::tab:selected {{
    color: {tab_fg_sel};
    border-top: 2px solid {tab_sel_top};
}}
#terminal_tabs QTabBar::tab:hover {{ color: {fg}; }}
#terminal_tabs QTabBar::close-button {{
    subcontrol-position: right; subcontrol-origin: padding;
    width: 14px; height: 14px;
}}
#terminal_tabs QTabBar::close-button:hover {{
    background: {fg_danger}; border-radius: 3px;
}}

/* ══ 출력창 ═════════════════════════════════════════ */
#output_text {{
    color: {out_fg}; border: none;
    font-family: 'Monospace', monospace; font-size: 12px;
    padding: 4px;
}}

/* ══ 메뉴 ═══════════════════════════════════════════ */
QMenu {{ border: 1px solid {border}; font-size: 13px; }}
QMenu::item {{ padding: 6px 24px; }}
QMenu::item:selected {{ color: {fg_accent}; }}

/* ══ 상태바 ═════════════════════════════════════════ */
QStatusBar {{ color: {fg_dim}; font-size: 12px; padding: 2px 8px; }}
""")


    # ── ROS2 Detection ────────────────────────

    def _detect_ros2(self, ssh: "SSHConnection | None" = None):
        self.distro_combo.blockSignals(True)
        self.distro_combo.clear()
        if ssh:
            distros = ssh.get_ros2_distros()
        else:
            distros = get_ros2_distros()
        if not distros:
            src = f"[{ssh.label}]" if ssh else "로컬"
            self._log(f"[WARN] {src} ROS2 설치를 찾지 못했습니다")
            self.distro_combo.addItem("(not found)")
        else:
            self.distro_combo.addItems(distros)
            for pref in ['jazzy', 'humble', 'iron']:
                if pref in distros:
                    self.distro_combo.setCurrentText(pref)
                    break
        self.distro_combo.blockSignals(False)
        # 수동으로 첫 번째 distro 선택 적용
        first = self.distro_combo.currentText()
        if first and first != "(not found)":
            self._on_distro_changed(first)
        self._load_workspaces()

    def _ros_setup(self):
        """현재 distro의 setup.bash 경로. 없으면 빈 문자열"""
        if not self.current_distro:
            return ""
        if self.current_ssh:
            return f"/opt/ros/{self.current_distro}/setup.bash"
        return _find_setup_bash(self.current_distro) or ""

    def _ros_src(self):
        """'source /path/setup.bash && ' 문자열 반환."""
        setup = self._ros_setup()
        return f"source {setup} && " if setup else ""

    # ── File System Abstraction (local / remote) ──────────

    def _fs_exists(self, path_str: str) -> bool:
        if self.current_ssh:
            return self.current_ssh.exists(path_str)
        return Path(path_str).exists()

    def _fs_listdir(self, path_str: str) -> list:
        """[(name, is_dir), ...]"""
        if self.current_ssh:
            return self.current_ssh.listdir_attr(path_str)
        p = Path(path_str)
        if not p.exists():
            return []
        return [(item.name, item.is_dir()) for item in p.iterdir()]

    def _fs_read_text(self, path_str: str) -> str:
        if self.current_ssh:
            return self.current_ssh.read_text(path_str)
        try:
            return Path(path_str).read_text(errors="ignore")
        except Exception:
            return ""

    def _fs_join(self, *parts: str) -> str:
        """경로 조합 (로컬은 os.path, 리모트는 posixpath)"""
        import posixpath
        if self.current_ssh:
            return posixpath.join(*parts)
        return str(Path(*parts))

    def _update_tool_buttons(self):
        enabled = bool(self.current_distro and self.current_workspace)
        for btn in self.tool_btns:
            btn.setEnabled(enabled)

    def _on_distro_changed(self, distro):
        if not distro or distro == "(not found)":
            return
        self.current_distro = distro
        self.ros_env = get_ros_env(distro)
        self._apply_domain_id_to_env()
        self._log(f"[INFO] ROS2 {distro} sourced")
        self.statusBar().showMessage(f"ROS2 {distro} active")
        self._update_tool_buttons()

    def _setup_bashrc_prompt(self):
        """처음 실행 시 ~/.bashrc에 PROMPT_COMMAND 자동 추가 (없는 경우에만)"""
        marker = "# ros2_gui_manager: domain id sync"
        bashrc = Path.home() / ".bashrc"
        prompt_cmd = (
            f"\n{marker}\n"
            f"PROMPT_COMMAND='export ROS_DOMAIN_ID=$(cat ~/.ros_domain_id 2>/dev/null || echo 0)'\n"
        )
        # ~/.ros_domain_id 초기화
        domain_file = Path.home() / ".ros_domain_id"
        if not domain_file.exists():
            domain_file.write_text(str(self.domain_spin.value()))

        if bashrc.exists() and marker not in bashrc.read_text():
            with bashrc.open("a") as f:
                f.write(prompt_cmd)

    def _on_domain_id_changed(self, value):
        os.environ["ROS_DOMAIN_ID"] = str(value)
        if self.ros_env is not None:
            self.ros_env["ROS_DOMAIN_ID"] = str(value)
        # 기존 터미널에서도 반영되도록 파일에 저장
        try:
            Path.home().joinpath(".ros_domain_id").write_text(str(value))
        except Exception:
            pass
        self._log(f"[INFO] ROS_DOMAIN_ID → {value}")
        self.statusBar().showMessage(f"ROS_DOMAIN_ID = {value}", 3000)

    def _apply_domain_id_to_env(self):
        """ros_env 갱신 후 현재 Domain ID 값을 반영"""
        if self.ros_env is not None:
            self.ros_env["ROS_DOMAIN_ID"] = str(self.domain_spin.value())

    # ── Workspace ─────────────────────────────

    def _load_workspaces(self):
        self.ws_combo.blockSignals(True)
        self.ws_combo.clear()
        self.ws_combo.addItem("(select workspace)")
        cfg = self._cfg()
        # 로컬 워크스페이스
        for ws in cfg.get("workspaces", []):
            if Path(ws).exists():
                self.ws_combo.addItem(ws)
        # 리모트 워크스페이스 (연결된 SSH 호스트만)
        for rws in cfg.get("remote_workspaces", []):
            ssh_id = rws.get("ssh_id", "")
            path   = rws.get("path", "")
            if ssh_id in self.ssh_connections:
                ssh = self.ssh_connections[ssh_id]
                display = f"[{ssh.label}] {path}"
                self.ws_combo.addItem(display)
        self.ws_combo.blockSignals(False)
        self._refresh_tree()

    def _on_workspace_changed(self, display_text):
        if not display_text or display_text == "(select workspace)":
            self.current_workspace = None
            self.current_ssh = None
            self._update_tool_buttons()
            return

        # 리모트 워크스페이스 여부 판별
        cfg = self._cfg()
        resolved_path = display_text
        new_ssh = None
        for rws in cfg.get("remote_workspaces", []):
            ssh_id = rws.get("ssh_id", "")
            path   = rws.get("path", "")
            if ssh_id in self.ssh_connections:
                ssh = self.ssh_connections[ssh_id]
                if display_text == f"[{ssh.label}] {path}":
                    new_ssh = ssh
                    resolved_path = path
                    break

        self.current_ssh = new_ssh
        if new_ssh:
            self.current_workspace = resolved_path   # str for remote
            self._log(f"[INFO] Remote Workspace [{new_ssh.label}]: {resolved_path}")
        else:
            self.current_workspace = Path(display_text)
            self._log(f"[INFO] Workspace: {display_text}")

        self._refresh_tree()
        self._update_tool_buttons()
        self._auto_select_workspace_in_tree(display_text)

    def _auto_select_workspace_in_tree(self, display_text):
        """트리에서 워크스페이스 항목을 자동 선택하고 우측 패널을 업데이트"""
        for i in range(self.tree.topLevelItemCount()):
            item = self.tree.topLevelItem(i)
            if item.data(0, Qt.UserRole + 2) == display_text:  # display key
                self.tree.setCurrentItem(item)
                ws_path = str(self.current_workspace)
                ws_name = ws_path.rstrip("/").split("/")[-1]
                self.ws_info_name.setText(f"Name:  {ws_name}")
                self.ws_info_path.setText(f"Path:  {ws_path}")
                self.stack.setCurrentIndex(1)
                item.setExpanded(True)
                break

    def _create_workspace(self):
        dlg = QDialog(self)
        dlg.setWindowTitle("New Workspace")
        dlg.setFixedSize(420, 200)
        lay = QFormLayout(dlg)
        lay.setContentsMargins(20, 20, 20, 20)
        lay.setSpacing(12)

        name_in = QLineEdit("ros2_ws")
        lay.addRow("Name:", name_in)

        path_row = QHBoxLayout()
        path_in = QLineEdit(str(Path.home()))
        browse = QPushButton("Browse…")
        browse.setObjectName("action_default")
        browse.setFixedWidth(80)
        browse.clicked.connect(lambda: path_in.setText(
            QFileDialog.getExistingDirectory(dlg, "Select Location") or path_in.text()
        ))
        path_row.addWidget(path_in)
        path_row.addWidget(browse)
        lay.addRow("Location:", path_row)

        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(dlg.accept)
        btns.rejected.connect(dlg.reject)
        lay.addRow(btns)

        if dlg.exec_() != QDialog.Accepted:
            return

        name = name_in.text().strip() or "ros2_ws"
        ws_path = Path(path_in.text()) / name
        ws_path.mkdir(parents=True, exist_ok=True)
        (ws_path / "src").mkdir(exist_ok=True)

        cfg = self._cfg()
        if str(ws_path) not in cfg.get("workspaces", []):
            cfg.setdefault("workspaces", []).append(str(ws_path))
            self._save_cfg(cfg)

        self._log(f"[OK] Workspace created: {ws_path}")
        self._load_workspaces()
        self.ws_combo.setCurrentText(str(ws_path))

    def _open_workspace(self):
        """기존 워크스페이스 폴더 선택 → 유효성 검증 → 등록"""
        path_str = QFileDialog.getExistingDirectory(
            self, "기존 워크스페이스 선택", str(Path.home())
        )
        if not path_str:
            return

        ws_path = Path(path_str)

        # ── 유효성 검증 ──────────────────────────
        warnings = []

        if not (ws_path / "src").exists():
            warnings.append("src/ 폴더가 없습니다. ROS2 워크스페이스가 맞나요?")

        has_install = (ws_path / "install" / "setup.bash").exists()
        if not has_install:
            warnings.append("install/setup.bash 없음 → 빌드가 필요합니다.")

        if warnings:
            msg = "\n".join(f"  • {w}" for w in warnings)
            answer = QMessageBox.question(
                self,
                "워크스페이스 확인",
                f"경고 사항이 있습니다:\n\n{msg}\n\n그래도 등록하시겠습니까?",
                QMessageBox.Yes | QMessageBox.No
            )
            if answer != QMessageBox.Yes:
                return

        # ── 중복 체크 ────────────────────────────
        cfg = self._cfg()
        if str(ws_path) in cfg.get("workspaces", []):
            QMessageBox.information(
                self, "알림", f"이미 등록된 워크스페이스입니다.\n{ws_path}"
            )
            self.ws_combo.setCurrentText(str(ws_path))
            return

        # ── 등록 ─────────────────────────────────
        cfg.setdefault("workspaces", []).append(str(ws_path))
        self._save_cfg(cfg)

        status = "빌드됨" if has_install else "빌드 필요"
        self._log(f"[OK] 워크스페이스 등록: {ws_path}  [{status}]")
        self._load_workspaces()
        self.ws_combo.setCurrentText(str(ws_path))


        if not self._require_ws():
            return
        self._run_cmd(
            f"{self._ros_src()}colcon build --symlink-install 2>&1",
            cwd=str(self.current_workspace)
        )

    def _build_workspace(self):
        if not self._require_ws():
            return
        self._run_cmd(
            f"{self._ros_src()}colcon build --symlink-install 2>&1",
            cwd=str(self.current_workspace)
        )

    def _source_workspace(self):
        if not self._require_ws():
            return
        ws_str = str(self.current_workspace)
        import posixpath
        setup_path = (posixpath.join(ws_str, "install", "setup.bash")
                      if self.current_ssh else
                      str(Path(ws_str) / "install" / "setup.bash"))
        if not self._fs_exists(setup_path):
            self._log("[WARN] No install/setup.bash — build workspace first.")
            return
        if self.current_ssh:
            self._log(f"[OK] Remote workspace sourced: {setup_path}")
        else:
            env = get_ws_env(self.current_distro, self.current_workspace)
            self.ros_env = env
            self._apply_domain_id_to_env()
            self._log(f"[OK] Workspace sourced: {setup_path}")

    def _clean_workspace(self):
        if not self._require_ws():
            return
        if QMessageBox.question(
            self, "Clean Workspace",
            "Delete build/, install/, log/ ?",
            QMessageBox.Yes | QMessageBox.No
        ) != QMessageBox.Yes:
            return
        ws_str = str(self.current_workspace)
        if self.current_ssh:
            import posixpath
            for d in ['build', 'install', 'log']:
                p = posixpath.join(ws_str, d)
                if self.current_ssh.exists(p):
                    out, rc = self.current_ssh.exec(f"rm -rf {p}")
                    self._log(f"[OK] Removed {p}" if rc == 0 else f"[ERROR] rm -rf {p}: {out}")
        else:
            for d in ['build', 'install', 'log']:
                p = self.current_workspace / d
                if p.exists():
                    shutil.rmtree(p)
                    self._log(f"[OK] Removed {p}")

    def _clean_and_build(self):
        """Clean 후 자동 Build"""
        if not self._require_ws():
            return
        if QMessageBox.question(
            self, "Clean & Build",
            "build/, install/, log/ 를 삭제 후 전체 빌드합니다.\n계속하시겠습니까?",
            QMessageBox.Yes | QMessageBox.No
        ) != QMessageBox.Yes:
            return
        ws_str = str(self.current_workspace)
        if self.current_ssh:
            import posixpath
            for d in ['build', 'install', 'log']:
                p = posixpath.join(ws_str, d)
                if self.current_ssh.exists(p):
                    self.current_ssh.exec(f"rm -rf {p}")
                    self._log(f"[OK] Removed {p}")
        else:
            for d in ['build', 'install', 'log']:
                p = self.current_workspace / d
                if p.exists():
                    shutil.rmtree(p)
                    self._log(f"[OK] Removed {p}")
        self._build_workspace()

    def _clean_package(self):
        """선택된 패키지의 build/install 캐시만 삭제"""
        pkg = self._selected_package()
        if not pkg:
            return
        if QMessageBox.question(
            self, "Clean Package",
            f"패키지 '{pkg}' 의 빌드 캐시를 삭제합니다.\n"
            f"  build/{pkg}\n  install/{pkg}\n\n계속하시겠습니까?",
            QMessageBox.Yes | QMessageBox.No
        ) != QMessageBox.Yes:
            return
        ws_str = str(self.current_workspace)
        removed = False
        if self.current_ssh:
            import posixpath
            for d in ['build', 'install']:
                p = posixpath.join(ws_str, d, pkg)
                if self.current_ssh.exists(p):
                    self.current_ssh.exec(f"rm -rf {p}")
                    self._log(f"[OK] Removed {p}")
                    removed = True
        else:
            for d in ['build', 'install']:
                p = self.current_workspace / d / pkg
                if p.exists():
                    shutil.rmtree(p)
                    self._log(f"[OK] Removed {p}")
                    removed = True
        if not removed:
            self._log(f"[INFO] '{pkg}' 에 대한 빌드 캐시가 없습니다.")

    def _open_ws_terminal(self):
        self._open_terminal(cwd=str(self.current_workspace) if self.current_workspace else None)

    # ── Package ───────────────────────────────

    def _create_package(self):
        if not self._require_ws():
            return
        dlg = QDialog(self)
        dlg.setWindowTitle("New Package")
        dlg.setFixedSize(420, 240)
        lay = QFormLayout(dlg)
        lay.setContentsMargins(20, 20, 20, 20)
        lay.setSpacing(12)

        name_in = QLineEdit()
        name_in.setPlaceholderText("my_package")
        lay.addRow("Package Name:", name_in)

        btype = QComboBox()
        btype.addItems(["ament_python", "ament_cmake"])
        btype.setObjectName("bar_combo")
        lay.addRow("Build Type:", btype)

        deps_in = QLineEdit()
        deps_in.setPlaceholderText("rclpy std_msgs  (space separated)")
        lay.addRow("Dependencies:", deps_in)

        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(dlg.accept)
        btns.rejected.connect(dlg.reject)
        lay.addRow(btns)

        if dlg.exec_() != QDialog.Accepted:
            return

        name = name_in.text().strip()
        if not name:
            return

        deps_flag = f"--dependencies {deps_in.text().strip()}" if deps_in.text().strip() else ""
        import posixpath
        ws_str = str(self.current_workspace)
        src = posixpath.join(ws_str, "src") if self.current_ssh else str(Path(ws_str) / "src")

        self._run_cmd(
            f"{self._ros_src()}ros2 pkg create --build-type {btype.currentText()} {deps_flag} {name} 2>&1",
            cwd=src,
            on_finish=self._refresh_tree
        )

    def _build_package(self):
        pkg = self._selected_package()
        if not pkg:
            return
        self._run_cmd(
            f"{self._ros_src()}colcon build --packages-select {pkg} --symlink-install 2>&1",
            cwd=str(self.current_workspace)
        )

    def _open_pkg_terminal(self):
        pkg = self._selected_package()
        if not pkg:
            return
        ws_str = str(self.current_workspace)
        import posixpath
        cwd = (posixpath.join(ws_str, "src", pkg)
               if self.current_ssh else
               str(Path(ws_str) / "src" / pkg))
        self._open_terminal(cwd=cwd)

    # ── Parameter Parser ──────────────────────

    def _parse_node_params(self, node_path):
        """Python 노드 소스에서 ROS2 파라미터 선언 추출
        반환: [{'name': str, 'default': str, 'type': str}]
        """
        import re
        params = []
        if not node_path or not Path(node_path).exists():
            return params
        try:
            content = Path(node_path).read_text(errors="ignore")

            # declare_parameter('name', default) 패턴
            pattern = r"declare_parameter\s*\(\s*['\"](\w+)['\"](?:\s*,\s*([^,\)]+))?"
            for m in re.finditer(pattern, content):
                name    = m.group(1)
                default = m.group(2).strip() if m.group(2) else ""
                # 타입 추론
                if default.startswith(("'", '"')):
                    ptype = "string"
                    default = default.strip("'\"")
                elif default in ("True", "False", "true", "false"):
                    ptype = "bool"
                elif "." in default:
                    ptype = "float"
                elif default.lstrip("-").isdigit():
                    ptype = "int"
                else:
                    ptype = "string"
                if name not in [p["name"] for p in params]:
                    params.append({"name": name, "default": default, "type": ptype})

            # add_argument('--name', default=...) 패턴 (argparse)
            pattern2 = r"add_argument\s*\(\s*['\"]--?([\w-]+)['\"].*?default\s*=\s*([^,\)]+)"
            for m in re.finditer(pattern2, content, re.DOTALL):
                name    = m.group(1).replace("-", "_")
                default = m.group(2).strip().strip("'\"")
                if name not in [p["name"] for p in params]:
                    params.append({"name": name, "default": default, "type": "string"})
        except Exception:
            pass
        return params

    def _parse_launch_params(self, lf_path, pkg_dir=None):
        """Launch 파일에서 argument 선언 추출
        반환: [{'name': str, 'default': str, 'description': str}]
        """
        import re
        params = []
        if not lf_path or not Path(lf_path).exists():
            return params

        def _resolve_default(default, pkg_dir):
            """상대 경로 기본값을 절대 경로로 변환"""
            if not default or not pkg_dir:
                return default
            # $(find-pkg-share ...) 치환 → 실제 패키지 경로
            default = re.sub(
                r"\$\(find-pkg-share\s+[\w_]+\)",
                str(pkg_dir),
                default
            )
            # 상대 경로 → 패키지 디렉토리 기준 절대 경로
            p = Path(default)
            if not p.is_absolute():
                candidate = pkg_dir / default
                if candidate.exists():
                    return str(candidate)
            return default

        try:
            content = Path(lf_path).read_text(errors="ignore")
            ext     = Path(lf_path).suffix.lower()

            if ext == ".xml":
                pattern = r'<arg\s+name=["\'](\w+)["\'](?:[^>]*?default=["\']([^"\']*)["\'])?(?:[^>]*?description=["\']([^"\']*)["\'])?'
                for m in re.finditer(pattern, content):
                    default = _resolve_default(m.group(2) or "", pkg_dir)
                    params.append({
                        "name":        m.group(1),
                        "default":     default,
                        "description": m.group(3) or "",
                    })

            elif ext in (".py", ""):
                pattern = r"DeclareLaunchArgument\s*\(\s*['\"](\w+)['\"](?:.*?default_value\s*=\s*['\"]([^'\"]*)['\"])?(?:.*?description\s*=\s*['\"]([^'\"]*)['\"])?"
                for m in re.finditer(pattern, content, re.DOTALL):
                    default = _resolve_default(m.group(2) or "", pkg_dir)
                    params.append({
                        "name":        m.group(1),
                        "default":     default,
                        "description": m.group(3) or "",
                    })

            elif ext in (".yaml", ".yml"):
                for line in content.splitlines():
                    m = re.match(r"\s*([\w_]+)\s*:\s*(.+)", line)
                    if m:
                        default = _resolve_default(m.group(2).strip(), pkg_dir)
                        params.append({
                            "name":        m.group(1),
                            "default":     default,
                            "description": "",
                        })
        except Exception:
            pass
        return params

    def _show_run_dialog(self, title, cmd_preview, param_style="node"):
        """단순 파라미터 입력 다이얼로그 - 한 줄 입력"""
        dlg = QDialog(self)
        dlg.setWindowTitle(f"실행 — {title}")
        dlg.setMinimumWidth(560)
        lay = QVBoxLayout(dlg)
        lay.setContentsMargins(16, 16, 16, 12)
        lay.setSpacing(10)

        # 실행 명령 미리보기
        prev_lbl = QLabel("실행 명령:")
        prev_lbl.setObjectName("info_label")
        lay.addWidget(prev_lbl)

        preview = QLabel(f"  {cmd_preview} ...")
        preview.setObjectName("info_label")
        preview.setStyleSheet("font-family: monospace; color: #888;")
        lay.addWidget(preview)

        # 파라미터 입력
        param_lbl = QLabel("파라미터 (없으면 비워두고 실행):")
        param_lbl.setObjectName("info_label")
        lay.addWidget(param_lbl)

        param_in = QLineEdit()
        if param_style == "node":
            param_in.setPlaceholderText("예: param1:=value1 param2:=value2")
        else:
            param_in.setPlaceholderText("예: map:=my_map.yaml use_sim_time:=true")
        lay.addWidget(param_in)

        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.button(QDialogButtonBox.Ok).setText("실행")
        btns.button(QDialogButtonBox.Cancel).setText("취소")
        btns.button(QDialogButtonBox.Ok).setAutoDefault(False)
        btns.button(QDialogButtonBox.Ok).setDefault(False)
        btns.accepted.connect(dlg.accept)
        btns.rejected.connect(dlg.reject)
        lay.addWidget(btns)

        if dlg.exec_() != QDialog.Accepted:
            return None, False

        params_str = param_in.text().strip()

        if param_style == "node" and params_str:
            # 각 param을 -p로 감싸고 따옴표 처리
            parts = params_str.split()
            ros_args = " ".join(f"-p '{p}'" for p in parts)
            return f"--ros-args {ros_args}", True
        elif param_style == "launch" and params_str:
            # 각 param을 따옴표로 감싸서 bash 해석 방지
            parts = params_str.split()
            quoted = " ".join(f"'{p}'" for p in parts)
            return quoted, True
        else:
            return "", True



    # ── Node ──────────────────────────────────

    def _create_node(self):
        node_name = self.new_node_input.text().strip()
        if not node_name:
            QMessageBox.warning(self, "Warning", "Enter a node name.")
            return
        pkg = self._selected_package()
        if not pkg:
            return

        if self.current_ssh:
            QMessageBox.information(self, "알림",
                "노드 파일 생성은 로컬 워크스페이스에서만 지원합니다.\n"
                "원격에서는 직접 에디터로 파일을 만들어 주세요.")
            return

        pkg_path = Path(str(self.current_workspace)) / "src" / pkg
        node_file = pkg_path / pkg / f"{node_name}.py"

        if node_file.exists():
            QMessageBox.warning(self, "Warning", f"Node '{node_name}' already exists.")
            return

        node_file.parent.mkdir(parents=True, exist_ok=True)
        init = node_file.parent / "__init__.py"
        if not init.exists():
            init.write_text(NodeTemplates.init_py())

        node_file.write_text(NodeTemplates.python_node(pkg, node_name))
        node_file.chmod(0o644)

        NodeTemplates.update_setup_py(pkg_path / "setup.py", pkg, node_name)

        self._log(f"[OK] Node created: {node_file}")
        self.new_node_input.clear()
        self._refresh_tree()

    def _run_node(self):
        item = self.tree.currentItem()
        if not item or item.data(0, Qt.UserRole) != "node":
            return

        # 아이콘 제거하여 노드명/패키지명 추출
        raw_node = item.text(0)
        for icon in ("🔵  ", "⚙  ", "📜  "):
            raw_node = raw_node.replace(icon, "")
        node_name = raw_node.strip()

        pkg_name = item.parent().text(0).split("  ", 1)[-1].strip()

        node_type = item.data(0, Qt.UserRole + 2) or "python"
        ws_str    = str(self.current_workspace)
        import posixpath
        setup_path = (posixpath.join(ws_str, "install", "setup.bash")
                      if self.current_ssh else
                      str(Path(ws_str) / "install" / "setup.bash"))

        if not self._fs_exists(setup_path):
            if QMessageBox.question(
                self, "Build Required", "Build workspace first?",
                QMessageBox.Yes | QMessageBox.No
            ) == QMessageBox.Yes:
                self._build_workspace()
            return

        # 파라미터 입력 다이얼로그
        extra_args, accepted = self._show_run_dialog(
            f"{pkg_name}/{node_name}",
            f"ros2 run {pkg_name} {node_name}",
            param_style="node"
        )
        if not accepted:
            return

        # 탭 출력 위젯 생성
        tab_output = QPlainTextEdit()
        tab_output.setReadOnly(True)
        tab_output.setObjectName("output_text")
        tab_output.setFont(QFont("Monospace", 10))
        tab_output.setMaximumBlockCount(MAX_TAB_LINES)

        type_icon  = "🔵" if node_type == "python" else "⚙" if node_type == "cpp" else "📜"
        tab_label  = f"● {type_icon} {pkg_name}/{node_name}"
        tab_idx    = self.tab_widget.addTab(tab_output, tab_label)
        self.tab_widget.setCurrentIndex(tab_idx)

        cmd = (f"source {self._ros_setup()} "
               f"&& source {setup_path} "
               f"&& ros2 run {pkg_name} {node_name}"
               f"{' ' + extra_args if extra_args else ''}")

        if self.current_ssh:
            worker = RemoteNodeWorkerThread(self.current_ssh, cmd, cwd=ws_str)
        else:
            worker = NodeWorkerThread(cmd, env=self.ros_env, cwd=self.current_workspace)

        def _append(batch, _w=tab_output):
            _w.appendPlainText(batch)  # QPlainTextEdit 전용 - 빠름

        def _on_finish(code, _w=tab_output):
            status = "✓ 완료" if code == 0 else f"✗ 종료({code})"
            for i in range(self.tab_widget.count()):
                if self.tab_widget.widget(i) is _w:
                    base = self.tab_widget.tabText(i).replace("● ", "")
                    self.tab_widget.setTabText(i, f"■ {base}")
                    break
            _w.appendPlainText(f"\n{'─'*48}\n[{status}]")

        worker.batch_signal.connect(_append, Qt.QueuedConnection)
        worker.finished_signal.connect(_on_finish, Qt.QueuedConnection)
        worker.start()

        self.node_tabs[tab_idx] = worker
        self._log(f"[RUN] {pkg_name}/{node_name} ({node_type}) → 탭 {tab_idx}")


    # ── Editor ────────────────────────────────


    def _detect_editors(self):
        """
        시스템에 설치된 텍스트 에디터를 실행 파일 직접 탐지.
        .desktop 파싱 방식 대신 known 에디터 실행파일을 직접 확인.
        반환: [(label, cmd), ...]
        """
        # (표시명, 실행 명령어) - 순서가 표시 우선순위
        EDITOR_CANDIDATES = [
            ("VS Code",              "code"),
            ("VS Code Insiders",     "code-insiders"),
            ("Cursor",               "cursor"),
            ("Windsurf",             "windsurf"),
            ("Antigravity",          "antigravity"),
            ("Zed",                  "zed"),
            ("Sublime Text",         "subl"),
            ("Atom",                 "atom"),
            ("Gedit",                "gedit"),
            ("Kate",                 "kate"),
            ("KWrite",               "kwrite"),
            ("Mousepad",             "mousepad"),
            ("Featherpad",           "featherpad"),
            ("Leafpad",              "leafpad"),
            ("Pluma",                "pluma"),
            ("Xed",                  "xed"),
            ("Lite XL",              "lite-xl"),
            ("Lapce",                "lapce"),
            ("Helix",                "hx"),
            ("Neovim (GUI)",         "nvim-qt"),
            ("Emacs (GUI)",          "emacs"),
            ("Nano (terminal)",      "xterm -e nano"),
            ("Vim (terminal)",       "xterm -e vim"),
            ("Neovim (terminal)",    "xterm -e nvim"),
        ]

        # Mac: xterm 대신 osascript로 Terminal.app에서 실행
        if IS_MAC:
            EDITOR_CANDIDATES = [
                (label, f"osascript -e 'tell app \"Terminal\" to do script \"{exe}\"'" )
                if cmd.startswith("xterm -e") else (label, cmd)
                for label, cmd in EDITOR_CANDIDATES
                for exe in [cmd.split()[-1]]
            ]

        found = []
        for label, cmd in EDITOR_CANDIDATES:
            exe = cmd.split()[0]
            if IS_MAC and exe == "osascript":
                # osascript는 항상 존재, 실제 에디터 존재 여부 확인
                actual_exe = cmd.split('"')[-2].split()[0]
                if shutil.which(actual_exe):
                    found.append((label, cmd))
            elif shutil.which(exe):
                found.append((label, cmd))

        return found  # [(label, exec_cmd), ...]


    def _open_with_editor(self, file_path):
        """에디터 선택 다이얼로그 → 파일 열기"""
        if not file_path or not Path(file_path).exists():
            self._log(f"[ERROR] 파일 없음: {file_path}")
            return

        editors = self._detect_editors()

        # 저장된 선호 에디터 - 현재 유효한 에디터 목록과 대조 검증
        cfg           = self._cfg()
        preferred_cmd = cfg.get("preferred_editor", "")
        valid_cmds    = {cmd for _, cmd in editors}

        # 저장된 값이 현재 목록에 없으면 무시하고 config에서도 제거
        if preferred_cmd and preferred_cmd not in valid_cmds:
            self._log(f"[INFO] 저장된 편집기 설정 초기화: {preferred_cmd}")
            cfg.pop("preferred_editor", None)
            self._save_cfg(cfg)
            preferred_cmd = ""

        if not editors:
            QMessageBox.warning(
                self, "편집기 없음",
                "설치된 텍스트 편집기를 찾을 수 없습니다.\n"
                "VS Code, Gedit, Kate 등을 설치 후 다시 시도해주세요."
            )
            return

        # ── 선택 다이얼로그 ──────────────────────
        dlg = QDialog(self)
        dlg.setWindowTitle("편집기 선택")
        dlg.setFixedSize(380, 320)
        lay = QVBoxLayout(dlg)
        lay.setContentsMargins(20, 20, 20, 16)
        lay.setSpacing(10)

        lbl = QLabel(f"편집기를 선택하세요:\n{Path(file_path).name}")
        lbl.setObjectName("info_label")
        lay.addWidget(lbl)

        from PyQt5.QtWidgets import QListWidget, QListWidgetItem, QCheckBox
        lst = QListWidget()
        lst.setObjectName("proj_tree")
        lst.setFocusPolicy(Qt.ClickFocus)   # Enter 키가 OK 버튼 트리거 방지
        for label, cmd in editors:
            item = QListWidgetItem(label)
            item.setData(Qt.UserRole, cmd)
            if cmd == preferred_cmd:
                item.setSelected(True)
            lst.addItem(item)
        if not lst.selectedItems() and lst.count() > 0:
            lst.item(0).setSelected(True)
        lst.setMinimumHeight(160)
        lay.addWidget(lst)

        chk = QCheckBox("이 편집기를 기본으로 저장")
        chk.setChecked(True)
        lay.addWidget(chk)

        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(dlg.accept)
        btns.rejected.connect(dlg.reject)
        # OK 버튼이 기본 버튼(Enter 트리거)이 되지 않도록
        ok_btn = btns.button(QDialogButtonBox.Ok)
        if ok_btn:
            ok_btn.setAutoDefault(False)
            ok_btn.setDefault(False)
        lay.addWidget(btns)

        result = dlg.exec_()

        # Cancel 또는 창 닫기 → 무조건 종료
        if result != QDialog.Accepted:
            return

        selected = lst.selectedItems()
        if not selected:
            return

        chosen_cmd = selected[0].data(Qt.UserRole)
        if not chosen_cmd:
            return

        # 선호 에디터 저장
        if chk.isChecked():
            cfg["preferred_editor"] = chosen_cmd
            self._save_cfg(cfg)

        # 파일 열기
        cmd_parts = chosen_cmd.split()
        subprocess.Popen(cmd_parts + [file_path], start_new_session=True)
        self._log(f"[EDIT] {chosen_cmd} {file_path}")

    def _edit_node(self):
        item = self.tree.currentItem()
        if not item or item.data(0, Qt.UserRole) != "node":
            return
        path = item.data(0, Qt.UserRole + 1)
        self._open_with_editor(path)

    def _run_launch(self):
        item = self.tree.currentItem()
        if not item or item.data(0, Qt.UserRole) != "launch":
            return
        lf_path  = item.data(0, Qt.UserRole + 1)
        pkg_name = item.data(0, Qt.UserRole + 2)
        lf_name  = lf_path.rstrip("/").split("/")[-1]
        ws_str   = str(self.current_workspace)
        import posixpath
        setup_path = (posixpath.join(ws_str, "install", "setup.bash")
                      if self.current_ssh else
                      str(Path(ws_str) / "install" / "setup.bash"))

        if not self._fs_exists(setup_path):
            if QMessageBox.question(
                self, "Build Required", "Build workspace first?",
                QMessageBox.Yes | QMessageBox.No
            ) == QMessageBox.Yes:
                self._build_workspace()
            return

        # 파라미터 입력 다이얼로그
        extra_args, accepted = self._show_run_dialog(
            f"{pkg_name}/{lf_name}",
            f"ros2 launch {pkg_name} {lf_name}",
            param_style="launch"
        )
        if not accepted:
            return

        tab_output = QPlainTextEdit()
        tab_output.setReadOnly(True)
        tab_output.setObjectName("output_text")
        tab_output.setFont(QFont("Monospace", 10))
        tab_output.setMaximumBlockCount(MAX_TAB_LINES)

        tab_label = f"[LAUNCH] {pkg_name}/{lf_name}"
        tab_idx   = self.tab_widget.addTab(tab_output, tab_label)
        self.tab_widget.setCurrentIndex(tab_idx)

        cmd = (f"source {self._ros_setup()} "
               f"&& source {setup_path} "
               f"&& ros2 launch {pkg_name} {lf_name}"
               f"{' ' + extra_args if extra_args else ''}")

        if self.current_ssh:
            worker = RemoteNodeWorkerThread(self.current_ssh, cmd, cwd=ws_str)
        else:
            worker = NodeWorkerThread(cmd, env=self.ros_env, cwd=self.current_workspace)

        def _append(batch, _w=tab_output):
            _w.appendPlainText(batch)

        def _on_finish(code, _w=tab_output):
            status = "✓ 완료" if code == 0 else f"✗ 종료({code})"
            for i in range(self.tab_widget.count()):
                if self.tab_widget.widget(i) is _w:
                    base = self.tab_widget.tabText(i).replace("● ", "").replace("[LAUNCH] ", "")
                    self.tab_widget.setTabText(i, f"■ {base}")
                    break
            _w.appendPlainText(f"\n{'─'*48}\n[{status}]")

        worker.batch_signal.connect(_append, Qt.QueuedConnection)
        worker.finished_signal.connect(_on_finish, Qt.QueuedConnection)
        worker.start()

        self.node_tabs[tab_idx] = worker
        self._log(f"[LAUNCH] {pkg_name}/{lf_name} → 탭 {tab_idx}")

    def _edit_launch(self):
        item = self.tree.currentItem()
        if not item or item.data(0, Qt.UserRole) != "launch":
            return
        path = item.data(0, Qt.UserRole + 1)
        self._open_with_editor(path)

    # ── Tree ──────────────────────────────────

    def _scan_nodes(self, pkg_dir_str: str, ssh=None) -> list:
        """
        패키지 디렉토리에서 노드 목록을 수집 (로컬/리모트 공용).
        반환: [{'name': str, 'path': str, 'type': 'python'|'cpp'|'script'}]
        """
        import re
        import posixpath

        nodes = {}
        if ssh:
            join = posixpath.join
            exists = ssh.exists
            listdir = ssh.listdir_attr   # [(name, is_dir)]
            read_text = ssh.read_text
        else:
            def join(*p): return str(Path(*p))
            def exists(p): return Path(p).exists()
            def listdir(p):
                try:
                    return [(i.name, i.is_dir()) for i in Path(p).iterdir()]
                except Exception:
                    return []
            def read_text(p):
                try:
                    return Path(p).read_text(errors="ignore")
                except Exception:
                    return ""

        pkg_name = pkg_dir_str.rstrip("/").split("/")[-1]

        # ── 1. setup.py console_scripts ──
        setup_py = join(pkg_dir_str, "setup.py")
        if exists(setup_py):
            content = read_text(setup_py)
            pattern = r"['\"](\w+)\s*=\s*([\w.]+):(\w+)['\"]"
            for m in re.finditer(pattern, content):
                node_name, module_path = m.group(1), m.group(2)
                rel = module_path.replace(".", "/") + ".py"
                candidates = [
                    join(pkg_dir_str, rel),
                    join(pkg_dir_str, pkg_name, module_path.split(".")[-1] + ".py"),
                ]
                found_path = next((c for c in candidates if exists(c)), "")
                if node_name not in nodes:
                    nodes[node_name] = {"name": node_name, "path": found_path,
                                        "type": "python", "source": "setup.py"}

        # ── 2. scripts/ 폴더 ──
        scripts_dir = join(pkg_dir_str, "scripts")
        if exists(scripts_dir):
            for name, is_dir in sorted(listdir(scripts_dir)):
                if is_dir or name == "__init__.py":
                    continue
                stem, ext = (name.rsplit(".", 1) + [""])[:2] if "." in name else (name, "")
                if ext in ("py", "") and stem not in nodes:
                    nodes[stem] = {"name": stem, "path": join(scripts_dir, name),
                                   "type": "script", "source": "scripts/"}

        # ── 3. 패키지명/ 디렉토리 Python 파일 ──
        py_dir = join(pkg_dir_str, pkg_name)
        if exists(py_dir):
            for name, is_dir in sorted(listdir(py_dir)):
                if is_dir or name == "__init__.py" or not name.endswith(".py"):
                    continue
                stem = name[:-3]
                if stem not in nodes:
                    nodes[stem] = {"name": stem, "path": join(py_dir, name),
                                   "type": "python", "source": "pkg_dir"}

        # ── 4. C++ 노드: CMakeLists.txt ──
        cmake = join(pkg_dir_str, "CMakeLists.txt")
        if exists(cmake):
            content = read_text(cmake)
            pattern = r"add_executable\s*\(\s*(\w+)\s+([^)]+)\)"
            for m in re.finditer(pattern, content):
                node_name = m.group(1)
                src_files = m.group(2).split()
                found_path = ""
                for sf in src_files:
                    for cand in [join(pkg_dir_str, sf), join(pkg_dir_str, "src", sf)]:
                        if exists(cand):
                            found_path = cand
                            break
                    if found_path:
                        break
                if node_name not in nodes:
                    nodes[node_name] = {"name": node_name, "path": found_path,
                                        "type": "cpp", "source": "CMakeLists.txt"}

        return list(nodes.values())

    def _scan_launch_files(self, pkg_dir_str: str, ssh=None) -> list:
        """패키지 내 launch/ 폴더에서 launch 파일 목록 반환 (로컬/리모트 공용)"""
        import posixpath
        if ssh:
            join = posixpath.join
            exists = ssh.exists
            listdir = ssh.listdir_attr
        else:
            def join(*p): return str(Path(*p))
            def exists(p): return Path(p).exists()
            def listdir(p):
                try:
                    return [(i.name, i.is_dir()) for i in Path(p).iterdir()]
                except Exception:
                    return []

        launch_dir = join(pkg_dir_str, "launch")
        if not exists(launch_dir):
            return []
        valid_exts = {".py", ".xml", ".yaml", ".yml"}
        files = []
        for name, is_dir in sorted(listdir(launch_dir)):
            if is_dir:
                continue
            ext = "." + name.rsplit(".", 1)[-1] if "." in name else ""
            if ext in valid_exts:
                files.append(join(launch_dir, name))
        return files

    def _refresh_tree(self):
        self.tree.clear()
        cfg = self._cfg()
        import posixpath

        def _add_ws_to_tree(ws_str: str, ssh, display_key: str):
            """하나의 워크스페이스를 트리에 추가"""
            if ssh:
                join = posixpath.join
                ws_exists = ssh.exists
                listdir = ssh.listdir_attr
            else:
                def join(*p): return str(Path(*p))
                def ws_exists(p): return Path(p).exists()
                def listdir(p):
                    try:
                        return [(i.name, i.is_dir()) for i in Path(p).iterdir()]
                    except Exception:
                        return []

            if not ws_exists(ws_str):
                return

            ws_name = ws_str.rstrip("/").split("/")[-1]
            prefix = f"[SSH]  " if ssh else "[WS]  "
            ws_item = QTreeWidgetItem([f"{prefix}{ws_name}"])
            ws_item.setData(0, Qt.UserRole, "workspace")
            ws_item.setData(0, Qt.UserRole + 1, ws_str)
            ws_item.setData(0, Qt.UserRole + 2, display_key)   # 콤보 선택과 매칭

            is_current = (display_key == self.ws_combo.currentText())
            if is_current:
                ws_item.setForeground(0, QColor("#5b9cf6"))

            src_dir = join(ws_str, "src")
            if not ws_exists(src_dir):
                self._log(f"[WARN] src/ 폴더 없음: {ws_str}")
            else:
                # 패키지 디렉토리 수집
                pkg_dirs = []
                for name, is_dir in sorted(listdir(src_dir)):
                    if not is_dir:
                        continue
                    pkg_path = join(src_dir, name)
                    if ws_exists(join(pkg_path, "package.xml")):
                        pkg_dirs.append(pkg_path)
                    else:
                        for sub_name, sub_is_dir in sorted(listdir(pkg_path)):
                            if sub_is_dir:
                                sub_path = join(pkg_path, sub_name)
                                if ws_exists(join(sub_path, "package.xml")):
                                    pkg_dirs.append(sub_path)

                self._log(f"[INFO] {ws_name}: 패키지 {len(pkg_dirs)}개 발견")

                for pkg_dir_str in pkg_dirs:
                    pkg_name = pkg_dir_str.rstrip("/").split("/")[-1]
                    is_cpp = (ws_exists(join(pkg_dir_str, "CMakeLists.txt")) and
                              not ws_exists(join(pkg_dir_str, "setup.py")))
                    pkg_label = "[CMAKE]" if is_cpp else "[PKG]"

                    pkg_item = QTreeWidgetItem([f"{pkg_label}  {pkg_name}"])
                    pkg_item.setData(0, Qt.UserRole, "package")
                    pkg_item.setData(0, Qt.UserRole + 1, pkg_dir_str)

                    # 노드 스캔
                    for node_info in self._scan_nodes(pkg_dir_str, ssh):
                        icon = {"python": "[PY]", "cpp": "[C++]"}.get(node_info["type"], "[SH]")
                        n_item = QTreeWidgetItem([f"{icon}  {node_info['name']}"])
                        n_item.setData(0, Qt.UserRole, "node")
                        n_item.setData(0, Qt.UserRole + 1, node_info["path"])
                        n_item.setData(0, Qt.UserRole + 2, node_info["type"])
                        n_item.setToolTip(0,
                            f"Name:   {node_info['name']}\n"
                            f"Type:   {node_info['type']}\n"
                            f"Source: {node_info['source']}\n"
                            f"Path:   {node_info['path'] or '(built binary)'}")
                        pkg_item.addChild(n_item)

                    # Launch 파일 스캔
                    for lf in self._scan_launch_files(pkg_dir_str, ssh):
                        lf_name = lf.rstrip("/").split("/")[-1]
                        ext = "." + lf_name.rsplit(".", 1)[-1] if "." in lf_name else ""
                        icon = {"py": "[LPY]", "xml": "[LXML]"}.get(ext.lstrip("."), "[LYML]")
                        lf_item = QTreeWidgetItem([f"{icon}  {lf_name}"])
                        lf_item.setData(0, Qt.UserRole, "launch")
                        lf_item.setData(0, Qt.UserRole + 1, lf)
                        lf_item.setData(0, Qt.UserRole + 2, pkg_name)
                        lf_item.setToolTip(0, f"Launch: {lf}")
                        pkg_item.addChild(lf_item)

                    ws_item.addChild(pkg_item)

            self.tree.addTopLevelItem(ws_item)
            ws_item.setExpanded(is_current)
            for i in range(ws_item.childCount()):
                ws_item.child(i).setExpanded(is_current)

        # 로컬 워크스페이스
        for ws_str in cfg.get("workspaces", []):
            if Path(ws_str).exists():
                _add_ws_to_tree(ws_str, None, ws_str)

        # 리모트 워크스페이스
        for rws in cfg.get("remote_workspaces", []):
            ssh_id = rws.get("ssh_id", "")
            path   = rws.get("path", "")
            if ssh_id in self.ssh_connections:
                ssh = self.ssh_connections[ssh_id]
                display = f"[{ssh.label}] {path}"
                _add_ws_to_tree(path, ssh, display)


    def _on_item_clicked(self, item, _col):
        role = item.data(0, Qt.UserRole)
        path = item.data(0, Qt.UserRole + 1)

        if role == "workspace":
            display_key = item.data(0, Qt.UserRole + 2)
            self.ws_combo.setCurrentText(display_key)   # _on_workspace_changed 가 처리
            ws_name = path.rstrip("/").split("/")[-1]
            self.ws_info_name.setText(f"Name:  {ws_name}")
            self.ws_info_path.setText(f"Path:  {path}")
            self.stack.setCurrentIndex(1)

        elif role == "package":
            pkg_name = path.rstrip("/").split("/")[-1]
            self.pkg_info_name.setText(f"Name:  {pkg_name}")
            self.pkg_info_path.setText(f"Path:  {path}")
            self.stack.setCurrentIndex(2)

        elif role == "node":
            node_name = item.text(0).split("  ", 1)[-1].strip()
            pkg_name  = item.parent().text(0).split("  ", 1)[-1].strip()
            self.node_info_name.setText(f"Name:     {node_name}")
            self.node_info_pkg.setText(f"Package:  {pkg_name}")
            self.stack.setCurrentIndex(3)

        elif role == "launch":
            lf_path  = item.data(0, Qt.UserRole + 1)
            pkg_name = item.data(0, Qt.UserRole + 2)
            lf_name  = lf_path.rstrip("/").split("/")[-1]
            self.launch_info_name.setText(f"File:     {lf_name}")
            self.launch_info_pkg.setText(f"Package:  {pkg_name}")
            self.launch_info_path.setText(f"Path:     {lf_path}")
            self.stack.setCurrentIndex(4)

    def _context_menu(self, pos):
        item = self.tree.itemAt(pos)
        if not item:
            return
        role = item.data(0, Qt.UserRole)
        menu = QMenu(self)

        if role == "workspace":
            menu.addAction("Build",           self._build_workspace)
            menu.addAction("Source",          self._source_workspace)
            menu.addAction("Add Package",     self._create_package)
            menu.addSeparator()
            menu.addAction("Remove from list", lambda: self._remove_workspace(item))
        elif role == "package":
            menu.addAction("Build Package",   self._build_package)
            menu.addAction("Add Node",        self._create_node)
            menu.addAction("Open Terminal",   self._open_pkg_terminal)
        elif role == "node":
            menu.addAction("Run",             self._run_node)
            menu.addAction("Edit Source",     self._edit_node)
        elif role == "launch":
            menu.addAction("Run Launch",      self._run_launch)
            menu.addAction("Edit Source",     self._edit_launch)

        menu.exec_(self.tree.viewport().mapToGlobal(pos))

    def _remove_workspace(self, item):
        path        = item.data(0, Qt.UserRole + 1)
        display_key = item.data(0, Qt.UserRole + 2)
        cfg = self._cfg()
        # 로컬 or 리모트 판별
        if display_key == path:
            cfg["workspaces"] = [w for w in cfg.get("workspaces", []) if w != path]
        else:
            cfg["remote_workspaces"] = [
                r for r in cfg.get("remote_workspaces", [])
                if not (r["path"] == path and
                        self.ssh_connections.get(r["ssh_id"], object()).label
                        == display_key.split("] ")[0].lstrip("["))
            ]
        if self.current_ssh and str(self.current_workspace) == path:
            self.current_workspace = None
            self.current_ssh = None
            self.ssh_status_lbl.setText("")
        self._save_cfg(cfg)
        self._load_workspaces()

    def _selected_package(self):
        item = self.tree.currentItem()
        if not item:
            return None
        role = item.data(0, Qt.UserRole)
        if role == "package":
            return item.data(0, Qt.UserRole + 1).rstrip("/").split("/")[-1]
        if role == "node":
            path = item.data(0, Qt.UserRole + 1)
            # .../pkg_name/pkg_name/node.py → parent.parent = pkg_name
            parts = path.rstrip("/").split("/")
            return parts[-3] if len(parts) >= 3 else None
        return None

    # ── External Tools ────────────────────────

    def _open_terminal(self, cwd=None):
        # ── SSH 리모트: 로컬 터미널에서 ssh 명령으로 접속 ──
        if self.current_ssh:
            ssh = self.current_ssh
            ws_str = str(self.current_workspace) if self.current_workspace else ""
            distro = self.current_distro or ""
            ros_src = f"source /opt/ros/{distro}/setup.bash && " if distro else ""
            setup_path = f"{ws_str}/install/setup.bash" if ws_str else ""
            ws_src = f"source {setup_path} && " if ws_str and ssh.exists(setup_path) else ""
            init_cmd = f"{ros_src}{ws_src}bash"
            cwd_part = f"cd {ws_str} && " if ws_str else ""
            remote_cmd = f"{cwd_part}{init_cmd}"
            ssh_cmd = f"ssh -t {ssh.user}@{ssh.host} -p {ssh.port} '{remote_cmd}'"
            for term in ["gnome-terminal", "xterm", "konsole", "x-terminal-emulator"]:
                if shutil.which(term):
                    if term == "gnome-terminal":
                        subprocess.Popen([term, "--", BASH, "-c", ssh_cmd])
                    else:
                        subprocess.Popen([term, "-e", f"{BASH} -c '{ssh_cmd}'"])
                    self._log(f"[SSH TERM] {ssh_cmd}")
                    return
            self._log("[WARN] 로컬 터미널 에뮬레이터를 찾지 못했습니다")
            return

        # ── 로컬 ──
        cwd = str(cwd or self.current_workspace or Path.home())
        distro = self.current_distro or ""
        ws_src = ""
        if self.current_workspace:
            s = Path(str(self.current_workspace)) / "install" / "setup.bash"
            if s.exists():
                ws_src = f"source {s} && "
        domain_id = os.environ.get("ROS_DOMAIN_ID", "0")
        env_inject = f"export ROS_DOMAIN_ID={domain_id} && "
        setup_bash = _find_setup_bash(distro) if distro else None
        ros_src = f"source {setup_bash} && " if setup_bash else ""
        init = f"{env_inject}{ros_src}{ws_src}{BASH}"

        if IS_MAC:
            # iTerm2가 설치된 경우 우선 사용, 없으면 Terminal.app
            if Path("/Applications/iTerm.app").exists():
                script = (
                    f'tell application "iTerm2"\n'
                    f'  create window with default profile\n'
                    f'  tell current session of current window\n'
                    f'    write text "cd {cwd} && {init}"\n'
                    f'  end tell\n'
                    f'end tell'
                )
            else:
                script = (
                    f'tell application "Terminal" to activate\n'
                    f'tell application "Terminal" to do script "cd {cwd} && {init}"'
                )
            subprocess.Popen(["osascript", "-e", script])
            return

        for term in ["gnome-terminal", "xterm", "konsole", "x-terminal-emulator"]:
            if shutil.which(term):
                if term == "gnome-terminal":
                    subprocess.Popen([term, f"--working-directory={cwd}", "--", BASH, "-c", init])
                else:
                    subprocess.Popen([term, "-e", f"{BASH} -c '{init}'"])
                return
        self._log("[WARN] No terminal emulator found (gnome-terminal / xterm / konsole)")

    def _launch_terminal_cmd(self, cmd):
        if IS_MAC:
            script = (
                f'tell application "Terminal" to activate\n'
                f'tell application "Terminal" to do script "{cmd}; read -p \'[Press Enter to close]\'"'
            )
            subprocess.Popen(["osascript", "-e", script])
            return

        for term in ["gnome-terminal", "xterm", "konsole"]:
            if shutil.which(term):
                full = f"{BASH} -c '{cmd}; echo; read -p \"[Press Enter to close]\""
                if term == "gnome-terminal":
                    subprocess.Popen([term, "--", BASH, "-c", f"{BASH} -c \"{cmd}\"; read -p '[Press Enter]'"])
                else:
                    subprocess.Popen([term, "-e", full])
                return

    def _open_rviz(self):
        if not self._require_distro():
            return
        env = self.ros_env or get_ros_env(self.current_distro)
        subprocess.Popen(
            [BASH, "-c", f"source {self._ros_setup()} && rviz2"],
            env=env
        )
        self._log("[INFO] RViz2 launched")

    def _open_rqt(self):
        if not self._require_distro():
            return
        env = self.ros_env or get_ros_env(self.current_distro)
        subprocess.Popen(
            [BASH, "-c", f"source {self._ros_setup()} && rqt"],
            env=env
        )
        self._log("[INFO] rqt launched")

    # ── Command Runner ────────────────────────

    def _run_cmd(self, cmd, cwd=None, on_finish=None):
        self._log(f"\n{'─'*52}")
        self._log(f"$ {cmd.split('&&')[-1].strip()}")
        self._log(f"{'─'*52}")

        # 빌드 출력 중 심볼릭 링크 충돌 감지 플래그
        self._symlink_conflict_detected = False

        if self.current_ssh:
            cwd_str = str(cwd) if cwd else None
            self.worker = RemoteWorkerThread(self.current_ssh, cmd, cwd=cwd_str)
        else:
            self.worker = WorkerThread(cmd, env=self.ros_env, cwd=cwd)

        def _check_output(line):
            self._log(line)
            # 심볼릭 링크 충돌 패턴 감지
            if "existing path cannot be removed: Is a directory" in line \
               or "failed to create symbolic link" in line:
                self._symlink_conflict_detected = True

        def _on_finish(code):
            self._log(
                f"\n{'─'*52}\n"
                f"[{'✓  OK' if code == 0 else '✗  FAILED'}] exit code: {code}\n"
            )
            # 빌드 실패 + 심볼릭 링크 충돌 → 자동 안내
            if code != 0 and self._symlink_conflict_detected:
                answer = QMessageBox.question(
                    self,
                    "빌드 오류 감지",
                    "심볼릭 링크 충돌이 감지됐습니다.\n\n"
                    "이전 빌드 캐시와 충돌이 발생했습니다.\n"
                    "Clean 후 재빌드할까요?",
                    QMessageBox.Yes | QMessageBox.No
                )
                if answer == QMessageBox.Yes:
                    self._clean_and_build()

        self.worker.output_signal.connect(_check_output)
        self.worker.finished_signal.connect(_on_finish)
        if on_finish:
            self.worker.finished_signal.connect(lambda _: on_finish())
        self.worker.start()

    def _log(self, text):
        self.output.appendPlainText(text)

    # ── Helpers ───────────────────────────────

    def _require_ws(self):
        if not self.current_workspace:
            self._log("[ERROR] No workspace selected.")
            return False
        if not self.current_distro:
            self._log("[ERROR] No ROS2 distro selected.")
            return False
        return True

    def _require_distro(self):
        if not self.current_distro:
            self._log("[ERROR] No ROS2 distro selected.")
            return False
        return True

    # ── SSH Management ────────────────────────

    def _ensure_paramiko(self, parent=None) -> bool:
        """paramiko 설치 여부 확인 → 없으면 자동 설치 제안. True면 사용 가능."""
        import importlib.util
        if importlib.util.find_spec("paramiko") is not None:
            return True
        ans = QMessageBox.question(
            parent or self,
            "paramiko 필요",
            "SSH 기능을 사용하려면 paramiko 패키지가 필요합니다.\n\n"
            "지금 설치하시겠습니까?\n"
            "  pip install paramiko",
            QMessageBox.Yes | QMessageBox.No,
        )
        if ans != QMessageBox.Yes:
            return False
        import subprocess as _sp
        in_venv = sys.prefix != sys.base_prefix
        cmd = [sys.executable, "-m", "pip", "install", "paramiko"]
        if not in_venv:
            cmd.append("--break-system-packages")
        self._log("[INFO] paramiko 설치 중...")
        result = _sp.run(cmd, capture_output=True, text=True)
        if result.returncode == 0:
            self._log("[OK] paramiko 설치 완료. 다시 연결합니다.")
            return True
        # --break-system-packages 없이 재시도
        if not in_venv:
            result = _sp.run(
                [sys.executable, "-m", "pip", "install", "paramiko"],
                capture_output=True, text=True
            )
            if result.returncode == 0:
                self._log("[OK] paramiko 설치 완료.")
                return True
        self._log(f"[ERROR] paramiko 설치 실패:\n{result.stderr.strip()}")
        QMessageBox.critical(parent or self, "설치 실패",
            f"paramiko 설치에 실패했습니다.\n\n"
            f"터미널에서 직접 실행해 주세요:\n"
            f"  pip install paramiko")
        return False

    def _do_ssh_connect(self, params: dict, parent_dlg=None) -> "SSHConnection | None":
        """SSH 연결 시도 → 성공 시 SSHConnection 반환, 실패 시 None"""
        if not params.get("host") or not params.get("user"):
            return None
        if not self._ensure_paramiko(parent_dlg):
            return None
        try:
            ssh = SSHConnection(
                params["host"], params["user"], params["port"],
                key_path=params.get("key"),
                password=params.get("password") or None,
            )
            ssh_id = ssh.id
            self.ssh_connections[ssh_id] = ssh
            # 저장
            cfg = self._cfg()
            cfg["ssh_hosts"][ssh_id] = {
                k: v for k, v in params.items() if k != "password"
            }
            self._save_cfg(cfg)
            self._log(f"[SSH] 연결됨: {ssh_id}")
            self.ssh_status_lbl.setText(f"● {ssh.label}")
            self._detect_ros2(ssh)
            return ssh
        except Exception as e:
            QMessageBox.critical(parent_dlg or self, "연결 실패", str(e))
            self._log(f"[SSH ERROR] {e}")
            return None

    def _manage_ssh(self):
        """SSH 연결 버튼 — 미연결 시 새 연결, 연결 중 시 관리 메뉴"""
        # 연결된 호스트가 없으면 바로 연결 다이얼로그
        if not self.ssh_connections:
            self._new_ssh_connection()
            return

        # 이미 연결된 호스트가 있으면 관리 메뉴
        from PyQt5.QtWidgets import QListWidget, QListWidgetItem
        dlg = QDialog(self)
        dlg.setWindowTitle("SSH 연결 관리")
        dlg.setMinimumSize(420, 280)
        lay = QVBoxLayout(dlg)
        lay.setContentsMargins(16, 16, 16, 12)
        lay.setSpacing(10)

        lst = QListWidget()
        lst.setObjectName("proj_tree")

        def _refresh():
            lst.clear()
            cfg = self._cfg()
            all_ids = set(self.ssh_connections) | set(cfg.get("ssh_hosts", {}))
            for ssh_id in sorted(all_ids):
                status = "● 연결됨" if ssh_id in self.ssh_connections else "○ 미연결"
                item = QListWidgetItem(f"{status}  {ssh_id}")
                item.setData(Qt.UserRole, ssh_id)
                lst.addItem(item)

        _refresh()
        lay.addWidget(lst)

        btn_row = QHBoxLayout()
        b_new  = QPushButton("+ 새 연결")
        b_conn = QPushButton("재연결")
        b_disc = QPushButton("연결 해제")
        b_del  = QPushButton("삭제")
        b_close = QPushButton("닫기")
        for b in [b_new, b_conn, b_disc, b_del, b_close]:
            b.setObjectName("action_default")
            btn_row.addWidget(b)
        lay.addLayout(btn_row)

        def _new():
            dlg.accept()
            self._new_ssh_connection()

        def _reconnect():
            sel = lst.selectedItems()
            if not sel:
                return
            ssh_id = sel[0].data(Qt.UserRole)
            cfg = self._cfg()
            params = cfg.get("ssh_hosts", {}).get(ssh_id, {})
            if not params:
                return
            # 비밀번호는 저장 안 하므로 필요 시 재입력
            d = SSHConnectDialog(dlg, default_str=ssh_id.rsplit(":", 1)[0])
            if d.exec_() != QDialog.Accepted:
                return
            self._do_ssh_connect(d.get_params(), dlg)
            _refresh()

        def _disconnect():
            sel = lst.selectedItems()
            if not sel:
                return
            ssh_id = sel[0].data(Qt.UserRole)
            if ssh_id in self.ssh_connections:
                self.ssh_connections[ssh_id].close()
                del self.ssh_connections[ssh_id]
                if self.current_ssh and self.current_ssh.id == ssh_id:
                    self.current_ssh = None
                    self.current_workspace = None
                    self.ssh_status_lbl.setText("")
                self._log(f"[SSH] 연결 해제: {ssh_id}")
                self._load_workspaces()
            _refresh()

        def _delete():
            sel = lst.selectedItems()
            if not sel:
                return
            ssh_id = sel[0].data(Qt.UserRole)
            _disconnect()
            cfg = self._cfg()
            cfg["ssh_hosts"].pop(ssh_id, None)
            cfg["remote_workspaces"] = [
                r for r in cfg.get("remote_workspaces", [])
                if r.get("ssh_id") != ssh_id
            ]
            self._save_cfg(cfg)
            _refresh()

        b_new.clicked.connect(_new)
        b_conn.clicked.connect(_reconnect)
        b_disc.clicked.connect(_disconnect)
        b_del.clicked.connect(_delete)
        b_close.clicked.connect(dlg.accept)
        dlg.exec_()

    def _new_ssh_connection(self):
        """새 SSH 연결 다이얼로그 → 연결 성공 시 바로 WS 브라우저"""
        d = SSHConnectDialog(self)
        if d.exec_() != QDialog.Accepted:
            return
        ssh = self._do_ssh_connect(d.get_params())
        if ssh:
            # 연결 성공 → 곧바로 워크스페이스 선택
            self._browse_and_register_ws(ssh)

    def _open_remote_workspace(self):
        """연결된 SSH 호스트 선택 후 원격 WS 브라우저로 등록"""
        if not self.ssh_connections:
            # 연결 없으면 새 연결부터
            self._new_ssh_connection()
            return

        # 연결 호스트가 여러 개면 선택, 하나면 바로 사용
        if len(self.ssh_connections) == 1:
            ssh = next(iter(self.ssh_connections.values()))
        else:
            dlg = QDialog(self)
            dlg.setWindowTitle("호스트 선택")
            dlg.setFixedSize(360, 140)
            lay = QVBoxLayout(dlg)
            lay.setContentsMargins(20, 16, 20, 12)
            combo = QComboBox()
            combo.setObjectName("bar_combo")
            for ssh_id, s in self.ssh_connections.items():
                combo.addItem(s.label, ssh_id)
            lay.addWidget(combo)
            btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
            btns.accepted.connect(dlg.accept)
            btns.rejected.connect(dlg.reject)
            lay.addWidget(btns)
            if dlg.exec_() != QDialog.Accepted:
                return
            ssh = self.ssh_connections[combo.currentData()]

        self._browse_and_register_ws(ssh)

    def _browse_and_register_ws(self, ssh: "SSHConnection"):
        """원격 파일 브라우저로 WS 폴더 선택 후 등록"""
        browser = RemoteBrowseDialog(ssh, self)
        if browser.exec_() != QDialog.Accepted:
            return
        path = browser.selected_path
        if not path:
            return

        # 유효성 경고
        warnings = []
        if not ssh.exists(f"{path}/src"):
            warnings.append("src/ 폴더 없음 — ROS2 워크스페이스가 맞나요?")
        if warnings:
            msg = "\n".join(f"  • {w}" for w in warnings)
            if QMessageBox.question(
                self, "경고", f"{msg}\n\n그래도 등록하시겠습니까?",
                QMessageBox.Yes | QMessageBox.No
            ) != QMessageBox.Yes:
                return

        cfg = self._cfg()
        remote_wss = cfg.setdefault("remote_workspaces", [])
        ssh_id = ssh.id
        if not any(r["ssh_id"] == ssh_id and r["path"] == path for r in remote_wss):
            remote_wss.append({"ssh_id": ssh_id, "path": path})
            self._save_cfg(cfg)

        self._log(f"[OK] 원격 워크스페이스 등록: [{ssh.label}] {path}")
        self._load_workspaces()
        self.ws_combo.setCurrentText(f"[{ssh.label}] {path}")

    # ── Config ────────────────────────────────

    def _cfg_path(self):
        d = Path.home() / ".config" / "ros2_gui_manager"
        d.mkdir(parents=True, exist_ok=True)
        return d / "config.json"

    def _cfg(self):
        p = self._cfg_path()
        if p.exists():
            try:
                data = json.loads(p.read_text())
                data.setdefault("workspaces", [])
                data.setdefault("ssh_hosts", {})
                data.setdefault("remote_workspaces", [])
                return data
            except Exception:
                pass
        return {"workspaces": [], "ssh_hosts": {}, "remote_workspaces": []}

    def _save_cfg(self, cfg):
        self._cfg_path().write_text(json.dumps(cfg, indent=2))


# ─────────────────────────────────────────────
#  Entry
# ─────────────────────────────────────────────

def main():
    app = QApplication(sys.argv)
    app.setApplicationName("ROS2 GUI Manager")
    app.setStyle("Fusion")
    win = MainWindow()
    win.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
