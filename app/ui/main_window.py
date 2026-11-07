from __future__ import annotations

from pathlib import Path
import html

from PySide6.QtCore import QObject, QThread, QTimer, Qt, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QComboBox, QFileDialog, QFrame, QGridLayout, QHBoxLayout, QLabel,
    QLineEdit, QListWidget, QListWidgetItem, QMainWindow, QMessageBox,
    QPushButton, QPlainTextEdit, QStackedWidget, QTextBrowser, QVBoxLayout,
    QWidget, QSplitter, QInputDialog
)

from app.ai.agent import AuraAgent
from app.ai.code_generator import CodeGenerator
from app.ai.ollama_client import OllamaClient
from app.desktop.tools import get_system_overview, get_top_processes
from app.files.file_tools import search_files, read_text_file
from app.files.change_manager import ChangeManager
from app.database.db import (
    add_message, create_conversation, get_messages, list_conversations,
    update_conversation_title,
)


class TaskWorker(QObject):
    finished = Signal(str)
    failed = Signal(str)

    def __init__(self, task: str, client: OllamaClient, payload: dict):
        super().__init__()
        self.task, self.client, self.payload = task, client, payload

    def run(self):
        try:
            if self.task == "chat":
                result = AuraAgent(client=self.client).run(self.payload["messages"])
            elif self.task == "code":
                result = CodeGenerator(client=self.client).generate(
                    self.payload["request"], self.payload.get("language", "Python"),
                    self.payload.get("context", "")
                )
            else:
                raise ValueError("Unknown background task.")
            self.finished.emit(result)
        except Exception as exc:
            self.failed.emit(str(exc))


