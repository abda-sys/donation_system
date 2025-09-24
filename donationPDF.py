import mysql.connector, sys, os
from decimal import Decimal, InvalidOperation
from datetime import datetime
from admin_auth import passLoop, set_password

# PDF lib
try:
    from reportlab.pdfgen import canvas
    from reportlab.lib.pagesizes import A6
except ImportError:
    print("error, install reportlab first ")
    sys.exit(1)

DB_CONFIG = {
    "host": "localhost",
    "user": "root",
    "password": "56&abcABC",
    "database": "donationDataSys_db"
}

# ---------------------------
# RECEIPT CONFIG
# ---------------------------
RECEIPT_DIR = "receipts"
ORG_NAME = "YAYASAN ALHIKMAH"

os.makedirs(RECEIPT_DIR, exist_ok=True)


# ---------------------------
# HELPER
# ---------------------------
def get_connection():
    return mysql.connector.connect(**DB_CONFIG)


def safe_input(prompt, default=None, required=False):
    while True:
        s = input(prompt).strip()
        if s == "" and default is not None:
            return default
        if required and s == "":
            print("Field must be filled.")
            continue
        return s


def normalize_base(s):
    if not s:
        return None
    s = s.lower().strip()
    if s in ("personal", "person", "per", "p"):
        return "per"
    if s in ("company", "com", "c"):
        return "com"
    return s


def normalize_kind(s):
    if not s:
        return None
    s = s.lower().strip()
    if s in ("barang", "i", "g"):
        return "items"
    if s in ("money", "uang", "m"):
        return "money"
    return s


def format_rupiah(amount):
    try:
        a = Decimal(amount)
    except Exception:
        return str(amount)
    if a == a.to_integral():
        s = f"{int(a):,}".replace(",", ".")
        return f"Rp {s}"
    else:
        s = f"{a:,.2f}"
        s = s.replace(",", "X").replace(".", ",").replace("X", ".")
        return f"Rp {s}"


def generate_receipt_pdf(donor_row, donation_row, donation_type, meta, filename=None):
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    if filename is None:
        filename = f"receipt_{donor_row.get('id_donor')}_{donation_type}_{meta.get('donation_id')}_{ts}.pdf"
    path = os.path.join(RECEIPT_DIR, filename)
    try:
        c = canvas.Canvas(path, pagesize=A6)
        width, height = A6
        x_left = 40
        y = height - 40

        # Header
        c.setFont("Courier-Bold", 16)
        c.drawCentredString(width / 2, y, ORG_NAME)
        y -= 20
        c.setFont("Courier-Bold", 12)
        c.drawCentredString(width / 2, y, "BUKTI DONASI")
        y -= 18

        c.setFont("Courier", 10)
        c.line(x_left, y, width - x_left, y)
        y -= 14

        # Donor fields
        fields = [
            ("Tanggal", meta.get('generated_at', datetime.now()).strftime("%Y-%m-%d %H:%M:%S")),
            ("ID Donor", donor_row.get('id_donor')),
            ("NIK", donor_row.get('nik') or "-"),
            ("Nama", donor_row.get('name')),
            ("Base", donor_row.get('donationBase') or "-"),
            ("Company", donor_row.get('company_name') or "-"),
            ("Alamat", donor_row.get('address') or "-"),
        ]
        for label, val in fields:
            c.drawString(x_left, y, f"{label} : {val}")
            y -= 14
        if donor_row.get('description'):
            c.drawString(x_left, y, f"Desc: {donor_row.get('description')}")
            y -= 14

        y -= 6
        c.line(x_left, y, width - x_left, y)
        y -= 16

        c.setFont("Courier-Bold", 10)
        c.drawString(x_left, y, "Detail Donasi:")
        y -= 14
        c.setFont("Courier", 10)

        if donation_type == "money":
            c.drawString(x_left, y, f"Tipe: Uang")
            y -= 14
            c.drawString(x_left, y, f"ID Transaksi: {meta.get('donation_id')}")
            y -= 14
            c.drawString(x_left, y, f"Pembayaran: {donation_row.get('paymentMethod') or '-'}")
            y -= 14
            amt = donation_row.get('amount')
            c.drawString(x_left, y, f"Jumlah: {format_rupiah(amt)}")
            y -= 14
        else:
            c.drawString(x_left, y, f"Tipe: Barang/Perlengkapan")
            y -= 14
            c.drawString(x_left, y, f"ID Transaksi: {meta.get('donation_id')}")
            y -= 14
            c.drawString(x_left, y, f"Jenis Item: {donation_row.get('itemName')}")
            y -= 14
            c.drawString(x_left, y, f"Quantity: {donation_row.get('Quantity')}")
            y -= 14

        y -= 10
        c.line(x_left, y, width - x_left, y)
        y -= 18
        c.setFont("Courier", 10)
        c.drawString(x_left, y, "Terima kasih atas donasi Anda")
        y -= 14
        c.drawString(x_left, y, "semoga berkah dunia dan akhirat.")
        y -= 20
        c.drawString(x_left, y, "(tanda tangan)")

        c.showPage()
        c.save()
        return path
    except Exception as e:
        print("Gagal membuat PDF:", e)
        return None


