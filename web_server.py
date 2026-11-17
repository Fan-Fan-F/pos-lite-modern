"""
Embedded offline Web POS Server and REST API for pos-lite-modern.
Built entirely with Python 3 standard library (http.server, json, urllib).
Provides REST endpoints and a responsive Single Page Application (SPA).
"""

from __future__ import annotations

import json
import os
import sys
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlparse

from pos_core import (
    DEFAULT_DB_PATH,
    Database,
    InsufficientPaymentError,
    InsufficientStockError,
    POSError,
    POSService,
)

HTML_PAGE = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>POS-Lite-Modern | 离线收银与库存系统</title>
<style>
  :root {
    --bg-main: #0f172a;
    --bg-card: #1e293b;
    --bg-card-hover: #334155;
    --text-primary: #f8fafc;
    --text-muted: #94a3b8;
    --primary: #3b82f6;
    --primary-hover: #2563eb;
    --success: #10b981;
    --success-hover: #059669;
    --warning: #f59e0b;
    --danger: #ef4444;
    --border: #334155;
    --font: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
  }
  * { box-sizing: border-box; margin: 0; padding: 0; font-family: var(--font); }
  body { background: var(--bg-main); color: var(--text-primary); min-height: 100vh; display: flex; flex-direction: column; }
  
  /* Header */
  header {
    background: #090d16;
    border-bottom: 1px solid var(--border);
    padding: 12px 24px;
    display: flex;
    justify-content: space-between;
    align-items: center;
  }
  .logo { font-size: 1.25rem; font-weight: 700; color: #60a5fa; display: flex; align-items: center; gap: 8px; }
  .logo span { font-size: 0.8rem; background: #1e3a8a; color: #bfdbfe; padding: 2px 8px; border-radius: 9999px; }
  .nav-tabs { display: flex; gap: 8px; }
  .tab-btn {
    background: transparent; border: none; color: var(--text-muted); padding: 8px 16px;
    border-radius: 6px; cursor: pointer; font-weight: 500; font-size: 0.95rem; transition: all 0.2s;
  }
  .tab-btn:hover { color: var(--text-primary); background: var(--bg-card); }
  .tab-btn.active { color: white; background: var(--primary); }
  .user-badge { font-size: 0.85rem; color: var(--text-muted); background: var(--bg-card); padding: 6px 12px; border-radius: 20px; border: 1px solid var(--border); }

  /* Main Container */
  main { flex: 1; padding: 20px 24px; max-width: 1440px; margin: 0 auto; width: 100%; }
  .tab-panel { display: none; }
  .tab-panel.active { display: block; animation: fadeIn 0.15s ease-in; }
  @keyframes fadeIn { from { opacity: 0; transform: translateY(4px); } to { opacity: 1; transform: translateY(0); } }

  /* Dashboard Cards */
  .grid-cards { display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 16px; margin-bottom: 24px; }
  .stat-card { background: var(--bg-card); padding: 18px; border-radius: 10px; border: 1px solid var(--border); }
  .stat-title { font-size: 0.85rem; color: var(--text-muted); margin-bottom: 6px; }
  .stat-val { font-size: 1.8rem; font-weight: 700; color: var(--text-primary); }
  .stat-val.green { color: var(--success); }
  .stat-val.amber { color: var(--warning); }

  /* POS Cashier Layout */
  .pos-container { display: grid; grid-template-columns: 1fr 380px; gap: 20px; height: calc(100vh - 120px); }
  .catalog-pane { display: flex; flex-direction: column; overflow: hidden; }
  .catalog-header { display: flex; gap: 12px; margin-bottom: 14px; }
  .search-input {
    flex: 1; background: var(--bg-card); border: 1px solid var(--border); color: white;
    padding: 10px 14px; border-radius: 8px; font-size: 0.95rem; outline: none;
  }
  .search-input:focus { border-color: var(--primary); }
  .cat-pills { display: flex; gap: 8px; overflow-x: auto; padding-bottom: 8px; margin-bottom: 12px; }
  .pill {
    white-space: nowrap; background: var(--bg-card); border: 1px solid var(--border);
    color: var(--text-muted); padding: 5px 12px; border-radius: 16px; font-size: 0.85rem; cursor: pointer;
  }
  .pill.active { background: #2563eb; color: white; border-color: #3b82f6; }
  .products-grid {
    flex: 1; overflow-y: auto; display: grid; grid-template-columns: repeat(auto-fill, minmax(180px, 1fr));
    gap: 14px; align-content: start; padding-right: 6px;
  }
  .prod-card {
    background: var(--bg-card); border: 1px solid var(--border); border-radius: 8px;
    padding: 14px; cursor: pointer; transition: transform 0.15s, border-color 0.15s; display: flex; flex-direction: column; justify-content: space-between;
  }
  .prod-card:hover { transform: translateY(-2px); border-color: var(--primary); }
  .prod-sku { font-size: 0.75rem; color: var(--text-muted); margin-bottom: 4px; }
  .prod-name { font-weight: 600; font-size: 0.95rem; margin-bottom: 8px; line-height: 1.3; }
  .prod-meta { display: flex; justify-content: space-between; align-items: baseline; }
  .prod-price { color: #38bdf8; font-weight: 700; font-size: 1.1rem; }
  .prod-stock { font-size: 0.8rem; color: var(--text-muted); }
  .prod-stock.low { color: var(--warning); font-weight: bold; }

  /* Cart Pane */
  .cart-pane {
    background: var(--bg-card); border: 1px solid var(--border); border-radius: 10px;
    display: flex; flex-direction: column; overflow: hidden;
  }
  .cart-header { padding: 14px 18px; border-bottom: 1px solid var(--border); font-weight: 600; display: flex; justify-content: space-between; align-items: center; }
  .cart-items { flex: 1; overflow-y: auto; padding: 12px 18px; display: flex; flex-direction: column; gap: 10px; }
  .cart-item {
    display: flex; justify-content: space-between; align-items: center; background: #0f172a;
    padding: 10px 12px; border-radius: 6px; border: 1px solid var(--border);
  }
  .item-title { font-weight: 600; font-size: 0.9rem; margin-bottom: 2px; }
  .item-sub { font-size: 0.75rem; color: var(--text-muted); }
  .item-ctrls { display: flex; align-items: center; gap: 8px; }
  .qty-btn {
    background: var(--bg-card); border: 1px solid var(--border); color: white; width: 26px; height: 26px;
    border-radius: 4px; cursor: pointer; display: flex; align-items: center; justify-content: center; font-weight: bold;
  }
  .qty-btn:hover { background: #334155; }
  .cart-footer { padding: 16px 18px; border-top: 1px solid var(--border); background: #131d2e; display: flex; flex-direction: column; gap: 10px; }
  .row-calc { display: flex; justify-content: space-between; font-size: 0.9rem; color: var(--text-muted); }
  .row-total { display: flex; justify-content: space-between; font-size: 1.25rem; font-weight: 700; color: white; }
  .input-group { display: flex; gap: 8px; align-items: center; }
  .input-group label { font-size: 0.85rem; color: var(--text-muted); width: 80px; }
  .input-sm {
    flex: 1; background: var(--bg-card); border: 1px solid var(--border); color: white;
    padding: 6px 10px; border-radius: 6px; text-align: right; font-weight: 600;
  }
  .btn-checkout {
    background: var(--success); color: white; border: none; padding: 12px; border-radius: 8px;
    font-size: 1.05rem; font-weight: 700; cursor: pointer; transition: background 0.2s; margin-top: 6px;
  }
  .btn-checkout:hover { background: var(--success-hover); }

  /* Standard Table */
  .table-box { background: var(--bg-card); border: 1px solid var(--border); border-radius: 10px; overflow: hidden; }
  table { width: 100%; border-collapse: collapse; text-align: left; font-size: 0.9rem; }
  th { background: #0f172a; padding: 12px 16px; color: var(--text-muted); font-weight: 600; border-bottom: 1px solid var(--border); }
  td { padding: 12px 16px; border-bottom: 1px solid var(--border); }
  tr:last-child td { border-bottom: none; }
  tr:hover td { background: var(--bg-card-hover); }
  .badge { padding: 3px 8px; border-radius: 4px; font-size: 0.75rem; font-weight: 600; }
  .badge-warn { background: #78350f; color: #fde68a; }
  .badge-ok { background: #064e3b; color: #a7f3d0; }

  /* Modal */
  .modal-overlay {
    position: fixed; top: 0; left: 0; width: 100vw; height: 100vh; background: rgba(0,0,0,0.7);
    display: none; align-items: center; justify-content: center; z-index: 1000;
  }
  .modal-overlay.active { display: flex; }
  .modal-card {
    background: var(--bg-card); border: 1px solid var(--border); border-radius: 12px;
    width: 90%; max-width: 520px; max-height: 90vh; display: flex; flex-direction: column; overflow: hidden;
  }
  .modal-head { padding: 16px 20px; border-bottom: 1px solid var(--border); display: flex; justify-content: space-between; align-items: center; }
  .modal-body { padding: 20px; overflow-y: auto; }
  .receipt-box {
    background: #020617; color: #38bdf8; font-family: "Courier New", Courier, monospace;
    padding: 16px; border-radius: 8px; font-size: 0.85rem; white-space: pre-wrap; line-height: 1.4; border: 1px solid var(--border);
  }
  .btn-primary { background: var(--primary); color: white; border: none; padding: 8px 16px; border-radius: 6px; cursor: pointer; font-weight: 600; }
  .btn-secondary { background: var(--bg-card-hover); color: white; border: 1px solid var(--border); padding: 8px 16px; border-radius: 6px; cursor: pointer; }
</style>
</head>
<body>

<header>
  <div class="logo">
    <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="2" y="3" width="20" height="14" rx="2"/><line x1="8" y1="21" x2="16" y2="21"/><line x1="12" y1="17" x2="12" y2="21"/></svg>
    POS-Lite-Modern
    <span>Offline POS</span>
  </div>
  <nav class="nav-tabs">
    <button class="tab-btn active" onclick="switchTab('pos')">收银台 (POS)</button>
    <button class="tab-btn" onclick="switchTab('products')">商品与库存</button>
    <button class="tab-btn" onclick="switchTab('reports')">报表与仪表盘</button>
    <button class="tab-btn" onclick="switchTab('suppliers')">分类与供应商</button>
    <button class="tab-btn" onclick="switchTab('users')">员工角色</button>
  </nav>
  <div class="user-badge" id="userBadge">登录: admin (系统管理员)</div>
</header>

<main>
  <!-- TAB 1: POS CASHIER -->
  <section id="tab-pos" class="tab-panel active">
    <div class="pos-container">
      <div class="catalog-pane">
        <div class="catalog-header">
          <input type="text" id="searchInput" class="search-input" placeholder="输入商品名称 / SKU / 条码快速选购..." oninput="filterProducts()">
        </div>
        <div class="cat-pills" id="categoryPills">
          <div class="pill active" onclick="selectCategory(null)">全部全部分类</div>
        </div>
        <div class="products-grid" id="productsGrid">
          <!-- Rendered by JS -->
        </div>
      </div>

      <div class="cart-pane">
        <div class="cart-header">
          <span>当前购物车清单</span>
          <span id="cartCountBadge" style="font-size: 0.8rem; color: var(--text-muted);">0 件商品</span>
        </div>
        <div class="cart-items" id="cartList">
          <div style="text-align: center; color: var(--text-muted); margin-top: 40px;">购物车为空<br>点击左侧商品即可快速加购</div>
        </div>
        <div class="cart-footer">
          <div class="row-calc">
            <span>小计 Subtotal</span>
            <span id="subtotalLabel">$0.00</span>
          </div>
          <div class="input-group">
            <label>优惠折扣 $</label>
            <input type="number" step="0.5" min="0" value="0.00" id="discountInput" class="input-sm" oninput="updateTotals()">
          </div>
          <div class="row-total">
            <span>应收总额</span>
            <span id="totalLabel" style="color: #38bdf8;">$0.00</span>
          </div>
          <div class="input-group">
            <label>实收现金 $</label>
            <input type="number" step="1" min="0" value="0.00" id="paidInput" class="input-sm" oninput="updateTotals()">
          </div>
          <div class="row-calc" style="font-weight: 600; color: #10b981;">
            <span>找零 Change</span>
            <span id="changeLabel">$0.00</span>
          </div>
          <button class="btn-checkout" onclick="performCheckout()">结算出单 (Print Receipt)</button>
        </div>
      </div>
    </div>
  </section>

  <!-- TAB 2: PRODUCTS & INVENTORY -->
  <section id="tab-products" class="tab-panel">
    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px;">
      <h2>商品档案与库存追踪</h2>
      <div style="display: flex; gap: 10px;">
        <button class="btn-primary" onclick="openNewProductModal()">+ 新建商品</button>
        <button class="btn-secondary" onclick="openRestockModal()">📦 采购入库</button>
      </div>
    </div>
    <div class="table-box">
      <table>
        <thead>
          <tr>
            <th>SKU</th>
            <th>商品名称</th>
            <th>分类</th>
            <th>进货成本</th>
            <th>销售单价</th>
            <th>当前库存</th>
            <th>预警阈值</th>
            <th>库存状态</th>
          </tr>
        </thead>
        <tbody id="inventoryTableBody">
          <!-- Rendered by JS -->
        </tbody>
      </table>
    </div>
  </section>

  <!-- TAB 3: REPORTS & DASHBOARD -->
  <section id="tab-reports" class="tab-panel">
    <div class="grid-cards">
      <div class="stat-card">
        <div class="stat-title">今日销售额 Today Sales</div>
        <div class="stat-val green" id="dashTodayRev">$0.00</div>
      </div>
      <div class="stat-card">
        <div class="stat-title">今日订单数 Today Orders</div>
        <div class="stat-val" id="dashTodayOrders">0</div>
      </div>
      <div class="stat-card">
        <div class="stat-title">总库存商品数量 Units</div>
        <div class="stat-val" id="dashStockUnits">0</div>
      </div>
      <div class="stat-card">
        <div class="stat-title">低库存警戒品项 Low Stock</div>
        <div class="stat-val amber" id="dashLowStockCount">0</div>
      </div>
    </div>

    <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 20px;">
      <div class="table-box">
        <div style="padding: 12px 16px; font-weight: 600; border-bottom: 1px solid var(--border);">近 7 日销售趋势</div>
        <table>
          <thead>
            <tr><th>日期</th><th>订单笔数</th><th>应收小计</th><th>实收总额</th></tr>
          </thead>
          <tbody id="dailySalesBody"></tbody>
        </table>
      </div>

      <div class="table-box">
        <div style="padding: 12px 16px; font-weight: 600; border-bottom: 1px solid var(--border);">畅销商品排行 Top Selling</div>
        <table>
          <thead>
            <tr><th>SKU</th><th>商品名称</th><th>售出件数</th><th>销售金额</th></tr>
          </thead>
          <tbody id="topSellingBody"></tbody>
        </table>
      </div>
    </div>
  </section>

  <!-- TAB 4: SUPPLIERS & CATEGORIES -->
  <section id="tab-suppliers" class="tab-panel">
    <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 20px;">
      <div>
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px;">
          <h3>商品分类管理</h3>
          <button class="btn-primary" onclick="openAddCatModal()">+ 新增分类</button>
        </div>
        <div class="table-box">
          <table>
            <thead><tr><th>ID</th><th>分类名</th><th>描述</th><th>商品数</th></tr></thead>
            <tbody id="catTableBody"></tbody>
          </table>
        </div>
      </div>
      <div>
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px;">
          <h3>供应商档案</h3>
          <button class="btn-primary" onclick="openAddSupModal()">+ 新增供应商</button>
        </div>
        <div class="table-box">
          <table>
            <thead><tr><th>名称</th><th>联系人</th><th>电话</th><th>邮箱</th></tr></thead>
            <tbody id="supTableBody"></tbody>
          </table>
        </div>
      </div>
    </div>
  </section>

  <!-- TAB 5: USERS & EMPLOYEES -->
  <section id="tab-users" class="tab-panel">
    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px;">
      <h2>员工与收银员管理</h2>
      <button class="btn-primary" onclick="openAddUserModal()">+ 新建员工账号</button>
    </div>
    <div class="table-box">
      <table>
        <thead>
          <tr><th>ID</th><th>用户名</th><th>姓名</th><th>系统角色</th><th>状态</th><th>创建时间</th></tr>
        </thead>
        <tbody id="usersTableBody"></tbody>
      </table>
    </div>
  </section>
</main>

<!-- RECEIPT MODAL -->
<div class="modal-overlay" id="receiptModal">
  <div class="modal-card">
    <div class="modal-head">
      <h3 style="font-size: 1.1rem; color: #38bdf8;">收银结算成功 · 小票已生成</h3>
      <button onclick="closeModal('receiptModal')" style="background: none; border: none; color: white; cursor: pointer; font-size: 1.2rem;">&times;</button>
    </div>
    <div class="modal-body">
      <pre class="receipt-box" id="receiptContent"></pre>
      <div style="display: flex; justify-content: flex-end; gap: 10px; margin-top: 14px;">
        <button class="btn-secondary" onclick="copyReceipt()">复制小票纯文本</button>
        <button class="btn-primary" onclick="closeModal('receiptModal')">完成并下一单</button>
      </div>
    </div>
  </div>
</div>

<!-- RESTOCK MODAL -->
<div class="modal-overlay" id="restockModal">
  <div class="modal-card">
    <div class="modal-head">
      <h3>商品采购入库</h3>
      <button onclick="closeModal('restockModal')" style="background: none; border: none; color: white; cursor: pointer; font-size: 1.2rem;">&times;</button>
    </div>
    <div class="modal-body" style="display: flex; flex-direction: column; gap: 12px;">
      <div>
        <label style="font-size: 0.85rem; color: var(--text-muted); display: block; margin-bottom: 4px;">选择商品</label>
        <select id="restockProductSelect" class="search-input" style="width: 100%;"></select>
      </div>
      <div>
        <label style="font-size: 0.85rem; color: var(--text-muted); display: block; margin-bottom: 4px;">入库数量 (件)</label>
        <input type="number" id="restockQty" class="search-input" min="1" value="10">
      </div>
      <div>
        <label style="font-size: 0.85rem; color: var(--text-muted); display: block; margin-bottom: 4px;">进货单价成本 ($)</label>
        <input type="number" id="restockCost" step="0.1" class="search-input" value="5.00">
      </div>
      <div style="display: flex; justify-content: flex-end; gap: 10px; margin-top: 8px;">
        <button class="btn-secondary" onclick="closeModal('restockModal')">取消</button>
        <button class="btn-primary" onclick="submitRestock()">确认入库</button>
      </div>
    </div>
  </div>
</div>

<script>
let state = {
  products: [],
  categories: [],
  suppliers: [],
  users: [],
  cart: {}, // sku -> { product, quantity }
  activeCategory: null,
  activeTab: 'pos'
};

async function api(path, method = 'GET', data = null) {
  const opts = { method, headers: { 'Content-Type': 'application/json' } };
  if (data) opts.body = JSON.stringify(data);
  const res = await fetch(path, opts);
  if (!res.ok) {
    const err = await res.json().catch(() => ({ error: 'Request failed' }));
    throw new Error(err.error || 'Server error');
  }
  return res.json();
}

function switchTab(tab) {
  state.activeTab = tab;
  document.querySelectorAll('.tab-btn').forEach((b, i) => {
    b.classList.toggle('active', ['pos', 'products', 'reports', 'suppliers', 'users'][i] === tab);
  });
  document.querySelectorAll('.tab-panel').forEach(p => {
    p.classList.toggle('active', p.id === 'tab-' + tab);
  });
  if (tab === 'reports') loadReports();
  if (tab === 'products') loadProducts();
  if (tab === 'suppliers') loadSuppliersAndCats();
  if (tab === 'users') loadUsers();
}

async function init() {
  await loadCategories();
  await loadProducts();
}

async function loadCategories() {
  state.categories = await api('/api/categories');
  const pills = document.getElementById('categoryPills');
  pills.innerHTML = '<div class="pill active" onclick="selectCategory(null)">全部分类</div>';
  state.categories.forEach(c => {
    const div = document.createElement('div');
    div.className = 'pill';
    div.innerText = c.name;
    div.onclick = () => selectCategory(c.id);
    pills.appendChild(div);
  });
}

function selectCategory(cid) {
  state.activeCategory = cid;
  document.querySelectorAll('.cat-pills .pill').forEach((p, idx) => {
    if (cid === null && idx === 0) p.classList.add('active');
    else if (cid !== null && idx > 0 && state.categories[idx - 1].id === cid) p.classList.add('active');
    else p.classList.remove('active');
  });
  renderProducts();
}

async function loadProducts() {
  state.products = await api('/api/products');
  renderProducts();
  renderInventoryTable();
}

function filterProducts() {
  renderProducts();
}

function renderProducts() {
  const query = document.getElementById('searchInput').value.toLowerCase().trim();
  const grid = document.getElementById('productsGrid');
  grid.innerHTML = '';

  const filtered = state.products.filter(p => {
    const matchCat = state.activeCategory === null || p.category_id === state.activeCategory;
    const matchQ = !query || p.name.toLowerCase().includes(query) || p.sku.toLowerCase().includes(query);
    return matchCat && matchQ;
  });

  if (filtered.length === 0) {
    grid.innerHTML = '<div style="color: var(--text-muted); grid-column: 1/-1; padding: 20px;">未找到匹配商品</div>';
    return;
  }

  filtered.forEach(p => {
    const card = document.createElement('div');
    card.className = 'prod-card';
    card.onclick = () => addToCart(p);
    card.innerHTML = `
      <div>
        <div class="prod-sku">${p.sku}</div>
        <div class="prod-name">${p.name}</div>
      </div>
      <div class="prod-meta">
        <span class="prod-price">$${p.sale_price.toFixed(2)}</span>
        <span class="prod-stock ${p.is_low_stock ? 'low' : ''}">库存: ${p.stock_quantity}</span>
      </div>
    `;
    grid.appendChild(card);
  });
}

function addToCart(p) {
  if (p.stock_quantity <= 0) {
    alert(`商品 [${p.name}] 当前库存为 0，无法加购！`);
    return;
  }
  const curr = state.cart[p.sku] ? state.cart[p.sku].quantity : 0;
  if (curr + 1 > p.stock_quantity) {
    alert(`已达到库存上限 (${p.stock_quantity} 件)！`);
    return;
  }
  if (!state.cart[p.sku]) {
    state.cart[p.sku] = { product: p, quantity: 1 };
  } else {
    state.cart[p.sku].quantity += 1;
  }
  renderCart();
}

function changeCartQty(sku, delta) {
  if (!state.cart[sku]) return;
  const p = state.cart[sku].product;
  const newQty = state.cart[sku].quantity + delta;
  if (newQty <= 0) {
    delete state.cart[sku];
  } else if (newQty > p.stock_quantity) {
    alert(`超出当前库存量 (${p.stock_quantity} 件)`);
    return;
  } else {
    state.cart[sku].quantity = newQty;
  }
  renderCart();
}

function renderCart() {
  const container = document.getElementById('cartList');
  const items = Object.values(state.cart);
  if (items.length === 0) {
    container.innerHTML = '<div style="text-align: center; color: var(--text-muted); margin-top: 40px;">购物车为空<br>点击左侧商品即可快速加购</div>';
    document.getElementById('cartCountBadge').innerText = '0 件商品';
    updateTotals();
    return;
  }

  let totalItems = 0;
  container.innerHTML = '';
  items.forEach(it => {
    totalItems += it.quantity;
    const div = document.createElement('div');
    div.className = 'cart-item';
    div.innerHTML = `
      <div style="flex: 1;">
        <div class="item-title">${it.product.name}</div>
        <div class="item-sub">$${it.product.sale_price.toFixed(2)} / 件</div>
      </div>
      <div class="item-ctrls">
        <button class="qty-btn" onclick="changeCartQty('${it.product.sku}', -1)">-</button>
        <span style="font-weight: 600; min-width: 20px; text-align: center;">${it.quantity}</span>
        <button class="qty-btn" onclick="changeCartQty('${it.product.sku}', 1)">+</button>
      </div>
      <div style="font-weight: 700; width: 65px; text-align: right; color: #38bdf8;">
        $${(it.product.sale_price * it.quantity).toFixed(2)}
      </div>
    `;
    container.appendChild(div);
  });
  document.getElementById('cartCountBadge').innerText = `${totalItems} 件商品`;
  updateTotals();
}

function updateTotals() {
  const items = Object.values(state.cart);
  let subtotal = 0;
  items.forEach(it => subtotal += it.product.sale_price * it.quantity);
  const discount = Math.max(0, parseFloat(document.getElementById('discountInput').value) || 0);
  const total = Math.max(0, subtotal - discount);

  document.getElementById('subtotalLabel').innerText = '$' + subtotal.toFixed(2);
  document.getElementById('totalLabel').innerText = '$' + total.toFixed(2);

  const paidInput = document.getElementById('paidInput');
  let paid = parseFloat(paidInput.value);
  if (isNaN(paid) || paid === 0) {
    paid = total;
    paidInput.value = total.toFixed(2);
  }
  const change = Math.max(0, paid - total);
  document.getElementById('changeLabel').innerText = '$' + change.toFixed(2);
}

async function performCheckout() {
  const items = Object.values(state.cart).map(it => ({
    sku: it.product.sku,
    quantity: it.quantity
  }));
  if (items.length === 0) {
    alert('购物车为空，请先选择商品！');
    return;
  }
  const discount = parseFloat(document.getElementById('discountInput').value) || 0;
  const paid = parseFloat(document.getElementById('paidInput').value) || 0;

  try {
    const res = await api('/api/checkout', 'POST', {
      items,
      discount_amount: discount,
      paid_amount: paid,
      customer_name: 'Walk-in Customer'
    });

    state.cart = {};
    renderCart();
    document.getElementById('discountInput').value = '0.00';
    document.getElementById('paidInput').value = '0.00';
    
    // Show receipt modal
    document.getElementById('receiptContent').innerText = res.receipt_text;
    document.getElementById('receiptModal').classList.add('active');
    
    // Refresh products
    await loadProducts();
  } catch (err) {
    alert('收银结算失败: ' + err.message);
  }
}

function copyReceipt() {
  const txt = document.getElementById('receiptContent').innerText;
  navigator.clipboard.writeText(txt).then(() => alert('小票文本已复制到剪贴板！'));
}

function closeModal(id) {
  document.getElementById(id).classList.remove('active');
}

function renderInventoryTable() {
  const tbody = document.getElementById('inventoryTableBody');
  tbody.innerHTML = '';
  state.products.forEach(p => {
    const tr = document.createElement('tr');
    tr.innerHTML = `
      <td style="font-family: monospace;">${p.sku}</td>
      <td style="font-weight: 600;">${p.name}</td>
      <td>${p.category_name || '-'}</td>
      <td>$${p.cost_price.toFixed(2)}</td>
      <td style="color: #38bdf8; font-weight: 600;">$${p.sale_price.toFixed(2)}</td>
      <td style="font-weight: 700;">${p.stock_quantity}</td>
      <td>${p.min_stock_alert}</td>
      <td>
        <span class="badge ${p.is_low_stock ? 'badge-warn' : 'badge-ok'}">
          ${p.is_low_stock ? '低库存警报' : '正常'}
        </span>
      </td>
    `;
    tbody.appendChild(tr);
  });
}

async function loadReports() {
  const [dash, rep] = await Promise.all([api('/api/dashboard'), api('/api/reports')]);
  document.getElementById('dashTodayRev').innerText = '$' + dash.today_revenue.toFixed(2);
  document.getElementById('dashTodayOrders').innerText = dash.today_orders;
  document.getElementById('dashStockUnits').innerText = dash.total_stock_units;
  document.getElementById('dashLowStockCount').innerText = dash.low_stock_count;

  const dBody = document.getElementById('dailySalesBody');
  dBody.innerHTML = '';
  rep.daily_breakdown.forEach(d => {
    const tr = document.createElement('tr');
    tr.innerHTML = `<td>${d.sales_date}</td><td>${d.order_count}</td><td>$${d.total_subtotal.toFixed(2)}</td><td style="color: #10b981; font-weight: 600;">$${d.total_revenue.toFixed(2)}</td>`;
    dBody.appendChild(tr);
  });

  const tBody = document.getElementById('topSellingBody');
  tBody.innerHTML = '';
  rep.top_products.forEach(t => {
    const tr = document.createElement('tr');
    tr.innerHTML = `<td style="font-family: monospace;">${t.sku}</td><td>${t.product_name}</td><td>${t.total_qty_sold}</td><td style="color: #38bdf8; font-weight: 600;">$${t.total_sales_amount.toFixed(2)}</td>`;
    tBody.appendChild(tr);
  });
}

async function loadSuppliersAndCats() {
  const [cats, sups] = await Promise.all([api('/api/categories'), api('/api/suppliers')]);
  const cBody = document.getElementById('catTableBody');
  cBody.innerHTML = '';
  cats.forEach(c => {
    const tr = document.createElement('tr');
    tr.innerHTML = `<td>${c.id}</td><td><strong>${c.name}</strong></td><td>${c.description || '-'}</td><td>${c.product_count}</td>`;
    cBody.appendChild(tr);
  });

  const sBody = document.getElementById('supTableBody');
  sBody.innerHTML = '';
  sups.forEach(s => {
    const tr = document.createElement('tr');
    tr.innerHTML = `<td><strong>${s.name}</strong></td><td>${s.contact_person || '-'}</td><td>${s.phone || '-'}</td><td>${s.email || '-'}</td>`;
    sBody.appendChild(tr);
  });
}

async function loadUsers() {
  const users = await api('/api/users');
  const uBody = document.getElementById('usersTableBody');
  uBody.innerHTML = '';
  users.forEach(u => {
    const tr = document.createElement('tr');
    tr.innerHTML = `<td>${u.id}</td><td>${u.username}</td><td>${u.full_name}</td><td><span class="badge ${u.role === 'admin' ? 'badge-ok' : 'badge-warn'}">${u.role.toUpperCase()}</span></td><td>${u.is_active ? '启用' : '禁用'}</td><td>${u.created_at}</td>`;
    uBody.appendChild(tr);
  });
}

function openRestockModal() {
  const sel = document.getElementById('restockProductSelect');
  sel.innerHTML = '';
  state.products.forEach(p => {
    const opt = document.createElement('option');
    opt.value = p.id;
    opt.innerText = `[${p.sku}] ${p.name} (现存: ${p.stock_quantity})`;
    sel.appendChild(opt);
  });
  document.getElementById('restockModal').classList.add('active');
}

async function submitRestock() {
  const pid = parseInt(document.getElementById('restockProductSelect').value);
  const qty = parseInt(document.getElementById('restockQty').value);
  const cost = parseFloat(document.getElementById('restockCost').value);
  if (!pid || qty <= 0 || cost < 0) {
    alert('请填写正确的入库数量与成本');
    return;
  }
  try {
    const res = await api('/api/restock', 'POST', { product_id: pid, quantity: qty, unit_cost: cost });
    alert(`采购入库成功！单号: ${res.purchase_no}，新库存: ${res.new_stock}`);
    closeModal('restockModal');
    await loadProducts();
  } catch (err) {
    alert('入库失败: ' + err.message);
  }
}

function openNewProductModal() {
  const sku = prompt('请输入新商品 SKU (如 SKU-NEW-01):');
  if (!sku) return;
  const name = prompt('请输入商品名称:');
  if (!name) return;
  const price = parseFloat(prompt('请输入销售单价 ($):', '10.00'));
  if (isNaN(price)) return;
  const cost = parseFloat(prompt('请输入进货成本 ($):', '5.00')) || 0;
  const stock = parseInt(prompt('请输入初始库存数量:', '20')) || 0;

  api('/api/products', 'POST', {
    sku, name, sale_price: price, cost_price: cost, stock_quantity: stock, min_stock_alert: 5
  }).then(() => {
    alert('商品新建成功！');
    loadProducts();
  }).catch(e => alert('新建商品失败: ' + e.message));
}

function openAddCatModal() {
  const name = prompt('请输入分类名称:');
  if (!name) return;
  const desc = prompt('请输入分类描述 (选填):') || '';
  api('/api/categories', 'POST', { name, description: desc }).then(() => {
    alert('分类添加成功！');
    loadCategories();
    loadSuppliersAndCats();
  }).catch(e => alert('添加分类失败: ' + e.message));
}

function openAddSupModal() {
  const name = prompt('请输入供应商名称:');
  if (!name) return;
  const contact = prompt('联系人:') || '';
  const phone = prompt('电话:') || '';
  api('/api/suppliers', 'POST', { name, contact_person: contact, phone }).then(() => {
    alert('供应商添加成功！');
    loadSuppliersAndCats();
  }).catch(e => alert('添加供应商失败: ' + e.message));
}

function openAddUserModal() {
  const username = prompt('请输入员工登录用户名:');
  if (!username) return;
  const password = prompt('请输入初始密码:');
  if (!password) return;
  const name = prompt('请输入员工姓名:');
  if (!name) return;
  const role = prompt('角色 (admin / cashier):', 'cashier');
  api('/api/users', 'POST', { username, password, name, role }).then(() => {
    alert('员工账号创建成功！');
    loadUsers();
  }).catch(e => alert('创建员工失败: ' + e.message));
}

window.onload = init;
</script>
</body>
</html>
"""


class POSRequestHandler(BaseHTTPRequestHandler):
    def __init__(self, *args, service: POSService, **kwargs):
        self.service = service
        super().__init__(*args, **kwargs)

    def _send_json(self, data: Any, status: int = 200) -> None:
        raw = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.end_headers()
        self.wfile.write(raw)

    def _send_html(self, html: str, status: int = 200) -> None:
        raw = html.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_OPTIONS(self) -> None:
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.end_headers()

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path
        query = parse_qs(parsed.query)

        if path == "/" or path == "/index.html":
            self._send_html(HTML_PAGE)
            return

        # REST API Endpoints
        if path == "/api/dashboard":
            data = self.service.get_dashboard()
            self._send_json(data)
            return

        if path == "/api/products":
            search = query.get("search", [None])[0]
            cat_id = int(query["category_id"][0]) if "category_id" in query else None
            low_stock = query.get("low_stock", ["0"])[0] in ("1", "true")
            prods = self.service.list_products(search=search, category_id=cat_id, low_stock_only=low_stock)
            self._send_json(prods)
            return

        if path == "/api/categories":
            cats = self.service.list_categories()
            self._send_json(cats)
            return

        if path == "/api/suppliers":
            sups = self.service.list_suppliers()
            self._send_json(sups)
            return

        if path == "/api/users":
            users = self.service.list_users()
            self._send_json(users)
            return

        if path == "/api/orders":
            orders = self.service.list_recent_orders()
            self._send_json(orders)
            return

        if path == "/api/reports":
            days = int(query.get("days", [7])[0])
            rep = self.service.get_sales_report(days=days)
            self._send_json(rep)
            return

        if path.startswith("/api/receipts/"):
            inv = path.replace("/api/receipts/", "")
            order = self.service.get_order_by_invoice(inv)
            if not order:
                self._send_json({"error": "Invoice not found"}, 404)
            else:
                self._send_json({"invoice_no": inv, "receipt_text": order.get("receipt_text")})
            return

        self._send_json({"error": f"Endpoint '{path}' not found"}, 404)

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path

        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length) if content_length > 0 else b"{}"
        try:
            payload = json.loads(body.decode("utf-8")) if body else {}
        except Exception:
            self._send_json({"error": "Invalid JSON format"}, 400)
            return

        try:
            if path == "/api/auth/login":
                user = self.service.authenticate(payload.get("username", ""), payload.get("password", ""))
                if user:
                    self._send_json({"status": "ok", "user": user})
                else:
                    self._send_json({"status": "error", "error": "Invalid username or password"}, 401)
                return

            if path == "/api/checkout":
                items = payload.get("items", [])
                cashier_id = payload.get("cashier_id")
                cust_name = payload.get("customer_name", "Walk-in Customer")
                discount = float(payload.get("discount_amount", 0.0))
                paid = float(payload.get("paid_amount")) if "paid_amount" in payload and payload["paid_amount"] is not None else None
                method = payload.get("payment_method", "CASH")

                order = self.service.checkout(
                    cart_items=items,
                    cashier_id=cashier_id,
                    customer_name=cust_name,
                    discount_amount=discount,
                    paid_amount=paid,
                    payment_method=method
                )
                self._send_json(order, 201)
                return

            if path == "/api/restock":
                pid = int(payload["product_id"])
                qty = int(payload["quantity"])
                cost = float(payload["unit_cost"])
                notes = payload.get("notes", "Web Restock")
                res = self.service.restock_product(product_id=pid, quantity=qty, unit_cost=cost, notes=notes)
                self._send_json(res, 200)
                return

            if path == "/api/products":
                prod = self.service.create_product(
                    sku=payload["sku"],
                    name=payload["name"],
                    sale_price=float(payload["sale_price"]),
                    cost_price=float(payload.get("cost_price", 0.0)),
                    stock_quantity=int(payload.get("stock_quantity", 0)),
                    min_stock_alert=int(payload.get("min_stock_alert", 10)),
                    category_id=payload.get("category_id"),
                    supplier_id=payload.get("supplier_id"),
                    barcode=payload.get("barcode")
                )
                self._send_json(prod, 201)
                return

            if path == "/api/categories":
                cat = self.service.create_category(
                    name=payload["name"],
                    description=payload.get("description", "")
                )
                self._send_json(cat, 201)
                return

            if path == "/api/suppliers":
                sup = self.service.create_supplier(
                    name=payload["name"],
                    contact_person=payload.get("contact_person", ""),
                    phone=payload.get("phone", ""),
                    email=payload.get("email", ""),
                    address=payload.get("address", "")
                )
                self._send_json(sup, 201)
                return

            if path == "/api/users":
                user = self.service.create_user(
                    username=payload["username"],
                    password=payload["password"],
                    full_name=payload.get("name", payload["username"]),
                    role=payload.get("role", "cashier")
                )
                self._send_json(user, 201)
                return

            self._send_json({"error": f"Endpoint '{path}' not found"}, 404)

        except (InsufficientStockError, InsufficientPaymentError) as e:
            self._send_json({"error": str(e)}, 400)
        except POSError as e:
            self._send_json({"error": str(e)}, 400)
        except Exception as e:
            self._send_json({"error": f"Internal server error: {e}"}, 500)


def run_server(host: str = "127.0.0.1", port: int = 8080, db_path: str = DEFAULT_DB_PATH) -> None:
    db = Database(db_path)
    service = POSService(db)

    def handler_factory(*args, **kwargs):
        return POSRequestHandler(*args, service=service, **kwargs)

    server = HTTPServer((host, port), handler_factory)
    print("=" * 60)
    print(f"🚀 POS-Lite-Modern Server running at http://{host}:{port}/")
    print("   Offline POS, Zero External Dependencies, SQLite Storage")
    print(f"   Database: {db_path}")
    print("   Press Ctrl+C to terminate.")
    print("=" * 60)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping POS server...")
    finally:
        server.server_close()


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8080
    run_server(port=port)
