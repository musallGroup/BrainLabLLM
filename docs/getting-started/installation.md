# Installation

No coding experience, Python, or command-line use is required. This takes about a minute.

## 1. Get the installer package

Ask whoever manages the tool for your lab for `BrainLabLLM_Setup_Package.zip` (it's typically shared over the lab network or a shared drive — it's roughly 1.5 GB, since it includes the speech-to-text model so you don't need internet access later).

## 2. Unzip it

Right-click the `.zip` file and choose **Extract All**. You'll get a folder containing:

```
BrainLabLLM_Setup_Package/
├── BrainLabLLMSetup.exe   ← run this
├── BrainLabLLM/           ← the app itself (don't move or rename)
└── README.txt
```

!!! warning "Keep the setup file and the app folder together"
    `BrainLabLLMSetup.exe` looks for the `BrainLabLLM` folder sitting right next to it. If you move the `.exe` on its own, installation will fail with a "setup files missing" message.

## 3. Run the installer

Double-click **`BrainLabLLMSetup.exe`**.

!!! info "About the Windows warning screen"
    The first time you run it, Windows will very likely show a blue **"Windows protected your PC"** screen. This happens for *any* brand-new program that isn't yet widely downloaded — it's a reputation check, not a malware detection. Click **More info**, then **Run anyway**. You'll only see this once.

You'll see a small setup window:

- **Install location** is shown (no need to change it — it installs to your own user profile, so no administrator rights are needed)
- Leave **Create a Desktop shortcut** and **Launch after installing** checked (recommended)
- Click **Install**

A progress bar copies the app (this takes a few seconds to a minute depending on your disk), then shortcuts appear on your Desktop and in the Start Menu.

## 4. That's it

No restart, no additional downloads, no accounts. Speech recognition works completely offline; you'll only need the lab network once you start chatting or generating summaries.

Continue to the [Quick Start](quick-start.md) to try it out.

---

## For developers: building from source

If you're setting this up on a new lab machine and need to build the installer yourself (rather than reusing an existing package), see [Building from Source](../development/building.md).
