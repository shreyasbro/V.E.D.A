# V.E.D.A. — Virtual Executive Desktop Assistant

V.E.D.A. (Virtual Executive Desktop Assistant) is a Windows desktop assistant created by **Shreyas**.

The goal of V.E.D.A. is simple: instead of manually performing every small task on a Windows PC, you can communicate with your computer using natural language.

V.E.D.A. is designed to understand commands in **English, Hindi, and Hinglish** and perform useful desktop operations such as opening applications, typing text, taking screenshots, managing files, and automating desktop tasks.

---

## ✨ What is V.E.D.A.?

V.E.D.A. stands for **Virtual Executive Desktop Assistant**.

It is a desktop-based assistant designed to make interaction with a Windows computer more natural and convenient.

Instead of navigating through multiple menus or manually performing repetitive actions, you can give V.E.D.A. a natural-language instruction.

For example:

- "Open Chrome"
- "Take a screenshot"
- "Type this message"
- "Open this application"
- "Manage my files"
- "Automate this desktop task"

V.E.D.A. is intended to act as a practical desktop assistant rather than simply being a text-based chatbot.

---

# 🚀 Main Features

## 🖥️ Windows Desktop Interaction

V.E.D.A. can interact with the Windows desktop and perform various desktop-related operations.

Supported tasks include:

- Opening applications
- Typing text
- Taking screenshots
- Managing files
- Performing desktop automation
- Executing natural-language desktop commands

---

## 🤖 Natural-Language Interaction

You don't need to remember complicated commands.

Simply describe what you want V.E.D.A. to do.

V.E.D.A. supports:

- English
- Hindi
- Hinglish

### Examples

```
Open Chrome
Take a screenshot
Open my files
Type this message
Open an application
Automate this desktop task

The idea is to make computer interaction more natural and straightforward.
```
---
📦 Installation

V.E.D.A. is currently distributed as a Windows application package.

Step 1 — Install Python

Before installing and running V.E.D.A., make sure that the latest available version of Python is installed on your Windows PC.

Download Python from:
```
https://www.python.org/downloads/
```
During the Python installation, make sure that:

Add Python to PATH

is enabled.

After installing Python, verify that it is working by opening Command Prompt and running:
```
python --version
```
If that does not work, try:
```
py --version
```
Step 2 — Download V.E.D.A.

Download the V.E.D.A. application package from the provided Google Drive folder:
```
https://drive.google.com/drive/folders/1nqnjiPY1IRwolYZNuxkpFuP_VHTm7Ja0?usp=drive_link
```
Step 3 — Extract the Application

After downloading the package:

Extract the contents of the downloaded package.
Choose any preferred folder/location on your Windows PC.
Make sure the complete V.E.D.A. package remains together.
Do not remove required files from the extracted folder.

Step 4 — Build and Verify Dependencies

Before launching V.E.D.A., you must run the build process.

Normally, run:
```
BUILD V.E.D.A.bat
```
or:
```
build.bat
```
The build process installs and verifies the important dependencies and components required by V.E.D.A.

An internet connection is required during the build/dependency installation process.

Wait for the build process to finish successfully before launching V.E.D.A.

🔧 If the BAT Build File Does Not Work

If:
```
BUILD V.E.D.A.bat
```
or:
```
build.bat
```
does not work correctly, you can run the Python build script directly.

Open the V.E.D.A. folder and run:
```
python build.py
```
If python is not recognized, try:
```
py build.py
```
Allow the build process to complete before launching V.E.D.A.

Step 5 — Launch V.E.D.A.

After the build process has completed successfully, launch the main V.E.D.A. executable.

V.E.D.A. should then be ready for interaction.
---
🛠️ Important Installation Notes

Before running V.E.D.A., make sure that:

You are using a Windows PC.
The latest available Python version is installed.
Python is added to your system PATH.
The complete V.E.D.A. application package has been extracted.
Required environment files are present.
Required dependencies are available.
BUILD V.E.D.A.bat or build.bat has been executed successfully.
If the BAT build file does not work, run python build.py or py build.py.
Your PC has an active internet connection during the build/dependency installation process.

If the build process has not been completed, V.E.D.A. may not start or function correctly.

🎙️ How to Use V.E.D.A.

Once V.E.D.A. has been launched, interact with it using natural language.

You don't have to use a fixed command format.

#For example:
```
Open Chrome
```
V.E.D.A. can process the request and perform the corresponding desktop action.

#Another example:
```
Take a screenshot

Or:

Open my files

You can also use Hindi or Hinglish.
```
#For example:
```
Chrome open karo
Ek screenshot le lo
Meri files open karo
Ye text type karo
```
The purpose is to allow users to interact with their computer in the language and style that feels natural to them.
---
#🧩 Desktop Automation

