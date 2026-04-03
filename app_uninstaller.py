#!/usr/bin/env python3
"""
Linux Package Master (LPM)
A unified, production-grade terminal interface for managing packages across
APT, Snap, Flatpak, NPM, and Pip.
"""

import curses
import subprocess
import shutil
import os
import re
import json
import concurrent.futures
from datetime import datetime

# --- Configuration & Safety ---
TYPE_APT = "APT"
TYPE_SNAP = "Snap"
TYPE_FLATPAK = "Flatpak"
TYPE_NPM = "NPM"
TYPE_PIP = "Pip"

SOURCES_CONFIG = {
    TYPE_APT: {"key": "a", "color": 4, "desc": "System Apps (Debian)"},
    TYPE_SNAP: {"key": "s", "color": 5, "desc": "Canonical Snaps"},
    TYPE_FLATPAK: {"key": "f", "color": 6, "desc": "Flatpak Apps"},
    TYPE_NPM: {"key": "n", "color": 7, "desc": "Global JS Packages"},
    TYPE_PIP: {"key": "p", "color": 1, "desc": "Python Packages"},
}

SYSTEM_CRITICAL_PACKAGES = {
    'sudo', 'systemd', 'apt', 'bash', 'coreutils', 'gnome-shell', 
    'linux-image', 'grub', 'dpkg', 'libc6', 'xorg', 'wayland',
    'pip', 'pip3', 'npm', 'setuptools', 'wheel', 'python3', 'python'
}

# --- Global Paths for Cache ---
NPM_ROOT = None
PIP_SITE = None

# --- Utility Functions ---

def get_mtime_date(path):
    """Safely gets the modification date of a path."""
    try:
        if os.path.exists(path):
            mtime = os.path.getmtime(path)
            return datetime.fromtimestamp(mtime).strftime('%Y-%m-%d')
    except: pass
    return "unknown"

def fuzzy_match(query, target):
    query = query.lower()
    target = target.lower()
    it = iter(target)
    return all(char in it for char in query)

def run_command(cmd, shell=False):
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True, shell=shell, timeout=30)
        return result.stdout
    except: return ""

# --- Data Fetchers ---

def get_apt_packages():
    packages = []
    manual_out = run_command(['apt-mark', 'showmanual'])
    manual_pkgs = set(manual_out.splitlines())
    desktop_out = run_command("dpkg-query -S '/usr/share/applications/*.desktop' 2>/dev/stdout", shell=True)
    desktop_pkgs = {line.split(':')[0] for line in desktop_out.splitlines() if ':' in line}
    gui_pkgs = list(manual_pkgs.intersection(desktop_pkgs))
    
    if gui_pkgs:
        info_out = run_command(['dpkg-query', '-W', '-f=${Package}\t${Version}\n'] + gui_pkgs)
        for line in info_out.splitlines():
            if '\t' in line:
                name, version = line.split('\t')
                if name not in SYSTEM_CRITICAL_PACKAGES:
                    # APT Date: Check the .list file in /var/lib/dpkg/info/
                    date = get_mtime_date(f'/var/lib/dpkg/info/{name}.list')
                    packages.append({"name": name, "version": version, "type": TYPE_APT, "date": date})
    return packages

def get_snap_packages():
    if not shutil.which('snap'): return []
    ignore_regex = re.compile(r'core\d*|snapd|bare|gtk-common-themes|gnome-3-|kde-frameworks|wine-platform')
    out = run_command(['snap', 'list'])
    packages = []
    for line in out.splitlines()[1:]:
        parts = line.split()
        if len(parts) >= 2:
            name, version = parts[0], parts[1]
            if not ignore_regex.search(name) and name not in SYSTEM_CRITICAL_PACKAGES:
                # Snap Date: Check the /snap/{name} folder
                date = get_mtime_date(f'/snap/{name}/current')
                packages.append({"name": name, "version": version, "type": TYPE_SNAP, "date": date})
    return packages

