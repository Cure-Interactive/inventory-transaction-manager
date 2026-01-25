#!/usr/bin/env python3
# =============================================================================
# [📦 Inventory] [🧮 Weighted Average Cost] [🖥️ CustomTkinter App]
# =============================================================================
"""
@fileoverview
  Inventory transaction manager (PURCHASE/SALE) using weighted-average costing,
  implemented as a CustomTkinter desktop app to replace spreadsheet formulas.

  NEW: Project selection (like png_to_ico GUI):
  - Select a "Project Directory" (folder)
  - Transactions persist to: <ProjectDir>/inventory_data.json
  - Recent project folders persist to: <ScriptDir>/config.json

  NEW: SKU Aliases:
  - Aliases persist to: <ProjectDir>/inventory_data.json (alongside transactions)
  - Transactions + Overview tables show an Alias column (after SKU)
  - Transactions form has an Alias dropdown that sets the SKU field

  Sorting:
  - Transactions are sorted by Date ascending, then by stable insertion order.

  Date format accepted:
  - YYYY-MM-DD or M/D/YYYY (normalized to YYYY-MM-DD)
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, asdict
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

import customtkinter as ctk
import tkinter as tk
from tkinter import ttk, messagebox, filedialog

# =============================================================================
# Optional dependency: tkcalendar (nice date picker)
#   pip install tkcalendar
# =============================================================================
try:
  from tkcalendar import Calendar  # type: ignore
except Exception:
  Calendar = None  # type: ignore

def apply_entry_shortcuts(entry_widget) -> None:
  """
  Normalize common text shortcuts across OS for Tk/CustomTkinter entries:
    - Ctrl+A selects all
    - Ctrl+V replaces selection (if any), otherwise inserts at caret
  """
  # CTkEntry often wraps the real tk.Entry as `_entry`
  inner = getattr(entry_widget, "_entry", entry_widget)

  def _select_all(_e=None):
    try:
      inner.selection_range(0, tk.END)
      inner.icursor(tk.END)
    except Exception:
      pass
    return "break"

  def _paste_replace(_e=None):
    try:
      # If there's a selection, delete it first (Windows-style replace).
      try:
        sel_first = inner.index("sel.first")
        sel_last  = inner.index("sel.last")
        inner.delete(sel_first, sel_last)
      except Exception:
        pass

      clip = inner.clipboard_get()
      inner.insert(tk.INSERT, clip)
    except Exception:
      pass
    return "break"

  # Windows/Linux
  inner.bind("<Control-a>", _select_all, add="+")
  inner.bind("<Control-A>", _select_all, add="+")
  inner.bind("<Control-v>", _paste_replace, add="+")
  inner.bind("<Control-V>", _paste_replace, add="+")
  inner.bind("<Shift-Insert>", _paste_replace, add="+")

  # macOS (optional)
  inner.bind("<Command-a>", _select_all, add="+")
  inner.bind("<Command-v>", _paste_replace, add="+")

# =============================================================================
# Tooltips (best-effort; optional dependency)
# =============================================================================

try:
  from CTkToolTip import CTkToolTip  # type: ignore
except Exception:
  CTkToolTip = None  # type: ignore


def tooltip(*widgets: Any, text: str) -> None:
  """Attach (or update) the same tooltip on one or more Tk/CTk widgets.

  Behavior:
  - If CTkToolTip is not installed, this is a no-op.
  - Tooltips are cached on each widget as `_cure_tooltip`.
  - If a widget already has a tooltip, we best-effort close/destroy it first.

  Args:
    *widgets: One or more tkinter/customtkinter widgets.
    text: Tooltip text to show.
  """
  if CTkToolTip is None:
    return

  for w in widgets:
    if w is None:
      continue

    # Best-effort: remove old tooltip instance if we've attached one before.
    old = getattr(w, "_cure_tooltip", None)
    if old is not None:
      try:
        if hasattr(old, "hide"):
          old.hide()
      except Exception:
        pass
      try:
        if hasattr(old, "destroy"):
          old.destroy()
      except Exception:
        pass

    try:
      w._cure_tooltip = CTkToolTip(w, message=str(text))  # type: ignore[attr-defined]
    except Exception:
      # Last resort: never let tooltips break the UI.
      try:
        w._cure_tooltip = None  # type: ignore[attr-defined]
      except Exception:
        pass


# =============================================================================
# Window Icon (title bar / taskbar best-effort)
# =============================================================================

def set_window_icon(root, ico_path: str, png_path: str) -> None:
  """
  Set a title-bar icon with best-effort cross-platform behavior.

  Windows:
    - iconbitmap(.ico) works for title bar + taskbar in most cases.
  Linux/macOS:
    - iconphoto(.png) is the common path.

  Notes:
  - We try both; failures are ignored (best effort).
  - Paths should be absolute for reliability.
  """
  ico_abs = os.path.abspath(ico_path) if ico_path else ""
  png_abs = os.path.abspath(png_path) if png_path else ""

  try:
    if ico_abs and os.path.isfile(ico_abs):
      root.iconbitmap(ico_abs)
  except Exception:
    pass

  try:
    if png_abs and os.path.isfile(png_abs):
      img = tk.PhotoImage(file=png_abs)
      root.iconphoto(True, img)
      root._iconphoto_ref = img  # type: ignore[attr-defined]
  except Exception:
    pass


# =============================================================================
# TTK Theme Parity (Treeview + Scrollbar) — dark mode matching CustomTkinter
# =============================================================================

def _ttk_font(size: int, *, weight: str = "normal"):
  return ("Segoe UI", size, weight)

def _ctk_color(c):
  """
  Resolve a CustomTkinter theme color (single or (light,dark) tuple) to a color string.
  """
  if isinstance(c, (tuple, list)):
    return c[1]  # dark mode index
  return c

def apply_dark_ttk_treeview_style(root):
  """
  Force ttk.Treeview styling to match CustomTkinter dark mode.
  Safe to call multiple times.
  """
  style = ttk.Style(master=root)

  try:
    style.theme_use("default")
  except Exception:
    pass

  bg     = _ctk_color(ctk.ThemeManager.theme["CTkFrame"]["fg_color"])
  bg_alt = _ctk_color(ctk.ThemeManager.theme["CTkFrame"]["top_fg_color"])
  fg     = _ctk_color(ctk.ThemeManager.theme["CTkLabel"]["text_color"])
  sel_bg = _ctk_color(ctk.ThemeManager.theme["CTkButton"]["hover_color"])
  sel_fg = fg

  style.configure(
    "Treeview",
    background=bg,
    fieldbackground=bg,
    foreground=fg,
    rowheight=28,
    borderwidth=0,
    relief="flat",
    font=_ttk_font(12),
  )

  style.map(
    "Treeview",
    background=[("selected", sel_bg)],
    foreground=[("selected", sel_fg)],
  )

  style.configure(
    "Treeview.Heading",
    background=bg_alt,
    foreground=fg,
    relief="flat",
    borderwidth=0,
    font=_ttk_font(13, weight="bold"),
  )

  style.map(
    "Treeview.Heading",
    background=[("active", bg_alt)],
    foreground=[("active", fg)],
  )

def apply_dark_ttk_scrollbar_style(root):
  """
  Dark-mode ttk.Scrollbar styling to match CustomTkinter theme.

  Styles:
    - Dark.Vertical.TScrollbar
    - Dark.Horizontal.TScrollbar
  """
  style = ttk.Style(master=root)

  try:
    style.theme_use("default")
  except Exception:
    pass

  bg       = _ctk_color(ctk.ThemeManager.theme["CTkFrame"]["fg_color"])
  accent   = _ctk_color(ctk.ThemeManager.theme["CTkButton"]["fg_color"])
  accent_h = _ctk_color(ctk.ThemeManager.theme["CTkButton"]["hover_color"])

  def _configure_scrollbar_style(style_name: str) -> None:
    style.configure(
      style_name,
      background=accent,        # thumb
      troughcolor=bg,           # track
      bordercolor=bg,
      lightcolor=accent,
      darkcolor=accent,
      arrowcolor="#9aa4af",
      relief="flat",
      borderwidth=0,
      arrowsize=18,
      width=16,
    )

    style.map(
      style_name,
      background=[
        ("active", accent_h),
        ("!active", accent),
      ],
      arrowcolor=[
        ("active", "#9aa4af"),
        ("pressed", "#9aa4af"),
        ("!active", "#9aa4af"),
        ("disabled", "#666666"),
      ],
    )

  _configure_scrollbar_style("Dark.Vertical.TScrollbar")
  _configure_scrollbar_style("Dark.Horizontal.TScrollbar")


# =============================================================================
# [🧾 Constants]
# =============================================================================

TX_PURCHASE = "PURCHASE"
TX_SALE = "SALE"

SCRIPT_ROOT_DIR = os.path.dirname(os.path.abspath(__file__))

APP_ICON_ICO_PATH = os.path.join(SCRIPT_ROOT_DIR, "icon.ico")
APP_ICON_PNG_PATH = os.path.join(SCRIPT_ROOT_DIR, "icon.png")

APP_CONFIG_FILENAME = "config.json"
APP_CONFIG_PATH = os.path.join(SCRIPT_ROOT_DIR, APP_CONFIG_FILENAME)

PROJECT_DATA_FILENAME = "inventory_data.json"


# =============================================================================
# [🧰 Logging] cure-log-ish minimal console logger
# =============================================================================

class Log:
  ANSI = {
    "reset": "\x1b[0m",
    "red": "\x1b[31m",
    "green": "\x1b[32m",
    "yellow": "\x1b[33m",
    "cyan": "\x1b[36m",
  }

  @staticmethod
  def _ts() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

  @staticmethod
  def info(tag: str, msg: str, data: Optional[Dict[str, Any]] = None) -> None:
    Log._print("ℹ️", Log.ANSI["cyan"], tag, msg, data)

  @staticmethod
  def warn(tag: str, msg: str, data: Optional[Dict[str, Any]] = None) -> None:
    Log._print("⚠️", Log.ANSI["yellow"], tag, msg, data)

  @staticmethod
  def error(tag: str, msg: str, data: Optional[Dict[str, Any]] = None) -> None:
    Log._print("🛑", Log.ANSI["red"], tag, msg, data)

  @staticmethod
  def ok(tag: str, msg: str, data: Optional[Dict[str, Any]] = None) -> None:
    Log._print("✅", Log.ANSI["green"], tag, msg, data)

  @staticmethod
  def _print(icon: str, color: str, tag: str, msg: str, data: Optional[Dict[str, Any]]) -> None:
    base = f"[{Log._ts()}] {icon} {tag} {msg}"
    if data:
      base += f" {data}"
    print(f"{color}{base}{Log.ANSI['reset']}")


# =============================================================================
# [🧾 Data Model]
# =============================================================================

@dataclass
class Transaction:
  id: int
  date: str
  sku: str
  type: str
  qty: int
  purchase_unit_cost: float = 0.0
  sale_unit_price: float = 0.0
  note: str = ""
  created_order: int = 0


# =============================================================================
# [🧮 Inventory Engine]
# =============================================================================

class InventoryEngine:
  def compute(self, transactions: List[Transaction]) -> Tuple[List[Dict[str, Any]], Dict[str, Dict[str, Any]]]:
    txs = sorted(transactions, key=lambda t: (t.date, t.created_order, t.id))

    state: Dict[str, Dict[str, Any]] = {}
    computed_rows: List[Dict[str, Any]] = []

    for t in txs:
      sku = t.sku.strip()
      if sku not in state:
        state[sku] = {
          "onhand_qty": 0,
          "onhand_cost": 0.0,
          "avg_cost": 0.0,
          "last_tx_date": "",
          "last_sale_price": 0.0,
          "last_sale_date": "",
        }

      s = state[sku]
      prev_avg = float(s["avg_cost"])
      prev_qty = int(s["onhand_qty"])
      prev_cost = float(s["onhand_cost"])

      purchase_total_cost = 0.0
      cogs = 0.0
      sales_rev = 0.0
      gross_profit = 0.0

      if t.type == TX_PURCHASE:
        purchase_total_cost = float(t.qty) * float(t.purchase_unit_cost)
        s["onhand_qty"] = prev_qty + int(t.qty)
        s["onhand_cost"] = prev_cost + purchase_total_cost

      elif t.type == TX_SALE:
        cogs = float(t.qty) * prev_avg
        sales_rev = float(t.qty) * float(t.sale_unit_price)
        gross_profit = sales_rev - cogs

        s["onhand_qty"] = prev_qty - int(t.qty)
        s["onhand_cost"] = prev_cost - cogs

        s["last_sale_price"] = float(t.sale_unit_price)
        s["last_sale_date"] = t.date

      else:
        raise ValueError(f"Unknown type: {t.type}")

      if s["onhand_qty"] == 0:
        s["avg_cost"] = 0.0
        s["onhand_cost"] = 0.0
      else:
        s["avg_cost"] = float(s["onhand_cost"]) / float(s["onhand_qty"])

      s["last_tx_date"] = t.date

      computed_rows.append({
        "id": t.id,
        "date": t.date,
        "sku": sku,
        "type": t.type,
        "qty": t.qty,
        "purchase_unit_cost": float(t.purchase_unit_cost),
        "sale_unit_price": float(t.sale_unit_price),
        "purchase_total_cost": purchase_total_cost,
        "prev_avg_cost": prev_avg,
        "onhand_qty": int(s["onhand_qty"]),
        "avg_cost_after": float(s["avg_cost"]),
        "cogs": cogs,
        "onhand_cost": float(s["onhand_cost"]),
        "sales_rev": sales_rev,
        "gross_profit": gross_profit,
        "note": t.note,
      })

    overview: Dict[str, Dict[str, Any]] = {}
    for sku, s in state.items():
      qty = int(s["onhand_qty"])
      status = "IN STOCK"
      if qty < 0:
        status = "NEGATIVE (OVERSOLD)"
      elif qty == 0:
        status = "OUT"

      overview[sku] = {
        "sku": sku,
        "onhand_qty": qty,
        "avg_cost": float(s["avg_cost"]),
        "onhand_cost": float(s["onhand_cost"]),
        "last_tx_date": s["last_tx_date"],
        "last_sale_price": float(s["last_sale_price"]) if s["last_sale_date"] else 0.0,
        "status": status,
      }

    return computed_rows, overview


# =============================================================================
# [💾 JSON Helpers] (app config + project data)
# =============================================================================

def _read_json(path: str) -> dict:
  try:
    if not os.path.isfile(path):
      return {}
    with open(path, "r", encoding="utf-8") as f:
      data = json.load(f)
    return data if isinstance(data, dict) else {}
  except Exception:
    return {}

def _write_json_atomic(path: str, data: dict) -> None:
  try:
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
      json.dump(data, f, indent=2)
    os.replace(tmp, path)
  except Exception:
    return

def _norm_dir(p: str) -> str:
  return os.path.normpath(os.path.abspath(p))

def _dedupe_keep_order(items: List[str]) -> List[str]:
  seen = set()
  out: List[str] = []
  for x in items:
    if x in seen:
      continue
    seen.add(x)
    out.append(x)
  return out

def _filter_existing_dirs(items: List[str]) -> List[str]:
  out: List[str] = []
  for p in items:
    try:
      if os.path.isdir(p):
        out.append(p)
    except Exception:
      pass
  return out


# =============================================================================
# [🧠 Helpers]
# =============================================================================

def parse_date(raw: str) -> str:
  s = (raw or "").strip()
  if not s:
    raise ValueError("Date is required")

  if re.fullmatch(r"\d{4}-\d{2}-\d{2}", s):
    datetime.strptime(s, "%Y-%m-%d")
    return s

  if re.fullmatch(r"\d{1,2}/\d{1,2}/\d{4}", s):
    dt = datetime.strptime(s, "%m/%d/%Y")
    return dt.strftime("%Y-%m-%d")

  raise ValueError("Date must be YYYY-MM-DD or M/D/YYYY")

def money(x: float) -> str:
  return f"${x:,.2f}"


# =============================================================================
# [🖥️ UI App]
# =============================================================================

class InventoryApp(ctk.CTk):
  def __init__(self) -> None:
    super().__init__()

    set_window_icon(self, APP_ICON_ICO_PATH, APP_ICON_PNG_PATH)

    self.LOG_TAG = "[🧮 Inventory]"
    self.title("Inventory Transaction Manager (Weighted Avg Cost)")

    self.geometry("1480x820")
    ctk.set_appearance_mode("Dark")
    ctk.set_default_color_theme("dark-blue")

    # Apply ttk theming (Treeview + Scrollbar) to match CTk dark mode
    apply_dark_ttk_treeview_style(self)
    apply_dark_ttk_scrollbar_style(self)

    self.engine = InventoryEngine()

    # Project selection state
    self.project_dir: str = ""
    self.project_data_path: str = ""

    # Recent projects (stored beside this script)
    app_cfg = _read_json(APP_CONFIG_PATH)
    self.recent_project_dirs_max = int(app_cfg.get("recent_project_dirs_max", 10) or 10)
    if self.recent_project_dirs_max <= 0:
      self.recent_project_dirs_max = 10

    raw = app_cfg.get("recent_project_dirs", [])
    if not isinstance(raw, list):
      raw = []
    self.recent_project_dirs: List[str] = []
    for p in raw:
      if isinstance(p, str) and p.strip():
        self.recent_project_dirs.append(_norm_dir(p.strip()))
    self.recent_project_dirs = _dedupe_keep_order(self.recent_project_dirs)
    self.recent_project_dirs = _filter_existing_dirs(self.recent_project_dirs)
    self.recent_project_dirs = self.recent_project_dirs[: self.recent_project_dirs_max]
    self._persist_app_config()

    # Data
    self.transactions: List[Transaction] = []
    self.next_id = 1
    self.next_created_order = 1

    # Aliases
    # Stored as list of dicts: [{"sku": "...", "name": "..."}, ...]
    self.aliases_list: List[Dict[str, str]] = []
    self._alias_map: Dict[str, str] = {}  # normalized lookup (sku -> name)

    # Guard flags for SKU/Alias UI syncing
    self._alias_sync_guard = False

    self._build_ui()

    # Auto-load first recent project if available
    if self.recent_project_dirs:
      self.project_dir_var.set(self.recent_project_dirs[0])
      self._load_project_dir(self.recent_project_dirs[0])
    else:
      self._refresh_all()
      self._refresh_aliases_ui()
      self._set_tx_controls_enabled(False)

    Log.ok(self.LOG_TAG, "Ready.", {"recent_projects": len(self.recent_project_dirs)})

  # -----------------------------------------------------------------------------
  # App config persistence (recent projects)
  # -----------------------------------------------------------------------------

  def _persist_app_config(self) -> None:
    _write_json_atomic(APP_CONFIG_PATH, {
      "recent_project_dirs_max": int(self.recent_project_dirs_max),
      "recent_project_dirs": list(self.recent_project_dirs),
    })

  def _refresh_project_dropdown(self) -> None:
    self.project_combo.configure(values=list(self.recent_project_dirs))

  def _remember_project_dir(self, p: str) -> None:
    if not p:
      return
    p_norm = _norm_dir(p)
    if not os.path.isdir(p_norm):
      return

    items = [p_norm] + [x for x in self.recent_project_dirs if x != p_norm]
    items = _dedupe_keep_order(items)
    items = _filter_existing_dirs(items)
    items = items[: self.recent_project_dirs_max]
    self.recent_project_dirs = items

    self._persist_app_config()
    self._refresh_project_dropdown()

  def _clear_project_history(self) -> None:
    self.recent_project_dirs = []
    self._persist_app_config()
    self._refresh_project_dropdown()

  # -----------------------------------------------------------------------------
  # Project data IO
  # -----------------------------------------------------------------------------

  def _project_data_file_for_dir(self, project_dir: str) -> str:
    return os.path.join(os.path.abspath(project_dir), PROJECT_DATA_FILENAME)

  def _rebuild_alias_map(self) -> None:
    """
    Rebuild the fast lookup map (sku -> alias name) from self.aliases_list.
    """
    m: Dict[str, str] = {}
    for item in (self.aliases_list or []):
      if not isinstance(item, dict):
        continue
      sku = str(item.get("sku") or "").strip()
      name = str(item.get("name") or "").strip()
      if not sku or not name:
        continue
      m[sku] = name
    self._alias_map = m

  def _get_alias_for_sku(self, sku: str) -> str:
    s = (sku or "").strip()
    if not s:
      return ""
    return str(self._alias_map.get(s) or "").strip()

  def _load_project_data_from_file(self, path: str) -> Tuple[List[Transaction], List[Dict[str, str]]]:
    if not os.path.exists(path):
      return [], []
    with open(path, "r", encoding="utf-8") as f:
      raw = json.load(f)

    txs: List[Transaction] = []
    for item in raw.get("transactions", []):
      txs.append(Transaction(**item))

    aliases: List[Dict[str, str]] = []
    raw_aliases = raw.get("aliases", [])
    if isinstance(raw_aliases, dict):
      # Legacy-ish fallback: {"SKU":"Name", ...}
      for k, v in raw_aliases.items():
        sku = str(k or "").strip()
        name = str(v or "").strip()
        if sku and name:
          aliases.append({"sku": sku, "name": name})
    elif isinstance(raw_aliases, list):
      for a in raw_aliases:
        if not isinstance(a, dict):
          continue
        sku = str(a.get("sku") or "").strip()
        name = str(a.get("name") or "").strip()
        if sku and name:
          aliases.append({"sku": sku, "name": name})

    # Stable sort for UI
    aliases.sort(key=lambda x: (str(x.get("name", "")).lower(), str(x.get("sku", "")).lower()))

    return txs, aliases

  def _save_project_data_to_file(self, path: str, txs: List[Transaction], aliases: List[Dict[str, str]]) -> None:
    payload = {
      "transactions": [asdict(t) for t in txs],
      "aliases": list(aliases or []),
    }
    _write_json_atomic(path, payload)

  def _load_project_dir(self, project_dir: str) -> None:
    p = os.path.abspath(project_dir)
    if not os.path.isdir(p):
      messagebox.showerror("Project", "Project directory is missing or invalid.")
      return

    self.project_dir = p
    self.project_data_path = self._project_data_file_for_dir(p)

    txs, aliases = self._load_project_data_from_file(self.project_data_path)

    self.transactions = txs
    self._normalize_sort()

    self.aliases_list = aliases
    self._rebuild_alias_map()

    self.next_id = (max([t.id for t in self.transactions], default=0) + 1)
    self.next_created_order = (max([t.created_order for t in self.transactions], default=0) + 1)

    self._remember_project_dir(p)
    self._set_tx_controls_enabled(True)

    self._refresh_aliases_ui()
    self._refresh_all()

    Log.ok(self.LOG_TAG, "Loaded project.", {"project_dir": p, "tx_count": len(self.transactions), "alias_count": len(self.aliases_list)})

  def _save_and_refresh(self) -> None:
    if not self.project_data_path:
      messagebox.showerror("Project", "Select a Project Directory first.")
      return
    self._normalize_sort()
    self._save_project_data_to_file(self.project_data_path, self.transactions, self.aliases_list)
    self._refresh_aliases_ui()
    self._refresh_all()

  # -----------------------------------------------------------------------------
  # UI Construction
  # -----------------------------------------------------------------------------

  # =============================================================================
  # Tooltips
  # =============================================================================


  def _install_tab_button_tooltips(self) -> None:
    """Attach tooltips to CTkTabview tab buttons (segmented button)."""
    try:
      tabview = getattr(self, "tabs", None)
      if tabview is None:
        return

      seg = getattr(tabview, "_segmented_button", None)
      if seg is None:
        return

      btn_map = None
      for attr in ("_buttons_dict", "_buttons", "buttons"):
        v = getattr(seg, attr, None)
        if isinstance(v, dict):
          btn_map = v
          break

      if not isinstance(btn_map, dict):
        return

      tip_by_tab = {
        "Transactions": "Transactions: add/update/delete purchases & sales. This drives costing and the overview.",
        "Overview": "Overview: current inventory state (on-hand qty, WAC, totals) and optional summaries.",
        "Aliases": "Aliases: map friendly names to SKUs. Used in dropdowns and tables.",
      }

      for tab_name, tip in tip_by_tab.items():
        btn = btn_map.get(tab_name)
        if btn is not None:
          tooltip(btn, text=tip)
    except Exception:
      pass


  def _install_tooltips_explicit(self) -> None:
    """Attach curated tooltips to key UI widgets we store on `self`.

    Also ensures labels get the same tooltip as their associated value widgets.
    """
    def _attach(w: Any, msg: str) -> None:
      if w is None:
        return
      try:
        tooltip(w, text=msg)
      except Exception:
        pass

      # If this widget has an associated label, apply the SAME tooltip to the label too.
      try:
        lbl = self._tooltip_associated_label_widget(w)
        if lbl is not None:
          tooltip(lbl, text=msg)
      except Exception:
        pass

    try:
      _attach(self.tabs, "Tabs: switch between Transactions, Overview, and Aliases.")
    except Exception:
      pass

    try:
      self._install_tab_button_tooltips()
    except Exception:
      pass

    # Project bar (label + combo + buttons)
    _attach(getattr(self, "project_combo", None),
            "Project Directory: choose or type a project folder. Data saves to <ProjectDir>/inventory_data.json.")

    _attach(getattr(self, "btn_browse_project", None),
            "Browse: pick a project folder. Data file is created/used at <ProjectDir>/inventory_data.json.")

    _attach(getattr(self, "btn_load_project", None),
            "Load/Refresh: load the selected project folder and refresh all tables from <ProjectDir>/inventory_data.json.")

    _attach(getattr(self, "btn_clear_history", None),
            "Clear History: remove recent project folders from the dropdown (does NOT delete any project data files).")

    # Transactions form (labels will inherit via _attach)
    for w, msg in [
      (getattr(self, "entry_date", None), "Date: transaction date (YYYY-MM-DD or M/D/YYYY)."),
      (getattr(self, "btn_date_pick", None), "Pick Date: open a calendar selector to set the Date field."),
      (getattr(self, "entry_sku", None), "SKU: item identifier used for costing/aggregation."),

      (getattr(self, "lbl_tx_alias", None), "Alias: type to filter by alias name OR SKU; selecting an alias sets the SKU field."),
      (getattr(self, "entry_alias", None), "Alias: type to filter by alias name OR SKU; selecting an alias sets the SKU field."),
      (getattr(self, "btn_alias_drop", None), "Alias dropdown: show all aliases; typing filters by alias name OR SKU."),

      (getattr(self, "opt_type", None), "Type: Purchase increases inventory; Sale reduces inventory."),
      (getattr(self, "entry_qty", None), "Qty: number of units bought/sold."),
      (getattr(self, "entry_unit_price", None), "Unit Price: purchase cost per unit (for Purchase) or sale price per unit (for Sale)."),
      (getattr(self, "entry_note", None), "Note: optional text for receipts, customer, order, etc."),
      (getattr(self, "btn_add", None), "Add: append a new transaction row."),
      (getattr(self, "btn_update", None), "Update Selected: edit the selected transaction row. Enabled only when exactly one row is selected."),

      (getattr(self, "btn_delete", None), "Delete: remove the selected transaction row."),
      (getattr(self, "btn_export", None), "Export: write transactions to a CSV file for sharing/backup."),
      (getattr(self, "tx_tree", None), "Transactions table: hover cells for exact values; click rows to select."),
    ]:
      _attach(w, msg)

    # Overview tab
    for w, msg in [
      (getattr(self, "opt_ov_view", None), "Overview mode: choose summary view/grouping."),
      (getattr(self, "ov_tree", None), "Overview table: current on-hand, WAC, and totals per SKU/alias."),
      (getattr(self, "btn_ov_export", None), "Export Overview: save the current overview table."),
    ]:
      _attach(w, msg)

    # Aliases tab
    for w, msg in [
      (getattr(self, "entry_alias_name", None), "Alias Name: friendly display name (e.g., 'NES Controller')."),
      (getattr(self, "entry_alias_sku", None), "Alias SKU: the SKU value this alias maps to."),
      (getattr(self, "btn_alias_add", None), "Add Alias: create a new alias mapping."),
      (getattr(self, "btn_alias_update", None), "Update Selected: edit the selected alias mapping. Enabled only when exactly one row is selected."),

      (getattr(self, "btn_alias_delete", None), "Delete Alias: remove the selected alias mapping."),
      (getattr(self, "alias_tree", None), "Aliases table: select an alias to edit or delete."),
    ]:
      _attach(w, msg)


  def _tooltip_associated_label_widget(self, w: Any) -> Any:
    """Find the likely label widget associated with a widget by examining grid siblings.

    This targets the common pattern:
      Label @ (row=r, col=0) + Widget @ (row=r, col=1)

    Returns:
      The label widget if found; otherwise None.
    """
    try:
      info = w.grid_info() or {}
    except Exception:
      return None

    try:
      row = int(info.get("row"))
      col = int(info.get("column"))
    except Exception:
      return None

    parent = getattr(w, "master", None)
    if parent is None:
      return None

    candidate_cols = [max(col - 1, 0), 0]

    try:
      siblings = parent.winfo_children()
    except Exception:
      return None

    for ccol in candidate_cols:
      for sib in siblings:
        if sib is w:
          continue
        try:
          sinfo = sib.grid_info() or {}
          srow = int(sinfo.get("row"))
          scol = int(sinfo.get("column"))
        except Exception:
          continue
        if srow != row or scol != ccol:
          continue

        try:
          cls = sib.__class__.__name__
        except Exception:
          cls = ""
        if "Label" not in cls:
          continue

        try:
          t = str(sib.cget("text") or "").strip()
        except Exception:
          t = ""
        if t:
          return sib

    return None


  def _tooltip_associated_label_text(self, w: Any) -> str:
    """Try to infer a label text for a widget by examining its grid siblings."""
    lbl = self._tooltip_associated_label_widget(w)
    if lbl is None:
      return ""
    try:
      return str(lbl.cget("text") or "").strip()
    except Exception:
      return ""


  def _tooltip_text_for_widget(self, w: Any) -> str:
    """Infer a human-friendly tooltip string for a widget.

    Rules:
    - Only attach tooltips to interactive or informative widgets.
    - NEVER attach tooltips to container widgets (frames), or fall back to class names.
    - Labels do not get auto-tooltips; they inherit tooltips from their paired value widgets.
    """
    if w is None:
      return ""

    try:
      cls = w.__class__.__name__
    except Exception:
      cls = ""

    # -------------------------------------------------------------------------
    # Skip non-interactive containers / structural widgets
    # -------------------------------------------------------------------------
    # NOTE: This prevents "CTkFrame" and similar nonsense tooltips.
    skip_class_fragments = (
      "Frame",
      "Canvas",
      "Separator",
      "Scrollbar",
      "Toplevel",
    )
    if any(frag in cls for frag in skip_class_fragments):
      return ""

    # Labels: only get tooltips when mirrored from their value widgets.
    if "Label" in cls:
      return ""

    # -------------------------------------------------------------------------
    # Explicit widget text (buttons, tab buttons, etc.)
    # -------------------------------------------------------------------------
    for key in ("text", "placeholder_text"):
      try:
        t = str(w.cget(key) or "").strip()
      except Exception:
        t = ""
      if t:
        return t

    # -------------------------------------------------------------------------
    # Special-case: ttk.Treeview
    # -------------------------------------------------------------------------
    try:
      import tkinter.ttk as _ttk  # local import to avoid global cycles
      if isinstance(w, _ttk.Treeview):
        return "Table: hover headers for help; hover cells for exact values."
    except Exception:
      pass

    # -------------------------------------------------------------------------
    # Infer from sibling label (entries, comboboxes, option menus, etc.)
    # -------------------------------------------------------------------------
    label = self._tooltip_associated_label_text(w)
    if label:
      if "Entry" in cls:
        return f"Set {label}"
      if "ComboBox" in cls or "OptionMenu" in cls:
        return f"Select {label}"
      if "Slider" in cls:
        return f"Adjust {label}"
      if "Switch" in cls or "CheckBox" in cls or "RadioButton" in cls:
        return f"Toggle {label}"
      return label

    # No fallback. If we can’t infer something useful, skip tooltip entirely.
    return ""


  def _install_tooltips_recursive(self, root: Any) -> None:
    """Attach tooltips to every widget in the subtree rooted at `root`.

    Notes:
    - Best-effort and never throws.
    - Tooltips are only attached once per widget (`_cure_tooltip` guard).
    - IMPORTANT: never attach a tooltip to the app root window (`self`) because CTkToolTip can
      surface that tooltip while hovering child widgets (shows as "InventoryApp" over everything).
    """
    if CTkToolTip is None:
      return

    stack = [root]
    while stack:
      w = stack.pop()

      # Never tooltip the app/root window.
      if w is self:
        # If an old root tooltip exists (from a previous run), remove it.
        old = getattr(w, "_cure_tooltip", None)
        if old is not None:
          try:
            if hasattr(old, "hide"):
              old.hide()
          except Exception:
            pass
          try:
            if hasattr(old, "destroy"):
              old.destroy()
          except Exception:
            pass
          try:
            w._cure_tooltip = None  # type: ignore[attr-defined]
          except Exception:
            pass

        # Still recurse into children.
        try:
          stack.extend(list(w.winfo_children()))
        except Exception:
          pass
        continue

      # Skip if we've already attached a tooltip here.
      if getattr(w, "_cure_tooltip", None) is None:
        try:
          msg = self._tooltip_text_for_widget(w)
          if msg:
            tooltip(w, text=msg)

            # Mirror value widget tooltip to its label (labels do not get auto-tooltips)
            try:
              cls = w.__class__.__name__
            except Exception:
              cls = ""

            if any(k in cls for k in ("Entry", "ComboBox", "OptionMenu", "Slider", "Switch", "CheckBox", "RadioButton")):
              lbl = self._tooltip_associated_label_widget(w)
              if lbl is not None:
                tooltip(lbl, text=msg)
        except Exception:
          pass

      try:
        stack.extend(list(w.winfo_children()))
      except Exception:
        pass


  def _build_ui(self) -> None:

    self.grid_rowconfigure(1, weight=1)
    self.grid_columnconfigure(0, weight=1)

    # Top project bar (like your attached script)
    project_bar = ctk.CTkFrame(self)
    project_bar.grid(row=0, column=0, sticky="ew", padx=14, pady=(14, 8))
    project_bar.grid_columnconfigure(1, weight=1)

    self.lbl_project_dir = ctk.CTkLabel(project_bar, text="Project Directory:")
    self.lbl_project_dir.grid(row=0, column=0, padx=(10, 6), pady=10, sticky="w")

    self.project_dir_var = tk.StringVar(value=(self.recent_project_dirs[0] if self.recent_project_dirs else ""))
    self.project_combo = ctk.CTkComboBox(
      project_bar,
      variable=self.project_dir_var,
      values=list(self.recent_project_dirs),
      state="normal",
      command=lambda _choice: self._on_project_combo_selected(),
    )
    self.project_combo.grid(row=0, column=1, padx=6, pady=10, sticky="ew")

    self.btn_browse_project = ctk.CTkButton(project_bar, text="Browse…", width=110, command=self._on_browse_project)
    self.btn_browse_project.grid(row=0, column=2, padx=6, pady=10)

    self.btn_load_project = ctk.CTkButton(project_bar, text="Load/Refresh", width=130, command=self._on_load_project)
    self.btn_load_project.grid(row=0, column=3, padx=6, pady=10)

    self.btn_clear_history = ctk.CTkButton(project_bar, text="Clear History", width=120, command=self._on_clear_history)
    self.btn_clear_history.grid(row=0, column=4, padx=(6, 10), pady=10)

    # Tabs
    self.tabs = ctk.CTkTabview(self)
    self.tabs.grid(row=1, column=0, sticky="nsew", padx=14, pady=(0, 14))

    self.tab_tx = self.tabs.add("Transactions")
    self.tab_ov = self.tabs.add("Overview")
    self.tab_alias = self.tabs.add("Aliases")

    self._build_transactions_tab()
    self._build_overview_tab()
    self._build_aliases_tab()
    # Tooltips (best-effort): attach curated tips first, then fill in the rest.
    self._install_tooltips_explicit()
    # IMPORTANT: Do NOT recurse from the app root; it creates a root-level tooltip ("InventoryApp")
    # that can appear over child widgets. Recurse from the tab container instead.
    self._install_tooltips_recursive(self.tabs)

  def _build_transactions_tab(self) -> None:
    # Row 0: inputs. Row 1: note + action buttons. Row 2: table.
    self.tab_tx.grid_rowconfigure(0, weight=0)
    self.tab_tx.grid_rowconfigure(1, weight=0)
    self.tab_tx.grid_rowconfigure(2, weight=1)
    self.tab_tx.grid_columnconfigure(0, weight=1)

    # Split into two independent grids so the dynamic unit label never reflows the buttons.
    form_row = ctk.CTkFrame(self.tab_tx)
    form_row.grid(row=0, column=0, sticky="ew", padx=10, pady=(10, 4))

    action_row = ctk.CTkFrame(self.tab_tx)
    action_row.grid(row=1, column=0, sticky="ew", padx=10, pady=(0, 6))
    action_row.grid_columnconfigure(1, weight=1)

    self.var_date = tk.StringVar(value=datetime.now().strftime("%Y-%m-%d"))
    self.var_sku = tk.StringVar(value="")
    self.var_type = tk.StringVar(value=TX_PURCHASE)
    self.var_qty = tk.StringVar(value="1")
    self.var_purchase_unit = tk.StringVar(value="1.00")
    self.var_sale_unit = tk.StringVar(value="3.00")

    # Alias chooser (display-only selection; selecting sets SKU)
    self.var_alias_choice = tk.StringVar(value="")

    # Single "unit" field that swaps meaning based on Type.
    self.var_unit_price = tk.StringVar(value=self.var_purchase_unit.get())
    self._last_type_for_unit = self.var_type.get()

    self.var_note = tk.StringVar(value="")

    # Keep Alias dropdown synced when SKU typed
    try:
      self.var_sku.trace_add("write", lambda *_: self._sync_alias_choice_from_sku())
    except Exception:
      pass

    ctk.CTkLabel(form_row, text="Date").grid(row=0, column=0, padx=(10, 6), pady=10)

    # Date picker (entry + calendar button)
    self.date_picker = ctk.CTkFrame(form_row, fg_color="transparent")
    self.date_picker.grid(row=0, column=1, padx=6, pady=10, sticky="w")

    self.entry_date = ctk.CTkEntry(self.date_picker, textvariable=self.var_date, width=120)
    self.entry_date.grid(row=0, column=0)
    apply_entry_shortcuts(self.entry_date)

    self.btn_date_pick = ctk.CTkButton(self.date_picker, text="📅", width=32, command=self._on_pick_date)
    self.btn_date_pick.grid(row=0, column=1, padx=(6, 0))

    # -------------------------------------------------------------------------
    # In-window Date dropdown (themed overlay; no separate popup window)
    # -------------------------------------------------------------------------

    # Overlay dropdown (parent is Transactions tab so it can overlay tab contents)
    self._date_dropdown = ctk.CTkFrame(self.tab_tx, corner_radius=10, border_width=1)
    self._date_dropdown.place_forget()
    self._date_dropdown_visible = False

    # Theme colors (match CTk dark mode)
    _date_bg       = _ctk_color(ctk.ThemeManager.theme["CTkFrame"]["fg_color"])
    _date_bg_alt   = _ctk_color(ctk.ThemeManager.theme["CTkFrame"]["top_fg_color"])
    _date_fg       = _ctk_color(ctk.ThemeManager.theme["CTkLabel"]["text_color"])
    _date_accent   = _ctk_color(ctk.ThemeManager.theme["CTkButton"]["fg_color"])
    _date_accent_h = _ctk_color(ctk.ThemeManager.theme["CTkButton"]["hover_color"])

    # Calendar is a Tk widget; we host it inside a Tk frame so bg matches cleanly.
    self._date_cal_host = tk.Frame(self._date_dropdown, bg=_date_bg)
    self._date_cal_host.grid(row=0, column=0, sticky="nsew", padx=10, pady=(10, 6))

    # Buttons row (CTk)
    self._date_btn_row = ctk.CTkFrame(self._date_dropdown, fg_color="transparent")
    self._date_btn_row.grid(row=1, column=0, sticky="ew", padx=10, pady=(0, 10))
    self._date_btn_row.grid_columnconfigure(0, weight=1)
    self._date_btn_row.grid_columnconfigure(1, weight=1)
    self._date_btn_row.grid_columnconfigure(2, weight=1)

    self._date_btn_today  = ctk.CTkButton(self._date_btn_row, text="Today",  width=90)
    self._date_btn_ok     = ctk.CTkButton(self._date_btn_row, text="OK",     width=90)
    self._date_btn_cancel = ctk.CTkButton(self._date_btn_row, text="Cancel", width=90)

    self._date_btn_today.grid(row=0, column=0, padx=(0, 8), sticky="ew")
    self._date_btn_ok.grid(row=0, column=1, padx=8, sticky="ew")
    self._date_btn_cancel.grid(row=0, column=2, padx=(8, 0), sticky="ew")

    # We create/destroy Calendar instance as needed (tkcalendar can be optional).
    self._date_cal = None

    _date_state = {"after_id": None}

    def _date_is_descendant(widget: Any, parent: Any) -> bool:
      try:
        w = widget
        while w is not None:
          if w == parent:
            return True
          w = getattr(w, "master", None)
      except Exception:
        pass
      return False

    def _date_dropdown_hide() -> None:
      if not getattr(self, "_date_dropdown_visible", False):
        return
      try:
        self._date_dropdown.place_forget()
      except Exception:
        pass
      self._date_dropdown_visible = False

    def _date_dropdown_place_near_entry(*, prefer_below: bool = True) -> None:
      """
      Place dropdown near the date picker, clamped inside the Transactions tab.
      Tries below first; if not enough space, flips above.
      """
      try:
        self.update_idletasks()

        # Entry screen coords
        ex = int(self.entry_date.winfo_rootx())
        ey = int(self.entry_date.winfo_rooty())
        eh = int(self.entry_date.winfo_height())

        # Tab screen coords
        tx = int(self.tab_tx.winfo_rootx())
        ty = int(self.tab_tx.winfo_rooty())
        tw = int(self.tab_tx.winfo_width() or 0)
        th = int(self.tab_tx.winfo_height() or 0)

        # Convert to coords relative to tab
        x = ex - tx
        y_below = (ey - ty) + eh
        y_above = (ey - ty)

        # Width matches the picker (entry+button)
        w_drop = int(self.date_picker.winfo_width() or 0)
        if w_drop <= 10:
          w_drop = 320

        try:
          self._date_dropdown.configure(width=w_drop)
        except Exception:
          pass

        # Measure content height
        self._date_dropdown.update_idletasks()
        try:
          content_h = int(self._date_dropdown.winfo_reqheight() or 280)
        except Exception:
          content_h = 280

        # Available space
        below_space = max(th - y_below - 6, 0)
        above_space = max(y_above - 6, 0)

        use_below = prefer_below
        if use_below and below_space < content_h and above_space > below_space:
          use_below = False
        elif (not use_below) and above_space < content_h and below_space > above_space:
          use_below = True

        if use_below:
          y = max(0, y_below - 1)
        else:
          y = max(0, y_above - content_h - 1)

        # Clamp X inside tab
        if tw > 40:
          x = max(0, min(x, max(tw - w_drop - 6, 0)))

        self._date_dropdown.place(x=x, y=y)
        self._date_dropdown.lift()
        self._date_dropdown_visible = True
      except Exception:
        _date_dropdown_hide()

    def _date_calendar_rebuild(year: int, month: int, day: int) -> None:
      """
      (Re)create the tkcalendar Calendar inside the host, themed to CTk colors.
      """
      try:
        for child in self._date_cal_host.winfo_children():
          child.destroy()
      except Exception:
        pass

      from tkinter import font as tkfont

      # Match your table font sizes (Treeview uses 12/13 in apply_dark_ttk_treeview_style()).
      _cal_font = tkfont.nametofont("TkDefaultFont").copy()
      _cal_font.configure(size=13)

      _cal_headers_font = _cal_font.copy()
      _cal_headers_font.configure(size=14, weight="bold")

      self._date_cal = Calendar(
        self._date_cal_host,
        selectmode="day",
        year=int(year),
        month=int(month),
        day=int(day),
        date_pattern="yyyy-mm-dd",

        # ✅ Font sizing
        font=_cal_font,
        headersfont=_cal_headers_font,

        # Theme colors
        background=_date_bg,
        foreground=_date_fg,
        bordercolor=_date_bg,
        headersbackground=_date_bg_alt,
        headersforeground=_date_fg,
        selectbackground=_date_accent,
        selectforeground=_date_fg,
        normalbackground=_date_bg,
        normalforeground=_date_fg,
        weekendbackground=_date_bg,
        weekendforeground=_date_fg,
        othermonthbackground=_date_bg,
        othermonthforeground="#707070",
        othermonthwebackground=_date_bg,
        othermonthweforeground="#707070",
      )

      self._date_cal.pack(fill="both", expand=True)

    def _date_dropdown_show_from_current_entry() -> None:
      if Calendar is None:
        messagebox.showinfo(
          "Date Picker",
          "Calendar picker requires optional dependency:\n\n"
          "  pip install tkcalendar\n\n"
          "You can still type the date as YYYY-MM-DD or M/D/YYYY."
        )
        try:
          self.entry_date.focus_set()
        except Exception:
          pass
        return

      # Parse current date (best-effort)
      try:
        cur = parse_date(self.var_date.get())
        y = int(cur[0:4]); m = int(cur[5:7]); d = int(cur[8:10])
      except Exception:
        now = datetime.now()
        y, m, d = now.year, now.month, now.day

      _date_calendar_rebuild(y, m, d)
      _date_dropdown_place_near_entry(prefer_below=True)

    def _date_ok() -> None:
      picked = ""
      try:
        if self._date_cal is not None:
          picked = str(self._date_cal.get_date() or "").strip()
      except Exception:
        picked = ""

      if picked:
        try:
          self.var_date.set(parse_date(picked))
        except Exception:
          self.var_date.set(picked)

      _date_dropdown_hide()

      try:
        self.entry_date.focus_set()
        self.entry_date.icursor(tk.END)
      except Exception:
        pass

    def _date_today() -> None:
      try:
        if self._date_cal is not None:
          self._date_cal.selection_set(datetime.now().strftime("%Y-%m-%d"))
      except Exception:
        pass

    def _date_cancel() -> None:
      _date_dropdown_hide()
      try:
        self.entry_date.focus_set()
      except Exception:
        pass

    self._date_btn_today.configure(command=_date_today)
    self._date_btn_ok.configure(command=_date_ok)
    self._date_btn_cancel.configure(command=_date_cancel)

    def _date_toggle_dropdown() -> None:
      if getattr(self, "_date_dropdown_visible", False):
        _date_dropdown_hide()
      else:
        _date_dropdown_show_from_current_entry()

    # Store helpers for use elsewhere (like disable/enable)
    self._date_dropdown_hide = _date_dropdown_hide
    self._date_dropdown_toggle = _date_toggle_dropdown
    self._date_dropdown_show = _date_dropdown_show_from_current_entry

    # Esc closes date dropdown (when date entry focused)
    self.entry_date.bind("<Escape>", lambda _e: _date_dropdown_hide())

    # Clicking outside closes dropdown
    if not getattr(self, "_date_outside_click_bound", False):
      self._date_outside_click_bound = True

      def _on_any_click_close_date(e) -> None:
        try:
          w = e.widget

          # Inside date picker (entry + button) = keep open
          if _date_is_descendant(w, self.date_picker):
            return

          # Inside dropdown = keep open
          if _date_is_descendant(w, self._date_dropdown):
            return

          _date_dropdown_hide()
        except Exception:
          pass

      self.bind_all("<Button-1>", _on_any_click_close_date, add="+")

    ctk.CTkLabel(form_row, text="SKU").grid(row=0, column=2, padx=(14, 6), pady=10)
    self.entry_sku = ctk.CTkEntry(form_row, textvariable=self.var_sku, width=200)
    self.entry_sku.grid(row=0, column=3, padx=6, pady=10)
    apply_entry_shortcuts(self.entry_sku)

    self.lbl_tx_alias = ctk.CTkLabel(form_row, text="Alias")
    self.lbl_tx_alias.grid(row=0, column=4, padx=(14, 6), pady=10)

    # Alias picker (Entry + non-focus-stealing suggestion overlay)
    self.alias_picker = ctk.CTkFrame(form_row, fg_color="transparent")
    self.alias_picker.grid(row=0, column=5, padx=6, pady=10, sticky="w")
    self.alias_picker.grid_columnconfigure(0, weight=1)

    self.entry_alias = ctk.CTkEntry(self.alias_picker, textvariable=self.var_alias_choice, width=226)
    self.entry_alias.grid(row=0, column=0, sticky="ew")
    apply_entry_shortcuts(self.entry_alias)

    self.btn_alias_drop = ctk.CTkButton(self.alias_picker, text="▾", width=32)
    self.btn_alias_drop.grid(row=0, column=1, padx=(6, 0))

    # Cache of all alias display values (rebuilt by _refresh_alias_dropdown)
    self._alias_dropdown_values = [""] + self._build_alias_display_values()

    # Overlay dropdown (IMPORTANT: parent is the Transactions tab so it can overlay tab contents)
    self._alias_dropdown = ctk.CTkFrame(self.tab_tx, corner_radius=10, border_width=1)
    self._alias_dropdown.place_forget()
    self._alias_dropdown_visible = False

    # Height is set dynamically on each open/refresh based on available space + content size.
    self._alias_dropdown_scroll = ctk.CTkScrollableFrame(self._alias_dropdown, width=512, height=10)
    self._alias_dropdown_scroll.grid(row=0, column=0, sticky="nsew", padx=6, pady=6)

    # Runtime sizing cache
    self._alias_dropdown_content_px = 80

    _alias_filter_state = {"after_id": None}

    def _alias_is_descendant(widget: Any, parent: Any) -> bool:
      try:
        w = widget
        while w is not None:
          if w == parent:
            return True
          w = getattr(w, "master", None)
      except Exception:
        pass
      return False

    def _alias_dropdown_hide() -> None:
      if not getattr(self, "_alias_dropdown_visible", False):
        return
      try:
        self._alias_dropdown.place_forget()
      except Exception:
        pass
      self._alias_dropdown_visible = False

    def _alias_dropdown_place_below_entry() -> None:
      """
      Place dropdown directly under the alias entry, relative to the Transactions tab.
      This ensures the dropdown overlays tab contents (no "hidden under row" gap).
      """
      try:
        self.update_idletasks()

        # Screen coords (absolute)
        ex = int(self.entry_alias.winfo_rootx())
        ey = int(self.entry_alias.winfo_rooty())
        eh = int(self.entry_alias.winfo_height())

        # Convert to coords relative to the Transactions tab (self.tab_tx)
        tx = int(self.tab_tx.winfo_rootx())
        ty = int(self.tab_tx.winfo_rooty())

        x = ex - tx
        y = (ey - ty) + eh

        # Width matches the picker (entry + button)
        w_drop = int(self.alias_picker.winfo_width() or 0)
        if w_drop <= 10:
          w_drop = 512

        try:
          self._alias_dropdown.configure(width=w_drop)
        except Exception:
          pass

        # Tiny seam tweak (optional)
        y = max(0, y - 1)

        self._alias_dropdown.place(x=x, y=y)
        self._alias_dropdown.lift()  # now lifts above all tab content siblings
        self._alias_dropdown_visible = True
      except Exception:
        _alias_dropdown_hide()

    def _alias_dropdown_render(values: List[str]) -> None:
      try:
        for child in self._alias_dropdown_scroll.winfo_children():
          child.destroy()
      except Exception:
        pass

      shown = [v for v in values if v]  # ignore blank sentinel for UI
      if not shown:
        # Content wants to be small when empty.
        self._alias_dropdown_content_px = 64
        ctk.CTkLabel(self._alias_dropdown_scroll, text="No matches").grid(row=0, column=0, sticky="w", padx=8, pady=6)
        return

      # Limit rendered rows for performance; scroll holds the rest if needed later.
      MAX_ROWS = 80
      shown = shown[:MAX_ROWS]

      def _pick(val: str) -> None:
        try:
          self.var_alias_choice.set(val)
        except Exception:
          pass

        _alias_dropdown_hide()

        # Commit selection behavior (sets SKU) but DO NOT move focus away.
        self._on_alias_selected_in_tx_form()

        # Put caret back in alias entry (move cursor to end)
        def _focus_alias_end() -> None:
          try:
            self.entry_alias.focus_set()
          except Exception:
            return

          # Best-effort: CTkEntry sometimes wraps the underlying tk.Entry as `_entry`
          try:
            self.entry_alias.icursor(tk.END)
            try:
              self.entry_alias.xview_moveto(1.0)  # ensure end is visible
            except Exception:
              pass
            return
          except Exception:
            pass

          try:
            inner = getattr(self.entry_alias, "_entry", None)
            if inner is not None:
              inner.icursor(tk.END)
              try:
                inner.xview_moveto(1.0)
              except Exception:
                pass
          except Exception:
            pass

        try:
          self.after(1, _focus_alias_end)
        except Exception:
          _focus_alias_end()

      for i, v in enumerate(shown):
        btn = ctk.CTkButton(
          self._alias_dropdown_scroll,
          text=v,
          anchor="w",
          height=26,
          fg_color="transparent",
          hover=True,
          command=lambda vv=v: _pick(vv),
        )
        btn.grid(row=i, column=0, sticky="ew", padx=2, pady=1)

      try:
        self._alias_dropdown_scroll.grid_columnconfigure(0, weight=1)
      except Exception:
        pass

    def _alias_apply_filter(show_if_any: bool = True) -> None:
      raw_in = (self.var_alias_choice.get() or "")
      q = raw_in.strip()

      all_values = list(getattr(self, "_alias_dropdown_values", None) or ([""] + self._build_alias_display_values()))
      only = [v for v in all_values if v]

      def _norm(s: str) -> str:
        # Lower, remove most punctuation, collapse whitespace.
        s2 = re.sub(r"[^a-zA-Z0-9]+", " ", str(s or "").lower())
        return re.sub(r"\s+", " ", s2).strip()

      qn = _norm(q)

      # EMPTY SEARCH => show ALL aliases
      if not qn:
        filtered = only
      else:
        q_tokens = [t for t in qn.split(" ") if t]

        filtered = []
        for disp in only:
          sku, name = self._parse_alias_display_value(disp)

          # Search space includes BOTH: alias name + sku
          hay = _norm(f"{name} {sku}")

          # All tokens must be present (order-independent)
          if all(t in hay for t in q_tokens):
            filtered.append(disp)

      _alias_dropdown_render(filtered)

      if show_if_any and (qn or filtered):
        _alias_dropdown_place_below_entry()
        # Do NOT touch focus/caret here — it breaks cursor position while typing/refocusing.
      else:
        _alias_dropdown_hide()

    def _alias_apply_filter_debounced(_event=None) -> None:
      if _alias_filter_state["after_id"] is not None:
        try:
          self.after_cancel(_alias_filter_state["after_id"])
        except Exception:
          pass
        _alias_filter_state["after_id"] = None

      _alias_filter_state["after_id"] = self.after(60, _alias_apply_filter)

    def _alias_toggle_dropdown() -> None:
      if getattr(self, "_alias_dropdown_visible", False):
        _alias_dropdown_hide()
      else:
        # show full list
        _alias_dropdown_render([v for v in (getattr(self, "_alias_dropdown_values", []) or []) if v])
        _alias_dropdown_place_below_entry()
        # Do NOT touch focus/caret here.

    self.btn_alias_drop.configure(command=_alias_toggle_dropdown)

    # Typing: filter and keep dropdown visible (without stealing focus)
    self.entry_alias.bind("<KeyRelease>", _alias_apply_filter_debounced)

    # Clicking into the Alias entry should open the dropdown (show all if empty, filtered if not).
    def _alias_open_on_click(_e=None) -> None:
      # Let the click set caret first, then place/render dropdown.
      try:
        self.after(1, lambda: _alias_apply_filter(show_if_any=True))
      except Exception:
        pass

    # Focus-in (tabbing into the field) should also open it.
    def _alias_open_on_focus(_e=None) -> None:
      try:
        if not getattr(self, "_alias_dropdown_visible", False):
          self.after(1, lambda: _alias_apply_filter(show_if_any=True))
      except Exception:
        pass

    self.entry_alias.bind("<Button-1>", _alias_open_on_click)
    self.entry_alias.bind("<FocusIn>", _alias_open_on_focus)

    # Esc closes dropdown
    self.entry_alias.bind("<Escape>", lambda _e: _alias_dropdown_hide())

    # Clicking outside closes dropdown (additive bind so we don’t break other handlers)
    if not getattr(self, "_alias_outside_click_bound", False):
      self._alias_outside_click_bound = True

      def _on_any_click_close_alias(e) -> None:
        try:
          w = e.widget

          # Treat clicks anywhere inside the alias picker (entry + button) as "inside".
          # CTk widgets often emit events from internal child widgets, not the outer widget.
          if _alias_is_descendant(w, self.alias_picker):
            return

          # Treat clicks inside the dropdown as "inside".
          if _alias_is_descendant(w, self._alias_dropdown):
            return

          _alias_dropdown_hide()
        except Exception:
          pass

      self.bind_all("<Button-1>", _on_any_click_close_alias, add="+")

    # Let _refresh_alias_dropdown update + hide if needed
    self._alias_dropdown_hide = _alias_dropdown_hide

    ctk.CTkLabel(form_row, text="Type").grid(row=0, column=6, padx=(14, 6), pady=10)
    self.opt_type = ctk.CTkOptionMenu(
      form_row,
      values=[TX_PURCHASE, TX_SALE],
      variable=self.var_type,
      width=140,
      command=lambda _: self._sync_type_fields(),
    )
    self.opt_type.grid(row=0, column=7, padx=6, pady=10)

    ctk.CTkLabel(form_row, text="Qty").grid(row=0, column=8, padx=(14, 6), pady=10)
    self.entry_qty = ctk.CTkEntry(form_row, textvariable=self.var_qty, width=80)
    self.entry_qty.grid(row=0, column=9, padx=6, pady=10)
    apply_entry_shortcuts(self.entry_qty)

    self.lbl_unit_price = ctk.CTkLabel(form_row, text="Purchase Unit Cost")
    self.lbl_unit_price.grid(row=0, column=10, padx=(14, 6), pady=10)

    self.entry_unit_price = ctk.CTkEntry(form_row, textvariable=self.var_unit_price, width=120)
    self.entry_unit_price.grid(row=0, column=11, padx=6, pady=10)
    apply_entry_shortcuts(self.entry_unit_price)

    ctk.CTkLabel(action_row, text="Note").grid(row=0, column=0, padx=(10, 6), pady=(0, 10))
    self.entry_note = ctk.CTkEntry(action_row, textvariable=self.var_note)
    self.entry_note.grid(row=0, column=1, sticky="ew", padx=6, pady=(0, 10))
    apply_entry_shortcuts(self.entry_note)

    buttons_frame = ctk.CTkFrame(action_row, fg_color="transparent")
    buttons_frame.grid(row=0, column=2, padx=(6, 10), pady=(0, 10), sticky="e")

    self.btn_add = ctk.CTkButton(buttons_frame, text="Add", command=self._on_add)
    self.btn_add.grid(row=0, column=0, padx=6, sticky="ew")

    self.btn_update = ctk.CTkButton(buttons_frame, text="Update Selected", command=self._on_update_selected)
    self.btn_update.grid(row=0, column=1, padx=6, sticky="ew")

    self.btn_delete = ctk.CTkButton(
      buttons_frame,
      text="Delete Selected",
      fg_color="#8B2D2D",
      hover_color="#A53636",
      command=self._on_delete_selected,
    )
    self.btn_delete.grid(row=0, column=2, padx=6, sticky="ew")

    self.btn_export = ctk.CTkButton(buttons_frame, text="Export CSV", command=self._export_csv)
    self.btn_export.grid(row=0, column=3, padx=6, sticky="ew")

    # ---------------------------------------------------------
    # Transactions Table (ttk.Treeview) — gitea-like behavior
    # - Zebra striping using CTk theme colors
    # - Hover tooltip shows ONLY the hovered cell value
    # - Both scrollbars (v/h)
    # ---------------------------------------------------------

    table_frame = ctk.CTkFrame(self.tab_tx)
    table_frame.grid(row=2, column=0, sticky="nsew", padx=10, pady=(6, 10))

    table_frame.grid_rowconfigure(0, weight=1)
    table_frame.grid_columnconfigure(0, weight=1)
    table_frame.grid_rowconfigure(1, weight=0)

    columns = [
      "id", "date", "sku", "alias", "type", "qty",
      "purchase_unit_cost", "sale_unit_price",
      "purchase_total_cost", "prev_avg_cost",
      "onhand_qty", "avg_cost_after",
      "cogs", "onhand_cost", "sales_rev", "gross_profit",
      "note",
    ]

    self.tx_tree = ttk.Treeview(
      table_frame,
      columns=columns,
      show="headings",
      height=18,
      selectmode="extended",
      style="Treeview",
    )
    self.tx_tree.grid(row=0, column=0, sticky="nsew")

    vsb = ttk.Scrollbar(
      table_frame,
      orient="vertical",
      command=self.tx_tree.yview,
      style="Dark.Vertical.TScrollbar",
    )
    hsb = ttk.Scrollbar(
      table_frame,
      orient="horizontal",
      command=self.tx_tree.xview,
      style="Dark.Horizontal.TScrollbar",
    )
    self.tx_tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
    vsb.grid(row=0, column=1, sticky="ns")
    hsb.grid(row=1, column=0, sticky="ew")

    # Zebra + error tint tags
    self.tx_tree.tag_configure("odd",  background=_ctk_color(ctk.ThemeManager.theme["CTkFrame"]["top_fg_color"]))
    self.tx_tree.tag_configure("even", background=_ctk_color(ctk.ThemeManager.theme["CTkFrame"]["fg_color"]))

    self.tx_tree.tag_configure("status_error_even", background="#3d1f1f")
    self.tx_tree.tag_configure("status_error_odd",  background="#462424")

    headings = {
      "id": "ID",
      "date": "Date",
      "sku": "SKU",
      "alias": "Alias",
      "type": "Type",
      "qty": "Qty",
      "purchase_unit_cost": "Purchase Unit Cost",
      "sale_unit_price": "Sale Unit Price",
      "purchase_total_cost": "Purchase Total Cost",
      "prev_avg_cost": "Prev Avg Cost",
      "onhand_qty": "OnHand Qty",
      "avg_cost_after": "Avg Cost",
      "cogs": "COGS",
      "onhand_cost": "OnHand Cost",
      "sales_rev": "Sales Rev",
      "gross_profit": "Gross Profit",
      "note": "Note",
    }

    widths = {
      "id": 60, "date": 120, "sku": 200, "alias": 260, "type": 120, "qty": 80,
      "purchase_unit_cost": 165, "sale_unit_price": 145,
      "purchase_total_cost": 175, "prev_avg_cost": 145,
      "onhand_qty": 120, "avg_cost_after": 130,
      "cogs": 130, "onhand_cost": 155, "sales_rev": 140, "gross_profit": 180,
      "note": 380,
    }

    col_anchor = {
      "id": "center",
      "date": "w",
      "sku": "w",
      "alias": "w",
      "type": "center",
      "qty": "e",
      "purchase_unit_cost": "e",
      "sale_unit_price": "e",
      "purchase_total_cost": "e",
      "prev_avg_cost": "e",
      "onhand_qty": "e",
      "avg_cost_after": "e",
      "cogs": "e",
      "onhand_cost": "e",
      "sales_rev": "e",
      "gross_profit": "e",
      "note": "w",
    }

    head_anchor = {
      k: ("center" if v == "center" else ("e" if v == "e" else "w"))
      for k, v in col_anchor.items()
    }

    heading_gutter = "  "  # visual separation between adjacent headers

    for ci, c in enumerate(columns):
      base_text = headings.get(c, c)
      head_text = (f"{base_text}{heading_gutter}" if ci < (len(columns) - 1) else base_text)

      self.tx_tree.heading(
        c,
        text=head_text,
        anchor=head_anchor.get(c, "w"),
      )
      self.tx_tree.column(
        c,
        width=widths.get(c, 120),
        minwidth=32,
        anchor=col_anchor.get(c, "w"),
        stretch=False,
      )

    # ---------------------------------------------------------
    # Fit columns: let ONLY ["sku","alias","note"] stretch when possible.
    # If fixed columns exceed viewport, rely on h-scroll.
    # ---------------------------------------------------------

    _fit_after_id = {"id": None}

    def _fit_columns_now() -> None:
      try:
        frame_w = int(table_frame.winfo_width() or 0)
      except Exception:
        frame_w = 0
      if frame_w < 100:
        self.after(50, _fit_columns_now)
        return

      try:
        sb_w = int(vsb.winfo_width() or vsb.winfo_reqwidth() or 16)
      except Exception:
        sb_w = 16

      avail = max(frame_w - sb_w - 6, 64)

      stretch_cols = ("sku", "alias", "note")
      fixed_cols = tuple(c for c in columns if c not in stretch_cols)

      fixed_w = 0
      for c in fixed_cols:
        try:
          fixed_w += int(self.tx_tree.column(c, "width") or 0)
        except Exception:
          pass

      if fixed_w >= (avail - 64):
        return

      stretch_avail = max(avail - fixed_w, 64)

      # Proportional split across N stretch columns based on current widths.
      cur_w: Dict[str, int] = {}
      total = 0
      for c in stretch_cols:
        try:
          w = int(self.tx_tree.column(c, "width") or widths.get(c, 120) or 120)
        except Exception:
          w = int(widths.get(c, 120) or 120)
        w = max(w, 32)
        cur_w[c] = w
        total += w

      total = max(total, 1)

      used = 0
      for c in stretch_cols[:-1]:
        new_w = max(32, int(stretch_avail * (cur_w[c] / total)))
        used += new_w
        try:
          self.tx_tree.column(c, width=new_w)
        except Exception:
          pass

      last_c = stretch_cols[-1]
      last_w = max(32, int(stretch_avail - used))
      try:
        self.tx_tree.column(last_c, width=last_w)
      except Exception:
        pass

    def _fit_columns_debounced(_event=None) -> None:
      if _fit_after_id["id"] is not None:
        try:
          self.after_cancel(_fit_after_id["id"])
        except Exception:
          pass
      _fit_after_id["id"] = self.after(30, _fit_columns_now)

    table_frame.bind("<Configure>", _fit_columns_debounced)

    # ---------------------------------------------------------
    # Hover tooltip: ONLY hovered cell value (literal)
    # ---------------------------------------------------------

    _tree_tip_state = {"win": None, "lbl": None, "font": None, "last": None}

    def _tree_tip_hide() -> None:
      win = _tree_tip_state.get("win")
      if win is not None:
        try:
          win.destroy()
        except Exception:
          pass
      _tree_tip_state["win"] = None
      _tree_tip_state["lbl"] = None
      _tree_tip_state["last"] = None

    def _tree_tip_show(*, text: str, x_root: int, y_root: int) -> None:
      if _tree_tip_state["win"] is None:
        win = tk.Toplevel(self)
        win.withdraw()
        win.overrideredirect(True)
        try:
          win.attributes("-topmost", True)
        except Exception:
          pass

        bg = _ctk_color(ctk.ThemeManager.theme["CTkFrame"]["top_fg_color"])
        fg = _ctk_color(ctk.ThemeManager.theme["CTkLabel"]["text_color"])

        from tkinter import font as tkfont
        if _tree_tip_state["font"] is None:
          f = tkfont.nametofont("TkDefaultFont").copy()
          try:
            f.configure(size=int(f.cget("size")) + 4)
          except Exception:
            f.configure(size=14)
          _tree_tip_state["font"] = f

        lbl = tk.Label(
          win,
          text="",
          justify="left",
          anchor="w",
          padx=8,
          pady=4,
          bg=bg,
          fg=fg,
          font=_tree_tip_state["font"],
          bd=1,
          relief="solid",
        )
        lbl.pack()
        _tree_tip_state["win"] = win
        _tree_tip_state["lbl"] = lbl

      win = _tree_tip_state["win"]
      lbl = _tree_tip_state["lbl"]
      if win is None or lbl is None:
        return

      lbl.configure(text=text)
      x = x_root + 14
      y = y_root + 16
      try:
        win.geometry(f"+{x}+{y}")
        win.deiconify()
      except Exception:
        pass

    header_tooltips = {
      "id": "ID: internal transaction row id.",
      "date": "Date: transaction date (sorted ascending for costing).",
      "sku": "SKU: item identifier used for costing/aggregation.",
      "alias": "Alias: friendly name for the SKU (from Aliases tab).",
      "type": "Type: PURCHASE adds inventory; SALE removes inventory.",
      "qty": "Qty: units bought/sold.",
      "purchase_unit_cost": "Purchase Unit Cost: per-unit cost on PURCHASE rows.",
      "sale_unit_price": "Sale Unit Price: per-unit sale price on SALE rows.",
      "purchase_total_cost": "Purchase Total Cost: Qty × Purchase Unit Cost.",
      "prev_avg_cost": "Prev Avg Cost: weighted average cost before this transaction.",
      "onhand_qty": "OnHand Qty: inventory quantity after this transaction.",
      "avg_cost_after": "Avg Cost: weighted average cost after this transaction.",
      "cogs": "COGS: Qty × Prev Avg Cost (for SALE rows).",
      "onhand_cost": "OnHand Cost: total cost value of inventory after this transaction.",
      "sales_rev": "Sales Rev: Qty × Sale Unit Price (for SALE rows).",
      "gross_profit": "Gross Profit: Sales Rev − COGS (for SALE rows).",
      "note": "Note: free text note for receipts/orders/etc.",
    }

    def _tree_on_hover(event) -> None:
      region = self.tx_tree.identify_region(event.x, event.y)

      # Header hover tooltip
      if region == "heading":
        col = self.tx_tree.identify_column(event.x)
        if not col or col == "#0":
          _tree_tip_hide()
          return

        cols = list(self.tx_tree["columns"])
        try:
          idx = int(col[1:]) - 1
        except Exception:
          _tree_tip_hide()
          return
        if idx < 0 or idx >= len(cols):
          _tree_tip_hide()
          return

        col_id = cols[idx]
        text = str(header_tooltips.get(col_id) or headings.get(col_id) or col_id).strip()

        key = ("__heading__", col_id, text)
        if _tree_tip_state["last"] != key:
          _tree_tip_state["last"] = key
        _tree_tip_show(text=text, x_root=event.x_root, y_root=event.y_root)
        return

      # Cell hover tooltip (existing behavior)
      if region != "cell":
        _tree_tip_hide()
        return

      iid = self.tx_tree.identify_row(event.y)
      col = self.tx_tree.identify_column(event.x)
      if not iid or not col or col == "#0":
        _tree_tip_hide()
        return

      cols = list(self.tx_tree["columns"])
      try:
        idx = int(col[1:]) - 1
      except Exception:
        _tree_tip_hide()
        return

      if idx < 0 or idx >= len(cols):
        _tree_tip_hide()
        return

      col_id = cols[idx]

      try:
        val = self.tx_tree.set(iid, col_id)
      except Exception:
        _tree_tip_hide()
        return

      text = str(val)
      key = (iid, col_id, text)
      if _tree_tip_state["last"] != key:
        _tree_tip_state["last"] = key
      _tree_tip_show(text=text, x_root=event.x_root, y_root=event.y_root)

    self.tx_tree.bind("<Motion>", _tree_on_hover)
    self.tx_tree.bind("<Leave>", lambda _e: _tree_tip_hide())
    self.tx_tree.bind("<ButtonPress>", lambda _e: _tree_tip_hide())
    self.tx_tree.bind("<MouseWheel>", lambda _e: _tree_tip_hide())
    self.tx_tree.bind("<Button-4>", lambda _e: _tree_tip_hide())
    self.tx_tree.bind("<Button-5>", lambda _e: _tree_tip_hide())

    self._tx_tree_tip_hide = _tree_tip_hide

    def _on_tx_tree_select(_e=None) -> None:
      self._load_selected_into_form()
      self._sync_tx_update_selected_state()

    self.tx_tree.bind("<<TreeviewSelect>>", _on_tx_tree_select)

    self._sync_type_fields()

  def _build_overview_tab(self) -> None:
    # Layout: top controls + table frame
    self.tab_ov.grid_rowconfigure(1, weight=1)
    self.tab_ov.grid_columnconfigure(0, weight=1)

    # ---------------------------------------------------------
    # Controls
    # ---------------------------------------------------------

    controls = ctk.CTkFrame(self.tab_ov)
    controls.grid(row=0, column=0, sticky="ew", padx=10, pady=(10, 6))
    # Column 2 holds the Export button; let it stretch so the button can sit on the far right.
    controls.grid_columnconfigure(2, weight=1)

    ctk.CTkLabel(controls, text="View").grid(row=0, column=0, padx=(10, 6), pady=10, sticky="w")

    self.ov_view_var = tk.StringVar(value="Inventory")
    self.opt_ov_view = ctk.CTkOptionMenu(
      controls,
      values=["Inventory", "Monthly"],
      variable=self.ov_view_var,
      width=160,
      command=lambda _v: self._on_overview_view_changed(),
    )
    self.opt_ov_view.grid(row=0, column=1, padx=6, pady=10, sticky="w")

    self.btn_ov_export = ctk.CTkButton(controls, text="Export CSV", command=self._export_overview_csv)
    self.btn_ov_export.grid(row=0, column=2, padx=(6, 10), pady=10, sticky="e")

    # ---------------------------------------------------------
    # Table
    # ---------------------------------------------------------

    frame = ctk.CTkFrame(self.tab_ov)
    frame.grid(row=1, column=0, sticky="nsew", padx=10, pady=(6, 10))
    frame.grid_rowconfigure(0, weight=1)
    frame.grid_columnconfigure(0, weight=1)
    frame.grid_rowconfigure(1, weight=0)

    # Keep refs for resize-fit logic
    self._ov_frame = frame

    self.ov_tree = ttk.Treeview(
      frame,
      columns=[],
      show="headings",
      height=18,
      selectmode="extended",
      style="Treeview",
    )
    self.ov_tree.grid(row=0, column=0, sticky="nsew")

    vsb = ttk.Scrollbar(
      frame,
      orient="vertical",
      command=self.ov_tree.yview,
      style="Dark.Vertical.TScrollbar",
    )
    hsb = ttk.Scrollbar(
      frame,
      orient="horizontal",
      command=self.ov_tree.xview,
      style="Dark.Horizontal.TScrollbar",
    )
    self.ov_tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)

    vsb.grid(row=0, column=1, sticky="ns")
    hsb.grid(row=1, column=0, sticky="ew")

    self._ov_vsb = vsb

    # Zebra + status tint tags (same naming as gitea_repository_backup)
    self.ov_tree.tag_configure(
      "odd",
      background=_ctk_color(ctk.ThemeManager.theme["CTkFrame"]["top_fg_color"]),
    )
    self.ov_tree.tag_configure(
      "even",
      background=_ctk_color(ctk.ThemeManager.theme["CTkFrame"]["fg_color"]),
    )

    self.ov_tree.tag_configure("status_done_even", background="#1f3d2b")   # dark green (even)
    self.ov_tree.tag_configure("status_done_odd",  background="#244632")   # dark green (odd)
    self.ov_tree.tag_configure("status_error_even", background="#3d1f1f")  # dark red (even)
    self.ov_tree.tag_configure("status_error_odd",  background="#462424")  # dark red (odd)

    # ---------------------------------------------------------
    # Auto-fit columns to viewport (robust across view modes)
    # ---------------------------------------------------------

    self._ov_fit_after_id = {"id": None}

    def _fit_columns_now() -> None:
      try:
        frame_w = int(self._ov_frame.winfo_width() or 0)
      except Exception:
        frame_w = 0

      if frame_w < 100:
        self.after(50, _fit_columns_now)
        return

      try:
        sb_w = int(self._ov_vsb.winfo_width() or self._ov_vsb.winfo_reqwidth() or 16)
      except Exception:
        sb_w = 16

      avail = max(frame_w - sb_w - 6, 64)

      cols = list(self.ov_tree["columns"] or [])
      if not cols:
        return

      mode = (self.ov_view_var.get() or "Inventory").strip()

      if mode == "Monthly":
        # Even-split ALL monthly columns across the viewport.
        stretch_cols = list(cols)
      else:
        stretch_cols = [c for c in ["sku", "alias", "status"] if c in cols]

      fixed_cols = [c for c in cols if c not in stretch_cols]

      fixed_w = 0
      for c in fixed_cols:
        try:
          fixed_w += int(self.ov_tree.column(c, "width") or 0)
        except Exception:
          pass

      if not stretch_cols:
        return

      if fixed_w >= (avail - 64):
        return

      stretch_avail = max(avail - fixed_w, 64)

      # Split evenly across stretch columns (simple + predictable)
      per = max(int(stretch_avail / max(len(stretch_cols), 1)), 32)
      for c in stretch_cols[:-1]:
        try:
          self.ov_tree.column(c, width=per)
        except Exception:
          pass

      # Last gets remainder to avoid rounding drift
      try:
        used = 0
        for c in stretch_cols[:-1]:
          used += int(self.ov_tree.column(c, "width") or per)
        last_w = max(int(stretch_avail - used), 32)
        self.ov_tree.column(stretch_cols[-1], width=last_w)
      except Exception:
        pass

    def _fit_columns_debounced(_event=None) -> None:
      if self._ov_fit_after_id["id"] is not None:
        try:
          self.after_cancel(self._ov_fit_after_id["id"])
        except Exception:
          pass
      self._ov_fit_after_id["id"] = self.after(30, _fit_columns_now)

    frame.bind("<Configure>", _fit_columns_debounced)
    self._ov_fit_columns_now = _fit_columns_now

    # ---------------------------------------------------------
    # Treeview hover tooltip: show ONLY hovered cell value (literal)
    # ---------------------------------------------------------

    _tree_tip_state = {
      "win": None,
      "lbl": None,
      "font": None,  # cached tk Font for tooltip
      "last": None,  # (iid, col_id, value)
    }

    def _tree_tip_hide() -> None:
      win = _tree_tip_state.get("win")
      if win is not None:
        try:
          win.destroy()
        except Exception:
          pass
      _tree_tip_state["win"] = None
      _tree_tip_state["lbl"] = None
      _tree_tip_state["last"] = None

    def _tree_tip_show(*, text: str, x_root: int, y_root: int) -> None:
      if _tree_tip_state["win"] is None:
        win = tk.Toplevel(self)
        win.withdraw()
        win.overrideredirect(True)
        try:
          win.attributes("-topmost", True)
        except Exception:
          pass

        bg = _ctk_color(ctk.ThemeManager.theme["CTkFrame"]["top_fg_color"])
        fg = _ctk_color(ctk.ThemeManager.theme["CTkLabel"]["text_color"])

        from tkinter import font as tkfont

        if _tree_tip_state["font"] is None:
          f = tkfont.nametofont("TkDefaultFont").copy()
          try:
            f.configure(size=int(f.cget("size")) + 4)
          except Exception:
            f.configure(size=14)
          _tree_tip_state["font"] = f

        lbl = tk.Label(
          win,
          text="",
          justify="left",
          anchor="w",
          padx=8,
          pady=4,
          bg=bg,
          fg=fg,
          font=_tree_tip_state["font"],
          bd=1,
          relief="solid",
        )
        lbl.pack()

        _tree_tip_state["win"] = win
        _tree_tip_state["lbl"] = lbl

      win = _tree_tip_state["win"]
      lbl = _tree_tip_state["lbl"]
      if win is None or lbl is None:
        return

      lbl.configure(text=text)

      x = x_root + 14
      y = y_root + 16

      try:
        win.geometry(f"+{x}+{y}")
        win.deiconify()
      except Exception:
        pass

    header_tooltips = {
      # Inventory mode
      "sku": "SKU: item identifier.",
      "alias": "Alias: friendly name for SKU (from Aliases tab).",
      "onhand_qty": "OnHand Qty: current inventory quantity.",
      "avg_cost": "Avg Cost: weighted average cost per unit (current).",
      "onhand_cost": "OnHand Cost: total inventory value (Qty × Avg Cost).",
      "last_tx_date": "Last Tx Date: most recent transaction date for this SKU.",
      "last_sale_price": "Last Sale Price: most recent sale unit price for this SKU.",
      "status": "Status: IN STOCK / OUT / NEGATIVE (OVERSOLD).",

      # Monthly mode
      "month": "Month bucket (YYYY-MM).",
      "month_date": "Month Date (YYYY-MM-01).",
      "purchase_cost": "Purchase Cost: sum of purchase totals in the month.",
      "sales_amount": "Sales Amount: sum of sales revenue in the month.",
      "cogs": "COGS: sum of cost-of-goods-sold in the month.",
    }

    def _tree_on_hover(event) -> None:
      region = self.ov_tree.identify_region(event.x, event.y)

      # Header hover tooltip
      if region == "heading":
        col = self.ov_tree.identify_column(event.x)
        if not col or col == "#0":
          _tree_tip_hide()
          return

        cols = list(self.ov_tree["columns"])
        try:
          idx = int(col[1:]) - 1
        except Exception:
          _tree_tip_hide()
          return

        if idx < 0 or idx >= len(cols):
          _tree_tip_hide()
          return

        col_id = cols[idx]

        # Prefer our map, else fall back to the displayed heading text (strip gutter).
        text = header_tooltips.get(col_id)
        if not text:
          try:
            text = str(self.ov_tree.heading(col_id, "text") or "").strip()
          except Exception:
            text = col_id
          text = text.strip()

        key = ("__heading__", col_id, text)
        if _tree_tip_state["last"] != key:
          _tree_tip_state["last"] = key
        _tree_tip_show(text=str(text), x_root=event.x_root, y_root=event.y_root)
        return

      # Cell hover tooltip (existing behavior)
      if region != "cell":
        _tree_tip_hide()
        return

      iid = self.ov_tree.identify_row(event.y)
      col = self.ov_tree.identify_column(event.x)
      if not iid or not col or col == "#0":
        _tree_tip_hide()
        return

      cols = list(self.ov_tree["columns"])
      try:
        idx = int(col[1:]) - 1
      except Exception:
        _tree_tip_hide()
        return

      if idx < 0 or idx >= len(cols):
        _tree_tip_hide()
        return

      col_id = cols[idx]

      try:
        val = self.ov_tree.set(iid, col_id)
      except Exception:
        _tree_tip_hide()
        return

      text = str(val)

      key = (iid, col_id, text)
      if _tree_tip_state["last"] != key:
        _tree_tip_state["last"] = key
        _tree_tip_show(text=text, x_root=event.x_root, y_root=event.y_root)
      else:
        _tree_tip_show(text=text, x_root=event.x_root, y_root=event.y_root)

    self.ov_tree.bind("<Motion>", _tree_on_hover)
    self.ov_tree.bind("<Leave>", lambda _e: _tree_tip_hide())
    self.ov_tree.bind("<ButtonPress>", lambda _e: _tree_tip_hide())
    self.ov_tree.bind("<MouseWheel>", lambda _e: _tree_tip_hide())  # Windows
    self.ov_tree.bind("<Button-4>", lambda _e: _tree_tip_hide())    # Linux scroll up
    self.ov_tree.bind("<Button-5>", lambda _e: _tree_tip_hide())    # Linux scroll down

    self._ov_tree_tip_hide = _tree_tip_hide

    # Configure initial view columns
    self._configure_overview_tree_for_view()

  def _build_aliases_tab(self) -> None:
    self.tab_alias.grid_rowconfigure(1, weight=1)
    self.tab_alias.grid_columnconfigure(0, weight=1)

    form = ctk.CTkFrame(self.tab_alias)
    form.grid(row=0, column=0, sticky="ew", padx=10, pady=(10, 6))

    ctk.CTkLabel(form, text="SKU").grid(row=0, column=0, padx=(10, 6), pady=10, sticky="w")
    self.var_alias_sku = tk.StringVar(value="")
    self.entry_alias_sku = ctk.CTkEntry(form, textvariable=self.var_alias_sku, width=220)
    self.entry_alias_sku.grid(row=0, column=1, padx=6, pady=10, sticky="w")
    apply_entry_shortcuts(self.entry_alias_sku)

    ctk.CTkLabel(form, text="Name").grid(row=0, column=2, padx=(14, 6), pady=10, sticky="w")
    self.var_alias_name = tk.StringVar(value="")
    self.entry_alias_name = ctk.CTkEntry(form, textvariable=self.var_alias_name, width=360)
    self.entry_alias_name.grid(row=0, column=3, padx=6, pady=10, sticky="w")
    apply_entry_shortcuts(self.entry_alias_name)

    btns = ctk.CTkFrame(form, fg_color="transparent")
    btns.grid(row=0, column=4, padx=(12, 10), pady=10, sticky="e")

    self.btn_alias_add = ctk.CTkButton(btns, text="Add", width=110, command=self._on_alias_add)
    self.btn_alias_add.grid(row=0, column=0, padx=6)

    self.btn_alias_update = ctk.CTkButton(btns, text="Update Selected", width=160, command=self._on_alias_update_selected)
    self.btn_alias_update.grid(row=0, column=1, padx=6)

    self.btn_alias_delete = ctk.CTkButton(
      btns,
      text="Delete Selected",
      width=150,
      fg_color="#8B2D2D",
      hover_color="#A53636",
      command=self._on_alias_delete_selected,
    )
    self.btn_alias_delete.grid(row=0, column=2, padx=6)

    # Table
    table_frame = ctk.CTkFrame(self.tab_alias)
    table_frame.grid(row=1, column=0, sticky="nsew", padx=10, pady=(6, 10))
    table_frame.grid_rowconfigure(0, weight=1)
    table_frame.grid_columnconfigure(0, weight=1)
    table_frame.grid_rowconfigure(1, weight=0)

    self.alias_tree = ttk.Treeview(
      table_frame,
      columns=["sku", "name"],
      show="headings",
      height=18,
      selectmode="extended",
      style="Treeview",
    )
    self.alias_tree.grid(row=0, column=0, sticky="nsew")

    vsb = ttk.Scrollbar(
      table_frame,
      orient="vertical",
      command=self.alias_tree.yview,
      style="Dark.Vertical.TScrollbar",
    )
    hsb = ttk.Scrollbar(
      table_frame,
      orient="horizontal",
      command=self.alias_tree.xview,
      style="Dark.Horizontal.TScrollbar",
    )
    self.alias_tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
    vsb.grid(row=0, column=1, sticky="ns")
    hsb.grid(row=1, column=0, sticky="ew")

    self.alias_tree.tag_configure("odd",  background=_ctk_color(ctk.ThemeManager.theme["CTkFrame"]["top_fg_color"]))
    self.alias_tree.tag_configure("even", background=_ctk_color(ctk.ThemeManager.theme["CTkFrame"]["fg_color"]))

    heading_gutter = "  "
    self.alias_tree.heading("sku", text=f"SKU{heading_gutter}", anchor="w")
    self.alias_tree.heading("name", text="Name", anchor="w")
    self.alias_tree.column("sku", width=240, minwidth=80, anchor="w", stretch=False)
    self.alias_tree.column("name", width=520, minwidth=120, anchor="w", stretch=True)

    # ---------------------------------------------------------
    # Header hover tooltip (Aliases table)
    # ---------------------------------------------------------

    _alias_tip_state = {"win": None, "lbl": None, "font": None, "last": None}

    def _alias_tip_hide() -> None:
      win = _alias_tip_state.get("win")
      if win is not None:
        try:
          win.destroy()
        except Exception:
          pass
      _alias_tip_state["win"] = None
      _alias_tip_state["lbl"] = None
      _alias_tip_state["last"] = None

    def _alias_tip_show(*, text: str, x_root: int, y_root: int) -> None:
      if _alias_tip_state["win"] is None:
        win = tk.Toplevel(self)
        win.withdraw()
        win.overrideredirect(True)
        try:
          win.attributes("-topmost", True)
        except Exception:
          pass

        bg = _ctk_color(ctk.ThemeManager.theme["CTkFrame"]["top_fg_color"])
        fg = _ctk_color(ctk.ThemeManager.theme["CTkLabel"]["text_color"])

        from tkinter import font as tkfont
        if _alias_tip_state["font"] is None:
          f = tkfont.nametofont("TkDefaultFont").copy()
          try:
            f.configure(size=int(f.cget("size")) + 4)
          except Exception:
            f.configure(size=14)
          _alias_tip_state["font"] = f

        lbl = tk.Label(
          win,
          text="",
          justify="left",
          anchor="w",
          padx=8,
          pady=4,
          bg=bg,
          fg=fg,
          font=_alias_tip_state["font"],
          bd=1,
          relief="solid",
        )
        lbl.pack()
        _alias_tip_state["win"] = win
        _alias_tip_state["lbl"] = lbl

      win = _alias_tip_state["win"]
      lbl = _alias_tip_state["lbl"]
      if win is None or lbl is None:
        return

      lbl.configure(text=text)
      x = x_root + 14
      y = y_root + 16
      try:
        win.geometry(f"+{x}+{y}")
        win.deiconify()
      except Exception:
        pass

    _alias_header_tooltips = {
      "sku": "SKU: the inventory identifier this alias maps to.",
      "name": "Name: friendly display name shown in tables and dropdowns.",
    }

    def _alias_on_hover(event) -> None:
      region = self.alias_tree.identify_region(event.x, event.y)

      # Header hover tooltip
      if region == "heading":
        col = self.alias_tree.identify_column(event.x)
        if not col or col == "#0":
          _alias_tip_hide()
          return

        cols = list(self.alias_tree["columns"])
        try:
          idx = int(col[1:]) - 1
        except Exception:
          _alias_tip_hide()
          return

        if idx < 0 or idx >= len(cols):
          _alias_tip_hide()
          return

        col_id = cols[idx]
        text = str(_alias_header_tooltips.get(col_id) or col_id)

        key = ("__heading__", col_id, text)
        if _alias_tip_state["last"] != key:
          _alias_tip_state["last"] = key
        _alias_tip_show(text=text, x_root=event.x_root, y_root=event.y_root)
        return

      # Cell hover tooltip: show ONLY hovered cell value (literal)
      if region != "cell":
        _alias_tip_hide()
        return

      iid = self.alias_tree.identify_row(event.y)
      col = self.alias_tree.identify_column(event.x)
      if not iid or not col or col == "#0":
        _alias_tip_hide()
        return

      cols = list(self.alias_tree["columns"])
      try:
        idx = int(col[1:]) - 1
      except Exception:
        _alias_tip_hide()
        return

      if idx < 0 or idx >= len(cols):
        _alias_tip_hide()
        return

      col_id = cols[idx]

      try:
        val = self.alias_tree.set(iid, col_id)
      except Exception:
        _alias_tip_hide()
        return

      text = str(val)
      key = (iid, col_id, text)

      if _alias_tip_state["last"] != key:
        _alias_tip_state["last"] = key
        _alias_tip_show(text=text, x_root=event.x_root, y_root=event.y_root)
      else:
        _alias_tip_show(text=text, x_root=event.x_root, y_root=event.y_root)

    self.alias_tree.bind("<Motion>", _alias_on_hover)
    self.alias_tree.bind("<Leave>", lambda _e: _alias_tip_hide())
    self.alias_tree.bind("<ButtonPress>", lambda _e: _alias_tip_hide())
    self.alias_tree.bind("<MouseWheel>", lambda _e: _alias_tip_hide())
    self.alias_tree.bind("<Button-4>", lambda _e: _alias_tip_hide())
    self.alias_tree.bind("<Button-5>", lambda _e: _alias_tip_hide())

    def _on_alias_tree_select(_e=None) -> None:
      self._load_selected_alias_into_form()
      self._sync_alias_update_selected_state()

    self.alias_tree.bind("<<TreeviewSelect>>", _on_alias_tree_select)


  def _on_pick_date(self) -> None:
    """
    Toggle the in-window calendar dropdown and set the Transactions form Date field.

    Behavior:
      - If tkcalendar is available: show a themed overlay calendar (inside the main window).
      - If not available: show a short info message (keeps app dependency-light).
    """
    try:
      # Overlay helpers are created during _build_transactions_tab()
      toggle = getattr(self, "_date_dropdown_toggle", None)
      if callable(toggle):
        toggle()
        return
    except Exception:
      pass

    # Fallback (shouldn't happen unless UI not built yet)
    if Calendar is None:
      messagebox.showinfo(
        "Date Picker",
        "Calendar picker requires optional dependency:\n\n"
        "  pip install tkcalendar\n\n"
        "You can still type the date as YYYY-MM-DD or M/D/YYYY."
      )
      try:
        self.entry_date.focus_set()
      except Exception:
        pass

  # -----------------------------------------------------------------------------
  # Project bar callbacks
  # -----------------------------------------------------------------------------

  def _on_project_combo_selected(self) -> None:
    # Same behavior as your attached script: selecting loads immediately
    self._on_load_project()

  def _on_browse_project(self) -> None:
    p = filedialog.askdirectory(title="Select Project Directory")
    if not p:
      return
    self.project_dir_var.set(os.path.abspath(p))
    self._on_load_project()

  def _on_load_project(self) -> None:
    p = (self.project_dir_var.get() or "").strip()
    if not p or not os.path.isdir(p):
      messagebox.showerror("Project", "Project directory is missing or invalid.")
      return
    self._load_project_dir(p)

  def _on_clear_history(self) -> None:
    if not messagebox.askyesno("Clear History", "Clear recent project directory history?"):
      return
    self._clear_project_history()
    self.project_dir_var.set("")
    self.project_dir = ""
    self.project_data_path = ""
    self.transactions = []
    self.aliases_list = []
    self._rebuild_alias_map()
    self.next_id = 1
    self.next_created_order = 1
    self._set_tx_controls_enabled(False)
    self._refresh_aliases_ui()
    self._refresh_all()

  # -----------------------------------------------------------------------------
  # Enable/disable controls if no project loaded
  # -----------------------------------------------------------------------------

  def _set_tx_controls_enabled(self, enabled: bool) -> None:
    state_entry = "normal" if enabled else "disabled"
    state_btn = "normal" if enabled else "disabled"

    for w in [self.entry_date, self.entry_sku, self.entry_qty, self.entry_unit_price, self.entry_note]:
      try:
        w.configure(state=state_entry)
      except Exception:
        pass

    for w in [getattr(self, "btn_date_pick", None)]:
      if w is None:
        continue
      try:
        w.configure(state=("normal" if enabled else "disabled"))
      except Exception:
        pass

    # Alias picker (Entry + dropdown button)
    for w in [getattr(self, "entry_alias", None), getattr(self, "btn_alias_drop", None)]:
      if w is None:
        continue
      try:
        w.configure(state=("normal" if enabled else "disabled"))
      except Exception:
        pass

    if not enabled:
      try:
        if hasattr(self, "_alias_dropdown_hide"):
          self._alias_dropdown_hide()
      except Exception:
        pass

      try:
        if hasattr(self, "_date_dropdown_hide"):
          self._date_dropdown_hide()
      except Exception:
        pass

    for w in [self.opt_type]:
      try:
        w.configure(state=state_btn)
      except Exception:
        pass

    for b in [self.btn_add, self.btn_update, self.btn_delete, self.btn_export]:
      try:
        b.configure(state=state_btn)
      except Exception:
        pass

    # Overview tab controls
    for w in [getattr(self, "opt_ov_view", None)]:

      if w is None:
        continue
      try:
        w.configure(state=state_btn)
      except Exception:
        pass

    for b in [getattr(self, "btn_ov_export", None)]:
      if b is None:
        continue
      try:
        b.configure(state=state_btn)
      except Exception:
        pass

    # Aliases tab controls
    for w in [getattr(self, "entry_alias_sku", None), getattr(self, "entry_alias_name", None)]:
      if w is None:
        continue
      try:
        w.configure(state=state_entry)
      except Exception:
        pass

    for b in [getattr(self, "btn_alias_add", None), getattr(self, "btn_alias_update", None), getattr(self, "btn_alias_delete", None)]:
      if b is None:
        continue
      try:
        b.configure(state=state_btn)
      except Exception:
        pass

    # Keep "Update Selected" buttons disabled unless exactly one row is selected.
    try:
      self._sync_update_selected_buttons_state()
    except Exception:
      pass

  # -----------------------------------------------------------------------------
  # Alias UI syncing (Transactions form dropdown)
  # -----------------------------------------------------------------------------

  def _build_alias_display_values(self) -> List[str]:
    """
    Build Alias dropdown display values.

    Format:
      "<Name>  [<SKU>]"
    """
    out: List[str] = []
    for a in (self.aliases_list or []):
      sku = str(a.get("sku") or "").strip()
      name = str(a.get("name") or "").strip()
      if not sku or not name:
        continue
      out.append(f"{name}  [{sku}]")
    out.sort(key=lambda s: s.lower())
    return out

  def _parse_alias_display_value(self, s: str) -> Tuple[str, str]:
    """
    Parse "<Name>  [<SKU>]" -> (sku, name)
    """
    raw = str(s or "").strip()
    if not raw:
      return "", ""
    m = re.search(r"\[(.+?)\]\s*$", raw)
    if not m:
      return "", raw
    sku = m.group(1).strip()
    name = raw[: m.start()].strip()
    return sku, name

  def _refresh_alias_dropdown(self) -> None:
    """
    Refresh the Transactions-tab Alias dropdown cache.

    IMPORTANT:
      We no longer use `alias_combo` (CTkComboBox). The Transactions tab now uses
      `entry_alias` + an overlay dropdown, so this must NOT early-return when
      `alias_combo` is absent.

    Behavior:
      - Rebuild `self._alias_dropdown_values` from `self.aliases_list`.
      - Hide the overlay dropdown if it is currently visible.
      - Sync the displayed alias text from the current SKU (if any).
    """
    self._alias_dropdown_values = [""] + self._build_alias_display_values()

    # If dropdown is open, close it so it can't show stale entries
    try:
      if hasattr(self, "_alias_dropdown_hide"):
        self._alias_dropdown_hide()
    except Exception:
      pass

    # Keep selection consistent with current SKU
    self._sync_alias_choice_from_sku()

  def _sync_alias_choice_from_sku(self) -> None:
    if self._alias_sync_guard:
      return
    self._alias_sync_guard = True
    try:
      sku = (self.var_sku.get() or "").strip()
      name = self._get_alias_for_sku(sku)
      if sku and name:
        disp = f"{name}  [{sku}]"
        try:
          self.var_alias_choice.set(disp)
        except Exception:
          pass
      else:
        try:
          if (self.var_alias_choice.get() or "").strip():
            self.var_alias_choice.set("")
        except Exception:
          pass
    finally:
      self._alias_sync_guard = False

  def _on_alias_selected_in_tx_form(self) -> None:
    if self._alias_sync_guard:
      return
    self._alias_sync_guard = True
    try:
      choice = (self.var_alias_choice.get() or "").strip()
      if not choice:
        return
      sku, _name = self._parse_alias_display_value(choice)
      if sku:
        # Set SKU, but DO NOT steal focus from the Alias dropdown.
        self.var_sku.set(sku)
    finally:
      self._alias_sync_guard = False

  # -----------------------------------------------------------------------------
  # Aliases Tab Actions
  # -----------------------------------------------------------------------------

  def _refresh_aliases_ui(self) -> None:
    """
    Refresh alias tab table + transactions form dropdown.
    Safe to call even before UI exists.
    """
    self._rebuild_alias_map()
    self._refresh_alias_dropdown()

    if not hasattr(self, "alias_tree"):
      return

    try:
      self.alias_tree.delete(*self.alias_tree.get_children())
    except Exception:
      return

    rows = list(self.aliases_list or [])
    rows.sort(key=lambda x: (str(x.get("name", "")).lower(), str(x.get("sku", "")).lower()))

    for i, a in enumerate(rows):
      sku = str(a.get("sku") or "").strip()
      name = str(a.get("name") or "").strip()
      if not sku or not name:
        continue
      pad_l = "  "
      values = (f"{pad_l}{sku}", f"{pad_l}{name}")
      tag = "even" if (i % 2) == 0 else "odd"
      self.alias_tree.insert("", "end", iid=sku, values=values, tags=(tag,))

    # Keep "Update Selected" disabled unless exactly one row is selected.
    try:
      self._sync_alias_update_selected_state()
    except Exception:
      pass

  def _get_selected_alias_skus(self) -> List[str]:
    """
    Get all selected alias SKUs (extended selection).
    Returns a sorted list of unique SKUs.
    """
    if not hasattr(self, "alias_tree"):
      return []
    sel = self.alias_tree.selection()
    if not sel:
      return []
    out = []
    for iid in sel:
      s = str(iid or "").strip()
      if s:
        out.append(s)
    out = sorted(set(out), key=lambda x: x.lower())
    return out

  def _get_selected_alias_sku(self) -> Optional[str]:
    if not hasattr(self, "alias_tree"):
      return None
    sel = self.alias_tree.selection()
    if not sel:
      return None
    return str(sel[0])

  def _load_selected_alias_into_form(self) -> None:
    sku = self._get_selected_alias_sku()
    if not sku:
      return
    name = self._get_alias_for_sku(sku)
    self.var_alias_sku.set(sku)
    self.var_alias_name.set(name)

  def _read_alias_form(self) -> Tuple[str, str]:
    sku = str(self.var_alias_sku.get() or "").strip()
    name = str(self.var_alias_name.get() or "").strip()
    if not sku:
      raise ValueError("Alias SKU is required")
    if not name:
      raise ValueError("Alias Name is required")
    return sku, name

  def _upsert_alias(self, sku: str, name: str) -> None:
    sku = str(sku or "").strip()
    name = str(name or "").strip()
    if not sku or not name:
      return

    found = False
    for a in self.aliases_list:
      if str(a.get("sku") or "").strip() == sku:
        a["name"] = name
        found = True
        break

    if not found:
      self.aliases_list.append({"sku": sku, "name": name})

    self.aliases_list.sort(key=lambda x: (str(x.get("name", "")).lower(), str(x.get("sku", "")).lower()))

  def _on_alias_add(self) -> None:
    if not self.project_data_path:
      messagebox.showerror("Project", "Select a Project Directory first.")
      return
    try:
      sku, name = self._read_alias_form()
    except Exception as e:
      messagebox.showerror("Invalid", str(e))
      return

    self._upsert_alias(sku, name)
    self._save_and_refresh()
    try:
      if hasattr(self, "alias_tree") and self.alias_tree.exists(sku):
        self.alias_tree.selection_set(sku)
        self.alias_tree.focus(sku)
        self.alias_tree.see(sku)
    except Exception:
      pass
    Log.ok(self.LOG_TAG, "Added/updated alias.", {"sku": sku})

  def _on_alias_delete_selected(self) -> None:
    if not self.project_data_path:
      messagebox.showerror("Project", "Select a Project Directory first.")
      return

    skus = self._get_selected_alias_skus()
    if not skus:
      messagebox.showinfo("Delete", "Select one or more alias rows first.")
      return

    preview = ", ".join(skus[:10])
    if len(skus) > 10:
      preview += f", … (+{len(skus) - 10} more)"

    if not messagebox.askyesno("Delete Alias", f"Delete {len(skus)} selected alias(es)?\n\nSKUs: {preview}"):
      return

    sku_set = set(skus)
    before = len(self.aliases_list)
    self.aliases_list = [a for a in self.aliases_list if str(a.get("sku") or "").strip() not in sku_set]
    after = len(self.aliases_list)

    self._save_and_refresh()
    self.var_alias_sku.set("")
    self.var_alias_name.set("")
    Log.warn(self.LOG_TAG, "Deleted aliases.", {"count": (before - after), "skus": skus})

  # -----------------------------------------------------------------------------
  # UI Actions
  # -----------------------------------------------------------------------------

  def _sync_type_fields(self) -> None:
    t = self.var_type.get()

    # Persist what the user typed into the appropriate backing var before swapping.
    cur = (self.var_unit_price.get() or "").strip()
    prev = getattr(self, "_last_type_for_unit", None)

    if prev == TX_PURCHASE:
      self.var_purchase_unit.set(cur or self.var_purchase_unit.get())
    elif prev == TX_SALE:
      self.var_sale_unit.set(cur or self.var_sale_unit.get())

    # Swap label + displayed value.
    if t == TX_PURCHASE:
      self.lbl_unit_price.configure(text="Purchase Unit Cost")
      self.var_unit_price.set(self.var_purchase_unit.get())
    else:
      self.lbl_unit_price.configure(text="Sale Unit Price")
      self.var_unit_price.set(self.var_sale_unit.get())

    self._last_type_for_unit = t

    # Disable field if no project loaded (matches prior behavior).
    self.entry_unit_price.configure(state=("normal" if self.project_data_path else "disabled"))

  def _on_add(self) -> None:
    if not self.project_data_path:
      messagebox.showerror("Project", "Select a Project Directory first.")
      return

    try:
      tx = self._read_form_to_transaction(existing_id=None)
    except Exception as e:
      messagebox.showerror("Invalid", str(e))
      return

    self.transactions.append(tx)
    self._save_and_refresh()
    self._select_tx_id(tx.id)
    Log.ok(self.LOG_TAG, "Added transaction.", {"id": tx.id, "sku": tx.sku, "type": tx.type})

  def _on_update_selected(self) -> None:
    if not self.project_data_path:
      messagebox.showerror("Project", "Select a Project Directory first.")
      return

    ids = self._get_selected_tx_ids()
    if not ids:
      messagebox.showinfo("Update", "Select a transaction row first.")
      return

    if len(ids) != 1:
      messagebox.showwarning("Update", "Please select exactly ONE transaction row to update.")
      return

    sel = ids[0]

    try:
      updated = self._read_form_to_transaction(existing_id=sel)
    except Exception as e:
      messagebox.showerror("Invalid", str(e))
      return

    for i, t in enumerate(self.transactions):
      if t.id == sel:
        # Preserve original insertion order for stable sorting.
        updated.created_order = t.created_order
        self.transactions[i] = updated
        break

    self._save_and_refresh()
    self._select_tx_id(sel)
    Log.ok(self.LOG_TAG, "Updated transaction.", {"id": sel})

  def _on_alias_update_selected(self) -> None:
    if not self.project_data_path:
      messagebox.showerror("Project", "Select a Project Directory first.")
      return

    skus = self._get_selected_alias_skus()
    if not skus:
      messagebox.showinfo("Update", "Select an alias row first.")
      return

    if len(skus) != 1:
      messagebox.showwarning("Update", "Please select exactly ONE alias row to update.")
      return

    sel_sku = skus[0]

    try:
      sku, name = self._read_alias_form()
    except Exception as e:
      messagebox.showerror("Invalid", str(e))
      return

    if sku != sel_sku:
      # Renaming SKU key: delete old, insert new
      self.aliases_list = [a for a in self.aliases_list if str(a.get("sku") or "").strip() != sel_sku]
    self._upsert_alias(sku, name)

    self._save_and_refresh()
    try:
      if hasattr(self, "alias_tree") and self.alias_tree.exists(sku):
        self.alias_tree.selection_set(sku)
        self.alias_tree.focus(sku)
        self.alias_tree.see(sku)
    except Exception:
      pass
    Log.ok(self.LOG_TAG, "Updated alias.", {"sku": sel_sku, "new_sku": sku})

  def _on_delete_selected(self) -> None:
    if not self.project_data_path:
      messagebox.showerror("Project", "Select a Project Directory first.")
      return

    ids = self._get_selected_tx_ids()
    if not ids:
      messagebox.showinfo("Delete", "Select one or more transaction rows first.")
      return

    preview = ", ".join(str(x) for x in ids[:10])
    if len(ids) > 10:
      preview += f", … (+{len(ids) - 10} more)"

    if not messagebox.askyesno("Delete", f"Delete {len(ids)} selected transaction(s)?\n\nIDs: {preview}"):
      return

    id_set = set(ids)
    before = len(self.transactions)
    self.transactions = [t for t in self.transactions if t.id not in id_set]
    after = len(self.transactions)

    self._save_and_refresh()
    Log.warn(self.LOG_TAG, "Deleted transactions.", {"count": (before - after), "ids": ids})

  def _load_selected_into_form(self) -> None:
    sel = self._get_selected_tx_id()
    if sel is None:
      return
    tx = next((t for t in self.transactions if t.id == sel), None)
    if not tx:
      return

    self.var_date.set(tx.date)
    self.var_sku.set(tx.sku)
    self.var_type.set(tx.type)
    self.var_qty.set(str(tx.qty))
    self.var_purchase_unit.set(f"{tx.purchase_unit_cost:.2f}")
    self.var_sale_unit.set(f"{tx.sale_unit_price:.2f}")

    if tx.type == TX_PURCHASE:
      self.var_unit_price.set(self.var_purchase_unit.get())
      self._last_type_for_unit = TX_PURCHASE
    else:
      self.var_unit_price.set(self.var_sale_unit.get())
      self._last_type_for_unit = TX_SALE

    self.var_note.set(tx.note or "")
    self._sync_type_fields()
    self._sync_alias_choice_from_sku()

  def _read_form_to_transaction(self, existing_id: Optional[int]) -> Transaction:
    date = parse_date(self.var_date.get())
    sku = (self.var_sku.get() or "").strip()
    if not sku:
      raise ValueError("SKU is required")

    ttype = self.var_type.get()
    if ttype not in (TX_PURCHASE, TX_SALE):
      raise ValueError("Type must be PURCHASE or SALE")

    try:
      qty = int(self.var_qty.get())
    except:
      raise ValueError("Qty must be an integer")
    if qty <= 0:
      raise ValueError("Qty must be > 0")

    purchase_unit = 0.0
    sale_unit = 0.0

    if ttype == TX_PURCHASE:
      try:
        purchase_unit = float(self.var_unit_price.get())
      except:
        raise ValueError("Purchase Unit Cost must be a number")
      if purchase_unit < 0:
        raise ValueError("Purchase Unit Cost must be >= 0")
    else:
      try:
        sale_unit = float(self.var_unit_price.get())
      except:
        raise ValueError("Sale Unit Price must be a number")
      if sale_unit < 0:
        raise ValueError("Sale Unit Price must be >= 0")

    note = (self.var_note.get() or "").strip()

    if existing_id is None:
      tx_id = self.next_id
      self.next_id += 1
      created_order = self.next_created_order
      self.next_created_order += 1
    else:
      tx_id = existing_id
      created_order = 0  # overwritten by caller

    return Transaction(
      id=tx_id,
      date=date,
      sku=sku,
      type=ttype,
      qty=qty,
      purchase_unit_cost=purchase_unit,
      sale_unit_price=sale_unit,
      note=note,
      created_order=created_order,
    )

  # -----------------------------------------------------------------------------
  # Refresh / Sort
  # -----------------------------------------------------------------------------

  def _normalize_sort(self) -> None:
    self.transactions.sort(key=lambda t: (t.date, t.created_order, t.id))

  def _refresh_all(self) -> None:
    rows, overview = self.engine.compute(self.transactions)
    self._refresh_tx_table(rows)
    self._refresh_overview_table(overview, rows)

  def _refresh_tx_table(self, rows: List[Dict[str, Any]]) -> None:
    # If a hover-tooltip is currently visible, kill it before rebuilding rows.
    try:
      if hasattr(self, "_tx_tree_tip_hide") and callable(self._tx_tree_tip_hide):
        self._tx_tree_tip_hide()
    except Exception:
      pass

    self.tx_tree.delete(*self.tx_tree.get_children())

    # Most recent first (date DESC). Tie-breaker: higher ID first.
    rows_sorted = sorted(
      rows,
      key=lambda r: (str(r.get("date", "")), int(r.get("id", 0) or 0)),
      reverse=True,
    )

    for i, r in enumerate(rows_sorted):
      # Fake "cell padding" for left-aligned text fields (Treeview has no per-cell padding on Windows ttk)
      pad_l = "  "  # 2 spaces

      sku = str(r.get("sku") or "").strip()
      alias = self._get_alias_for_sku(sku)

      values = (
        r["id"],
        f"{pad_l}{r['date']}",
        f"{pad_l}{sku}",
        f"{pad_l}{alias}" if alias else "",
        r["type"],
        r["qty"],
        money(r["purchase_unit_cost"]) if r["type"] == TX_PURCHASE else "",
        money(r["sale_unit_price"]) if r["type"] == TX_SALE else "",
        money(r["purchase_total_cost"]) if r["type"] == TX_PURCHASE else money(0.0),
        money(r["prev_avg_cost"]),
        r["onhand_qty"],
        money(r["avg_cost_after"]),
        money(r["cogs"]),
        money(r["onhand_cost"]),
        money(r["sales_rev"]),
        money(r["gross_profit"]),
        f"{pad_l}{(r['note'] or '')}" if (r["note"] or "") else "",
      )

      # Zebra striping + "error" tint when inventory goes negative after this row
      is_even = (i % 2) == 0
      zebra_tag = "even" if is_even else "odd"

      tag = zebra_tag
      if int(r.get("onhand_qty", 0) or 0) < 0:
        tag = "status_error_even" if is_even else "status_error_odd"

      self.tx_tree.insert("", "end", iid=str(r["id"]), values=values, tags=(tag,))

    # Keep "Update Selected" disabled unless exactly one row is selected.
    try:
      self._sync_tx_update_selected_state()
    except Exception:
      pass

  # ---------------------------------------------------------------------------
  # Overview view (Inventory vs Monthly)
  # ---------------------------------------------------------------------------

  def _on_overview_view_changed(self) -> None:
    self._configure_overview_tree_for_view()
    self._refresh_all()

  def _configure_overview_tree_for_view(self) -> None:
    mode = (self.ov_view_var.get() or "Inventory").strip()

    if mode == "Monthly":
      columns = ["month", "month_date", "purchase_cost", "sales_amount", "cogs"]
      headings = {
        "month": "Month",
        "month_date": "Month Date",
        "purchase_cost": "Purchase Cost",
        "sales_amount": "Sales Amount",
        "cogs": "COGS",
      }
      widths = {
        "month": 140,
        "month_date": 140,
        "purchase_cost": 170,
        "sales_amount": 170,
        "cogs": 150,
      }
      col_anchor = {
        "month": "w",
        "month_date": "w",
        "purchase_cost": "e",
        "sales_amount": "e",
        "cogs": "e",
      }
    else:
      columns = ["sku", "alias", "onhand_qty", "avg_cost", "onhand_cost", "last_tx_date", "last_sale_price", "status"]
      headings = {
        "sku": "SKU",
        "alias": "Alias",
        "onhand_qty": "OnHand Qty",
        "avg_cost": "Avg Cost",
        "onhand_cost": "OnHand Cost",
        "last_tx_date": "Last Tx Date",
        "last_sale_price": "Last Sale Price",
        "status": "Status",
      }
      widths = {
        "sku": 220,
        "alias": 260,
        "onhand_qty": 120,
        "avg_cost": 120,
        "onhand_cost": 170,
        "last_tx_date": 150,
        "last_sale_price": 150,
        "status": 220,
      }
      col_anchor = {
        "sku": "w",
        "alias": "w",
        "onhand_qty": "e",
        "avg_cost": "e",
        "onhand_cost": "e",
        "last_tx_date": "w",
        "last_sale_price": "e",
        "status": "center",
      }

    # Apply column set
    self.ov_tree["columns"] = columns

    head_anchor = {
      k: ("center" if v == "center" else ("e" if v == "e" else "w"))
      for k, v in col_anchor.items()
    }

    heading_gutter = "  "  # visual separation between adjacent headers

    for ci, c in enumerate(columns):
      base_text = headings.get(c, c)
      head_text = (f"{base_text}{heading_gutter}" if ci < (len(columns) - 1) else base_text)

      self.ov_tree.heading(
        c,
        text=head_text,
        anchor=head_anchor.get(c, "w"),
      )
      self.ov_tree.column(
        c,
        width=widths.get(c, 120),
        minwidth=32,
        anchor=col_anchor.get(c, "w"),
        stretch=(mode == "Monthly"),
      )

    # Fit after reconfig
    try:
      if hasattr(self, "_ov_fit_columns_now") and callable(self._ov_fit_columns_now):
        self.after(1, self._ov_fit_columns_now)
    except Exception:
      pass

  def _compute_monthly_report_rows(self, rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Build month aggregate rows from computed per-transaction rows.

    Columns:
      - month: YYYY-MM
      - month_date: YYYY-MM-01
      - purchase_cost: sum(purchase_total_cost) for PURCHASE rows
      - sales_amount: sum(sales_rev) for SALE rows
      - cogs: sum(cogs) for SALE rows
    """
    bucket: Dict[str, Dict[str, float]] = {}

    for r in (rows or []):
      d = str(r.get("date") or "")
      if len(d) < 7:
        continue
      month = d[:7]

      if month not in bucket:
        bucket[month] = {"purchase_cost": 0.0, "sales_amount": 0.0, "cogs": 0.0}

      if r.get("type") == TX_PURCHASE:
        bucket[month]["purchase_cost"] += float(r.get("purchase_total_cost") or 0.0)
      elif r.get("type") == TX_SALE:
        bucket[month]["sales_amount"] += float(r.get("sales_rev") or 0.0)
        bucket[month]["cogs"] += float(r.get("cogs") or 0.0)

    out: List[Dict[str, Any]] = []
    for month in sorted(bucket.keys(), reverse=True):
      out.append({
        "month": month,
        "month_date": f"{month}-01",
        "purchase_cost": float(bucket[month]["purchase_cost"]),
        "sales_amount": float(bucket[month]["sales_amount"]),
        "cogs": float(bucket[month]["cogs"]),
      })
    return out

  def _refresh_overview_table(self, overview: Dict[str, Dict[str, Any]], rows: List[Dict[str, Any]]) -> None:
    mode = (self.ov_view_var.get() or "Inventory").strip()
    if mode == "Monthly":
      month_rows = self._compute_monthly_report_rows(rows)
      self._refresh_overview_table_monthly(month_rows)
    else:
      self._refresh_overview_table_inventory(overview)

  def _refresh_overview_table_inventory(self, overview: Dict[str, Dict[str, Any]]) -> None:
    try:
      if hasattr(self, "_ov_tree_tip_hide") and callable(self._ov_tree_tip_hide):
        self._ov_tree_tip_hide()
    except Exception:
      pass

    self.ov_tree.delete(*self.ov_tree.get_children())

    def _ov_sort_key(sku_key: str):
      s = overview.get(sku_key) or {}
      qty = int(s.get("onhand_qty", 0) or 0)
      status = str(s.get("status") or "").strip().upper()

      # Group order:
      #   0 = NEGATIVE (top)
      #   1 = IN STOCK
      #   2 = OUT (bottom)
      if qty < 0 or "NEGATIVE" in status:
        grp = 0
      elif qty == 0 or status == "OUT":
        grp = 2
      else:
        grp = 1

      sku_norm = str(s.get("sku") or sku_key or "").strip()
      alias = self._get_alias_for_sku(sku_norm)
      alias_norm = str(alias or "").strip().lower()
      sku_norm_l = sku_norm.lower()

      # Within NEGATIVE: most negative first (e.g., -10 before -1)
      neg_qty_key = qty if grp == 0 else 0

      return (grp, neg_qty_key, alias_norm, sku_norm_l)

    sorted_skus = sorted(overview.keys(), key=_ov_sort_key)

    for i, sku in enumerate(sorted_skus):
      s = overview[sku]
      pad_l = "  "  # 2 spaces

      alias = self._get_alias_for_sku(str(s.get("sku") or "").strip())

      values = (
        f"{pad_l}{s['sku']}",
        f"{pad_l}{alias}" if alias else "",
        s["onhand_qty"],
        money(s["avg_cost"]),
        money(s["onhand_cost"]),
        f"{pad_l}{s['last_tx_date']}" if s["last_tx_date"] else "",
        money(s["last_sale_price"]) if s["last_sale_price"] else "",
        s["status"],
      )

      is_even = (i % 2) == 0
      zebra_tag = "even" if is_even else "odd"

      tag = zebra_tag
      status = str(s.get("status") or "").strip().upper()
      if "NEGATIVE" in status or int(s.get("onhand_qty", 0) or 0) < 0:
        tag = "status_error_even" if is_even else "status_error_odd"
      elif status == "IN STOCK":
        tag = "status_done_even" if is_even else "status_done_odd"

      self.ov_tree.insert("", "end", iid=sku, values=values, tags=(tag,))

  def _refresh_overview_table_monthly(self, month_rows: List[Dict[str, Any]]) -> None:
    try:
      if hasattr(self, "_ov_tree_tip_hide") and callable(self._ov_tree_tip_hide):
        self._ov_tree_tip_hide()
    except Exception:
      pass

    self.ov_tree.delete(*self.ov_tree.get_children())

    for i, r in enumerate(month_rows or []):
      pad_l = "  "  # 2 spaces

      values = (
        f"{pad_l}{r['month']}",
        f"{pad_l}{r['month_date']}",
        money(float(r.get("purchase_cost") or 0.0)),
        money(float(r.get("sales_amount") or 0.0)),
        money(float(r.get("cogs") or 0.0)),
      )

      is_even = (i % 2) == 0
      tag = "even" if is_even else "odd"
      self.ov_tree.insert("", "end", iid=str(r["month"]), values=values, tags=(tag,))

  def _export_overview_csv(self) -> None:
    if not self.project_data_path:
      messagebox.showerror("Project", "Select a Project Directory first.")
      return

    mode = (self.ov_view_var.get() or "Inventory").strip()
    initialfile = "overview_monthly.csv" if mode == "Monthly" else "overview_inventory.csv"

    path = filedialog.asksaveasfilename(
      title="Export CSV",
      defaultextension=".csv",
      filetypes=[("CSV", "*.csv")],
      initialfile=initialfile,
      initialdir=self.project_dir or None,
    )
    if not path:
      return

    rows, overview = self.engine.compute(self.transactions)

    if mode == "Monthly":
      data_rows = self._compute_monthly_report_rows(rows)
      headers = ["month", "month_date", "purchase_cost", "sales_amount", "cogs"]
    else:
      data_rows = []
      for sku in sorted(overview.keys()):
        s = overview[sku]
        data_rows.append({
          "sku": s["sku"],
          "alias": self._get_alias_for_sku(str(s.get("sku") or "").strip()),
          "onhand_qty": s["onhand_qty"],
          "avg_cost": float(s["avg_cost"]),
          "onhand_cost": float(s["onhand_cost"]),
          "last_tx_date": s["last_tx_date"],
          "last_sale_price": float(s["last_sale_price"]),
          "status": s["status"],
        })
      headers = ["sku", "alias", "onhand_qty", "avg_cost", "onhand_cost", "last_tx_date", "last_sale_price", "status"]

    try:
      with open(path, "w", encoding="utf-8", newline="") as f:
        f.write(",".join(headers) + "\n")
        for r in data_rows:
          line = []
          for h in headers:
            v = r.get(h, "")
            if isinstance(v, str):
              if "," in v or '"' in v:
                v = '"' + v.replace('"', '""') + '"'
              line.append(v)
            else:
              line.append(str(v))
          f.write(",".join(line) + "\n")
      Log.ok(self.LOG_TAG, "Exported overview CSV.", {"path": path, "mode": mode})
      messagebox.showinfo("Export", f"Exported to:\n{path}")
    except Exception as e:
      Log.error(self.LOG_TAG, "Overview CSV export failed.", {"error": str(e)})
      messagebox.showerror("Export Failed", str(e))

  # -----------------------------------------------------------------------------
  # Selection Helpers
  # -----------------------------------------------------------------------------

  def _set_ctk_button_enabled(self, btn: Any, enabled: bool) -> None:
    """Enable/disable a CTkButton-like widget (best-effort)."""
    if btn is None:
      return
    try:
      btn.configure(state=("normal" if enabled else "disabled"))
    except Exception:
      pass

  def _sync_tx_update_selected_state(self) -> None:
    """Disable Transactions 'Update Selected' unless exactly one row is selected."""
    try:
      has_project = bool(self.project_data_path)
      sel_count = len(self._get_selected_tx_ids())
      self._set_ctk_button_enabled(getattr(self, "btn_update", None), bool(has_project and sel_count == 1))
    except Exception:
      pass

  def _sync_alias_update_selected_state(self) -> None:
    """Disable Aliases 'Update Selected' unless exactly one row is selected."""
    try:
      has_project = bool(self.project_data_path)
      sel_count = len(self._get_selected_alias_skus())
      self._set_ctk_button_enabled(getattr(self, "btn_alias_update", None), bool(has_project and sel_count == 1))
    except Exception:
      pass

  def _sync_update_selected_buttons_state(self) -> None:
    """Sync all 'Update Selected' button states across views (best-effort)."""
    self._sync_tx_update_selected_state()
    self._sync_alias_update_selected_state()

  def _get_selected_tx_id(self) -> Optional[int]:

    """
    Get the "primary" selected transaction ID.
    Keeps legacy single-select call sites working.
    """
    ids = self._get_selected_tx_ids()
    return ids[0] if ids else None

  def _get_selected_tx_ids(self) -> List[int]:
    """
    Get all selected transaction IDs (extended selection).
    Returns a sorted list of ints.
    """
    sel = self.tx_tree.selection()
    if not sel:
      return []
    out: List[int] = []
    for iid in sel:
      try:
        out.append(int(iid))
      except Exception:
        pass
    out = sorted(set(out))
    return out

  def _select_tx_id(self, tx_id: int) -> None:
    iid = str(tx_id)
    if self.tx_tree.exists(iid):
      self.tx_tree.selection_set(iid)
      self.tx_tree.focus(iid)
      self.tx_tree.see(iid)

  # -----------------------------------------------------------------------------
  # Export
  # -----------------------------------------------------------------------------

  def _export_csv(self) -> None:
    if not self.project_data_path:
      messagebox.showerror("Project", "Select a Project Directory first.")
      return

    path = filedialog.asksaveasfilename(
      title="Export CSV",
      defaultextension=".csv",
      filetypes=[("CSV", "*.csv")],
      initialfile="transactions_export.csv",
      initialdir=self.project_dir or None,
    )
    if not path:
      return

    rows, _ = self.engine.compute(self.transactions)

    headers = [
      "id","date","sku","alias","type","qty",
      "purchase_unit_cost","sale_unit_price",
      "purchase_total_cost","prev_avg_cost",
      "onhand_qty","avg_cost_after",
      "cogs","onhand_cost","sales_rev","gross_profit",
      "note"
    ]

    try:
      with open(path, "w", encoding="utf-8", newline="") as f:
        f.write(",".join(headers) + "\n")
        for r in rows:
          # add alias on the fly (not part of engine rows)
          sku = str(r.get("sku") or "").strip()
          r2 = dict(r)
          r2["alias"] = self._get_alias_for_sku(sku)

          line = []
          for h in headers:
            v = r2.get(h, "")
            if isinstance(v, str):
              if "," in v or '"' in v:
                v = '"' + v.replace('"', '""') + '"'
              line.append(v)
            else:
              line.append(str(v))
          f.write(",".join(line) + "\n")
      Log.ok(self.LOG_TAG, "Exported CSV.", {"path": path})
      messagebox.showinfo("Export", f"Exported to:\n{path}")
    except Exception as e:
      Log.error(self.LOG_TAG, "CSV export failed.", {"error": str(e)})
      messagebox.showerror("Export Failed", str(e))


# =============================================================================
# [🚀 Main]
# =============================================================================

def main() -> None:
  app = InventoryApp()
  app.mainloop()

if __name__ == "__main__":
  main()
