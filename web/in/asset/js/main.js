(function () {
  const STORAGE_KEY = "inventory-transaction-manager-web";

  const BUILTIN_FIELDS = [
    { key: "date", label: "Date", source: "system", type: "date", hideable: false, enumEditable: false, removable: false, required: true },
    { key: "sku", label: "SKU", source: "system", type: "text", hideable: false, enumEditable: false, removable: false, required: true },
    { key: "type", label: "Type", source: "system", type: "enum", options: ["PURCHASE", "SALE"], hideable: false, enumEditable: false, removable: false, required: true },
    { key: "qty", label: "Qty", source: "system", type: "number", hideable: false, enumEditable: false, removable: false, required: true },
    { key: "purchase_unit_cost", label: "Purchase Unit Cost", source: "system", type: "number", hideable: false, enumEditable: false, removable: false },
    { key: "sale_unit_price", label: "Sale Unit Price", source: "system", type: "number", hideable: false, enumEditable: false, removable: false },
    { key: "note", label: "Note", source: "system", type: "text", hideable: true, enumEditable: false, removable: true },
    { key: "alias", label: "Alias", source: "system", type: "text", hideable: true, enumEditable: false, removable: true, computed: true }
  ];

  const OVERVIEW_FIELDS = [
    "sku",
    "name",
    "alias",
    "onhand_qty",
    "avg_cost_after",
    "onhand_cost",
    "last_tx_date",
    "last_sale_price",
    "status"
  ];

  let state = loadState();

  document.addEventListener("DOMContentLoaded", init);

  function init() {
    bindTabs();
    bindGlobalActions();
    bindForms();
    hydrateBrand();
    renderAll();
  }

  function defaultState() {
    return {
      transactions: [],
      aliases: {},
      custom_fields_schema: [],
      field_overrides: {}
    };
  }

  function loadState() {
    try {
      const raw = localStorage.getItem(STORAGE_KEY);
      if (!raw) {
        return defaultState();
      }
      return normalizeState(JSON.parse(raw));
    } catch (error) {
      console.warn("Failed to load local state", error);
      return defaultState();
    }
  }

  function normalizeState(value) {
    const fallback = defaultState();
    return {
      transactions: Array.isArray(value.transactions) ? value.transactions : fallback.transactions,
      aliases: isPlainObject(value.aliases) ? value.aliases : fallback.aliases,
      custom_fields_schema: Array.isArray(value.custom_fields_schema) ? value.custom_fields_schema : fallback.custom_fields_schema,
      field_overrides: isPlainObject(value.field_overrides) ? value.field_overrides : fallback.field_overrides
    };
  }

  function saveState() {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(state, null, 2));
  }

  function bindTabs() {
    document.querySelectorAll("[data-tab]").forEach((button) => {
      button.addEventListener("click", () => {
        const tab = button.dataset.tab;
        document.querySelectorAll("[data-tab]").forEach((item) => item.classList.toggle("is-active", item === button));
        document.querySelectorAll("[data-panel]").forEach((panel) => panel.classList.toggle("is-active", panel.dataset.panel === tab));
      });
    });
  }

  function bindGlobalActions() {
    const importInput = document.querySelector("[data-import-input]");
    document.querySelector("[data-action='import-json']").addEventListener("click", () => importInput.click());
    importInput.addEventListener("change", onImportJson);

    document.querySelector("[data-action='export-json']").addEventListener("click", () => {
      downloadFile("inventory_data.json", "application/json", JSON.stringify(state, null, 2));
    });

    document.querySelector("[data-action='seed-demo']").addEventListener("click", () => {
      state = demoState();
      persistAndRender();
    });

    document.querySelector("[data-action='clear-transactions']").addEventListener("click", () => {
      state.transactions = [];
      persistAndRender();
    });

    document.querySelector("[data-action='export-transactions-csv']").addEventListener("click", () => {
      const columns = transactionColumns();
      const rows = state.transactions.map((row) => columns.map((column) => displayTransactionValue(row, column.key)));
      downloadFile("transactions.csv", "text/csv", toCsv(columns.map((column) => column.label), rows));
    });

    document.querySelector("[data-action='export-overview-csv']").addEventListener("click", () => {
      const mode = document.querySelector("[data-overview-mode]").value;
      const rows = mode === "monthly" ? computeMonthlyOverview() : computeInventoryOverview();
      const headers = rows.length ? Object.keys(rows[0]) : [];
      const values = rows.map((row) => headers.map((key) => row[key]));
      downloadFile(`overview-${mode}.csv`, "text/csv", toCsv(headers, values));
    });

    document.querySelector("[data-overview-mode]").addEventListener("change", renderOverviewTable);
  }

  function bindForms() {
    document.querySelector("[data-form='transaction']").addEventListener("submit", onSubmitTransaction);
    document.querySelector("[data-form='alias']").addEventListener("submit", onSubmitAlias);
    document.querySelector("[data-form='field']").addEventListener("submit", onSubmitField);
  }

  function hydrateBrand() {
    const sloganNode = document.querySelector("[data-brand-slogan]");
    if (sloganNode) {
      sloganNode.textContent = "Browser-side parity track for transactions, aliases, overview, and field control.";
    }
  }

  function onSubmitTransaction(event) {
    event.preventDefault();
    const form = event.currentTarget;
    const formData = new FormData(form);
    const transaction = {
      id: createId(),
      date: formData.get("date"),
      sku: String(formData.get("sku") || "").trim(),
      type: String(formData.get("type") || "").trim(),
      qty: toNumber(formData.get("qty")),
      purchase_unit_cost: toNullableNumber(formData.get("purchase_unit_cost")),
      sale_unit_price: toNullableNumber(formData.get("sale_unit_price")),
      note: String(formData.get("note") || "").trim()
    };

    state.custom_fields_schema.forEach((field) => {
      const value = formData.get(`custom:${field.key}`);
      transaction[field.key] = field.type === "number" ? toNullableNumber(value) : String(value || "").trim();
    });

    if (!transaction.date || !transaction.sku || !transaction.type || !transaction.qty) {
      return;
    }

    state.transactions.push(transaction);
    form.reset();
    persistAndRender();
  }

  function onSubmitAlias(event) {
    event.preventDefault();
    const formData = new FormData(event.currentTarget);
    const sku = String(formData.get("sku") || "").trim();
    if (!sku) {
      return;
    }
    state.aliases[sku] = {
      sku,
      name: String(formData.get("name") || "").trim(),
      alias: String(formData.get("alias") || "").trim()
    };
    event.currentTarget.reset();
    persistAndRender();
  }

  function onSubmitField(event) {
    event.preventDefault();
    const formData = new FormData(event.currentTarget);
    const key = String(formData.get("key") || "").trim();
    if (!key) {
      return;
    }
    const existing = state.custom_fields_schema.some((field) => field.key === key);
    if (existing) {
      return;
    }
    const type = String(formData.get("type") || "text");
    state.custom_fields_schema.push({
      key,
      label: String(formData.get("label") || "").trim() || key,
      type,
      options: type === "enum" ? parseCsvList(formData.get("options")) : []
    });
    event.currentTarget.reset();
    persistAndRender();
  }

  function onImportJson(event) {
    const file = event.currentTarget.files && event.currentTarget.files[0];
    if (!file) {
      return;
    }
    const reader = new FileReader();
    reader.onload = () => {
      try {
        state = normalizeState(JSON.parse(String(reader.result || "{}")));
        persistAndRender();
      } catch (error) {
        console.warn("Import failed", error);
      }
      event.currentTarget.value = "";
    };
    reader.readAsText(file);
  }

  function persistAndRender() {
    saveState();
    renderAll();
  }

  function renderAll() {
    renderTransactionCustomFields();
    renderTransactionTable();
    renderOverviewTable();
    renderAliasTable();
    renderFieldTable();
  }

  function renderTransactionCustomFields() {
    const container = document.querySelector("[data-transaction-custom-fields]");
    container.innerHTML = "";
    if (!state.custom_fields_schema.length) {
      return;
    }
    const fragment = document.createDocumentFragment();
    state.custom_fields_schema.forEach((field) => {
      const label = document.createElement("label");
      label.className = "field";
      label.innerHTML = `<span class="field__label">${escapeHtml(field.label)}</span>`;
      let input;
      if (field.type === "enum") {
        input = document.createElement("select");
        input.name = `custom:${field.key}`;
        input.innerHTML = `<option value=""></option>${field.options.map((option) => `<option value="${escapeHtml(option)}">${escapeHtml(option)}</option>`).join("")}`;
      } else {
        input = document.createElement("input");
        input.name = `custom:${field.key}`;
        input.type = field.type === "number" ? "number" : "text";
      }
      label.appendChild(input);
      fragment.appendChild(label);
    });
    container.appendChild(fragment);
  }

  function renderTransactionTable() {
    const columns = transactionColumns();
    const table = document.querySelector("[data-table='transactions']");
    const rows = state.transactions
      .slice()
      .sort((left, right) => String(right.date).localeCompare(String(left.date)) || String(right.id).localeCompare(String(left.id)));
    document.querySelector("[data-transaction-summary]").textContent = `${rows.length} transaction${rows.length === 1 ? "" : "s"} loaded`;
    renderTable(table, columns, rows, (row, column) => displayTransactionValue(row, column.key));
  }

  function renderOverviewTable() {
    const table = document.querySelector("[data-table='overview']");
    const mode = document.querySelector("[data-overview-mode]").value;
    const rows = mode === "monthly" ? computeMonthlyOverview() : computeInventoryOverview();
    const columns = rows.length
      ? Object.keys(rows[0]).map((key) => ({ key, label: prettifyLabel(key) }))
      : OVERVIEW_FIELDS.map((key) => ({ key, label: prettifyLabel(key) }));
    renderTable(table, columns, rows, (row, column) => row[column.key]);
  }

  function renderAliasTable() {
    const table = document.querySelector("[data-table='aliases']");
    const rows = Object.values(state.aliases).sort((left, right) => left.sku.localeCompare(right.sku));
    renderTable(
      table,
      [
        { key: "sku", label: "SKU" },
        { key: "name", label: "Name" },
        { key: "alias", label: "Alias" }
      ],
      rows,
      (row, column) => row[column.key]
    );
  }

  function renderFieldTable() {
    const table = document.querySelector("[data-table='fields']");
    const rows = allFieldRows();
    renderTable(
      table,
      [
        { key: "label", label: "Label" },
        { key: "key", label: "Key" },
        { key: "source", label: "Source" },
        { key: "type", label: "Type" },
        { key: "capabilities", label: "Capabilities" },
        { key: "enabled", label: "Enabled" },
        { key: "actions", label: "Actions" }
      ],
      rows,
      (row, column) => {
        if (column.key === "enabled") {
          return row.enabled ? "Enabled" : "Hidden";
        }
        if (column.key === "actions") {
          return row.removable ? "Toggle visibility" : "Locked";
        }
        return row[column.key];
      },
      onFieldTableRender
    );
  }

  function onFieldTableRender(table, rows) {
    const bodyRows = table.querySelectorAll("tbody tr");
    bodyRows.forEach((rowElement, index) => {
      const row = rows[index];
      const actionCell = rowElement.lastElementChild;
      if (!row || !actionCell) {
        return;
      }
      actionCell.innerHTML = "";
      if (!row.removable) {
        actionCell.innerHTML = `<span class="pill pill--danger">Locked</span>`;
        return;
      }
      const button = document.createElement("button");
      button.className = "button";
      button.type = "button";
      button.textContent = row.enabled ? "Hide" : "Show";
      button.addEventListener("click", () => {
        state.field_overrides[row.key] = {
          enabled: !row.enabled
        };
        persistAndRender();
      });
      actionCell.appendChild(button);
    });
  }

  function renderTable(table, columns, rows, getValue, afterRender) {
    if (!rows.length) {
      table.innerHTML = `<tbody><tr><td><div class="empty-state">No rows yet.</div></td></tr></tbody>`;
      return;
    }

    table.innerHTML = `
      <thead>
        <tr>${columns.map((column) => `<th>${escapeHtml(column.label)}</th>`).join("")}</tr>
      </thead>
      <tbody>
        ${rows
          .map((row) => `<tr>${columns.map((column) => `<td>${formatCell(getValue(row, column))}</td>`).join("")}</tr>`)
          .join("")}
      </tbody>
    `;

    if (afterRender) {
      afterRender(table, rows);
    }
  }

  function transactionColumns() {
    const customColumns = state.custom_fields_schema.map((field) => ({
      key: field.key,
      label: field.label
    }));
    return visibleBuiltinColumns().concat(customColumns);
  }

  function visibleBuiltinColumns() {
    return BUILTIN_FIELDS.filter((field) => {
      if (!field.hideable) {
        return true;
      }
      const override = state.field_overrides[field.key];
      return override ? override.enabled !== false : true;
    }).map((field) => ({ key: field.key, label: field.label }));
  }

  function allFieldRows() {
    const builtinRows = BUILTIN_FIELDS.map((field) => ({
      key: field.key,
      label: field.label,
      source: "system",
      type: field.type,
      enabled: field.hideable ? (state.field_overrides[field.key] ? state.field_overrides[field.key].enabled !== false : true) : true,
      removable: field.removable,
      capabilities: capabilitySummary(field)
    }));

    const customRows = state.custom_fields_schema.map((field) => ({
      key: field.key,
      label: field.label,
      source: "custom",
      type: field.type,
      enabled: true,
      removable: false,
      capabilities: field.type === "enum" ? "schema, enum" : "schema"
    }));

    return builtinRows.concat(customRows);
  }

  function capabilitySummary(field) {
    const values = [];
    if (field.required) {
      values.push("required");
    }
    if (field.computed) {
      values.push("computed");
    }
    if (field.hideable) {
      values.push("hideable");
    }
    if (!field.enumEditable && field.type === "enum") {
      values.push("enum locked");
    }
    return values.join(", ") || "system";
  }

  function computeInventoryOverview() {
    const stateBySku = new Map();

    sortedTransactions().forEach((transaction) => {
      const sku = transaction.sku;
      const aliasInfo = state.aliases[sku] || {};
      const current = stateBySku.get(sku) || {
        sku,
        name: aliasInfo.name || "",
        alias: aliasInfo.alias || "",
        onhand_qty: 0,
        avg_cost_after: 0,
        onhand_cost: 0,
        last_tx_date: "",
        last_sale_price: "",
        status: "INACTIVE"
      };

      if (transaction.type === "PURCHASE") {
        const purchaseCost = toNumber(transaction.purchase_unit_cost);
        const nextQty = current.onhand_qty + transaction.qty;
        const totalCost = current.onhand_cost + transaction.qty * purchaseCost;
        current.onhand_qty = nextQty;
        current.onhand_cost = totalCost;
        current.avg_cost_after = nextQty ? totalCost / nextQty : 0;
      } else if (transaction.type === "SALE") {
        current.onhand_qty = current.onhand_qty - transaction.qty;
        current.onhand_cost = current.onhand_qty * current.avg_cost_after;
        current.last_sale_price = formatNumber(transaction.sale_unit_price);
      }

      current.name = aliasInfo.name || current.name;
      current.alias = aliasInfo.alias || current.alias;
      current.last_tx_date = transaction.date;
      current.status = current.onhand_qty > 0 ? "IN STOCK" : current.onhand_qty < 0 ? "NEGATIVE" : "OUT";

      stateBySku.set(sku, current);
    });

    return Array.from(stateBySku.values()).map((row) => ({
      sku: row.sku,
      name: row.name,
      alias: row.alias,
      onhand_qty: formatNumber(row.onhand_qty),
      avg_cost_after: formatNumber(row.avg_cost_after),
      onhand_cost: formatNumber(row.onhand_cost),
      last_tx_date: row.last_tx_date,
      last_sale_price: row.last_sale_price,
      status: row.status
    }));
  }

  function computeMonthlyOverview() {
    const monthly = new Map();
    sortedTransactions().forEach((transaction) => {
      const month = String(transaction.date || "").slice(0, 7);
      if (!month) {
        return;
      }
      const current = monthly.get(month) || {
        month,
        purchase_qty: 0,
        sale_qty: 0,
        purchase_total_cost: 0,
        sales_rev: 0
      };
      if (transaction.type === "PURCHASE") {
        current.purchase_qty += transaction.qty;
        current.purchase_total_cost += transaction.qty * toNumber(transaction.purchase_unit_cost);
      } else {
        current.sale_qty += transaction.qty;
        current.sales_rev += transaction.qty * toNumber(transaction.sale_unit_price);
      }
      monthly.set(month, current);
    });
    return Array.from(monthly.values())
      .sort((left, right) => left.month.localeCompare(right.month))
      .map((row) => ({
        month: row.month,
        purchase_qty: formatNumber(row.purchase_qty),
        sale_qty: formatNumber(row.sale_qty),
        purchase_total_cost: formatNumber(row.purchase_total_cost),
        sales_rev: formatNumber(row.sales_rev)
      }));
  }

  function sortedTransactions() {
    return state.transactions
      .slice()
      .sort((left, right) => String(left.date).localeCompare(String(right.date)) || String(left.id).localeCompare(String(right.id)));
  }

  function displayTransactionValue(row, key) {
    if (key === "alias") {
      return (state.aliases[row.sku] || {}).alias || "";
    }
    const value = row[key];
    return typeof value === "number" ? formatNumber(value) : value;
  }

  function demoState() {
    return normalizeState({
      transactions: [
        { id: createId(), date: "2026-05-01", sku: "SKU-1001", type: "PURCHASE", qty: 10, purchase_unit_cost: 8.25, sale_unit_price: null, note: "Opening receipt", warehouse_bin: "A1" },
        { id: createId(), date: "2026-05-03", sku: "SKU-1001", type: "SALE", qty: 3, purchase_unit_cost: null, sale_unit_price: 14.5, note: "Counter sale", warehouse_bin: "A1" },
        { id: createId(), date: "2026-05-04", sku: "SKU-2000", type: "PURCHASE", qty: 6, purchase_unit_cost: 12.4, sale_unit_price: null, note: "Restock", warehouse_bin: "Overflow" }
      ],
      aliases: {
        "SKU-1001": { sku: "SKU-1001", name: "Widget Prime", alias: "Front Shelf" },
        "SKU-2000": { sku: "SKU-2000", name: "Module Core", alias: "Back Room" }
      },
      custom_fields_schema: [
        { key: "warehouse_bin", label: "Warehouse Bin", type: "enum", options: ["A1", "Overflow", "Returns"] }
      ],
      field_overrides: {}
    });
  }

  function createId() {
    return `tx_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`;
  }

  function toCsv(headers, rows) {
    return [headers, ...rows]
      .map((row) => row.map((value) => csvCell(value)).join(","))
      .join("\n");
  }

  function csvCell(value) {
    const text = String(value == null ? "" : value);
    return `"${text.replace(/"/g, '""')}"`;
  }

  function downloadFile(name, type, content) {
    const blob = new Blob([content], { type });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = name;
    anchor.click();
    URL.revokeObjectURL(url);
  }

  function parseCsvList(value) {
    return String(value || "")
      .split(",")
      .map((item) => item.trim())
      .filter(Boolean);
  }

  function toNumber(value) {
    const result = Number(value);
    return Number.isFinite(result) ? result : 0;
  }

  function toNullableNumber(value) {
    if (value === null || value === undefined || value === "") {
      return null;
    }
    const result = Number(value);
    return Number.isFinite(result) ? result : null;
  }

  function formatNumber(value) {
    return Number(value || 0).toFixed(2).replace(/\.00$/, "");
  }

  function prettifyLabel(value) {
    return String(value)
      .split("_")
      .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
      .join(" ");
  }

  function formatCell(value) {
    if (value === null || value === undefined || value === "") {
      return "";
    }
    return escapeHtml(String(value));
  }

  function escapeHtml(value) {
    return String(value)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }

  function isPlainObject(value) {
    return value && typeof value === "object" && !Array.isArray(value);
  }
})();