def get_flatpak_packages():
    if not shutil.which('flatpak'): return []
    out = run_command(['flatpak', 'list', '--app', '--columns=name,application,version'])
    packages = []
    for line in out.splitlines():
        parts = line.split('\t')
        if len(parts) >= 3:
            name, app_id, version = parts[0], parts[1], parts[2]
            if app_id not in SYSTEM_CRITICAL_PACKAGES:
                # Flatpak Date: Check /var/lib/flatpak/app/{id}
                date = get_mtime_date(f'/var/lib/flatpak/app/{app_id}/current')
                packages.append({"name": name, "id": app_id, "version": version, "type": TYPE_FLATPAK, "date": date})
    return packages

def get_npm_packages():
    global NPM_ROOT
    if not shutil.which('npm'): return []
    if not NPM_ROOT:
        NPM_ROOT = run_command(['npm', 'root', '-g']).strip()
    
    out = run_command(['npm', 'list', '-g', '--depth=0', '--json'])
    if not out: return []
    try:
        data = json.loads(out)
        deps = data.get('dependencies', {})
        pkgs = []
        for name, info in deps.items():
            if name not in SYSTEM_CRITICAL_PACKAGES:
                date = get_mtime_date(os.path.join(NPM_ROOT, name))
                pkgs.append({"name": name, "version": info.get('version', 'unknown'), "type": TYPE_NPM, "date": date})
        return pkgs
    except: return []

def get_pip_packages():
    global PIP_SITE
    pip_cmd = shutil.which('pip3') or shutil.which('pip')
    if not pip_cmd: return []
    if not PIP_SITE:
        PIP_SITE = run_command(['python3', '-m', 'site', '--user-site']).strip()
    
    out = run_command([pip_cmd, 'list', '--user', '--format=json'])
    if not out: return []
    try:
        data = json.loads(out)
        pkgs = []
        for item in data:
            name = item.get('name')
            if name and name not in SYSTEM_CRITICAL_PACKAGES:
                # Use site-packages directory for mtime
                date = get_mtime_date(os.path.join(PIP_SITE, name.replace('-', '_')))
                pkgs.append({"name": name, "version": item.get('version'), "type": TYPE_PIP, "date": date})
        return pkgs
    except: return []

# --- TUI Implementation ---

