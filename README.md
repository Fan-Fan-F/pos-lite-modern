# POS-Lite-Modern (现代轻量离线收银与库存系统)

> 现代轻量、零外部依赖、面向离线环境的高效收银与进销存管理系统。
> A modern, zero-dependency, offline-first Point of Sale (POS) and inventory management system.

---

## 中文说明

### 项目介绍
**POS-Lite-Modern** 是专为中小门店、离线零售与轻量终端打造的收银与库存管理系统（POS）。针对传统 POS 系统依赖复杂大型数据库、笨重图形框架及必须联网的痛点，本项目采用 **Python 3 标准库 + SQLite3** 进行全新独立重构，实现了无需联网、无需安装庞大依赖、秒级启动且能在无头（Headless）Linux 终端与现代本地网页中自由切换的现代化收银闭环。

### 功能与改进点（与原思路的关系）
本项目借鉴了经典开源项目 [Point-of-Sales](https://github.com/sadatrafsanjani/Point-of-Sales) 在收银结账、商品分类与库存管理的优秀业务概念，并进行了全方位的现代化重构与强化：

1. **极致轻量与零依赖（Zero-Dependency）**：
   - 原项目采用 Java 21 + JavaFX + Hibernate + MySQL 重型技术栈；
   - 本项目完全基于 Python 3 标准库与嵌入式 SQLite3 独立实现，无需 `pip install` 任何第三方模块，免除 MySQL 运维与 Java 运行时安装成本。
2. **纯无头环境支持与 CLI / Web 双模交互**：
   - 原项目仅支持本地桌面窗口；
   - 本项目不仅提供完备的 CLI 命令行工具（支持脚本批处理与纯终端无图形运行），同时内置免配置的轻量 Web 收银端（集成漂亮响应式 SPA 单页，适配桌面、平板触控与扫码枪）。
3. **收银全链路闭环与原子扣减**：
   - 包含多商品动态加购、数量修改、整单与单品折扣核算、应收/实收找零即时计算。
   - 底层采用 SQLite 事务，严格保证库存扣减的原子性（ACID），杜绝超卖或并发脏读。
4. **标准热敏纯文本小票引擎**：
   - 原项目依赖外部 PDF 库；
   - 本项目原生生成清晰、规范的 58mm/80mm 格式化纯文本热敏小票，支持即时终端打印、自动生成流水号、保存与导出归档。
5. **智能库存监控与采购补货（Restock）**：
   - 动态安全库存阈值报警，自动高亮低库存商品。
   - 完整的采购入库流水，录入批次成本并自动增补库存。
6. **多维销售报表与仪表盘**：
   - 提供按日结账统计、热销商品销量排行、库存资产价值统计与毛利趋势分析。
7. **角色权限与账号安全**：
   - 支持管理员（Admin）与收银员（Cashier）分权。
   - 密码采用安全加盐的 PBKDF2-HMAC-SHA256 哈希算法存储。

### 快速开始

#### 1. 环境准备
仅需系统自带的 Python 3（Python 3.8+ 均可，无需任何额外依赖包）：
```bash
python3 --version
```

#### 2. 初始化数据库与演示数据
```bash
# 初始化数据库并载入开箱即用的演示商品、分类及供应商数据
python3 pos_app.py init-db --demo
```
> 默认管理账号：`admin` / `<your-secret>`  
> 默认收银账号：`cashier` / `<your-secret>`

#### 3. 命令行终端快速使用
```bash
# 查看所有商品与库存
python3 pos_app.py products

# 采购入库（增加商品库存）
python3 pos_app.py restock --product SKU-MIL-03 --qty 20 --cost 9.50

# 收银结算（开单、打折、计算找零、扣库存并保存小票）
python3 pos_app.py checkout --items "SKU-COF-01:2,SKU-CK-04:1" --discount 3.0 --paid 50.0 --save-receipt

# 查看销售报表与仪表盘
python3 pos_app.py report

# 查看低库存报警列表
python3 pos_app.py low-stock
```

#### 4. 启动本地 Web 收银端（可选）
```bash
python3 pos_app.py serve --port 8080
```
在浏览器中打开 `http://127.0.0.1:8080/` 即可进入图形化收银台与库存管理界面。

---

## English Description

### Overview
**POS-Lite-Modern** is a lightweight, zero-dependency, offline-first Point of Sale (POS) and inventory management system designed for retail stores, popup shops, and headless terminal devices. Addressing the heavyweight runtime requirements and external database dependencies of traditional POS software, this project is completely rewritten using **Python 3 standard library + SQLite3**. It runs seamlessly offline without network access or external package installations.

### Key Features & Modern Improvements
Inspired by the core business concepts of [Point-of-Sales](https://github.com/sadatrafsanjani/Point-of-Sales), this project implements an independent modern architecture:

1. **Zero External Dependencies**:
   - Replaces Java 21, JavaFX, Hibernate, and MySQL with native Python standard library and embedded SQLite3.
   - Zero `pip` dependencies; launches instantly on any Linux, macOS, or Windows environment.
2. **Headless Linux Support & Dual Mode (CLI + Web)**:
   - Full-featured command-line interface for terminal environments and automated scripts.
   - Built-in lightweight HTTP server serving a modern responsive Single-Page Application (SPA) for touchscreens and barcode scanners.
3. **Complete Checkout Workflow & Atomic Stock Deduction**:
   - Multi-item shopping cart, item quantity adjustment, custom discount calculation, cash tendered, and exact change calculation.
   - Fully protected by SQLite transactions (ACID) to prevent overselling.
4. **Formatted Plain-Text Thermal Receipt Engine**:
   - Generates standardized 58mm/80mm plain-text thermal receipts with timestamps, invoices, itemized details, and payment summary.
   - Supports terminal printing, file exports, and receipt retrieval by invoice ID.
5. **Inventory Tracking & Restocking**:
   - Low-stock threshold alerts and health monitoring.
   - Purchase and restocking workflow with batch unit cost tracking.
6. **Sales Analytics & Dashboard**:
   - Daily sales reports, best-selling product rankings, inventory valuation, and revenue metrics.
7. **Role-Based Access Control**:
   - Role separation between Administrators and Cashiers with PBKDF2-HMAC-SHA256 salted password hashing.

### Quick Start

#### 1. Requirements
Standard Python 3 (Python 3.8+ supported, no external packages required):
```bash
python3 --version
```

#### 2. Initialize Database & Demo Data
```bash
python3 pos_app.py init-db --demo
```
> Default Admin: `admin` / `<your-secret>`  
> Default Cashier: `cashier` / `<your-secret>`

#### 3. CLI Usage
```bash
# List products and current inventory
python3 pos_app.py products

# Restock inventory
python3 pos_app.py restock --product SKU-MIL-03 --qty 20 --cost 9.50

# Checkout cart items (item:qty), apply discount, tender payment, and save receipt
python3 pos_app.py checkout --items "SKU-COF-01:2,SKU-CK-04:1" --discount 3.0 --paid 50.0 --save-receipt

# View sales dashboard and reporting
python3 pos_app.py report

# View low stock warning list
python3 pos_app.py low-stock
```

#### 4. Run Local Offline Web Interface
```bash
python3 pos_app.py serve --port 8080
```
Open `http://127.0.0.1:8080/` in your browser to access the responsive web POS terminal.

---

## 来源与致谢 / Acknowledgements

本项目的思路与功能设计受到 Point-of-Sales（https://github.com/sadatrafsanjani/Point-of-Sales）启发，原项目作者为 sadatrafsanjani，代码为独立实现。

The concept and functional design of this project are inspired by Point-of-Sales (https://github.com/sadatrafsanjani/Point-of-Sales); the codebase is an independent implementation.

---

## 许可证 / License

本项目沿用 MIT 许可证，全文见根目录 [LICENSE](LICENSE)。

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