V.E.D.A. can be used for desktop automation tasks.

Instead of manually performing a sequence of actions, you can describe the task to V.E.D.A.

Examples include:
```
Open the application
Type this text
Take a screenshot
Open my files
Perform this desktop task
```
V.E.D.A. is designed to make these interactions easier through natural-language instructions.

📸 Screenshots

V.E.D.A. supports screenshot-related tasks.

You can ask V.E.D.A. to take a screenshot when needed.

Example:
```
Take a screenshot
```
This can be useful when you need to capture the current state of your Windows desktop.

📁 File Management

V.E.D.A. can assist with file-management tasks.

You can give natural-language instructions related to managing files on your Windows computer.

For example:
```
Open my files
Manage my files
```
The exact operation depends on the task you provide to V.E.D.A.
---
⌨️ Text Input

V.E.D.A. can type text on your computer when requested.

For example:
```
Type this message
```
This allows text-entry tasks to be performed through natural-language instructions rather than manually typing everything yourself.
---
🧠 Designed Around Natural Interaction

One of the main ideas behind V.E.D.A. is reducing the need for complicated command syntax.

Instead of learning a large list of special commands, users can communicate with V.E.D.A. naturally.

For example:
```
Open Chrome
```
is intended to be enough to communicate the task.

The same principle applies to Hindi and Hinglish:
```
Chrome open karo

or:

Screenshot le lo
```
🌐 Language Support
---
V.E.D.A. currently supports natural-language interaction in:

English
Hindi
Hinglish

This allows users to interact with V.E.D.A. without being restricted to English-only commands.
---
📱 Android

An Android version/companion experience is part of the broader V.E.D.A. direction.

The Android side is intended to provide a way to interact with and control the Windows V.E.D.A. system from an Android device.

The current documented installation process is for the Windows version.

Android installation and connection instructions will be documented separately when the Android build and connection workflow are finalized.
---
🔧 Build File

The V.E.D.A. package includes a build process that should be run before starting the application.

Use:

BUILD V.E.D.A.bat

or:

build.bat

If the BAT file does not work, use:

python build.py

or:

py build.py

The build process installs and verifies important dependencies and components.

An internet connection is required for this process.

⚠️ Before Running V.E.D.A.

Always make sure the build step has been completed first.

Recommended order:

1. Install the latest Python version
        ↓
2. Download V.E.D.A.
        ↓
3. Extract the package
        ↓
4. Check the required files
        ↓
5. Run BUILD V.E.D.A.bat / build.bat
        ↓
6. If the BAT file fails, run build.py
        ↓
7. Allow dependencies to install and verify
        ↓
8. Launch V.E.D.A.
        ↓
9. Give V.E.D.A. a natural-language command
🖥️ Platform

Current documented platform:

Windows PC

V.E.D.A. is currently distributed as a Windows desktop application package.
---
📌 Project Status

V.E.D.A. is an actively developed personal desktop-assistant project.

The project is focused on making interaction with a Windows PC more natural through:

Natural-language commands
Desktop interaction
File management
Screenshot functionality
Text input
Desktop automation
English, Hindi, and Hinglish support

More functionality can be added and improved as development continues.
---
🚧 Development Status

V.E.D.A. is currently under active development.

The project is still being developed, tested, and improved. Because of this, users may encounter:

Bugs
Unexpected behavior
Incomplete features
Crashes
Compatibility issues
Performance differences between PCs

Different Windows PCs may behave differently depending on factors such as:

Windows version
Hardware
Drivers
Permissions
Installed dependencies
System configuration

This is not yet a final/stable release.

Features may change, improve, or be replaced as development continues.

If you are using V.E.D.A. during this development stage, please keep in mind that bugs are expected.
---
🐛 Bug Reports & Feedback

If you find a bug or something that does not work correctly, please report it.

When reporting a bug, include as much useful information as possible.

For example:

Bug:
What happened?

Expected:
What should have happened?

Steps to reproduce:
1.
2.
3.

Windows Version:
V.E.D.A. Version:
Error Message:
Additional Information:

Screenshots, error messages, and relevant logs can also help identify and fix problems.

You can report bugs or send feedback at:

thakurshreyas436@gmail.com

Your feedback helps improve V.E.D.A. during development.
---
👨‍💻 Created By

Shreyas

V.E.D.A. — Virtual Executive Desktop Assistant

Built with the goal of making computer interaction simpler, more natural, and more accessible.
---
📜 Disclaimer

V.E.D.A. is an actively developed project, and functionality may change between versions.

Always use the latest available version and follow the installation instructions included with the current release.

V.E.D.A. is currently under development, so bugs and unexpected behavior may occur.

V.E.D.A.
Virtual Executive Desktop Assistant

Talk to your computer.
Let V.E.D.A. handle the task.
---
