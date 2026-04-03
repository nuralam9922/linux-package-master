# Linux Package Master (LPM) 🚀

**LPM** is a production-grade Terminal User Interface (TUI) designed to unify package management on Ubuntu. It provides a single, lightning-fast, and safe interface to search, filter, and uninstall applications across multiple package managers.

## ✨ Features

- **Unified Management:** Supports **APT**, **Snap**, **Flatpak**, **NPM (Global)**, and **Pip (Python)**.
- **Buttery Smooth UI:** 
  - Uses **Double-Buffered Rendering** (`noutrefresh` + `doupdate`) for zero-flicker performance.
  - **Smart Viewport Scrolling:** Only scrolls when the selection hits the edge, providing a natural navigation feel.
- **Informative & Sortable:**
  - **Installed Date:** View exactly when each package was installed on your system.
  - **Instant Sorting:** Press **`D`** to toggle between sorting by **Name** or **Installation Date**.
- **Parallel Scanning:** Uses multi-threading to fetch package lists from all sources simultaneously.
- **Safety First:**
  - **Filter GUI Only:** APT list is filtered to show only manually installed apps with GUI launchers (prevents system breakage).
  - **Critical Blacklist:** Hardcoded protection for system essentials like `sudo`, `kernel`, `systemd`, etc.
  - **No-Sudo for Dev:** Smartly uses `sudo` only where required (APT/Snap/Flatpak) and avoids it for user-level `pip` packages.
- **Modern TUI:**
  - **Fuzzy Search:** Quickly find any app with partial names.
  - **Batch Uninstallation:** Select multiple apps from different sources and remove them in one go.

## 🚀 Getting Started

### Prerequisites
- Python 3.6+
- Ubuntu/Debian-based Linux

### Installation
1. Download the script:
   ```bash
   (https://github.com/nuralam9922/-linux-package-master.git)
   ```
2. Make it executable:
   ```bash
   chmod +x lpm
   ```
3. (Optional) Move to your path to run from anywhere:
   ```bash
   sudo mv lpm /usr/local/bin/lpm
   ```

## 🎮 Controls

| Key | Action |
| :--- | :--- |
| **`↑ / ↓`** | Navigate through the list (Smooth Viewport) |
| **`Space`** | Select / Deselect a package |
| **`D`** | **Toggle Sorting** (By Name or Installation Date) |
| **`/`** | Activate fuzzy search mode |
| **`Enter`** | Start uninstallation of selected items |
| **`A, S, F, N, P`** | Toggle specific sources (APT, Snap, Flatpak, NPM, Pip) |
| **`Esc`** | Clear search / Exit search mode |
| **`Q`** | Quit the application |

## 🛠 Tech Stack
- **Language:** Python 3
- **TUI Library:** `curses` (Standard Library)
- **Concurrency:** `concurrent.futures` for parallel subprocess management.

## 📄 License
Distributed under the **MIT License**. See `LICENSE` for more information.
