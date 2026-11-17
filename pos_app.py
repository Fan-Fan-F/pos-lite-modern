#!/usr/bin/env python3
"""
POS-Lite-Modern: Command-Line Interface and Runner.
Modern, offline-first Point of Sale & Inventory Management System.
100% Python 3 standard library.
"""

from __future__ import annotations

import argparse
import os
import sys
from typing import List

from pos_core import (
    DEFAULT_DB_PATH,
    Database,
    InsufficientPaymentError,
    InsufficientStockError,
    POSError,
    POSService,
)


def format_table(headers: List[str], rows: List[List[str]]) -> str:
    """Formats clean ASCII tabular output."""
    if not headers and not rows:
        return "(empty)"
    col_widths = [len(h) for h in headers]
    for row in rows:
        for i, val in enumerate(row):
            if i < len(col_widths):
                col_widths[i] = max(col_widths[i], len(str(val)))
            else:
                col_widths.append(len(str(val)))

    sep = "+-" + "-+-".join("-" * w for w in col_widths) + "-+"
    header_line = "| " + " | ".join(h.ljust(col_widths[i]) for i, h in enumerate(headers)) + " |"

    res = [sep, header_line, sep]
    for row in rows:
        line = "| " + " | ".join(str(row[i]).ljust(col_widths[i]) if i < len(row) else "".ljust(col_widths[i]) for i in range(len(col_widths))) + " |"
        res.append(line)
    res.append(sep)
    return "\n".join(res)


def cmd_init_db(service: POSService, args: argparse.Namespace) -> None:
    res = service.db.seed_initial_data(create_demo=args.demo)
    print(f"[OK] {res['message']} (Demo data: {'Enabled' if args.demo else 'Disabled'})")
    print("Default accounts:")
    print("  - Admin  : admin / <your-secret>")
    print("  - Cashier: cashier / <your-secret>")


def cmd_users(service: POSService, args: argparse.Namespace) -> None:
    users = service.list_users()
    headers = ["ID", "Username", "Full Name", "Role", "Active", "Created At"]
    rows = [[str(u["id"]), u["username"], u["full_name"], u["role"], "Yes" if u["is_active"] else "No", u["created_at"]] for u in users]
    print("\n--- System Users & Employees ---")
    print(format_table(headers, rows))


def cmd_add_user(service: POSService, args: argparse.Namespace) -> None:
    try:
        user = service.create_user(
            username=args.username,
            password=args.password,
            full_name=args.name,
            role=args.role
        )
        print(f"[OK] User created successfully: ID {user['id']}, {user['username']} ({user['role']})")
    except Exception as e:
        print(f"[ERROR] Failed to create user: {e}", file=sys.stderr)
        sys.exit(1)


def cmd_categories(service: POSService, args: argparse.Namespace) -> None:
    cats = service.list_categories()
    headers = ["ID", "Category Name", "Description", "Products Count"]
    rows = [[str(c["id"]), c["name"], c["description"] or "", str(c["product_count"])] for c in cats]
    print("\n--- Product Categories ---")
    print(format_table(headers, rows))


def cmd_add_category(service: POSService, args: argparse.Namespace) -> None:
    cat = service.create_category(args.name, args.desc or "")
    print(f"[OK] Category '{cat['name']}' created with ID {cat['id']}")


def cmd_suppliers(service: POSService, args: argparse.Namespace) -> None:
    sups = service.list_suppliers()
    headers = ["ID", "Supplier Name", "Contact Person", "Phone", "Email", "Address"]
    rows = [[str(s["id"]), s["name"], s["contact_person"] or "", s["phone"] or "", s["email"] or "", s["address"] or ""] for s in sups]
    print("\n--- Suppliers ---")
    print(format_table(headers, rows))


def cmd_add_supplier(service: POSService, args: argparse.Namespace) -> None:
    sup = service.create_supplier(
        name=args.name,
        contact_person=args.contact or "",
        phone=args.phone or "",
        email=args.email or "",
        address=args.address or ""
    )
    print(f"[OK] Supplier '{sup['name']}' created with ID {sup['id']}")


