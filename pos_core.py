"""
Core business logic and SQLite database engine for pos-lite-modern.
Implements authentication, catalog management, inventory tracking,
POS checkout transaction, receipt generation, and sales reporting.
100% Python standard library.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
import sqlite3
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

DEFAULT_DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "pos_data.db")


# ---------------------------------------------------------------------------
# Password security helpers
# ---------------------------------------------------------------------------

def hash_password(password: str, salt: Optional[str] = None) -> Tuple[str, str]:
    """Generates PBKDF2-HMAC-SHA256 hash with random salt."""
    if not salt:
        salt = secrets.token_hex(16)
    hashed = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt.encode("utf-8"),
        100_000,
    ).hex()
    return hashed, salt


def verify_password(password: str, expected_hash: str, salt: str) -> bool:
    """Verifies password using constant-time comparison."""
    test_hash, _ = hash_password(password, salt)
    return hmac.compare_digest(test_hash, expected_hash)


# ---------------------------------------------------------------------------
# Domain Exceptions
# ---------------------------------------------------------------------------

class POSError(Exception):
    """Base POS domain error."""
    pass


class InsufficientStockError(POSError):
    """Raised when available inventory is lower than requested quantity."""
    pass


class InsufficientPaymentError(POSError):
    """Raised when paid amount is less than total bill."""
    pass


class EntityNotFoundError(POSError):
    """Raised when query entity does not exist."""
    pass


# ---------------------------------------------------------------------------
# Database Management & Schema
# ---------------------------------------------------------------------------

class Database:
    def __init__(self, db_path: str = DEFAULT_DB_PATH):
        self.db_path = db_path
        self._init_db()

    def get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON;")
        return conn

    def _init_db(self) -> None:
        """Initializes database tables if they do not exist."""
        os.makedirs(os.path.dirname(os.path.abspath(self.db_path)), exist_ok=True)
        with self.get_connection() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT UNIQUE NOT NULL,
                    password_hash TEXT NOT NULL,
                    salt TEXT NOT NULL,
                    full_name TEXT NOT NULL,
                    role TEXT NOT NULL CHECK(role IN ('admin', 'cashier')),
                    is_active INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS categories (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT UNIQUE NOT NULL,
                    description TEXT
                );

                CREATE TABLE IF NOT EXISTS suppliers (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    contact_person TEXT,
                    phone TEXT,
                    email TEXT,
                    address TEXT
                );

                CREATE TABLE IF NOT EXISTS products (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    sku TEXT UNIQUE NOT NULL,
                    barcode TEXT,
                    name TEXT NOT NULL,
                    category_id INTEGER,
                    supplier_id INTEGER,
                    cost_price REAL NOT NULL DEFAULT 0.0,
                    sale_price REAL NOT NULL DEFAULT 0.0,
                    stock_quantity INTEGER NOT NULL DEFAULT 0,
                    min_stock_alert INTEGER NOT NULL DEFAULT 10,
                    is_active INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(category_id) REFERENCES categories(id) ON DELETE SET NULL,
                    FOREIGN KEY(supplier_id) REFERENCES suppliers(id) ON DELETE SET NULL
                );

                CREATE TABLE IF NOT EXISTS purchases (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    purchase_no TEXT UNIQUE NOT NULL,
                    supplier_id INTEGER,
                    total_cost REAL NOT NULL,
                    notes TEXT,
                    created_by INTEGER,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(supplier_id) REFERENCES suppliers(id) ON DELETE SET NULL,
                    FOREIGN KEY(created_by) REFERENCES users(id) ON DELETE SET NULL
                );

                CREATE TABLE IF NOT EXISTS purchase_items (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    purchase_id INTEGER NOT NULL,
                    product_id INTEGER NOT NULL,
                    quantity INTEGER NOT NULL,
                    unit_cost REAL NOT NULL,
                    subtotal REAL NOT NULL,
                    FOREIGN KEY(purchase_id) REFERENCES purchases(id) ON DELETE CASCADE,
                    FOREIGN KEY(product_id) REFERENCES products(id) ON DELETE RESTRICT
                );

                CREATE TABLE IF NOT EXISTS orders (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    invoice_no TEXT UNIQUE NOT NULL,
                    cashier_id INTEGER,
                    customer_name TEXT NOT NULL DEFAULT 'Walk-in Customer',
                    subtotal REAL NOT NULL,
                    discount_amount REAL NOT NULL DEFAULT 0.0,
                    tax_amount REAL NOT NULL DEFAULT 0.0,
                    total_amount REAL NOT NULL,
                    paid_amount REAL NOT NULL,
                    change_amount REAL NOT NULL,
                    payment_method TEXT NOT NULL DEFAULT 'CASH',
                    status TEXT NOT NULL DEFAULT 'COMPLETED',
                    receipt_text TEXT,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(cashier_id) REFERENCES users(id) ON DELETE SET NULL
                );

                CREATE TABLE IF NOT EXISTS order_items (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    order_id INTEGER NOT NULL,
                    product_id INTEGER NOT NULL,
                    product_name TEXT NOT NULL,
                    sku TEXT NOT NULL,
                    unit_price REAL NOT NULL,
                    quantity INTEGER NOT NULL,
                    subtotal REAL NOT NULL,
                    FOREIGN KEY(order_id) REFERENCES orders(id) ON DELETE CASCADE,
                    FOREIGN KEY(product_id) REFERENCES products(id) ON DELETE RESTRICT
                );

                CREATE INDEX IF NOT EXISTS idx_products_sku ON products(sku);
                CREATE INDEX IF NOT EXISTS idx_orders_invoice ON orders(invoice_no);
                CREATE INDEX IF NOT EXISTS idx_orders_created ON orders(created_at);
            """)

    def seed_initial_data(self, create_demo: bool = True) -> Dict[str, Any]:
        """Seeds initial admin and optional demo inventory."""
        with self.get_connection() as conn:
            # Check if admin already exists
            cur = conn.cursor()
            cur.execute("SELECT id FROM users WHERE username = 'admin'")
            admin_row = cur.fetchone()
            if not admin_row:
                admin_initial_pw = os.environ.get("POS_ADMIN_PASSWORD", "<your-secret>")
                h, s = hash_password(admin_initial_pw)
                now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                cur.execute(
                    """INSERT INTO users (username, password_hash, salt, full_name, role, is_active, created_at)
                       VALUES (?, ?, ?, ?, ?, 1, ?)""",
                    ("admin", h, s, "Store Administrator", "admin", now)
                )

            # Cashier account
            cur.execute("SELECT id FROM users WHERE username = 'cashier'")
            if not cur.fetchone():
                cashier_initial_pw = os.environ.get("POS_CASHIER_PASSWORD", "<your-secret>")
                h, s = hash_password(cashier_initial_pw)
                now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                cur.execute(
                    """INSERT INTO users (username, password_hash, salt, full_name, role, is_active, created_at)
                       VALUES (?, ?, ?, ?, ?, 1, ?)""",
                    ("cashier", h, s, "Alice Wang (Cashier)", "cashier", now)
                )

            if create_demo:
                # Categories
                categories = [
                    ("Beverages", "Drinks, coffee, tea, and soda"),
                    ("Snacks & Bakery", "Bread, cookies, chips and pastries"),
                    ("Daily Essentials", "Personal care, household, and stationery")
                ]
                for name, desc in categories:
                    cur.execute(
                        "INSERT OR IGNORE INTO categories (name, description) VALUES (?, ?)",
                        (name, desc)
                    )

                # Suppliers
                suppliers = [
                    ("Global Fresh Foods Ltd", "David Zhang", "13800000001", "supply@globalfresh.com", "Industrial Park #1"),
                    ("Sunrise Daily Supplies Co", "Sarah Chen", "13800000002", "order@sunrisesupply.com", "East Logistics Center #5")
                ]
                for name, cp, phone, email, addr in suppliers:
                    cur.execute(
                        """INSERT OR IGNORE INTO suppliers (name, contact_person, phone, email, address)
                           VALUES (?, ?, ?, ?, ?)""",
                        (name, cp, phone, email, addr)
                    )

                # Fetch IDs
                cur.execute("SELECT id FROM categories WHERE name = 'Beverages'")
                cat_bev = cur.fetchone()[0]
                cur.execute("SELECT id FROM categories WHERE name = 'Snacks & Bakery'")
                cat_snack = cur.fetchone()[0]
                cur.execute("SELECT id FROM categories WHERE name = 'Daily Essentials'")
                cat_ess = cur.fetchone()[0]

                cur.execute("SELECT id FROM suppliers LIMIT 1")
                sup_id = cur.fetchone()[0]

                now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                demo_products = [
                    ("SKU-COF-01", "6901001001", "Cold Brew Americano 300ml", cat_bev, sup_id, 4.50, 12.00, 45, 10),
                    ("SKU-TEA-02", "6901001002", "Jasmine Green Tea 500ml", cat_bev, sup_id, 2.00, 6.50, 60, 15),
                    ("SKU-MIL-03", "6901001003", "Organic Oat Milk 1L", cat_bev, sup_id, 9.80, 22.00, 8, 10),  # Low stock
                    ("SKU-CK-04", "6902001004", "Butter Croissant", cat_snack, sup_id, 3.20, 9.00, 25, 8),
                    ("SKU-CH-05", "6902001005", "Sea Salt Potato Chips 110g", cat_snack, sup_id, 3.80, 8.50, 35, 10),
                    ("SKU-TIS-06", "6903001006", "Soft Facial Tissues 3-Ply", cat_ess, sup_id, 1.50, 4.00, 5, 10),   # Low stock
                    ("SKU-PEN-07", "6903001007", "Gel Ink Pen 0.5mm Black", cat_ess, sup_id, 0.80, 3.00, 120, 20),
                ]

                for sku, barcode, name, cid, sid, cost, sale, qty, min_alert in demo_products:
                    cur.execute("SELECT id FROM products WHERE sku = ?", (sku,))
                    if not cur.fetchone():
                        cur.execute(
                            """INSERT INTO products
                               (sku, barcode, name, category_id, supplier_id, cost_price, sale_price, stock_quantity, min_stock_alert, is_active, created_at)
                               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?)""",
                            (sku, barcode, name, cid, sid, cost, sale, qty, min_alert, now)
                        )
            conn.commit()

        return {"status": "success", "message": "Database initialized and seeded."}


