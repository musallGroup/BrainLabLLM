import os
import shutil
import subprocess
import sys
import tkinter as tk
from tkinter import messagebox, ttk

APP_NAME = "BrainLabLLM"
FOLDER_NAME = "BrainLabLLM"
EXE_NAME = "BrainLabLLM.exe"


def get_base_dir():
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def get_payload_dir():
    """The installer expects the built app folder to sit right next to it."""
    return os.path.join(get_base_dir(), FOLDER_NAME)


def get_install_dir():
    base = os.environ.get("LOCALAPPDATA", get_base_dir())
    return os.path.join(base, "Programs", FOLDER_NAME)


class InstallerApp:
    def __init__(self, root):
        self.root = root
        root.title(f"{APP_NAME} - Setup")
        root.geometry("500x340")
        root.resizable(False, False)

        ttk.Label(root, text=APP_NAME, font=("Segoe UI", 14, "bold")).pack(pady=(24, 4))
        ttk.Label(
            root, text="A local AI chat and meeting-notes assistant.", foreground="#666666"
        ).pack()

        info = ttk.Frame(root)
        info.pack(fill=tk.X, padx=28, pady=(24, 4))
        ttk.Label(info, text="Install location:").pack(anchor=tk.W)
        self.install_dir = get_install_dir()
        ttk.Label(info, text=self.install_dir, foreground="#444444", wraplength=440).pack(
            anchor=tk.W, pady=(2, 0)
        )

        self.shortcut_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(root, text="Create a Desktop shortcut", variable=self.shortcut_var).pack(
            anchor=tk.W, padx=28, pady=(16, 0)
        )

        self.launch_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(root, text="Launch after installing", variable=self.launch_var).pack(
            anchor=tk.W, padx=28, pady=(2, 0)
        )

        self.status_var = tk.StringVar(value="")
        ttk.Label(root, textvariable=self.status_var, foreground="#666666").pack(pady=(18, 4))

        self.progress = ttk.Progressbar(root, mode="determinate", length=440)
        self.progress.pack(pady=(0, 14))

        self.install_button = ttk.Button(root, text="Install", command=self.start_install)
        self.install_button.pack(pady=4)

    def start_install(self):
        payload = get_payload_dir()
        if not os.path.isdir(payload):
            messagebox.showerror(
                "Setup files missing",
                f"Could not find the application files next to this installer:\n\n{payload}\n\n"
                f"Make sure this setup program stays in the same folder as the "
                f"'{FOLDER_NAME}' folder it came with.",
            )
            return
        self.install_button.config(state=tk.DISABLED)
        self.root.after(50, lambda: self._do_install(payload))

    def _do_install(self, payload):
        try:
            self.status_var.set("Copying files...")
            self.root.update_idletasks()
            if os.path.exists(self.install_dir):
                shutil.rmtree(self.install_dir)
            self._copy_with_progress(payload, self.install_dir)

            exe_path = os.path.join(self.install_dir, EXE_NAME)

            if self.shortcut_var.get():
                self.status_var.set("Creating desktop shortcut...")
                self.root.update_idletasks()
                desktop = os.path.join(os.environ["USERPROFILE"], "Desktop")
                self._create_shortcut(exe_path, os.path.join(desktop, f"{APP_NAME}.lnk"))

            self.status_var.set("Creating Start Menu shortcut...")
            self.root.update_idletasks()
            start_menu = os.path.join(
                os.environ["APPDATA"], "Microsoft", "Windows", "Start Menu", "Programs"
            )
            self._create_shortcut(exe_path, os.path.join(start_menu, f"{APP_NAME}.lnk"))

            self.progress["value"] = 100
            self.status_var.set("Installation complete!")

            if self.launch_var.get():
                subprocess.Popen([exe_path], cwd=self.install_dir)

            messagebox.showinfo("Setup complete", f"{APP_NAME} has been installed.")
            self.root.destroy()
        except Exception as exc:
            messagebox.showerror("Installation failed", str(exc))
            self.install_button.config(state=tk.NORMAL)

    def _copy_with_progress(self, src, dst):
        all_files = []
        for root_dir, _dirs, files in os.walk(src):
            for f in files:
                all_files.append(os.path.join(root_dir, f))
        total = len(all_files) or 1
        os.makedirs(dst, exist_ok=True)
        for i, path in enumerate(all_files):
            rel = os.path.relpath(path, src)
            dest_path = os.path.join(dst, rel)
            os.makedirs(os.path.dirname(dest_path), exist_ok=True)
            shutil.copy2(path, dest_path)
            self.progress["value"] = (i + 1) / total * 100
            if i % 20 == 0:
                self.root.update_idletasks()

    def _create_shortcut(self, target, shortcut_path):
        os.makedirs(os.path.dirname(shortcut_path), exist_ok=True)
        ps_script = (
            "$WshShell = New-Object -ComObject WScript.Shell\n"
            f'$Shortcut = $WshShell.CreateShortcut("{shortcut_path}")\n'
            f'$Shortcut.TargetPath = "{target}"\n'
            f'$Shortcut.WorkingDirectory = "{os.path.dirname(target)}"\n'
            "$Shortcut.Save()\n"
        )
        subprocess.run(
            ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", ps_script],
            capture_output=True,
            check=True,
        )


def main():
    root = tk.Tk()
    InstallerApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