# ---------------------------
# CRUD FUNCTIONS (modified for PDF)
# ---------------------------
def add_donor():
    conn = get_connection()
    cur = conn.cursor()
    try:
        print("\nAdd Donor")
        name = safe_input(" Name: ", required=True)
        nik = safe_input(" NIK: ", required=False)

        raw_base = safe_input("Donation base (personal/company): ", default="personal")
        donationBase = normalize_base(raw_base)

        company_name = None
        if donationBase == "com":
            company_name = safe_input("Company Name: ", required=True)

        address = safe_input("Address: ", required=True)

        raw_kind = safe_input("Kind (money/items): ", default="money")
        donationKind = normalize_kind(raw_kind)

        description = safe_input("Desc (optional): ", default=None)

        # insert donor
        cur.execute("""
            INSERT INTO donors (name, nik, donationBase, company_name, address, donationKind, description)
            VALUES (%s,%s,%s,%s,%s,%s,%s)
        """, (name, nik, donationBase, company_name, address, donationKind, description))
        conn.commit()
        donor_id = cur.lastrowid
        print(f"Accepted with id {donor_id}")

        donation_id = None
        donation_type = donationKind
        # insert first donation according to kind
        if donationKind == "money":
            paymentMethod = safe_input("Payment (cash/transfer/qr): ", required=True).lower()
            while True:
                amt_s = safe_input("Amount (rupiah): ", required=True)
                try:
                    amount = Decimal(amt_s)
                    break
                except (InvalidOperation, ValueError):
                    print("Valid number pliss.")
            cur.execute("""
                INSERT INTO money_donations (id_donor, name, paymentMethod, amount)
                VALUES (%s,%s,%s,%s)
            """, (donor_id, name, paymentMethod, amount))
            conn.commit()
            donation_id = cur.lastrowid
            print("SUBMITTED YEYYY.")
        else:  # items
            itemName = safe_input("Item Name: ", required=True)
            quantity = safe_input("Quantity : ", required=True)
            cur.execute("""
                INSERT INTO item_donations (id_donor, name, itemName, Quantity)
                VALUES (%s,%s,%s,%s)
            """, (donor_id, name, itemName, quantity))
            conn.commit()
            donation_id = cur.lastrowid
            print("ALHAMDULILLAH SUCCESSFUL.")

        # After successful insertion, offer to print receipt (PDF)
        while True:
            want_print = safe_input("Cetak struk sekarang? (y/n): ", required=True).lower()
            if want_print not in ("y", "n"):
                print("pilih 'y' or 'n'")
                continue
            break

        if want_print == "y":
            cur2 = conn.cursor(dictionary=True)
            try:
                cur2.execute("SELECT * FROM donors WHERE id_donor = %s", (donor_id,))
                donor_row = cur2.fetchone()
                if donation_type == "money":
                    cur2.execute("SELECT * FROM money_donations WHERE id_money = %s", (donation_id,))
                    donation_row = cur2.fetchone()
                else:
                    cur2.execute("SELECT * FROM item_donations WHERE id_items = %s", (donation_id,))
                    donation_row = cur2.fetchone()

                meta = {"donation_id": donation_id, "generated_at": datetime.now()}
                path = generate_receipt_pdf(donor_row, donation_row, donation_type, meta)
                if path:
                    print(f"receipt saved: {path}")
            finally:
                cur2.close()
        else:
            print("okay no problem")

    except mysql.connector.Error as e:
        conn.rollback()
        print("Error DB:", e)
    finally:
        cur.close()
        conn.close()


