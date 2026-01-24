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

  def _build_ui(self) -> None:
    self.grid_rowconfigure(1, weight=1)
    self.grid_columnconfigure(0, weight=1)

    # Top project bar (like your attached script)
    project_bar = ctk.CTkFrame(self)
    project_bar.grid(row=0, column=0, sticky="ew", padx=14, pady=(14, 8))
    project_bar.grid_columnconfigure(1, weight=1)

    ctk.CTkLabel(project_bar, text="Project Directory:").grid(row=0, column=0, padx=(10, 6), pady=10, sticky="w")

    self.project_dir_var = tk.StringVar(value=(self.recent_project_dirs[0] if self.recent_project_dirs else ""))
    self.project_combo = ctk.CTkComboBox(
      project_bar,
      variable=self.project_dir_var,
      values=list(self.recent_project_dirs),
      state="normal",
      command=lambda _choice: self._on_project_combo_selected(),
    )
    self.project_combo.grid(row=0, column=1, padx=6, pady=10, sticky="ew")

    ctk.CTkButton(project_bar, text="Browse…", width=110, command=self._on_browse_project).grid(row=0, column=2, padx=6, pady=10)
    ctk.CTkButton(project_bar, text="Load/Refresh", width=130, command=self._on_load_project).grid(row=0, column=3, padx=6, pady=10)
    ctk.CTkButton(project_bar, text="Clear History", width=120, command=self._on_clear_history).grid(row=0, column=4, padx=(6, 10), pady=10)

    # Tabs
    self.tabs = ctk.CTkTabview(self)
    self.tabs.grid(row=1, column=0, sticky="nsew", padx=14, pady=(0, 14))

    self.tab_tx = self.tabs.add("Transactions")
    self.tab_ov = self.tabs.add("Overview")
    self.tab_alias = self.tabs.add("Aliases")

    self._build_transactions_tab()
    self._build_overview_tab()
    self._build_aliases_tab()

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
    self.entry_date = ctk.CTkEntry(form_row, textvariable=self.var_date, width=120)
    self.entry_date.grid(row=0, column=1, padx=6, pady=10)

    ctk.CTkLabel(form_row, text="SKU").grid(row=0, column=2, padx=(14, 6), pady=10)
    self.entry_sku = ctk.CTkEntry(form_row, textvariable=self.var_sku, width=200)
    self.entry_sku.grid(row=0, column=3, padx=6, pady=10)

    ctk.CTkLabel(form_row, text="Alias").grid(row=0, column=4, padx=(14, 6), pady=10)
    self.alias_combo = ctk.CTkOptionMenu(
      form_row,
      variable=self.var_alias_choice,
      values=[""],  # CTkOptionMenu needs at least 1 value
      width=260,
      command=lambda _choice: self._on_alias_selected_in_tx_form(),
    )

    self.alias_combo.grid(row=0, column=5, padx=6, pady=10)

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

    self.lbl_unit_price = ctk.CTkLabel(form_row, text="Purchase Unit Cost")
    self.lbl_unit_price.grid(row=0, column=10, padx=(14, 6), pady=10)

    self.entry_unit_price = ctk.CTkEntry(form_row, textvariable=self.var_unit_price, width=120)
    self.entry_unit_price.grid(row=0, column=11, padx=6, pady=10)

    ctk.CTkLabel(action_row, text="Note").grid(row=0, column=0, padx=(10, 6), pady=(0, 10))
    self.entry_note = ctk.CTkEntry(action_row, textvariable=self.var_note)
    self.entry_note.grid(row=0, column=1, sticky="ew", padx=6, pady=(0, 10))

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

    def _tree_on_hover(event) -> None:
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

    self.tx_tree.bind("<<TreeviewSelect>>", lambda _e: self._load_selected_into_form())
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

    def _tree_on_hover(event) -> None:
      iid = self.ov_tree.identify_row(event.y)
      col = self.ov_tree.identify_column(event.x)  # "#1", "#2", ...
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

    ctk.CTkLabel(form, text="Name").grid(row=0, column=2, padx=(14, 6), pady=10, sticky="w")
    self.var_alias_name = tk.StringVar(value="")
    self.entry_alias_name = ctk.CTkEntry(form, textvariable=self.var_alias_name, width=360)
    self.entry_alias_name.grid(row=0, column=3, padx=6, pady=10, sticky="w")

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

    self.alias_tree.bind("<<TreeviewSelect>>", lambda _e: self._load_selected_alias_into_form())

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

    # Alias dropdown (hard dropdown: no typing)
    for w in [getattr(self, "alias_combo", None)]:
      if w is None:
        continue
      try:
        w.configure(state=("readonly" if enabled else "disabled"))
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
    if not hasattr(self, "alias_combo"):
      return
    values = [""] + self._build_alias_display_values()
    try:
      self.alias_combo.configure(values=values)
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
        self.var_sku.set(sku)
        try:
          self.entry_qty.focus_set()
        except Exception:
          pass
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

  def _on_alias_update_selected(self) -> None:
    if not self.project_data_path:
      messagebox.showerror("Project", "Select a Project Directory first.")
      return
    sel_sku = self._get_selected_alias_sku()
    if not sel_sku:
      messagebox.showinfo("Update", "Select an alias row first.")
      return
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

    sel = self._get_selected_tx_id()
    if sel is None:
      messagebox.showinfo("Update", "Select a transaction row first.")
      return

    try:
      updated = self._read_form_to_transaction(existing_id=sel)
    except Exception as e:
      messagebox.showerror("Invalid", str(e))
      return

    for i, t in enumerate(self.transactions):
      if t.id == sel:
        updated.created_order = t.created_order
        self.transactions[i] = updated
        break

    self._save_and_refresh()
    self._select_tx_id(sel)
    Log.ok(self.LOG_TAG, "Updated transaction.", {"id": sel})

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

    for i, sku in enumerate(sorted(overview.keys())):
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