class LinuxPackageMaster:
    def __init__(self, stdscr):
        self.stdscr = stdscr
        self.all_packages = []
        self.filtered_packages = []
        self.selected_keys = set()
        self.current_pos = 0
        self.top_idx = 0
        self.search_query = ""
        self.is_searching = False
        self.loading = True
        self.enabled_sources = set(SOURCES_CONFIG.keys())
        self.sort_by_date = False

    def load_packages(self):
        self.loading = True
        self.all_packages = []
        fetchers = {TYPE_APT: get_apt_packages, TYPE_SNAP: get_snap_packages, TYPE_FLATPAK: get_flatpak_packages, TYPE_NPM: get_npm_packages, TYPE_PIP: get_pip_packages}
        active_fetchers = {t: f for t, f in fetchers.items() if t in self.enabled_sources}
        with concurrent.futures.ThreadPoolExecutor(max_workers=len(active_fetchers)) as executor:
            future_to_type = {executor.submit(f): t for t, f in active_fetchers.items()}
            for future in concurrent.futures.as_completed(future_to_type):
                try: self.all_packages.extend(future.result())
                except: pass
        self.apply_sort_and_filter()
        self.loading = False

    def apply_sort_and_filter(self):
        if not self.search_query:
            self.filtered_packages = [p for p in self.all_packages if p['type'] in self.enabled_sources]
        else:
            self.filtered_packages = [p for p in self.all_packages if p['type'] in self.enabled_sources and fuzzy_match(self.search_query, p['name'])]
        
        # Sorting
        if self.sort_by_date:
            self.filtered_packages.sort(key=lambda x: x['date'], reverse=True)
        else:
            self.filtered_packages.sort(key=lambda x: x['name'].lower())
        
        self.current_pos = min(self.current_pos, max(0, len(self.filtered_packages) - 1))

    def draw(self):
        """Buttery Smooth UI using noutrefresh and doupdate."""
        self.stdscr.erase()
        height, width = self.stdscr.getmaxyx()
        
        if height < 10 or width < 80:
            self.stdscr.addstr(0, 0, "Terminal too small! Resize to at least 80 chars wide.")
            self.stdscr.refresh()
            return

        # Viewport Scroll
        list_height = height - 6
        if self.current_pos < self.top_idx: self.top_idx = self.current_pos
        elif self.current_pos >= self.top_idx + list_height: self.top_idx = self.current_pos - list_height + 1

        # Header
        self.stdscr.attron(curses.color_pair(2) | curses.A_BOLD)
        self.stdscr.addstr(0, 0, " LINUX PACKAGE MASTER (LPM) ".center(width))
        self.stdscr.attroff(curses.color_pair(2) | curses.A_BOLD)

        # Filters & Sorting Status
        curr_x = 1
        for ptype, cfg in SOURCES_CONFIG.items():
            attr = curses.color_pair(cfg['color']) | curses.A_BOLD if ptype in self.enabled_sources else curses.A_DIM
            label = f"[{cfg['key'].upper()}] {ptype}"
            self.stdscr.addstr(1, curr_x, label, attr)
            curr_x += len(label) + 2
        
        sort_label = f" [D] Sort: {'Date' if self.sort_by_date else 'Name'} "
        self.stdscr.addstr(1, width - len(sort_label), sort_label, curses.A_REVERSE)

        # Search Bar
        search_label = " SEARCH: " if self.is_searching else " Search (/): "
        self.stdscr.addstr(2, 0, search_label, curses.color_pair(3))
        self.stdscr.addstr(2, len(search_label), self.search_query)
        if self.is_searching:
            curses.curs_set(1)
            self.stdscr.move(2, len(search_label) + len(self.search_query))
        else:
            curses.curs_set(0)

        # Footer
        help_text = " [↑/↓] Nav | [SPACE] Select | [D] Toggle Sort | [ENTER] Uninstall | [Q] Quit "
        self.stdscr.addstr(height - 1, 0, help_text.center(width)[:width-1], curses.A_REVERSE)

        if self.loading:
            self.stdscr.addstr(height // 2, (width // 2) - 10, "⚡ Syncing Package Repos...", curses.A_BOLD)
        elif not self.filtered_packages:
            self.stdscr.addstr(height // 2, (width // 2) - 10, "No packages found.")
        else:
            # Columns
            headers = f" {'   '} {'Package Name':<30} | {'Source':<8} | {'Date':<10} | {'Version'}"
            self.stdscr.addstr(4, 0, headers[:width-1], curses.A_UNDERLINE)

            end_idx = min(len(self.filtered_packages), self.top_idx + list_height)
            for i in range(self.top_idx, end_idx):
                pkg = self.filtered_packages[i]
                y = 5 + (i - self.top_idx)
                pkg_key = f"{pkg['name']}:{pkg['type']}"
                selected = pkg_key in self.selected_keys
                selector = "[X]" if selected else "[ ]"
                
                line = f" {selector} {pkg['name'][:30]:<30} | {pkg['type']:<8} | {pkg['date']:<10} | {pkg['version'][:20]}"
                
                if i == self.current_pos:
                    self.stdscr.attron(curses.A_REVERSE)
                    self.stdscr.addstr(y, 0, line[:width-1])
                    self.stdscr.attroff(curses.A_REVERSE)
                elif selected:
                    self.stdscr.attron(curses.color_pair(3))
                    self.stdscr.addstr(y, 0, line[:width-1])
                    self.stdscr.attroff(curses.color_pair(3))
                else:
                    self.stdscr.addstr(y, 0, line[:6+30+2])
                    color = SOURCES_CONFIG[pkg['type']]['color']
                    self.stdscr.addstr(y, 6 + 30 + 3, pkg['type'], curses.color_pair(color))
                    self.stdscr.addstr(y, 6 + 30 + 3 + 8 + 3, pkg['date'], curses.A_DIM)
                    self.stdscr.addstr(y, 6 + 30 + 3 + 8 + 3 + 10 + 3, pkg['version'][:20])

        self.stdscr.noutrefresh()
        curses.doupdate()

    def uninstall_selected(self):
        if not self.selected_keys: return
        to_remove = [p for p in self.all_packages if f"{p['name']}:{p['type']}" in self.selected_keys]
        self.stdscr.clear()
        self.stdscr.addstr(0, 0, "UNINSTALL PLAN:", curses.A_BOLD | curses.color_pair(3))
        for idx, pkg in enumerate(to_remove[:15]): self.stdscr.addstr(idx+2, 2, f"• {pkg['name']} ({pkg['type']})")
        self.stdscr.addstr(20, 0, "Proceed? (y/n): ", curses.A_BOLD)
        self.stdscr.refresh()
        if self.stdscr.getch() not in (ord('y'), ord('Y')): return

        curses.endwin()
        print("\n" + "="*60 + "\n LPM UNINSTALLER \n" + "="*60 + "\n")
        for pkg in to_remove:
            print(f"[*] Removing {pkg['name']} ({pkg['type']})...")
            try:
                if pkg['type'] == TYPE_APT: subprocess.run(['sudo', 'apt', 'purge', '-y', pkg['name']], check=True)
                elif pkg['type'] == TYPE_SNAP: subprocess.run(['sudo', 'snap', 'remove', pkg['name']], check=True)
                elif pkg['type'] == TYPE_FLATPAK: subprocess.run(['sudo', 'flatpak', 'uninstall', '-y', pkg.get('id', pkg['name'])], check=True)
                elif pkg['type'] == TYPE_NPM: subprocess.run(['npm', 'uninstall', '-g', pkg['name']], check=True)
                elif pkg['type'] == TYPE_PIP:
                    pip_cmd = shutil.which('pip3') or shutil.which('pip')
                    subprocess.run([pip_cmd, 'uninstall', '-y', pkg['name']], check=True)
                print(f"[OK] Done.\n")
            except Exception as e: print(f"[ERROR] {e}\n")
        input("Press ENTER to return.")
        self.selected_keys.clear()
        self.load_packages()

    def run(self):
        curses.init_pair(1, curses.COLOR_RED, curses.COLOR_BLACK)
        curses.init_pair(2, curses.COLOR_WHITE, curses.COLOR_BLUE)
        curses.init_pair(3, curses.COLOR_GREEN, curses.COLOR_BLACK)
        curses.init_pair(4, curses.COLOR_CYAN, curses.COLOR_BLACK)
        curses.init_pair(5, curses.COLOR_MAGENTA, curses.COLOR_BLACK)
        curses.init_pair(6, curses.COLOR_YELLOW, curses.COLOR_BLACK)
        curses.init_pair(7, curses.COLOR_WHITE, curses.COLOR_BLACK)
        self.load_packages()

        while True:
            self.draw()
            try: key = self.stdscr.getch()
            except KeyboardInterrupt: break
            if key == curses.KEY_RESIZE: continue
            if key == ord('q') and not self.is_searching: break
            if not self.is_searching:
                if key == ord('d'): self.sort_by_date = not self.sort_by_date; self.apply_sort_and_filter()
                for ptype, cfg in SOURCES_CONFIG.items():
                    if key == ord(cfg['key']):
                        if ptype in self.enabled_sources: self.enabled_sources.remove(ptype)
                        else: self.enabled_sources.add(ptype)
                        self.apply_sort_and_filter()

            if key == curses.KEY_UP: self.current_pos = max(0, self.current_pos - 1)
            elif key == curses.KEY_DOWN: self.current_pos = min(len(self.filtered_packages) - 1, self.current_pos + 1)
            elif key == ord(' '):
                if self.filtered_packages:
                    pkg = self.filtered_packages[self.current_pos]; k = f"{pkg['name']}:{pkg['type']}"
                    if k in self.selected_keys: self.selected_keys.remove(k)
                    else: self.selected_keys.add(k)
            elif key == ord('/'): self.is_searching = True
            elif key == 27: self.is_searching = False; self.search_query = ""; self.apply_sort_and_filter()
            elif key == 10:
                if self.is_searching: self.is_searching = False
                else: self.uninstall_selected()
            elif self.is_searching:
                if key == 8 or key == 127 or key == curses.KEY_BACKSPACE: self.search_query = self.search_query[:-1]
                elif 32 <= key <= 126: self.search_query += chr(key)
                self.apply_sort_and_filter()

if __name__ == "__main__":
    try: curses.wrapper(lambda stdscr: LinuxPackageMaster(stdscr).run())
    except Exception as e: print(f"LPM Crash: {e}")