# (remaining functions kept largely unchanged)

def _choose_from_list(rows):
    if not rows:
        return None
    if len(rows) == 1:
        return rows[0][0] if isinstance(rows[0], tuple) else rows[0]['id_donor']
    print("Some record founded (more than one):")
    for r in rows:
        if isinstance(r, dict):
            print(f"  id= {r['id_donor']} | name= {r['name']} | nik= {r.get('nik')} ")
        else:
            print(f"  id={r[0]} | name={r[1]}")
    while True:
        s = safe_input("choose id_donor (clear it if you want cancel): ", required=False)
        if s == "":
            return None
        try:
            return int(s)
        except ValueError:
            print("invalid number.")


def edit_donor():
    conn = get_connection()
    cur = conn.cursor(dictionary=True)
    try:
        print("\n=== Edit Donor ===")
        nik = safe_input("NIK of donor that you want to change: ", required=True)
        cur.execute("SELECT * FROM donors WHERE nik = %s", (nik,))
        rows = cur.fetchall()
        if not rows:
            print("not found.")
            return
        chosen_id = _choose_from_list(rows)
        if not chosen_id:
            print("Canceled.")
            return
        cur.execute("SELECT * FROM donors WHERE id_donor = %s", (chosen_id,))
        donor = cur.fetchone()
        if not donor:
            print("not found again.")
            return

        print("Leave empty what will not be changed.")
        new_name = safe_input(f"Name [{donor['name']}]: ", default=donor['name'])
        new_nik = safe_input(f"NIK [{donor['nik']}]: ", default=donor['nik'])
        raw_base = safe_input(f"Donation base (personal/company) [{donor['donationBase']}]: ", default=donor['donationBase'])
        new_base = normalize_base(raw_base)
        new_company = donor['company_name']
        if new_base == "com":
            new_company = safe_input(f"Company name [{donor.get('company_name') or ''}]: ", default=donor.get('company_name'))
        else:
            new_company = None
        new_address = safe_input(f"Address [{donor['address']}]: ", default=donor['address'])
        raw_kind = safe_input(f"Donation kind (money/items) [{donor['donationKind']}]: ", default=donor['donationKind'])
        new_kind = normalize_kind(raw_kind)
        new_description = safe_input(f"Description [{donor.get('description') or ''}]: ", default=donor.get('description'))

        cur2 = conn.cursor()
        try:
            cur2.execute("""
                UPDATE donors
                SET name=%s, nik=%s, donationBase=%s, company_name=%s, address=%s, donationKind=%s, description=%s
                WHERE id_donor=%s
            """, (new_name, new_nik, new_base, new_company, new_address, new_kind, new_description, chosen_id))
            conn.commit()
            print("successfully updated.")
        finally:
            cur2.close()

        if new_kind == "money":
            cur.execute("SELECT * FROM money_donations WHERE id_donor=%s", (chosen_id,))
            money_data = cur.fetchone()
            if money_data:
                print("\n=== Edit Money Donation ===")
                new_payment = safe_input(
                    f"Payment (cash/transfer/qr) [{money_data['paymentMethod']}]: ",
                    default=money_data['paymentMethod']
                )
                new_amount = safe_input(
                    f"Amount [{money_data['amount']}]: ",
                    default=str(money_data['amount'])
                )

                cur3 = conn.cursor()
                try:
                    cur3.execute("""
                        UPDATE money_donations
                        SET paymentMethod=%s, amount=%s
                        WHERE id_donor=%s
                    """, (new_payment, new_amount, chosen_id))
                    conn.commit()
                    print("SUCCESSFULLY UPDATED.")
                finally:
                    cur3.close()

        elif new_kind == "items":
            cur.execute("SELECT * FROM item_donations WHERE id_donor=%s", (chosen_id,))
            item_data = cur.fetchone()
            if item_data:
                print("\n=== Edit Items Donation ===")
                new_item = safe_input(
                    f"Item Name [{item_data['itemName']}]: ",
                    default=item_data['itemName']
                )
                new_quantity = safe_input(
                    f"Quantity [{item_data['Quantity']}]: ",
                    default=item_data['Quantity']
                )

                cur4 = conn.cursor()
                try:
                    cur4.execute("""
                        UPDATE item_donations
                        SET itemName=%s, Quantity=%s
                        WHERE id_donor=%s
                    """, (new_item, new_quantity, chosen_id))
                    conn.commit()
                    print("successfully updated.")
                finally:
                    cur4.close()

    except mysql.connector.Error as e:
        conn.rollback()
        print("Error DB:", e)
    finally:
        cur.close()
        conn.close()