class StatCard(QFrame):
    def __init__(self, title: str, value: str = "—", detail: str = ""):
        super().__init__()
        self.setObjectName("statCard")
        layout = QVBoxLayout(self)
        self.title = QLabel(title.upper())
        self.title.setObjectName("muted")
        self.value = QLabel(value)
        self.value.setObjectName("statValue")
        self.detail = QLabel(detail)
        self.detail.setObjectName("muted")
        layout.addWidget(self.title)
        layout.addWidget(self.value)
        layout.addWidget(self.detail)

    def update_value(self, value: str, detail: str = ""):
        self.value.setText(value)
        self.detail.setText(detail)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("AURA AI — Local Development Workspace")
        self.resize(1400, 880)
        self.setMinimumSize(1050, 680)
        self.client = OllamaClient()
        self.conversation_id = None
        self.thread = None
        self.worker = None
        self.workspace_path = Path.home() / "Projects"
        self.change_manager = None
        self._build_ui()
        self._apply_theme()
        self._load_conversations()
        self._new_conversation()
        self.refresh_dashboard()
        self.monitor_timer = QTimer(self)
        self.monitor_timer.timeout.connect(self.refresh_dashboard)
        self.monitor_timer.start(5000)

    def _build_ui(self):
        root = QWidget()
        layout = QHBoxLayout(root)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        sidebar = QWidget()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(245)
        side = QVBoxLayout(sidebar)
        side.setContentsMargins(18, 24, 18, 18)
        side.setSpacing(9)

        brand = QLabel("A U R A")
        brand.setObjectName("brand")
        side.addWidget(brand)
        side.addWidget(QLabel("LOCAL AI DEVELOPMENT"))
        side.addSpacing(14)

        self.nav_buttons = {}
        for key, label in [
            ("dashboard", "⌂   Overview"),
            ("chat", "◉   AI Chat"),
            ("projects", "▣   Projects & Files"),
            ("code", "</>   Code Assistant"),
            ("monitor", "▥   System Monitor"),
            ("settings", "⚙   Settings"),
        ]:
            button = QPushButton(label)
            button.setObjectName("navButton")
            button.setCheckable(True)
            button.clicked.connect(lambda checked=False, page=key: self.show_page(page))
            self.nav_buttons[key] = button
            side.addWidget(button)

        side.addSpacing(18)
        side.addWidget(QLabel("RECENT CONVERSATIONS"))
        self.history = QListWidget()
        self.history.setMaximumHeight(190)
        self.history.itemClicked.connect(self._open_conversation)
        side.addWidget(self.history)
        self.new_chat_button = QPushButton("+  New conversation")
        self.new_chat_button.clicked.connect(self._new_conversation)
        side.addWidget(self.new_chat_button)
        side.addStretch(1)
        self.connection_label = QLabel("● Checking local AI…")
        self.connection_label.setObjectName("muted")
        side.addWidget(self.connection_label)

        self.pages = QStackedWidget()
        self.page_index = {}

        self.page_index["dashboard"] = self.pages.addWidget(self._dashboard_page())
        self.page_index["chat"] = self.pages.addWidget(self._chat_page())
        self.page_index["projects"] = self.pages.addWidget(self._projects_page())
        self.page_index["code"] = self.pages.addWidget(self._code_page())
        self.page_index["monitor"] = self.pages.addWidget(self._monitor_page())
        self.page_index["settings"] = self.pages.addWidget(self._settings_page())

        layout.addWidget(sidebar)
        layout.addWidget(self.pages, 1)
        self.setCentralWidget(root)
        self.show_page("dashboard")

    def _page(self, title: str, subtitle: str):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(30, 25, 30, 25)
        layout.setSpacing(16)
        heading = QLabel(title)
        heading.setObjectName("pageTitle")
        sub = QLabel(subtitle)
        sub.setObjectName("muted")
        layout.addWidget(heading)
        layout.addWidget(sub)
        return page, layout

    def _dashboard_page(self):
        page, layout = self._page("Workspace overview", "Your local AI development environment at a glance.")
        cards = QGridLayout()
        self.cpu_card = StatCard("CPU usage")
        self.ram_card = StatCard("Memory")
        self.disk_card = StatCard("Storage")
        self.model_card = StatCard("Active model", self.client.model, "Ollama local runtime")
        for index, card in enumerate([self.cpu_card, self.ram_card, self.disk_card, self.model_card]):
            cards.addWidget(card, index // 2, index % 2)
        layout.addLayout(cards)
        section = QLabel("GET STARTED")
        section.setObjectName("sectionTitle")
        layout.addWidget(section)
        actions = QGridLayout()
        for title, description, key in [
            ("Chat with AURA", "Ask questions and inspect your codebase.", "chat"),
            ("Explore a project", "Browse source files in your workspace.", "projects"),
            ("Generate code", "Describe a feature and get a code draft.", "code"),
            ("Monitor your PC", "View CPU, memory and storage usage.", "monitor"),
        ]:
            card = QPushButton(title + "\n" + description)
            card.setObjectName("actionCard")
            card.setMinimumHeight(92)
            card.clicked.connect(lambda checked=False, target=key: self.show_page(target))
            actions.addWidget(card, actions.count() // 2, actions.count() % 2)
        layout.addLayout(actions)
        layout.addStretch(1)
        return page

    def _chat_page(self):
        page, layout = self._page("AI Chat", "Talk to your local assistant. Read-only project and system tools are available.")
        top = QHBoxLayout()
        self.chat_model_label = QLabel(self.client.model)
        self.chat_model_label.setObjectName("pill")
        top.addStretch(1)
        top.addWidget(self.chat_model_label)
        layout.addLayout(top)
        self.chat_view = QTextBrowser()
        self.chat_view.setObjectName("chatView")
        self.chat_view.setOpenExternalLinks(True)
        layout.addWidget(self.chat_view, 1)
        compose = QHBoxLayout()
        self.prompt_input = QLineEdit()
        self.prompt_input.setPlaceholderText("Ask AURA about code, files, debugging or your system…")
        self.prompt_input.returnPressed.connect(self._send_message)
        self.send_button = QPushButton("Send")
        self.send_button.clicked.connect(self._send_message)
        compose.addWidget(self.prompt_input, 1)
        compose.addWidget(self.send_button)
        layout.addLayout(compose)
        return page

    def _projects_page(self):
        page, layout = self._page("Projects & Files", "Browse files and inspect supported source files without modifying them.")
        bar = QHBoxLayout()
        self.workspace_label = QLabel(str(self.workspace_path))
        self.workspace_label.setObjectName("pill")
        choose = QPushButton("Choose folder")
        choose.clicked.connect(self._choose_workspace)
        refresh = QPushButton("Refresh")
        refresh.clicked.connect(self._refresh_files)
        bar.addWidget(self.workspace_label, 1)
        bar.addWidget(choose)
        bar.addWidget(refresh)
        layout.addLayout(bar)
        change_bar = QHBoxLayout()
        self.edit_file_button = QPushButton("Propose edit")
        self.edit_file_button.clicked.connect(self._propose_edit_selected)
        self.create_file_button = QPushButton("New file")
        self.create_file_button.clicked.connect(self._propose_create_file)
        self.delete_file_button = QPushButton("Move to trash")
        self.delete_file_button.clicked.connect(self._propose_delete_selected)
        self.recovery_button = QPushButton("Recovery")
        self.recovery_button.clicked.connect(self._open_recovery)
        change_bar.addWidget(self.edit_file_button)
        change_bar.addWidget(self.create_file_button)
        change_bar.addWidget(self.delete_file_button)
        change_bar.addWidget(self.recovery_button)
        change_bar.addStretch(1)
        layout.addLayout(change_bar)
        split = QSplitter(Qt.Orientation.Horizontal)
        self.file_list = QListWidget()
        self.file_list.itemClicked.connect(self._open_file)
        self.file_view = QPlainTextEdit()
        self.file_view.setReadOnly(True)
        self.file_view.setPlaceholderText("Select a supported text file to inspect its contents.")
        split.addWidget(self.file_list)
        split.addWidget(self.file_view)
        split.setSizes([360, 700])
        layout.addWidget(split, 1)
        self._refresh_files()
        return page

    def _code_page(self):
        page, layout = self._page("Code Assistant", "Generate code drafts with your local Ollama model. Nothing is written automatically.")
        layout.addWidget(QLabel("Describe what you want to build"))
        self.code_request = QPlainTextEdit()
        self.code_request.setPlaceholderText("Example: Create a Python class that validates and normalizes email addresses…")
        self.code_request.setMaximumHeight(145)
        layout.addWidget(self.code_request)
        row = QHBoxLayout()
        self.code_language = QComboBox()
        self.code_language.addItems(["Python", "JavaScript", "TypeScript", "Dart", "HTML/CSS", "C++", "SQL"])
        row.addWidget(QLabel("Language"))
        row.addWidget(self.code_language)
        self.generate_button = QPushButton("Generate code")
        self.generate_button.clicked.connect(self._generate_code)
        row.addStretch(1)
        row.addWidget(self.generate_button)
        layout.addLayout(row)
        self.code_output = QPlainTextEdit()
        self.code_output.setReadOnly(True)
        self.code_output.setPlaceholderText("Your generated code and explanation will appear here.")
        layout.addWidget(self.code_output, 1)
        return page

    def _monitor_page(self):
        page, layout = self._page("System Monitor", "Live overview of your computer. Statistics refresh every five seconds.")
        cards = QGridLayout()
        self.monitor_cpu = StatCard("CPU usage")
        self.monitor_ram = StatCard("Memory")
        self.monitor_disk = StatCard("Disk")
        self.monitor_swap = StatCard("Swap")
        for i, card in enumerate([self.monitor_cpu, self.monitor_ram, self.monitor_disk, self.monitor_swap]):
            cards.addWidget(card, i // 2, i % 2)
        layout.addLayout(cards)
        layout.addWidget(QLabel("TOP MEMORY PROCESSES"))
        self.process_view = QPlainTextEdit()
        self.process_view.setReadOnly(True)
        layout.addWidget(self.process_view, 1)
        refresh = QPushButton("Refresh now")
        refresh.clicked.connect(self.refresh_dashboard)
        layout.addWidget(refresh)
        return page

    def _settings_page(self):
        page, layout = self._page("Settings", "Local runtime configuration.")
        layout.addWidget(QLabel("Ollama model"))
        self.settings_model = QLineEdit(self.client.model)
        layout.addWidget(self.settings_model)
        note = QLabel("Model selection is currently read from the AURA_MODEL environment variable. This screen displays the active setting; persistent editing will be added in a later milestone.")
        note.setObjectName("muted")
        note.setWordWrap(True)
        layout.addWidget(note)
        layout.addWidget(QLabel("Ollama server"))
        self.settings_url = QLineEdit(self.client.base_url)
        self.settings_url.setReadOnly(True)
        layout.addWidget(self.settings_url)
        layout.addStretch(1)
        return page

    def show_page(self, key: str):
        self.pages.setCurrentIndex(self.page_index[key])
        for name, button in self.nav_buttons.items():
            button.setChecked(name == key)
        if key == "projects":
            self._refresh_files()
        elif key in {"dashboard", "monitor"}:
            self.refresh_dashboard()

    def _apply_theme(self):
        self.setFont(QFont("Inter", 10))
        self.setStyleSheet("""
            QMainWindow, QWidget { background:#0e121b; color:#e8edf7; }
            QWidget#sidebar { background:#121824; border-right:1px solid #273247; }
            QLabel#brand { color:#8798ff; font-size:27px; font-weight:800; padding:8px 2px; }
            QLabel#pageTitle { font-size:27px; font-weight:750; color:#f5f7fc; }
            QLabel#sectionTitle { color:#aebaff; font-size:13px; font-weight:700; padding-top:12px; }
            QLabel#muted { color:#8f9bb0; font-size:11px; }
            QLabel#statValue { color:#f5f7ff; font-size:27px; font-weight:750; }
            QFrame#statCard { background:#171f2e; border:1px solid #2b3850; border-radius:12px; padding:10px; min-height:100px; }
            QLabel#pill { color:#bdc8ff; background:#202b43; border:1px solid #354568; border-radius:8px; padding:8px 12px; }
            QPushButton { background:#6578e8; color:white; border:0; border-radius:8px; padding:10px 15px; font-weight:650; }
            QPushButton:hover { background:#7889f2; }
            QPushButton:disabled { background:#384158; color:#9099ad; }
            QPushButton#navButton { text-align:left; background:transparent; color:#b7c1d3; padding:12px; }
            QPushButton#navButton:hover { background:#1c2739; color:white; }
            QPushButton#navButton:checked { background:#293657; color:#ffffff; border-left:3px solid #8798ff; }
            QPushButton#actionCard { text-align:left; background:#171f2e; border:1px solid #2b3850; padding:18px; min-height:75px; }
            QLineEdit, QPlainTextEdit, QTextBrowser, QListWidget, QComboBox { background:#151c29; color:#e8edf7; border:1px solid #303d54; border-radius:9px; padding:10px; selection-background-color:#5369c8; }
            QListWidget::item { padding:8px; border-radius:5px; }
            QListWidget::item:selected { background:#293657; }
            QSplitter::handle { background:#283449; }
        """)

    def _load_conversations(self):
        self.history.clear()
        for conversation in list_conversations():
            item = QListWidgetItem(conversation["title"])
            item.setData(Qt.ItemDataRole.UserRole, conversation["id"])
            self.history.addItem(item)

    def _new_conversation(self):
        if self.thread and self.thread.isRunning():
            return
        self.conversation_id = create_conversation()
        if hasattr(self, "chat_view"):
            self.chat_view.clear()
            self._append_message("assistant", "Hello! I'm AURA. What would you like to work on?")
        self._load_conversations()

    def _open_conversation(self, item):
        if self.thread and self.thread.isRunning():
            return
        conversation_id = item.data(Qt.ItemDataRole.UserRole)
        if not conversation_id:
            return
        self.conversation_id = int(conversation_id)
        self.chat_view.clear()
        for message in get_messages(self.conversation_id):
            self._append_message(message["role"], message["content"])
        self.show_page("chat")

    def _append_message(self, role: str, content: str):
        label = "YOU" if role == "user" else "AURA"
        safe = html.escape(content).replace("\n", "<br>")
        self.chat_view.append(
            f'<p style="color:#91a2ff;font-weight:700;margin-bottom:4px">{label}</p>'
            f'<p style="color:#e8edf7;margin-top:0;margin-bottom:18px">{safe}</p>'
        )

    def _start_task(self, task: str, payload: dict):
        if self.thread and self.thread.isRunning():
            return
        self.thread = QThread(self)
        self.worker = TaskWorker(task, self.client, payload)
        self.worker.moveToThread(self.thread)
        self.thread.started.connect(self.worker.run)
        self.worker.finished.connect(self._task_finished)
        self.worker.failed.connect(self._task_failed)
        self.worker.finished.connect(self.thread.quit)
        self.worker.failed.connect(self.thread.quit)
        self.thread.finished.connect(self._task_cleanup)
        self.thread.start()

    def _send_message(self):
        prompt = self.prompt_input.text().strip()
        if not prompt or (self.thread and self.thread.isRunning()):
            return
        if self.conversation_id is None:
            self.conversation_id = create_conversation()
        self.prompt_input.clear()
        self._append_message("user", prompt)
        add_message(self.conversation_id, "user", prompt)
        if len(prompt) < 55:
            update_conversation_title(self.conversation_id, prompt)
        context = get_messages(self.conversation_id, limit=10)
        messages = [{"role": row["role"], "content": row["content"]} for row in context]
        self.send_button.setEnabled(False)
        self.prompt_input.setEnabled(False)
        self.connection_label.setText("● AURA is thinking…")
        self._start_task("chat", {"messages": messages})

    def _generate_code(self):
        request = self.code_request.toPlainText().strip()
        if not request:
            QMessageBox.information(self, "Code Assistant", "Describe the code you want to generate first.")
            return
        self.generate_button.setEnabled(False)
        self.code_output.setPlainText("AURA is generating a draft…")
        self._start_task("code", {"request": request, "language": self.code_language.currentText()})

    def _task_finished(self, result: str):
        current_page = self.pages.currentIndex()
        if current_page == self.page_index["code"] and not self.generate_button.isEnabled():
            self.code_output.setPlainText(result)
        else:
            self._append_message("assistant", result)
            if self.conversation_id is not None:
                add_message(self.conversation_id, "assistant", result)
            self.connection_label.setText("● Ollama connected")
            self._load_conversations()

    def _task_failed(self, error: str):
        if hasattr(self, "code_output") and not self.generate_button.isEnabled():
            self.code_output.setPlainText("Generation failed: " + error)
        else:
            self._append_message("assistant", "Error: " + error)
        self.connection_label.setText("● Ollama unavailable")

    def _task_cleanup(self):
        self.send_button.setEnabled(True)
        self.prompt_input.setEnabled(True)
        self.generate_button.setEnabled(True)
        if self.worker:
            self.worker.deleteLater()
        if self.thread:
            self.thread.deleteLater()
        self.worker = None
        self.thread = None

    def _choose_workspace(self):
        chosen = QFileDialog.getExistingDirectory(self, "Choose project folder", str(self.workspace_path))
        if chosen:
            self.workspace_path = Path(chosen).expanduser().resolve()
            self.change_manager = None
            self.workspace_label.setText(str(self.workspace_path))
            self._refresh_files()

    def _refresh_files(self):
        if not hasattr(self, "file_list"):
            return
        self.file_list.clear()
        try:
            result = search_files(self.workspace_path, max_results=250)
            for entry in result["results"]:
                item = QListWidgetItem(f'{entry["name"]}    ·    {entry["size_mb"]} MB')
                item.setData(Qt.ItemDataRole.UserRole, entry["path"])
                self.file_list.addItem(item)
            if result["truncated"]:
                self.file_view.setPlainText("Showing the first 250 matching files. Narrow the folder to see more.")
        except Exception as exc:
            self.file_view.setPlainText(f"Could not list this folder: {exc}")

    def _open_file(self, item):
        path = item.data(Qt.ItemDataRole.UserRole)
        try:
            data = read_text_file(path, start_line=1, end_line=400)
            self.file_view.setPlainText(data["content"])
        except Exception as exc:
            self.file_view.setPlainText(f"Cannot preview this file: {exc}")

    def refresh_dashboard(self):
        try:
            stats = get_system_overview()
            cpu, memory, disk = stats["cpu"], stats["memory"], stats["disk"]
            self.cpu_card.update_value(f'{cpu["usage_percent"]:.1f}%', f'{cpu["logical_cores"]} logical cores')
            self.ram_card.update_value(f'{memory["used_gb"]:.1f} / {memory["total_gb"]:.1f} GB', f'{memory["usage_percent"]:.0f}% used')
            self.disk_card.update_value(f'{disk["free_gb"]:.1f} GB free', f'{disk["usage_percent"]:.0f}% used')
            self.monitor_cpu.update_value(f'{cpu["usage_percent"]:.1f}%', f'{cpu["logical_cores"]} logical cores')
            self.monitor_ram.update_value(f'{memory["used_gb"]:.1f} / {memory["total_gb"]:.1f} GB', f'{memory["usage_percent"]:.0f}% used')
            self.monitor_disk.update_value(f'{disk["used_gb"]:.1f} / {disk["total_gb"]:.1f} GB', f'{disk["usage_percent"]:.0f}% used')
            self.monitor_swap.update_value(f'{memory["swap_used_gb"]:.1f} / {memory["swap_total_gb"]:.1f} GB', f'{memory["swap_percent"]:.0f}% used')
            processes = get_top_processes(8)
            self.process_view.setPlainText("\n".join(
                f'{p["name"][:28]:28}  {p["memory_mb"]:>8.1f} MB   CPU {p["cpu_percent"]:>5.1f}%'
                for p in processes
            ))
        except Exception as exc:
            self.connection_label.setText(f"● Monitor error: {exc}")

    def closeEvent(self, event):
        self.monitor_timer.stop()
        if self.thread and self.thread.isRunning():
            self.thread.quit()
            self.thread.wait(2500)
        super().closeEvent(event)


    def _get_change_manager(self):
        if self.change_manager is None:
            self.change_manager = ChangeManager(self.workspace_path)
        return self.change_manager

    def _selected_file_path(self):
        item = self.file_list.currentItem()
        if item is None:
            QMessageBox.information(self, "Projects & Files", "Select a file first.")
            return None
        return Path(item.data(Qt.ItemDataRole.UserRole))

    def _confirm_proposal(self, proposal):
        preview = proposal.get("preview", {})
        diff = preview.get("diff") or preview.get("description") or "No text diff is available."
        target = preview.get("target", preview.get("destination", "Selected item"))
        message = (
            f"Proposed operation: {proposal.get('action', 'change')}\n"
            f"Target: {target}\n\n"
            "Review the preview carefully. Nothing has been changed yet.\n\n"
            f"{diff[:12000]}\n\n"
            "Approve and apply this change?"
        )
        answer = QMessageBox.question(
            self, "Review proposed change", message,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            self._get_change_manager().cancel(proposal["id"])
            QMessageBox.information(self, "Change cancelled", "No files were changed.")
            return
        try:
            result = self._get_change_manager().approve(proposal["id"])
            QMessageBox.information(
                self, "Change approved",
                f"The operation was applied.\n\n{result.get('result', {})}",
            )
            self._refresh_files()
        except Exception as exc:
            QMessageBox.critical(self, "Change not applied", str(exc))

    def _propose_edit_selected(self):
        path = self._selected_file_path()
        if path is None:
            return
        try:
            current = path.read_text(encoding="utf-8")
        except (OSError, UnicodeError) as exc:
            QMessageBox.warning(self, "Cannot edit file", str(exc))
            return
        new_content, accepted = QInputDialog.getMultiLineText(
            self, "Propose file edit",
            "Edit the file contents. A diff preview appears before approval:",
            current,
        )
        if not accepted:
            return
        try:
            proposal = self._get_change_manager().propose_edit_file(path, new_content)
            self._confirm_proposal(proposal)
        except Exception as exc:
            QMessageBox.warning(self, "Could not create proposal", str(exc))

    def _propose_create_file(self):
        relative_path, accepted = QInputDialog.getText(
            self, "Create file", "New file path relative to selected workspace:"
        )
        if not accepted or not relative_path.strip():
            return
        content, content_accepted = QInputDialog.getMultiLineText(
            self, "New file contents", "Enter initial text for the new file:"
        )
        if not content_accepted:
            return
        try:
            proposal = self._get_change_manager().propose_create_file(relative_path.strip(), content)
            self._confirm_proposal(proposal)
        except Exception as exc:
            QMessageBox.warning(self, "Could not create proposal", str(exc))

    def _propose_delete_selected(self):
        path = self._selected_file_path()
        if path is None:
            return
        try:
            proposal = self._get_change_manager().propose_delete(path)
            self._confirm_proposal(proposal)
        except Exception as exc:
            QMessageBox.warning(self, "Could not create proposal", str(exc))


    def _open_recovery(self):
        try:
            manager = self._get_change_manager()
            trash_items = manager.list_trash()
            backups = manager.list_backups()
        except Exception as exc:
            QMessageBox.warning(self, "Recovery", str(exc))
            return

        choices = []
        for item in trash_items:
            choices.append((
                f"TRASH  |  {item['original_path']}  |  {item['id'][:8]}",
                "trash", item["id"],
            ))
        for item in backups:
            choices.append((
                f"BACKUP |  {item['original_path']}  |  {item['id'][:8]}",
                "backup", item["id"],
            ))

        if not choices:
            QMessageBox.information(
                self, "Recovery", "There are currently no recoverable deleted files or backups."
            )
            return

        labels = [item[0] for item in choices]
        selected, accepted = QInputDialog.getItem(
            self, "AURA Recovery", "Choose an item to restore:", labels, 0, False
        )
        if not accepted or not selected:
            return

        choice = next(item for item in choices if item[0] == selected)
        try:
            if choice[1] == "trash":
                proposal = manager.propose_restore_trash(choice[2])
            else:
                proposal = manager.propose_restore_backup(choice[2])
            self._confirm_proposal(proposal)
        except Exception as exc:
            QMessageBox.warning(self, "Cannot restore item", str(exc))