def cmd_products(service: POSService, args: argparse.Namespace) -> None:
    products = service.list_products(
        search=args.search,
        category_id=args.category,
        low_stock_only=args.low_stock
    )
    headers = ["ID", "SKU", "Product Name", "Category", "Cost ($)", "Price ($)", "Stock", "Alert Limit", "Status"]
    rows = []
    for p in products:
        status = "LOW STOCK!" if p["is_low_stock"] else "Normal"
        rows.append([
            str(p["id"]),
            p["sku"],
            p["name"],
            p["category_name"] or "-",
            f"{p['cost_price']:.2f}",
            f"{p['sale_price']:.2f}",
            str(p["stock_quantity"]),
            str(p["min_stock_alert"]),
            status
        ])
    print(f"\n--- Products & Inventory ({'Low Stock Alerts Only' if args.low_stock else 'All'}) ---")
    print(format_table(headers, rows))


def cmd_add_product(service: POSService, args: argparse.Namespace) -> None:
    try:
        p = service.create_product(
            sku=args.sku,
            name=args.name,
            sale_price=args.price,
            cost_price=args.cost or 0.0,
            stock_quantity=args.qty or 0,
            min_stock_alert=args.alert or 10,
            category_id=args.category,
            supplier_id=args.supplier,
            barcode=args.barcode
        )
        print(f"[OK] Product created: [{p['sku']}] {p['name']} - Sale: ${p['sale_price']:.2f}, Stock: {p['stock_quantity']}")
    except Exception as e:
        print(f"[ERROR] Failed to add product: {e}", file=sys.stderr)
        sys.exit(1)


def cmd_restock(service: POSService, args: argparse.Namespace) -> None:
    try:
        # lookup product by id or sku
        prod = service.get_product_by_sku_or_barcode(args.product)
        if not prod:
            if args.product.isdigit():
                prod = service.get_product(int(args.product))
            else:
                raise POSError(f"Product '{args.product}' not found.")

        res = service.restock_product(
            product_id=prod["id"],
            quantity=args.qty,
            unit_cost=args.cost,
            notes=args.notes or "Restocked via CLI"
        )
        print(f"[OK] Restock Successful: {res['purchase_no']}")
        print(f"     Product   : {res['product_name']} (ID {res['product_id']})")
        print(f"     Added Qty : +{res['quantity_added']}")
        print(f"     New Stock : {res['new_stock']} units")
        print(f"     Total Cost: ${res['total_cost']:.2f} (@ ${res['unit_cost']:.2f}/ea)")
    except Exception as e:
        print(f"[ERROR] Restock failed: {e}", file=sys.stderr)
        sys.exit(1)


def cmd_checkout(service: POSService, args: argparse.Namespace) -> None:
    """
    Parses items string like: 'SKU-COF-01:2,SKU-CK-04:1'
    """
    try:
        items = []
        for pair in args.items.split(","):
            pair = pair.strip()
            if not pair:
                continue
            if ":" in pair:
                sku, qty_s = pair.split(":", 1)
                qty = int(qty_s.strip())
            else:
                sku = pair
                qty = 1
            items.append({"sku": sku.strip(), "quantity": qty})

        order = service.checkout(
            cart_items=items,
            cashier_id=args.cashier,
            customer_name=args.customer or "Walk-in Customer",
            discount_amount=args.discount or 0.0,
            paid_amount=args.paid,
            payment_method=args.method or "CASH"
        )

        print("\n" + order["receipt_text"] + "\n")
        print(f"[OK] Checkout Completed! Invoice: {order['invoice_no']}")
        print(f"     Total: ${order['total_amount']:.2f} | Paid: ${order['paid_amount']:.2f} | Change: ${order['change_amount']:.2f}")

        if args.save_receipt:
            filename = f"receipt_{order['invoice_no']}.txt"
            with open(filename, "w", encoding="utf-8") as f:
                f.write(order["receipt_text"])
            print(f"[OK] Receipt saved to file: {filename}")

    except InsufficientStockError as e:
        print(f"[ERROR] Stock Error: {e}", file=sys.stderr)
        sys.exit(2)
    except InsufficientPaymentError as e:
        print(f"[ERROR] Payment Error: {e}", file=sys.stderr)
        sys.exit(3)
    except Exception as e:
        print(f"[ERROR] Checkout Failed: {e}", file=sys.stderr)
        sys.exit(1)


