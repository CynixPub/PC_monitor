# CyMouse Monitor - AI Coding Instructions

## Project Overview
CyMouse Monitor is a desktop application built with **Python** and **PySide6** (Qt) that monitors serial data from an ESP32 device (CyMouse) and tracks mouse usage. It features a system tray integration, real-time data visualization, and historical data logging using SQLite.

## Architecture & Core Components

### Entry Point & UI
- **`main.py`**: Application entry point. Initializes `QApplication` and `MainWindow`.
- **`main_window.py`**: The primary controller.
  - Loads UI dynamically from `main.ui` using `QUiLoader`.
  - Manages the system tray icon (`QSystemTrayIcon`) and window visibility.
  - Connects UI signals to business logic.
- **`history_window.py`**: Displays historical data charts/tables.

### Serial Communication (`serial_worker.py`)
- **`SerialWorker`**: Handles all serial port interactions.
  - **Threading**: Must run in a separate `QThread` to prevent UI freezing.
  - **Protocol**: Implements a custom binary protocol with CRC16-XMODEM validation.
  - **Signals**: Uses `PySide6.QtCore.Signal` to push data to the main thread (e.g., `health_data_received`, `mouse_data_received`).
  - **Pattern**: Never call blocking serial methods from the main thread.

### Data Persistence (`database_handler.py`)
- **`DatabaseHandler`**: Manages SQLite interactions (`history.db`).
- **Schema**:
  - `health_data`: Stores time-series health metrics.
  - `mouse_data`: Stores cumulative mouse usage stats (single row, ID=1).
- **Path Handling**: Uses `utils.user_data_path` to ensure the DB is stored in a writable location (AppData/Home), crucial for packaged builds.

## Critical Developer Workflows

### UI Development
- **.ui Files**: The UI is defined in `main.ui` (Qt Designer format).
- **Loading**: Always use `utils.resource_path()` when loading assets (images, .ui files) to support both dev and PyInstaller environments.
  ```python
  from utils import resource_path
  loader.load(resource_path("main.ui"))
  ```

### Serial Protocol Implementation
- When adding new commands, update `constants.py`.
- Ensure all binary data packets are validated with `crc16_xmodem`.
- **Flow**:
  1. `SerialWorker` reads bytes.
  2. Validates CRC.
  3. Emits specific signal (e.g., `ack_received`).
  4. `MainWindow` slot handles the signal.

### Build & Packaging
- **Tool**: PyInstaller.
- **Spec File**: `CyMouseMonitor.spec`.
- **Command**: `pyinstaller CyMouseMonitor.spec`
- **Assets**: Ensure `main.ui` and icons are included in the `datas` list in the spec file.

## Project-Specific Conventions

- **Path Handling**: NEVER use relative paths like `./data.db`. Always use `utils.resource_path()` for read-only assets and `utils.user_data_path()` for writable data.
- **Signal Naming**: Use snake_case for custom signals (e.g., `health_data_received`).
- **Threading**: `SerialWorker` should be moved to a thread using `worker.moveToThread(thread)`.
- **Imports**: Prefer `PySide6` over `PyQt5`.

## Integration Points
- **ESP32**: Communicates via USB Serial. See `constants.py` for protocol definitions.
- **System Tray**: The app is designed to run in the background. Closing the window minimizes to tray (handled in `closeEvent`).
