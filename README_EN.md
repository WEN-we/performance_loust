# 🚀 Locust Stress Testing Platform

中文 | [English](./README_EN.md)

A Windows desktop stress testing platform based on Locust, featuring visual task management, real-time monitoring, and report generation.

![Python](https://img.shields.io/badge/Python-3.11+-blue)
![PySide6](https://img.shields.io/badge/PySide6-6.5+-green)
![Locust](https://img.shields.io/badge/Locust-2.20+-orange)
![Platform](https://img.shields.io/badge/Platform-Windows-blue)
![License](https://img.shields.io/badge/License-MIT-yellow)

---

## 📋 Features

### Core Capabilities
- **HTTP/HTTPS Stress Testing** — Full method support: GET/POST/PUT/DELETE/PATCH
- **WebSocket Stress Testing** — Native WebSocket protocol load testing
- **JWT Authentication** — Bearer Token / Basic Auth support
- **Parameterized Variables** — `${variable}` syntax with CSV data-driven testing
- **Custom Requests** — Header / Cookie / Token / JSON Body / Form / File Upload
- **Distributed Testing** — Master/Worker multi-machine coordination

### UI Features
- **6 Functional Pages** — Dashboard, Create Task, Execute Task, Real-time Monitor, History, Settings
- **Dark Mode** — One-click light/dark theme switching
- **Real-time Monitoring** — 12 core metrics + 4 line charts (matplotlib)
- **Report Export** — HTML / PDF / Excel / PNG multi-format
- **API Import** — Swagger/OpenAPI/Postman Collection one-click import

### Technical Features
- **Plugin System** — Dynamic plugin loading with hook system
- **Scheduled Tasks** — APScheduler Cron-based scheduling
- **System Monitoring** — Real-time CPU/Memory display
- **Logging** — Daily rotation with automatic traceback recording

---

## 📁 Project Structure

```
performance_loust/
│
├── main.py                    # Application entry point
├── build.py                   # PyInstaller build helper
├── requirements.txt           # Dependencies
│
├── config/                    # Configuration management
│   └── settings.py            # Singleton Settings, JSON config read/write
│
├── core/                      # Core engine
│   ├── locust_engine.py       # Locust engine (lazy import, PyInstaller compatible)
│   ├── distributed_manager.py # Distributed Master/Worker management
│   └── plugin_manager.py      # Plugin extension mechanism
│
├── database/                  # Data persistence layer
│   └── db_manager.py          # SQLite manager (5-table CRUD + connection pool + transactions)
│
├── services/                  # Business service layer
│   ├── task_service.py        # Task lifecycle management
│   ├── execution_service.py   # Task execution control (queue/pause/resume)
│   ├── report_service.py      # HTML/PDF/Excel/PNG report generation
│   ├── scheduler_service.py   # APScheduler scheduled tasks
│   └── api_import_service.py  # Swagger/OpenAPI/Postman import
│
├── ui/                        # UI framework layer
│   ├── main_window.py         # Main window (6-page integration)
│   ├── navigation.py          # Left navigation bar (programmatic icons)
│   ├── status_bar.py          # Top CPU/Memory status bar
│   └── styles.py              # QSS style management (light/dark themes)
│
├── pages/                     # Page component layer
│   ├── home_page.py           # Dashboard
│   ├── create_task_page.py    # Create/Edit task
│   ├── execute_task_page.py   # Execute task (status badge + queue)
│   ├── monitor_page.py        # Real-time monitoring (12 metrics + 4 charts)
│   ├── history_page.py        # History (pagination + export)
│   └── settings_page.py       # System settings
│
├── utils/                     # Utility layer
│   ├── logger.py              # Logging system (daily rotation + traceback)
│   ├── helpers.py             # Resource path/CSV/JSON/file operations
│   └── system_monitor.py      # CPU/Memory/Disk/Network monitoring
│
├── plugins/                   # Plugin directory (auto-scan loading)
├── resources/                 # Resource files (icons, etc.)
├── logs/                      # Log output directory
└── data/                      # SQLite database directory
```

---

## 🗄️ Database Design

| Table | Purpose | Key Fields |
|-------|---------|------------|
| `tasks` | Task configuration | name, type, method, url, headers, cookies, token, body, users, spawn_rate, run_time |
| `task_results` | Execution results | task_id, status, qps, tps, rps, avg/max/min/p95_response_time, fail_rate |
| `history` | Historical records | task_name, execute_time, duration, result_summary, stats_json |
| `settings` | System settings | key, value |
| `distributed_nodes` | Distributed nodes | task_id, node_type, host, port, status, worker_count |

---

## 🚀 Quick Start

### Prerequisites

- Python 3.11+
- Windows 10/11
- pip

### Installation

```bash
# 1. Clone the repository
git clone https://github.com/WEN-we/performance_loust.git
cd performance_loust

# 2. Create virtual environment
python -m venv .venv

# 3. Activate virtual environment
.venv\Scripts\activate

# 4. Install dependencies
pip install -r requirements.txt

# 5. Run the application
python main.py
```

### Direct Download

👉 Go to [Releases](https://github.com/WEN-we/performance_loust/releases) to download the Windows executable. No Python installation required.

---

## 📦 Building

```bash
# Install PyInstaller
pip install pyinstaller

# Build (directory mode, recommended)
pyinstaller --name LocustPlatform --windowed --noconfirm main.py

# Build (single file mode)
pyinstaller -F -w -i icon.ico --name LocustPlatform main.py

# Build using spec file
pyinstaller LocustPlatform.spec --noconfirm
```

The build output is located in `dist/LocustPlatform/`.

---

## 📊 Real-time Monitoring Metrics

| Metric | Description |
|--------|-------------|
| QPS | Queries Per Second |
| TPS | Transactions Per Second |
| RPS | Responses Per Second |
| Avg Response Time | Average response time across all requests |
| Max/Min Response Time | Response time extremes |
| P95 Response Time | 95th percentile response time |
| Failure Rate | Percentage of failed requests |
| Active Users | Current number of active virtual users |
| Success/Failure Count | Request statistics |

---

## 🔌 Plugin Development

Create a Python file in the `plugins/` directory, extending `PluginBase`:

```python
from core.plugin_manager import PluginBase, HookType

class MyPlugin(PluginBase):
    @property
    def name(self) -> str:
        return "my_plugin"

    def on_load(self) -> None:
        self.add_hook(HookType.PRE_REQUEST, self.before_request)

    def on_unload(self) -> None:
        pass

    def before_request(self, **kwargs):
        print("Pre-request processing")
```

Plugins in the `plugins/` directory are automatically discovered and loaded on startup.

---

## 🛠️ Tech Stack

| Component | Technology |
|-----------|------------|
| GUI Framework | PySide6 |
| Load Testing Engine | Locust |
| Charts | Matplotlib |
| Database | SQLite |
| Scheduling | APScheduler |
| Reports | Jinja2 / fpdf2 / openpyxl |
| System Monitoring | psutil |
| Packaging | PyInstaller |

---

## 📄 License

MIT License

---

## 🤝 Contributing

Issues and Pull Requests are welcome!