def cmd_receipt(service: POSService, args: argparse.Namespace) -> None:
    order = service.get_order_by_invoice(args.invoice)
    if not order:
        print(f"[ERROR] Order with invoice '{args.invoice}' not found.", file=sys.stderr)
        sys.exit(1)

    receipt = order.get("receipt_text") or "(No receipt text recorded)"
    print("\n" + receipt + "\n")

    if args.save:
        with open(args.save, "w", encoding="utf-8") as f:
            f.write(receipt)
        print(f"[OK] Receipt saved to {args.save}")


def cmd_report(service: POSService, args: argparse.Namespace) -> None:
    dash = service.get_dashboard()
    sales = service.get_sales_report(days=args.days or 7)

    print("\n" + "=" * 55)
    print("             POS DASHBOARD & SALES REPORT            ")
    print("=" * 55)
    print(f" Total Products   : {dash['total_products']:<10} | Total Units in Stock : {dash['total_stock_units']}")
    print(f" Inventory Cost   : ${dash['inventory_cost_value']:<9.2f} | Inventory Sale Value : ${dash['inventory_sale_value']:.2f}")
    print(f" Low Stock Alerts : {dash['low_stock_count']:<10} | Today's Revenue      : ${dash['today_revenue']:.2f} ({dash['today_orders']} orders)")
    print(f" All-Time Revenue : ${dash['total_revenue']:<9.2f} | All-Time Orders      : {dash['total_orders']}")
    print("-" * 55)

    print("\n[ Daily Sales Breakdown ]")
    daily_headers = ["Date", "Orders", "Subtotal ($)", "Discounts ($)", "Net Revenue ($)"]
    daily_rows = [
        [r["sales_date"], str(r["order_count"]), f"{r['total_subtotal']:.2f}", f"{r['total_discounts']:.2f}", f"{r['total_revenue']:.2f}"]
        for r in sales["daily_breakdown"]
    ]
    print(format_table(daily_headers, daily_rows))

    print("\n[ Top Selling Products ]")
    top_headers = ["SKU", "Product Name", "Qty Sold", "Sales Total ($)"]
    top_rows = [
        [r["sku"], r["product_name"], str(r["total_qty_sold"]), f"{r['total_sales_amount']:.2f}"]
        for r in sales["top_products"]
    ]
    print(format_table(top_headers, top_rows))

    if sales["low_stock_alerts"]:
        print("\n[ Low Stock Warnings ]")
        alert_headers = ["SKU", "Product Name", "Category", "Current Stock", "Alert Limit"]
        alert_rows = [
            [r["sku"], r["name"], r["category_name"] or "-", str(r["stock_quantity"]), str(r["min_stock_alert"])]
            for r in sales["low_stock_alerts"]
        ]
        print(format_table(alert_headers, alert_rows))


def cmd_low_stock(service: POSService, args: argparse.Namespace) -> None:
    prods = service.list_products(low_stock_only=True)
    if not prods:
        print("[OK] All products have healthy stock levels. No low stock alerts.")
        return
    headers = ["SKU", "Product Name", "Category", "Current Stock", "Alert Threshold", "Price ($)"]
    rows = [
        [p["sku"], p["name"], p["category_name"] or "-", str(p["stock_quantity"]), str(p["min_stock_alert"]), f"{p['sale_price']:.2f}"]
        for p in prods
    ]
    print(f"\n[WARNING] Found {len(prods)} products below or at safety threshold:")
    print(format_table(headers, rows))