def view_all_donors():
    conn = get_connection()
    cur = conn.cursor(dictionary=True)
    try:
        print("\n=== All Donor List ===")
        cur.execute("""
            SELECT id_donor, name, nik, donationBase, company_name, address, donationKind, description, date
            FROM donors
            ORDER BY date DESC
        """)
        rows = cur.fetchall()
        if not rows:
            print("Not found.")
            return
        for r in rows:
            print("-" * 50)
            print(f"id: {r['id_donor']} | name: {r['name']} | nik: {r['nik']} | base: {r['donationBase']} | kind: {r['donationKind']} | date: {r['date']}")
            if r['company_name']:
                print(f"  company: {r['company_name']}")
            print(f"  address: {r['address']}")
            if r['description']:
                print(f"  desc: {r['description']}")
        print("-" * 50)
    except mysql.connector.Error as e:
        print("Error DB:", e)
    finally:
        cur.close()
        conn.close()


def search_donor():
    conn = get_connection()
    cur = conn.cursor(dictionary=True)
    try:
        print("\n=== search Donor ===")
        kw = safe_input("enter NIK or Name: ", required=True)
        like = f"%{kw}%"
        cur.execute("""
            SELECT *
            FROM donors
            WHERE nik LIKE %s OR name LIKE %s
            ORDER BY date DESC
        """, (like, like))
        rows = cur.fetchall()
        if not rows:
            print("not found.")
            return
        for r in rows:
            print("=" * 40)
            print(f"ID Donor      : {r['id_donor']}")
            print(f"NIK           : {r['nik']}")
            print(f"Name          : {r['name']}")
            print(f"kind          : {r['donationKind']}")
            print(f"Base          : {r['donationBase']}")
            print(f"company       : {r['company_name'] or '-'}")
            print(f"Address       : {r['address']}")
            print(f"Desc          : {r['description'] or '-'}")
            print(f"Input Date    : {r['date']}")
            cur.execute("SELECT * FROM money_donations WHERE id_donor = %s", (r['id_donor'],))
            monies = cur.fetchall()
            if monies:
                print("-- Money Donation --")
                for m in monies:
                    print(f"   id_money={m['id_money']} | method={m['paymentMethod']} | amount={m['amount']}")
            cur.execute("SELECT * FROM item_donations WHERE id_donor = %s", (r['id_donor'],))
            items = cur.fetchall()
            if items:
                print("-- Item Donation --")
                for it in items:
                    print(f"   id_items={it['id_items']} | itemName={it['itemName']} | qty={it['Quantity']}")
        print("=" * 40)
    except mysql.connector.Error as e:
        print("Error DB:", e)
    finally:
        cur.close()
        conn.close()


def delete_donor():
    conn = get_connection()
    cur = conn.cursor(dictionary=True)
    try:
        print("\n=== Delete Donor ===")
        nik = safe_input("enter NIK donor that will be deleted: ", required=True)
        cur.execute("SELECT id_donor, name, nik FROM donors WHERE nik = %s", (nik,))
        rows = cur.fetchall()
        if not rows:
            print("not found.")
            return
        chosen_id = _choose_from_list(rows)
        if not chosen_id:
            print("canceled.")
            return
        confirm = safe_input(f"Are you sure you want to delete the donation with id={chosen_id}? (type 'y' for confirmation): ", required=True)
        if confirm.lower() != "y":
            print("canceled.")
            return
        cur2 = conn.cursor()
        try:
            cur2.execute("DELETE FROM donors WHERE id_donor = %s", (chosen_id,))
            conn.commit()
            print("successfully deleted.")
        finally:
            cur2.close()
    except mysql.connector.Error as e:
        conn.rollback()
        print("Error DB:", e)
    finally:
        cur.close()
        conn.close()