# ---------------------------------------------------------------------------
# Business Services
# ---------------------------------------------------------------------------

class POSService:
    def __init__(self, db: Optional[Database] = None):
        self.db = db or Database()

    # --- User & Auth ---
    def authenticate(self, username: str, password: str) -> Optional[Dict[str, Any]]:
        with self.db.get_connection() as conn:
            cur = conn.cursor()
            cur.execute(
                "SELECT id, username, password_hash, salt, full_name, role, is_active FROM users WHERE username = ?",
                (username,)
            )
            row = cur.fetchone()
            if not row:
                return None
            if not row["is_active"]:
                return None
            if verify_password(password, row["password_hash"], row["salt"]):
                return {
                    "id": row["id"],
                    "username": row["username"],
                    "full_name": row["full_name"],
                    "role": row["role"]
                }
            return None

    def create_user(self, username: str, password: str, full_name: str, role: str = "cashier") -> Dict[str, Any]:
        if role not in ("admin", "cashier"):
            raise ValueError("Role must be 'admin' or 'cashier'")
        h, s = hash_password(password)
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with self.db.get_connection() as conn:
            cur = conn.cursor()
            cur.execute(
                """INSERT INTO users (username, password_hash, salt, full_name, role, is_active, created_at)
                   VALUES (?, ?, ?, ?, ?, 1, ?)""",
                (username, h, s, full_name, role, now)
            )
            user_id = cur.lastrowid
            conn.commit()
            return {"id": user_id, "username": username, "full_name": full_name, "role": role}

    def list_users(self) -> List[Dict[str, Any]]:
        with self.db.get_connection() as conn:
            cur = conn.cursor()
            cur.execute("SELECT id, username, full_name, role, is_active, created_at FROM users ORDER BY id ASC")
            return [dict(r) for r in cur.fetchall()]

    # --- Categories ---
    def create_category(self, name: str, description: str = "") -> Dict[str, Any]:
        with self.db.get_connection() as conn:
            cur = conn.cursor()
            cur.execute("INSERT INTO categories (name, description) VALUES (?, ?)", (name, description))
            conn.commit()
            return {"id": cur.lastrowid, "name": name, "description": description}

    def list_categories(self) -> List[Dict[str, Any]]:
        with self.db.get_connection() as conn:
            cur = conn.cursor()
            cur.execute("""
                SELECT c.id, c.name, c.description, COUNT(p.id) AS product_count
                FROM categories c
                LEFT JOIN products p ON p.category_id = c.id
                GROUP BY c.id
                ORDER BY c.name ASC
            """)
            return [dict(r) for r in cur.fetchall()]

    # --- Suppliers ---
    def create_supplier(self, name: str, contact_person: str = "", phone: str = "", email: str = "", address: str = "") -> Dict[str, Any]:
        with self.db.get_connection() as conn:
            cur = conn.cursor()
            cur.execute(
                "INSERT INTO suppliers (name, contact_person, phone, email, address) VALUES (?, ?, ?, ?, ?)",
                (name, contact_person, phone, email, address)
            )
            conn.commit()
            return {"id": cur.lastrowid, "name": name, "contact_person": contact_person, "phone": phone, "email": email, "address": address}

    def list_suppliers(self) -> List[Dict[str, Any]]:
        with self.db.get_connection() as conn:
            cur = conn.cursor()
            cur.execute("SELECT * FROM suppliers ORDER BY id ASC")
            return [dict(r) for r in cur.fetchall()]

    # --- Products & Inventory ---
    def create_product(
        self,
        sku: str,
        name: str,
        sale_price: float,
        cost_price: float = 0.0,
        stock_quantity: int = 0,
        min_stock_alert: int = 10,
        category_id: Optional[int] = None,
        supplier_id: Optional[int] = None,
        barcode: Optional[str] = None,
    ) -> Dict[str, Any]:
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with self.db.get_connection() as conn:
            cur = conn.cursor()
            cur.execute(
                """INSERT INTO products
                   (sku, barcode, name, category_id, supplier_id, cost_price, sale_price, stock_quantity, min_stock_alert, is_active, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?)""",
                (sku, barcode or sku, name, category_id, supplier_id, float(cost_price), float(sale_price), int(stock_quantity), int(min_stock_alert), now)
            )
            prod_id = cur.lastrowid
            conn.commit()
            return self.get_product(prod_id)

    def get_product(self, product_id: int) -> Dict[str, Any]:
        with self.db.get_connection() as conn:
            cur = conn.cursor()
            cur.execute("""
                SELECT p.*, c.name AS category_name, s.name AS supplier_name
                FROM products p
                LEFT JOIN categories c ON p.category_id = c.id
                LEFT JOIN suppliers s ON p.supplier_id = s.id
                WHERE p.id = ?
            """, (product_id,))
            row = cur.fetchone()
            if not row:
                raise EntityNotFoundError(f"Product ID {product_id} not found.")
            res = dict(row)
            res["is_low_stock"] = res["stock_quantity"] <= res["min_stock_alert"]
            return res

    def get_product_by_sku_or_barcode(self, identifier: str) -> Optional[Dict[str, Any]]:
        with self.db.get_connection() as conn:
            cur = conn.cursor()
            cur.execute("""
                SELECT p.*, c.name AS category_name, s.name AS supplier_name
                FROM products p
                LEFT JOIN categories c ON p.category_id = c.id
                LEFT JOIN suppliers s ON p.supplier_id = s.id
                WHERE (p.sku = ? OR p.barcode = ? OR p.name = ?) AND p.is_active = 1
                LIMIT 1
            """, (identifier, identifier, identifier))
            row = cur.fetchone()
            if not row:
                return None
            res = dict(row)
            res["is_low_stock"] = res["stock_quantity"] <= res["min_stock_alert"]
            return res

    def list_products(
        self,
        search: Optional[str] = None,
        category_id: Optional[int] = None,
        low_stock_only: bool = False
    ) -> List[Dict[str, Any]]:
        with self.db.get_connection() as conn:
            cur = conn.cursor()
            sql = """
                SELECT p.*, c.name AS category_name, s.name AS supplier_name
                FROM products p
                LEFT JOIN categories c ON p.category_id = c.id
                LEFT JOIN suppliers s ON p.supplier_id = s.id
                WHERE p.is_active = 1
            """
            params: List[Any] = []
            if search:
                sql += " AND (p.name LIKE ? OR p.sku LIKE ? OR p.barcode LIKE ?)"
                kw = f"%{search}%"
                params.extend([kw, kw, kw])
            if category_id:
                sql += " AND p.category_id = ?"
                params.append(category_id)
            if low_stock_only:
                sql += " AND p.stock_quantity <= p.min_stock_alert"

            sql += " ORDER BY p.id ASC"
            cur.execute(sql, params)
            rows = [dict(r) for r in cur.fetchall()]
            for r in rows:
                r["is_low_stock"] = r["stock_quantity"] <= r["min_stock_alert"]
            return rows

    # --- Restocking / Purchase ---
    def restock_product(
        self,
        product_id: int,
        quantity: int,
        unit_cost: float,
        supplier_id: Optional[int] = None,
        notes: str = "Stock Purchase",
        user_id: Optional[int] = None
    ) -> Dict[str, Any]:
        """Adds stock to a product and creates a purchase record."""
        if quantity <= 0:
            raise ValueError("Restock quantity must be positive.")
        now = datetime.now()
        purchase_no = f"PO-{now.strftime('%Y%m%d%H%M%S')}-{secrets.randbelow(1000):03d}"
        now_str = now.strftime("%Y-%m-%d %H:%M:%S")

        with self.db.get_connection() as conn:
            cur = conn.cursor()
            cur.execute("SELECT id, name, stock_quantity, supplier_id, cost_price FROM products WHERE id = ?", (product_id,))
            prod = cur.fetchone()
            if not prod:
                raise EntityNotFoundError(f"Product {product_id} not found.")

            target_sup = supplier_id or prod["supplier_id"]
            subtotal = round(quantity * unit_cost, 2)

            # Insert purchase header
            cur.execute(
                """INSERT INTO purchases (purchase_no, supplier_id, total_cost, notes, created_by, created_at)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (purchase_no, target_sup, subtotal, notes, user_id, now_str)
            )
            purchase_id = cur.lastrowid

            # Insert purchase line item
            cur.execute(
                """INSERT INTO purchase_items (purchase_id, product_id, quantity, unit_cost, subtotal)
                   VALUES (?, ?, ?, ?, ?)""",
                (purchase_id, product_id, quantity, unit_cost, subtotal)
            )

            # Update product stock & cost price
            new_qty = prod["stock_quantity"] + quantity
            cur.execute(
                "UPDATE products SET stock_quantity = ?, cost_price = ? WHERE id = ?",
                (new_qty, unit_cost, product_id)
            )
            conn.commit()

            return {
                "purchase_no": purchase_no,
                "product_id": product_id,
                "product_name": prod["name"],
                "quantity_added": quantity,
                "new_stock": new_qty,
                "unit_cost": unit_cost,
                "total_cost": subtotal,
                "created_at": now_str
            }

    # --- POS Checkout / Cashier ---
    def checkout(
        self,
        cart_items: List[Dict[str, Any]],
        cashier_id: Optional[int] = None,
        customer_name: str = "Walk-in Customer",
        discount_amount: float = 0.0,
        paid_amount: Optional[float] = None,
        payment_method: str = "CASH"
    ) -> Dict[str, Any]:
        """
        Executes an atomic POS transaction:
        - Validates cart items and stock
        - Deducts stock quantity
        - Computes totals and change
        - Generates formatted text receipt
        - Records order and order items in database
        """
        if not cart_items:
            raise POSError("Cart cannot be empty.")

        now = datetime.now()
        invoice_no = f"INV-{now.strftime('%Y%m%d%H%M%S')}-{secrets.randbelow(1000):03d}"
        now_str = now.strftime("%Y-%m-%d %H:%M:%S")

        with self.db.get_connection() as conn:
            cur = conn.cursor()

            # Retrieve cashier info
            cashier_name = "Cashier"
            if cashier_id:
                cur.execute("SELECT full_name FROM users WHERE id = ?", (cashier_id,))
                c_row = cur.fetchone()
                if c_row:
                    cashier_name = c_row["full_name"]

            # Validate products and stock
            prepared_items = []
            subtotal = 0.0

            for item in cart_items:
                identifier = str(item.get("sku") or item.get("product_id") or item.get("id"))
                qty = int(item.get("quantity", 1))
                if qty <= 0:
                    raise ValueError(f"Invalid quantity {qty} for item {identifier}")

                # Query product by id or sku
                cur.execute(
                    """SELECT id, sku, barcode, name, sale_price, stock_quantity
                       FROM products
                       WHERE (id = ? OR sku = ? OR barcode = ?) AND is_active = 1""",
                    (identifier if identifier.isdigit() else -1, identifier, identifier)
                )
                prod = cur.fetchone()
                if not prod:
                    raise EntityNotFoundError(f"Product '{identifier}' not found in active inventory.")

                current_stock = prod["stock_quantity"]
                if current_stock < qty:
                    raise InsufficientStockError(
                        f"Insufficient stock for '{prod['name']}' (SKU: {prod['sku']}). "
                        f"Requested: {qty}, Available: {current_stock}."
                    )

                unit_price = float(prod["sale_price"])
                line_subtotal = round(unit_price * qty, 2)
                subtotal += line_subtotal

                prepared_items.append({
                    "product_id": prod["id"],
                    "sku": prod["sku"],
                    "name": prod["name"],
                    "unit_price": unit_price,
                    "quantity": qty,
                    "subtotal": line_subtotal,
                    "current_stock": current_stock
                })

            subtotal = round(subtotal, 2)
            discount_amount = max(0.0, round(float(discount_amount), 2))
            total_amount = max(0.0, round(subtotal - discount_amount, 2))

            if paid_amount is None:
                paid_amount = total_amount
            else:
                paid_amount = round(float(paid_amount), 2)

            if paid_amount < total_amount:
                raise InsufficientPaymentError(
                    f"Paid amount (${paid_amount:.2f}) is less than total amount (${total_amount:.2f})."
                )

            change_amount = round(paid_amount - total_amount, 2)

            # Generate formatted receipt text
            receipt_text = self._build_receipt_text(
                invoice_no=invoice_no,
                now_str=now_str,
                cashier_name=cashier_name,
                customer_name=customer_name,
                items=prepared_items,
                subtotal=subtotal,
                discount_amount=discount_amount,
                total_amount=total_amount,
                paid_amount=paid_amount,
                change_amount=change_amount,
                payment_method=payment_method
            )

            # Insert order
            cur.execute(
                """INSERT INTO orders
                   (invoice_no, cashier_id, customer_name, subtotal, discount_amount, tax_amount,
                    total_amount, paid_amount, change_amount, payment_method, status, receipt_text, created_at)
                   VALUES (?, ?, ?, ?, ?, 0.0, ?, ?, ?, ?, 'COMPLETED', ?, ?)""",
                (invoice_no, cashier_id, customer_name, subtotal, discount_amount,
                 total_amount, paid_amount, change_amount, payment_method, receipt_text, now_str)
            )
            order_id = cur.lastrowid

            # Insert order items and deduct stock
            for p_item in prepared_items:
                cur.execute(
                    """INSERT INTO order_items (order_id, product_id, product_name, sku, unit_price, quantity, subtotal)
                       VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (order_id, p_item["product_id"], p_item["name"], p_item["sku"],
                     p_item["unit_price"], p_item["quantity"], p_item["subtotal"])
                )
                cur.execute(
                    "UPDATE products SET stock_quantity = stock_quantity - ? WHERE id = ?",
                    (p_item["quantity"], p_item["product_id"])
                )

            conn.commit()

            return {
                "order_id": order_id,
                "invoice_no": invoice_no,
                "subtotal": subtotal,
                "discount_amount": discount_amount,
                "total_amount": total_amount,
                "paid_amount": paid_amount,
                "change_amount": change_amount,
                "payment_method": payment_method,
                "items": prepared_items,
                "receipt_text": receipt_text,
                "created_at": now_str
            }

    def _build_receipt_text(
        self,
        invoice_no: str,
        now_str: str,
        cashier_name: str,
        customer_name: str,
        items: List[Dict[str, Any]],
        subtotal: float,
        discount_amount: float,
        total_amount: float,
        paid_amount: float,
        change_amount: float,
        payment_method: str
    ) -> str:
        """Formats an 80mm/58mm standard thermal plain-text POS receipt."""
        w = 42
        lines = []
        lines.append("=" * w)
        lines.append("        POS-LITE MODERN STORE        ".center(w))
        lines.append("     Smart Offline POS System        ".center(w))
        lines.append("=" * w)
        lines.append(f"Invoice : {invoice_no}")
        lines.append(f"Date    : {now_str}")
        lines.append(f"Cashier : {cashier_name}")
        lines.append(f"Customer: {customer_name}")
        lines.append("-" * w)
        lines.append(f"{'Item':<20} {'Qty':>3} {'Price':>7} {'Total':>8}")
        lines.append("-" * w)

        for it in items:
            name = it["name"]
            if len(name) > 19:
                name = name[:17] + ".."
            qty = it["quantity"]
            price = f"${it['unit_price']:.2f}"
            tot = f"${it['subtotal']:.2f}"
            lines.append(f"{name:<20} {qty:>3} {price:>7} {tot:>8}")

        lines.append("-" * w)
        lines.append(f"{'Subtotal:':<28} ${subtotal:>10.2f}")
        if discount_amount > 0:
            lines.append(f"{'Discount:':<28} -${discount_amount:>9.2f}")
        lines.append(f"{'TOTAL DUE:':<28} ${total_amount:>10.2f}")
        lines.append("." * w)
        lines.append(f"{payment_method.upper()} Tendered:{'':<14} ${paid_amount:>10.2f}")
        lines.append(f"{'Change Given:':<28} ${change_amount:>10.2f}")
        lines.append("=" * w)
        lines.append("   Thank you for your business!      ".center(w))
        lines.append("     Please come again soon!         ".center(w))
        lines.append("   ||| | || ||||| |||| || |||| ||    ".center(w))
        lines.append("=" * w)
        return "\n".join(lines)

    def get_order_by_invoice(self, invoice_no: str) -> Optional[Dict[str, Any]]:
        with self.db.get_connection() as conn:
            cur = conn.cursor()
            cur.execute("""
                SELECT o.*, u.full_name AS cashier_name
                FROM orders o
                LEFT JOIN users u ON o.cashier_id = u.id
                WHERE o.invoice_no = ?
            """, (invoice_no,))
            order_row = cur.fetchone()
            if not order_row:
                return None
            order = dict(order_row)
            cur.execute("SELECT * FROM order_items WHERE order_id = ?", (order["id"],))
            order["items"] = [dict(r) for r in cur.fetchall()]
            return order

    def list_recent_orders(self, limit: int = 20) -> List[Dict[str, Any]]:
        with self.db.get_connection() as conn:
            cur = conn.cursor()
            cur.execute("""
                SELECT o.id, o.invoice_no, o.customer_name, o.total_amount, o.paid_amount,
                       o.change_amount, o.payment_method, o.created_at, u.full_name AS cashier_name,
                       COUNT(oi.id) AS item_count
                FROM orders o
                LEFT JOIN users u ON o.cashier_id = u.id
                LEFT JOIN order_items oi ON oi.order_id = o.id
                GROUP BY o.id
                ORDER BY o.id DESC
                LIMIT ?
            """, (limit,))
            return [dict(r) for r in cur.fetchall()]

    # --- Reporting & Dashboard ---
    def get_dashboard(self) -> Dict[str, Any]:
        with self.db.get_connection() as conn:
            cur = conn.cursor()
            today_prefix = datetime.now().strftime("%Y-%m-%d")

            # Products summary
            cur.execute("SELECT COUNT(*), SUM(stock_quantity), SUM(stock_quantity * cost_price), SUM(stock_quantity * sale_price) FROM products WHERE is_active = 1")
            prod_stats = cur.fetchone()
            total_products = prod_stats[0] or 0
            total_stock_units = prod_stats[1] or 0
            inventory_cost_value = round(prod_stats[2] or 0.0, 2)
            inventory_sale_value = round(prod_stats[3] or 0.0, 2)

            # Low stock products count
            cur.execute("SELECT COUNT(*) FROM products WHERE is_active = 1 AND stock_quantity <= min_stock_alert")
            low_stock_count = cur.fetchone()[0] or 0

            # Today sales
            cur.execute(
                "SELECT COUNT(*), SUM(total_amount) FROM orders WHERE created_at LIKE ?",
                (f"{today_prefix}%",)
            )
            today_stats = cur.fetchone()
            today_orders = today_stats[0] or 0
            today_revenue = round(today_stats[1] or 0.0, 2)

            # All time sales
            cur.execute("SELECT COUNT(*), SUM(total_amount) FROM orders")
            all_time = cur.fetchone()
            total_orders = all_time[0] or 0
            total_revenue = round(all_time[1] or 0.0, 2)

            return {
                "total_products": total_products,
                "total_stock_units": total_stock_units,
                "inventory_cost_value": inventory_cost_value,
                "inventory_sale_value": inventory_sale_value,
                "low_stock_count": low_stock_count,
                "today_orders": today_orders,
                "today_revenue": today_revenue,
                "total_orders": total_orders,
                "total_revenue": total_revenue,
            }

    def get_sales_report(self, days: int = 7) -> Dict[str, Any]:
        """Returns daily sales aggregations and top-selling products."""
        with self.db.get_connection() as conn:
            cur = conn.cursor()

            # Daily sales breakdown
            cur.execute("""
                SELECT SUBSTR(created_at, 1, 10) AS sales_date,
                       COUNT(id) AS order_count,
                       SUM(subtotal) AS total_subtotal,
                       SUM(discount_amount) AS total_discounts,
                       SUM(total_amount) AS total_revenue
                FROM orders
                GROUP BY sales_date
                ORDER BY sales_date DESC
                LIMIT ?
            """, (days,))
            daily_rows = [dict(r) for r in cur.fetchall()]

            # Top selling products
            cur.execute("""
                SELECT oi.sku, oi.product_name,
                       SUM(oi.quantity) AS total_qty_sold,
                       ROUND(SUM(oi.subtotal), 2) AS total_sales_amount
                FROM order_items oi
                JOIN orders o ON o.id = oi.order_id
                GROUP BY oi.product_id
                ORDER BY total_qty_sold DESC
                LIMIT 10
            """)
            top_products = [dict(r) for r in cur.fetchall()]

            # Low stock alert list
            cur.execute("""
                SELECT p.id, p.sku, p.name, p.stock_quantity, p.min_stock_alert, p.sale_price,
                       c.name AS category_name
                FROM products p
                LEFT JOIN categories c ON p.category_id = c.id
                WHERE p.is_active = 1 AND p.stock_quantity <= p.min_stock_alert
                ORDER BY p.stock_quantity ASC
            """)
            low_stock_alerts = [dict(r) for r in cur.fetchall()]

            return {
                "daily_breakdown": daily_rows,
                "top_products": top_products,
                "low_stock_alerts": low_stock_alerts,
            }
