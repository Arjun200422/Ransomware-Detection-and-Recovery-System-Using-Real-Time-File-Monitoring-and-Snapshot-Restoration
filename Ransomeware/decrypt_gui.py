
import os
import tkinter as tk
from tkinter import filedialog, messagebox
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.backends import default_backend
import base64

SALT_SIZE = 16
KDF_ITERS = 200_000

def derive_fernet_key(password: str, salt: bytes) -> bytes:
    password_bytes = password.encode("utf-8")
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=KDF_ITERS,
        backend=default_backend()
    )
    key = kdf.derive(password_bytes)
    return base64.urlsafe_b64encode(key)


class DecryptorApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Decrypt File (In-Place)")
        self.geometry("560x240")
        self.resizable(False, False)

        self.filepath = tk.StringVar(value="No file selected")
        self.password = tk.StringVar()

        tk.Label(self, text="Selected file:").pack(anchor='w', padx=10, pady=(12,0))
        self.file_label = tk.Label(self, textvariable=self.filepath, anchor='w', relief='sunken', width=75)
        self.file_label.pack(padx=10)

        btn_frame = tk.Frame(self)
        btn_frame.pack(padx=10, pady=8, fill='x')
        tk.Button(btn_frame, text="Choose File", width=14, command=self.choose_file).pack(side='left')
        tk.Button(btn_frame, text="Decrypt", width=14, command=self.decrypt_action).pack(side='left', padx=8)

        pw_frame = tk.Frame(self)
        pw_frame.pack(padx=10, fill='x')
        tk.Label(pw_frame, text="Password:").pack(anchor='w')
        self.pw_entry = tk.Entry(pw_frame, textvariable=self.password, show='*', width=66)
        self.pw_entry.pack(anchor='w', pady=(0,8))

        tk.Label(self, text="⚠️ The file will be overwritten with decrypted content.", fg='red', justify='left').pack(padx=10, anchor='w')

    def choose_file(self):
        path = filedialog.askopenfilename()
        if path:
            self.filepath.set(path)

    def decrypt_action(self):
        path = self.filepath.get()
        pw = self.password.get()
        if not os.path.isfile(path):
            messagebox.showerror("Error", "Please select a valid encrypted file.")
            return
        if not pw:
            messagebox.showerror("Error", "Please provide a password.")
            return
        if not messagebox.askokcancel("Confirm", f"This will decrypt and overwrite the file:\n{path}\n\nContinue?"):
            return

        try:
            with open(path, "rb") as f:
                content = f.read()
            salt = content[:SALT_SIZE]
            token = content[SALT_SIZE:]
            key = derive_fernet_key(pw, salt)
            fernet = Fernet(key)
            decrypted = fernet.decrypt(token)
            with open(path, "wb") as f:
                f.write(decrypted)

            # Custom message after decryption
            self.show_decrypted_message()
        except Exception as e:
            messagebox.showerror("Decryption failed", "Incorrect password or file corrupted.\n\n" + str(e))

    def show_decrypted_message(self):
        win = tk.Toplevel(self)
        win.title("Decrypted")
        win.geometry("400x200")
        win.resizable(False, False)
        tk.Label(win, text="✅ YOUR FILE HAS BEEN DECRYPTED ✅", font=("Arial", 14, "bold"), fg="green").pack(pady=30)
        tk.Label(win, text="Your file has been restored successfully.", fg="black").pack()
        tk.Button(win, text="OK", command=win.destroy, width=10).pack(pady=20)


if __name__ == "__main__":
    app = DecryptorApp()
    app.mainloop()
