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

    self.LOG_TAG = "[🧮 Inventory]"
    self.title("Inventory (Weighted Avg Cost) - CustomTkinter")
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

    self._build_ui()

    # Auto-load first recent project if available
    if self.recent_project_dirs:
      self.project_dir_var.set(self.recent_project_dirs[0])
      self._load_project_dir(self.recent_project_dirs[0])
    else:
      self._refresh_all()
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

  def _load_transactions_from_file(self, path: str) -> List[Transaction]:
    if not os.path.exists(path):
      return []
    with open(path, "r", encoding="utf-8") as f:
      raw = json.load(f)
    txs: List[Transaction] = []
    for item in raw.get("transactions", []):
      txs.append(Transaction(**item))
    return txs

  def _save_transactions_to_file(self, path: str, txs: List[Transaction]) -> None:
    payload = {"transactions": [asdict(t) for t in txs]}
    _write_json_atomic(path, payload)

  def _load_project_dir(self, project_dir: str) -> None:
    p = os.path.abspath(project_dir)
    if not os.path.isdir(p):
      messagebox.showerror("Project", "Project directory is missing or invalid.")
      return

    self.project_dir = p
    self.project_data_path = self._project_data_file_for_dir(p)

    self.transactions = self._load_transactions_from_file(self.project_data_path)
    self._normalize_sort()

    self.next_id = (max([t.id for t in self.transactions], default=0) + 1)
    self.next_created_order = (max([t.created_order for t in self.transactions], default=0) + 1)

    self._remember_project_dir(p)
    self._set_tx_controls_enabled(True)
    self._refresh_all()

    Log.ok(self.LOG_TAG, "Loaded project.", {"project_dir": p, "tx_count": len(self.transactions)})

  def _save_and_refresh(self) -> None:
    if not self.project_data_path:
      messagebox.showerror("Project", "Select a Project Directory first.")
      return
    self._normalize_sort()
    self._save_transactions_to_file(self.project_data_path, self.transactions)
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

    self._build_transactions_tab()
    self._build_overview_tab()

  def _build_transactions_tab(self) -> None:
    self.tab_tx.grid_rowconfigure(1, weight=1)
    self.tab_tx.grid_columnconfigure(0, weight=1)

    controls = ctk.CTkFrame(self.tab_tx)
    controls.grid(row=0, column=0, sticky="ew", padx=10, pady=(10, 6))
    controls.grid_columnconfigure(12, weight=1)

    self.var_date = tk.StringVar(value=datetime.now().strftime("%Y-%m-%d"))
    self.var_sku = tk.StringVar(value="")
    self.var_type = tk.StringVar(value=TX_PURCHASE)
    self.var_qty = tk.StringVar(value="1")
    self.var_purchase_unit = tk.StringVar(value="1.00")
    self.var_sale_unit = tk.StringVar(value="3.00")
    self.var_note = tk.StringVar(value="")

    ctk.CTkLabel(controls, text="Date").grid(row=0, column=0, padx=(10, 6), pady=10)
    self.entry_date = ctk.CTkEntry(controls, textvariable=self.var_date, width=120)
    self.entry_date.grid(row=0, column=1, padx=6, pady=10)

    ctk.CTkLabel(controls, text="SKU").grid(row=0, column=2, padx=(14, 6), pady=10)
    self.entry_sku = ctk.CTkEntry(controls, textvariable=self.var_sku, width=220)
    self.entry_sku.grid(row=0, column=3, padx=6, pady=10)

    ctk.CTkLabel(controls, text="Type").grid(row=0, column=4, padx=(14, 6), pady=10)
    self.opt_type = ctk.CTkOptionMenu(
      controls,
      values=[TX_PURCHASE, TX_SALE],
      variable=self.var_type,
      width=140,
      command=lambda _: self._sync_type_fields(),
    )
    self.opt_type.grid(row=0, column=5, padx=6, pady=10)

    ctk.CTkLabel(controls, text="Qty").grid(row=0, column=6, padx=(14, 6), pady=10)
    self.entry_qty = ctk.CTkEntry(controls, textvariable=self.var_qty, width=80)
    self.entry_qty.grid(row=0, column=7, padx=6, pady=10)

    ctk.CTkLabel(controls, text="Purchase Unit Cost").grid(row=0, column=8, padx=(14, 6), pady=10)
    self.entry_purchase_unit = ctk.CTkEntry(controls, textvariable=self.var_purchase_unit, width=120)
    self.entry_purchase_unit.grid(row=0, column=9, padx=6, pady=10)

    ctk.CTkLabel(controls, text="Sale Unit Price").grid(row=0, column=10, padx=(14, 6), pady=10)
    self.entry_sale_unit = ctk.CTkEntry(controls, textvariable=self.var_sale_unit, width=120)
    self.entry_sale_unit.grid(row=0, column=11, padx=6, pady=10)

    ctk.CTkLabel(controls, text="Note").grid(row=1, column=0, padx=(10, 6), pady=(0, 10))
    self.entry_note = ctk.CTkEntry(controls, textvariable=self.var_note, width=720)
    self.entry_note.grid(row=1, column=1, columnspan=8, sticky="w", padx=6, pady=(0, 10))

    self.btn_add = ctk.CTkButton(controls, text="Add", command=self._on_add)
    self.btn_add.grid(row=1, column=9, padx=6, pady=(0, 10), sticky="ew")

    self.btn_update = ctk.CTkButton(controls, text="Update Selected", command=self._on_update_selected)
    self.btn_update.grid(row=1, column=10, padx=6, pady=(0, 10), sticky="ew")

    self.btn_delete = ctk.CTkButton(
      controls,
      text="Delete Selected",
      fg_color="#8B2D2D",
      hover_color="#A53636",
      command=self._on_delete_selected,
    )
    self.btn_delete.grid(row=1, column=11, padx=6, pady=(0, 10), sticky="ew")

    self.btn_export = ctk.CTkButton(controls, text="Export CSV", command=self._export_csv)
    self.btn_export.grid(row=1, column=12, padx=6, pady=(0, 10), sticky="e")

    # ---------------------------------------------------------
    # Transactions Table (ttk.Treeview) — gitea-like behavior
    # - Zebra striping using CTk theme colors
    # - Hover tooltip shows ONLY the hovered cell value
    # - Both scrollbars (v/h)
    # ---------------------------------------------------------

    table_frame = ctk.CTkFrame(self.tab_tx)
    table_frame.grid(row=1, column=0, sticky="nsew", padx=10, pady=(6, 10))
    table_frame.grid_rowconfigure(0, weight=1)
    table_frame.grid_columnconfigure(0, weight=1)
    table_frame.grid_rowconfigure(1, weight=0)

    columns = [
      "id", "date", "sku", "type", "qty",
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
      "id": 60, "date": 120, "sku": 220, "type": 120, "qty": 80,
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
    # Fit columns: let ONLY ["sku", "note"] stretch when possible.
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

      stretch_cols = ("sku", "note")
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

      try:
        w_sku = int(self.tx_tree.column("sku", "width") or 1)
      except Exception:
        w_sku = widths.get("sku", 220)
      try:
        w_note = int(self.tx_tree.column("note", "width") or 1)
      except Exception:
        w_note = widths.get("note", 320)

      total = max(w_sku + w_note, 1)
      min_w = 32

      new_sku = max(min_w, int(stretch_avail * (w_sku / total)))
      new_note = max(min_w, int(stretch_avail - new_sku))

      self.tx_tree.column("sku", width=new_sku)
      self.tx_tree.column("note", width=new_note)

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
    controls.grid_columnconfigure(5, weight=1)

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
    self.btn_ov_export.grid(row=0, column=2, padx=6, pady=10, sticky="w")

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
        stretch_cols = [c for c in ["month"] if c in cols]
      else:
        stretch_cols = [c for c in ["sku", "status"] if c in cols]

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
    self.next_id = 1
    self.next_created_order = 1
    self._set_tx_controls_enabled(False)
    self._refresh_all()

  # -----------------------------------------------------------------------------
  # Enable/disable controls if no project loaded
  # -----------------------------------------------------------------------------

  def _set_tx_controls_enabled(self, enabled: bool) -> None:
    state_entry = "normal" if enabled else "disabled"
    state_btn = "normal" if enabled else "disabled"

    for w in [self.entry_date, self.entry_sku, self.entry_qty, self.entry_purchase_unit, self.entry_sale_unit, self.entry_note]:
      try:
        w.configure(state=state_entry)
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

    # Overview tab controls (optional until UI built)
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

  # -----------------------------------------------------------------------------
  # UI Actions
  # -----------------------------------------------------------------------------

  def _sync_type_fields(self) -> None:
    t = self.var_type.get()
    if t == TX_PURCHASE:
      self.entry_purchase_unit.configure(state="normal" if self.project_data_path else "disabled")
      self.entry_sale_unit.configure(state="disabled")
    else:
      self.entry_purchase_unit.configure(state="disabled")
      self.entry_sale_unit.configure(state="normal" if self.project_data_path else "disabled")

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

    sel = self._get_selected_tx_id()
    if sel is None:
      messagebox.showinfo("Delete", "Select a transaction row first.")
      return

    if not messagebox.askyesno("Delete", f"Delete transaction ID {sel}?"):
      return

    self.transactions = [t for t in self.transactions if t.id != sel]
    self._save_and_refresh()
    Log.warn(self.LOG_TAG, "Deleted transaction.", {"id": sel})

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
    self.var_note.set(tx.note or "")
    self._sync_type_fields()

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
        purchase_unit = float(self.var_purchase_unit.get())
      except:
        raise ValueError("Purchase Unit Cost must be a number")
      if purchase_unit < 0:
        raise ValueError("Purchase Unit Cost must be >= 0")
    else:
      try:
        sale_unit = float(self.var_sale_unit.get())
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

    for i, r in enumerate(rows):
      # Fake "cell padding" for left-aligned text fields (Treeview has no per-cell padding on Windows ttk)
      pad_l = "  "  # 2 spaces

      values = (
        r["id"],
        f"{pad_l}{r['date']}",
        f"{pad_l}{r['sku']}",
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
      columns = ["sku", "onhand_qty", "avg_cost", "onhand_cost", "last_tx_date", "last_sale_price", "status"]
      headings = {
        "sku": "SKU",
        "onhand_qty": "OnHand Qty",
        "avg_cost": "Avg Cost",
        "onhand_cost": "OnHand Cost",
        "last_tx_date": "Last Tx Date",
        "last_sale_price": "Last Sale Price",
        "status": "Status",
      }
      widths = {
        "sku": 240,
        "onhand_qty": 120,
        "avg_cost": 120,
        "onhand_cost": 170,
        "last_tx_date": 150,
        "last_sale_price": 150,
        "status": 220,
      }
      col_anchor = {
        "sku": "w",
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
        stretch=False,
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
    for month in sorted(bucket.keys()):
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

      values = (
        f"{pad_l}{s['sku']}",
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
          "onhand_qty": s["onhand_qty"],
          "avg_cost": float(s["avg_cost"]),
          "onhand_cost": float(s["onhand_cost"]),
          "last_tx_date": s["last_tx_date"],
          "last_sale_price": float(s["last_sale_price"]),
          "status": s["status"],
        })
      headers = ["sku", "onhand_qty", "avg_cost", "onhand_cost", "last_tx_date", "last_sale_price", "status"]

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
    sel = self.tx_tree.selection()
    if not sel:
      return None
    try:
      return int(sel[0])
    except:
      return None

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
      "id","date","sku","type","qty",
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
