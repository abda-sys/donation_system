import sys, hashlib, hmac, json, secrets, pwinput, getpass
from pathlib import Path

PASS_FILE = Path(__file__).parent / "pass.json"
ITERATIONS = 100_000

def set_password():
    try:
        pw = pwinput.pwinput("Masukkan password baru: ", mask="*")
        pw2 = pwinput.pwinput("Ulangi password: ", mask="*")
    except:
        pw = getpass.getpass("Masukkan password baru: ")
        pw2 = getpass.getpass("Ulangi password: ")
    if pw != pw2:
        print("Unmatch Password"); sys.exit(1)

    salt = secrets.token_bytes(16)
    PASS_FILE.write_text(json.dumps({
        "algo": "pbkdf2_sha256",
        "iterations": ITERATIONS,
        "salt": salt.hex(),
        "hash": hashlib.pbkdf2_hmac("sha256", pw.encode(), salt, ITERATIONS).hex()
    }), encoding="utf-8")
    try: PASS_FILE.chmod(0o600)
    except: pass
    print(f"Password stored {PASS_FILE}")

def verify_password(entered_pw):
    if not PASS_FILE.exists():
        print("Password Unavailable. Run: python admin_auth.py setpass")
        sys.exit(1)
    d = json.loads(PASS_FILE.read_text())
    dk = hashlib.pbkdf2_hmac("sha256",
                             entered_pw.encode(),
                             bytes.fromhex(d["salt"]),
                             d.get("iterations", ITERATIONS))
    return hmac.compare_digest(dk.hex(), d["hash"])

def passLoop(main_menu_func):
    attempts = 3
    while attempts > 0:
        try:
            pw = pwinput.pwinput("password first bro: ", mask="?")
        except Exception:
            pw = getpass.getpass("password first bro: ")
        if verify_password(pw):
            print("WELCOME ADMIN")
            main_menu_func()
            return True
        else:
            attempts -= 1
            if attempts > 0:
                print(f" \nWRONGGGG. {attempts} LEFT FOR YOU\n")
            else:
                print("GET OUTTTT"); sys.exit()

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "setpass":
        set_password()