# ---------------------------
# PRINT RECEIPT MENU (PDF)
# ---------------------------
def print_receipt_menu():
    conn = get_connection()
    cur = conn.cursor(dictionary=True)
    try:
        print("\n=== Print Receipt ===")
        kw = safe_input("Enter NIK or Name or ID Donor: ", required=True)
        rows = []
        if kw.isdigit():
            cur.execute("SELECT * FROM donors WHERE id_donor = %s", (int(kw),))
            row = cur.fetchone()
            if row:
                rows = [row]
        if not rows:
            like = f"%{kw}%"
            cur.execute("SELECT * FROM donors WHERE nik LIKE %s OR name LIKE %s ORDER BY date DESC", (like, like))
            rows = cur.fetchall()
        if not rows:
            print("not found.")
            return
        chosen_id = _choose_from_list(rows)
        if not chosen_id:
            print("canceled.")
            return

        cur.execute("SELECT * FROM donors WHERE id_donor = %s", (chosen_id,))
        donor = cur.fetchone()
        if not donor:
            print("not found.")
            return

        cur.execute("SELECT id_money AS id, paymentMethod, amount, date FROM money_donations WHERE id_donor = %s ORDER BY date DESC", (chosen_id,))
        monies = cur.fetchall()
        cur.execute("SELECT id_items AS id, itemName, Quantity, date FROM item_donations WHERE id_donor = %s ORDER BY date DESC", (chosen_id,))
        items = cur.fetchall()

        print("\nDonations:")
        idx_map = {}
        idx = 1
        for m in monies:
            print(f"{idx}. MONEY | id_money={m['id']} | {m.get('paymentMethod') or '-'} | {m.get('amount')} | {m.get('date')}")
            idx_map[str(idx)] = ("money", m['id'])
            idx += 1
        for it in items:
            print(f"{idx}. ITEMS | id_items={it['id']} | {it.get('itemName')} | qty={it.get('Quantity')} | {it.get('date')}")
            idx_map[str(idx)] = ("items", it['id'])
            idx += 1

        if not idx_map:
            print("there's no donors")
            return

        print("\nChoose the number you want to print or type 'a' to print all or type 'l' to print the last one")
        sel = safe_input("Your Choice: ", required=True)
        to_print = []
        if sel.lower() == "a":
            for v in idx_map.values():
                to_print.append(v)
        elif sel.lower() == "l":
            first_key = sorted(idx_map.keys(), key=lambda x: int(x))[0]
            to_print.append(idx_map[first_key])
        elif sel in idx_map:
            to_print.append(idx_map[sel])
        else:
            print("Invalid Choice.")
            return

        cur2 = conn.cursor(dictionary=True)
        try:
            for dtype, did in to_print:
                if dtype == "money":
                    cur2.execute("SELECT * FROM money_donations WHERE id_money = %s", (did,))
                    donation_row = cur2.fetchone()
                else:
                    cur2.execute("SELECT * FROM item_donations WHERE id_items = %s", (did,))
                    donation_row = cur2.fetchone()
                meta = {"donation_id": did, "generated_at": datetime.now()}
                path = generate_receipt_pdf(donor, donation_row, dtype, meta)
                if path:
                    print(f"Receipts Saved: {path}")
        finally:
            cur2.close()

    except mysql.connector.Error as e:
        print("Error DB:", e)
    finally:
        cur.close()
        conn.close()


# ---------------------------
# MENU UTAMA
# ---------------------------
def main_menu():
    while True:
        print("\n <<< Donation Management >>> ")
        print("1. Add Donor")
        print("2. Edit Donor")
        print("3. View All Donors")
        print("4. Search Donor")
        print("5. Delete Donor")
        print("6. Password Manager")
        print("7. Print Receipt")
        print("8. Exit")
        choice = safe_input("choose menu (1-8): ", required=True)

        if choice == "1":
            add_donor()
        elif choice == "2":
            edit_donor()
        elif choice == "3":
            view_all_donors()
        elif choice == "4":
            search_donor()
        elif choice == "5":
            delete_donor()
        elif choice == "6":
            set_password()
        elif choice == "7":
            print_receipt_menu()
        elif choice == "8":
            print("thank you admin byeeeee")
            sys.exit()
        else:
            print("invalid choice, try again.")


if __name__ == "__main__":
    print("\nLOGIN SECTION\n")
    passLoop(main_menu)