def cmd_serve(service: POSService, args: argparse.Namespace) -> None:
    from web_server import run_server
    run_server(host=args.host, port=args.port, db_path=service.db.db_path)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="POS-Lite-Modern: Modern lightweight offline POS & inventory system."
    )
    parser.add_argument("--db", default=DEFAULT_DB_PATH, help="Path to SQLite database file")

    subparsers = parser.add_subparsers(dest="command", required=True)

    # init-db
    p_init = subparsers.add_parser("init-db", help="Initialize database tables and default accounts")
    p_init.add_argument("--demo", action="store_true", help="Seed sample categories, suppliers, and products")

    # users
    subparsers.add_parser("users", help="List all users and employees")
    p_add_user = subparsers.add_parser("add-user", help="Create new user/employee")
    p_add_user.add_argument("--username", required=True)
    p_add_user.add_argument("--password", required=True)
    p_add_user.add_argument("--name", required=True)
    p_add_user.add_argument("--role", choices=["admin", "cashier"], default="cashier")

    # categories
    subparsers.add_parser("categories", help="List categories")
    p_add_cat = subparsers.add_parser("add-category", help="Add new category")
    p_add_cat.add_argument("--name", required=True)
    p_add_cat.add_argument("--desc", default="")

    # suppliers
    subparsers.add_parser("suppliers", help="List suppliers")
    p_add_sup = subparsers.add_parser("add-supplier", help="Add new supplier")
    p_add_sup.add_argument("--name", required=True)
    p_add_sup.add_argument("--contact", default="")
    p_add_sup.add_argument("--phone", default="")
    p_add_sup.add_argument("--email", default="")
    p_add_sup.add_argument("--address", default="")

    # products
    p_prods = subparsers.add_parser("products", help="List products and stock")
    p_prods.add_argument("--search", help="Search name or SKU")
    p_prods.add_argument("--category", type=int, help="Filter by category ID")
    p_prods.add_argument("--low-stock", action="store_true", help="Filter low stock items")

    p_add_prod = subparsers.add_parser("add-product", help="Add new product")
    p_add_prod.add_argument("--sku", required=True)
    p_add_prod.add_argument("--name", required=True)
    p_add_prod.add_argument("--price", type=float, required=True)
    p_add_prod.add_argument("--cost", type=float, default=0.0)
    p_add_prod.add_argument("--qty", type=int, default=0)
    p_add_prod.add_argument("--alert", type=int, default=10)
    p_add_prod.add_argument("--category", type=int)
    p_add_prod.add_argument("--supplier", type=int)
    p_add_prod.add_argument("--barcode")

    # restock
    p_restock = subparsers.add_parser("restock", help="Restock inventory from purchase")
    p_restock.add_argument("--product", required=True, help="Product SKU, barcode or ID")
    p_restock.add_argument("--qty", type=int, required=True, help="Quantity to add")
    p_restock.add_argument("--cost", type=float, required=True, help="Unit cost price")
    p_restock.add_argument("--notes", default="Restock via CLI")

    # checkout
    p_chk = subparsers.add_parser("checkout", help="Perform POS checkout order")
    p_chk.add_argument("--items", required=True, help="Cart items, e.g. 'SKU-01:2,SKU-02:1'")
    p_chk.add_argument("--paid", type=float, help="Cash tendered amount (defaults to exact total)")
    p_chk.add_argument("--discount", type=float, default=0.0, help="Discount amount")
    p_chk.add_argument("--customer", default="Walk-in Customer", help="Customer name")
    p_chk.add_argument("--cashier", type=int, help="Cashier user ID")
    p_chk.add_argument("--method", default="CASH", help="Payment method")
    p_chk.add_argument("--save-receipt", action="store_true", help="Save receipt text to file")

    # receipt
    p_rec = subparsers.add_parser("receipt", help="Display or save receipt by invoice number")
    p_rec.add_argument("--invoice", required=True, help="Invoice number")
    p_rec.add_argument("--save", help="Output file path to save receipt text")

    # report
    p_rep = subparsers.add_parser("report", help="Show sales & inventory dashboard report")
    p_rep.add_argument("--days", type=int, default=7, help="Days of history to analyze")

    # low-stock
    subparsers.add_parser("low-stock", help="List products with stock <= alert threshold")

    # serve
    p_srv = subparsers.add_parser("serve", help="Run local offline Web POS server")
    p_srv.add_argument("--host", default="127.0.0.1", help="Host interface (default 127.0.0.1)")
    p_srv.add_argument("--port", type=int, default=8080, help="Port to listen on (default 8080)")

    parsed = parser.parse_args()
    db = Database(parsed.db)
    service = POSService(db)

    handlers = {
        "init-db": cmd_init_db,
        "users": cmd_users,
        "add-user": cmd_add_user,
        "categories": cmd_categories,
        "add-category": cmd_add_category,
        "suppliers": cmd_suppliers,
        "add-supplier": cmd_add_supplier,
        "products": cmd_products,
        "add-product": cmd_add_product,
        "restock": cmd_restock,
        "checkout": cmd_checkout,
        "receipt": cmd_receipt,
        "report": cmd_report,
        "low-stock": cmd_low_stock,
        "serve": cmd_serve,
    }

    fn = handlers.get(parsed.command)
    if fn:
        fn(service, parsed)


if __name__ == "__main__":
    main()
