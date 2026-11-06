from __future__ import annotations

from PySide6.QtCore import QObject, QThread, Signal, Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSplitter,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from app.ai.ollama_client import OllamaClient, OllamaError
from app.ai.agent import AuraAgent
from app.database.db import (
    add_message,
    create_conversation,
    get_messages,
    list_conversations,
    update_conversation_title,
)


class ChatWorker(QObject):
    finished = Signal(str)
    failed = Signal(str)

    def __init__(self, client: OllamaClient, messages: list[dict[str, str]]) -> None:
        super().__init__()
        self.client = client
        self.messages = messages

    def run(self) -> None:
        try:
            self.finished.emit(AuraAgent(client=self.client).run(self.messages))
        except OllamaError as exc:
            self.failed.emit(str(exc))
        except Exception as exc:  # Keep unexpected worker errors visible to the UI.
            self.failed.emit(f"Unexpected AI error: {exc}")


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("AURA AI")
        self.resize(1180, 760)
        self.setMinimumSize(850, 560)

        self.client = OllamaClient()
        self.conversation_id: int | None = None
        self.thread: QThread | None = None
        self.worker: ChatWorker | None = None

        self._build_ui()
        self._apply_theme()
        self._load_conversations()
        self._new_conversation()

    def _build_ui(self) -> None:
        root = QWidget()
        outer = QHBoxLayout(root)
        outer.setContentsMargins(16, 16, 16, 16)
        outer.setSpacing(14)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setChildrenCollapsible(False)

        sidebar = QWidget()
        sidebar.setMinimumWidth(210)
        side = QVBoxLayout(sidebar)
        brand = QLabel("A U R A")
        brand.setObjectName("brand")
        side.addWidget(brand)
        side.addWidget(QLabel("LOCAL AI WORKSPACE"))

        self.new_button = QPushButton("+  New conversation")
        self.new_button.clicked.connect(self._new_conversation)
        side.addWidget(self.new_button)

        self.history = QListWidget()
        self.history.itemClicked.connect(self._open_selected_conversation)
        side.addWidget(QLabel("RECENT CHATS"))
        side.addWidget(self.history, 1)

        self.connection_label = QLabel("● Checking Ollama…")
        self.connection_label.setObjectName("muted")
        side.addWidget(self.connection_label)

        workspace = QWidget()
        main = QVBoxLayout(workspace)
        main.setContentsMargins(18, 12, 12, 12)
        main.setSpacing(12)

        top = QHBoxLayout()
        heading_box = QVBoxLayout()
        heading = QLabel("AI Workspace")
        heading.setObjectName("heading")
        subtitle = QLabel("A private assistant running on your computer")
        subtitle.setObjectName("muted")
        heading_box.addWidget(heading)
        heading_box.addWidget(subtitle)
        top.addLayout(heading_box)
        top.addStretch(1)
        self.model_label = QLabel(self.client.model)
        self.model_label.setObjectName("model")
        top.addWidget(self.model_label)
        main.addLayout(top)

        self.chat_view = QTextBrowser()
        self.chat_view.setOpenExternalLinks(True)
        self.chat_view.setObjectName("chat")
        main.addWidget(self.chat_view, 1)

        compose = QHBoxLayout()
        self.prompt_input = QLineEdit()
        self.prompt_input.setPlaceholderText("Ask AURA anything…")
        self.prompt_input.returnPressed.connect(self._send_message)
        self.send_button = QPushButton("Send")
        self.send_button.clicked.connect(self._send_message)
        compose.addWidget(self.prompt_input, 1)
        compose.addWidget(self.send_button)
        main.addLayout(compose)

        splitter.addWidget(sidebar)
        splitter.addWidget(workspace)
        splitter.setSizes([250, 900])
        outer.addWidget(splitter)
        self.setCentralWidget(root)

    def _apply_theme(self) -> None:
        self.setFont(QFont("Inter", 10))
        self.setStyleSheet("""
            QMainWindow, QWidget { background: #10131b; color: #e8ecf5; }
            QWidget#chat { background: #171c27; border: 1px solid #2b3445;
                           border-radius: 12px; padding: 14px; }
            QLabel#brand { color: #8d9cff; font-size: 25px; font-weight: 800;
                           padding: 10px 2px; }
            QLabel#heading { font-size: 23px; font-weight: 700; color: #f4f6fb; }
            QLabel#muted { color: #929db2; font-size: 11px; }
            QLabel#model { color: #aebaff; background: #20283b;
                           border: 1px solid #354266; border-radius: 9px;
                           padding: 8px 12px; }
            QPushButton { background: #6878e8; color: white; border: 0;
                          border-radius: 8px; padding: 10px 14px; font-weight: 600; }
            QPushButton:hover { background: #7c8aff; }
            QPushButton:disabled { background: #3a4053; color: #8991a5; }
            QLineEdit { background: #171c27; color: #f3f5fa;
                        border: 1px solid #354055; border-radius: 9px;
                        padding: 13px; selection-background-color: #6878e8; }
            QListWidget { background: #141923; color: #dce2ef;
                          border: 1px solid #293244; border-radius: 8px;
                          padding: 5px; outline: 0; }
            QListWidget::item { padding: 9px; border-radius: 5px; }
            QListWidget::item:selected { background: #293451; color: white; }
            QSplitter::handle { background: #252d3c; width: 2px; }
        """)

    def _load_conversations(self) -> None:
        self.history.clear()
        for conversation in list_conversations():
            item = self.history.addItem(conversation["title"])
            # QListWidget.addItem returns None; IDs are stored on the actual item.
            row = self.history.item(self.history.count() - 1)
            row.setData(Qt.ItemDataRole.UserRole, conversation["id"])

    def _new_conversation(self) -> None:
        if self.thread and self.thread.isRunning():
            return
        self.conversation_id = create_conversation()
        self.chat_view.clear()
        self._append_message("assistant", "Hello! I'm AURA. How can I help with your work today?")
        self._load_conversations()
        if self.history.count():
            self.history.setCurrentRow(0)

    def _open_selected_conversation(self, item) -> None:
        if self.thread and self.thread.isRunning():
            return
        conversation_id = item.data(Qt.ItemDataRole.UserRole)
        if not conversation_id:
            return
        self.conversation_id = int(conversation_id)
        self.chat_view.clear()
        for message in get_messages(self.conversation_id):
            self._append_message(message["role"], message["content"])

    def _append_message(self, role: str, content: str) -> None:
        label = "YOU" if role == "user" else "AURA"
        safe = (content.replace("&", "&amp;").replace("<", "&lt;")
                .replace(">", "&gt;").replace("\n", "<br>"))
        self.chat_view.append(
            f'<p style="color:#8f9cff;font-weight:700;margin-bottom:4px;">{label}</p>'
            f'<p style="color:#e8ecf5;margin-top:0;margin-bottom:18px;">{safe}</p>'
        )

    def _send_message(self) -> None:
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

        context = get_messages(self.conversation_id, limit=12)
        messages = [
            {"role": "system", "content":
             "You are AURA, a concise and helpful local-first desktop assistant. "
             "Do not claim to have accessed files or performed actions unless a tool "
             "actually did so. Never ask to run destructive commands. Keep answers "
             "clear and practical."}
        ]
        messages.extend({"role": row["role"], "content": row["content"]} for row in context)

        self.send_button.setEnabled(False)
        self.prompt_input.setEnabled(False)
        self.connection_label.setText("● AURA is thinking…")

        self.thread = QThread(self)
        self.worker = ChatWorker(self.client, messages)
        self.worker.moveToThread(self.thread)
        self.thread.started.connect(self.worker.run)
        self.worker.finished.connect(self._on_ai_response)
        self.worker.failed.connect(self._on_ai_error)
        self.worker.finished.connect(self.thread.quit)
        self.worker.failed.connect(self.thread.quit)
        self.thread.finished.connect(self._cleanup_worker)
        self.thread.start()

    def _on_ai_response(self, answer: str) -> None:
        self._append_message("assistant", answer)
        if self.conversation_id is not None:
            add_message(self.conversation_id, "assistant", answer)
        self.connection_label.setText("● Ollama connected")

    def _on_ai_error(self, error: str) -> None:
        self._append_message("assistant", f"Error: {error}")
        self.connection_label.setText("● Ollama unavailable")

    def _cleanup_worker(self) -> None:
        self.send_button.setEnabled(True)
        self.prompt_input.setEnabled(True)
        self.prompt_input.setFocus()
        if self.worker:
            self.worker.deleteLater()
        if self.thread:
            self.thread.deleteLater()
        self.worker = None
        self.thread = None

    def closeEvent(self, event) -> None:
        if self.thread and self.thread.isRunning():
            self.thread.quit()
            self.thread.wait(2000)
        super().closeEvent(event)
