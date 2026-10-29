import random
import sys
import time
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk


PROJECT_DIR = Path(__file__).resolve().parents[1]
if str(PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(PROJECT_DIR))

from Backend import database, importer


APP_TITLE = "Тестировщик"
EXAM_SECONDS_PER_QUESTION = 120
EXAM_MIN_SECONDS = 600

COLORS = {
    "bg": "#f6f8fb",
    "surface": "#ffffff",
    "surface_alt": "#f9fafb",
    "line": "#e5e7eb",
    "text": "#111827",
    "muted": "#6b7280",
    "primary": "#1d4ed8",
    "primary_dark": "#1e40af",
    "primary_soft": "#eff6ff",
    "success": "#047857",
    "success_soft": "#ecfdf5",
    "danger": "#b91c1c",
    "danger_soft": "#fef2f2",
    "warning_soft": "#fffbeb",
}


class DesktopApp(tk.Tk):
    def __init__(self):
        super().__init__()
        database.init_db()
        self.title(APP_TITLE)
        self.geometry("1120x720")
        self.minsize(960, 620)
        self.configure(bg=COLORS["bg"])

        self.user = None
        self.session_password = None
        self.active_test = None
        self.answers = {}
        self.current_question_index = 0
        self.exam_active = False
        self.test_finished = False
        self.locked = False
        self.exam_dialog_active = False
        self.remaining_seconds = 0
        self.timer_job = None
        self.focus_job = None
        self.lock_job = None
        self.ignore_focus_until = 0
        self.timer_label = None
        self.progress_label = None
        self.progress_bar = None
        self.exam_canvas = None
        self.question_cards = {}
        self.question_nav_buttons = {}
        self.answer_widgets = {}
        self.question_status_labels = {}

        self.build_style()
        self.setup_text_shortcuts()
        self.setup_exam_guards()
        self.show_login()

    def build_style(self):
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure(".", background=COLORS["bg"], foreground=COLORS["text"], font=("Segoe UI", 10))
        style.configure("Page.TFrame", background=COLORS["bg"])
        style.configure("Card.TFrame", background=COLORS["surface"], relief="flat")
        style.configure("Soft.TFrame", background=COLORS["surface_alt"])
        style.configure("TLabel", background=COLORS["bg"], foreground=COLORS["text"])
        style.configure("Card.TLabel", background=COLORS["surface"], foreground=COLORS["text"])
        style.configure("Muted.TLabel", background=COLORS["surface"], foreground=COLORS["muted"])
        style.configure("Soft.TLabel", background=COLORS["surface_alt"], foreground=COLORS["muted"])
        style.configure("Title.TLabel", background=COLORS["bg"], font=("Segoe UI", 24, "bold"))
        style.configure("Hero.TLabel", background=COLORS["surface"], font=("Segoe UI", 28, "bold"))
        style.configure("Header.TLabel", background=COLORS["surface"], font=("Segoe UI", 16, "bold"))
        style.configure("Question.TLabel", background=COLORS["surface"], font=("Segoe UI", 18, "bold"))
        style.configure("Metric.TLabel", background=COLORS["surface"], font=("Segoe UI", 22, "bold"))
        style.configure("TEntry", padding=10, fieldbackground=COLORS["surface"])
        style.configure("TSpinbox", padding=8, fieldbackground=COLORS["surface"])
        style.configure("TButton", padding=(14, 9), font=("Segoe UI", 10, "bold"))
        style.configure("Primary.TButton", background=COLORS["primary"], foreground="white", borderwidth=0)
        style.map("Primary.TButton", background=[("active", COLORS["primary_dark"])])
        style.configure("Ghost.TButton", background=COLORS["surface"], foreground=COLORS["text"], borderwidth=1)
        style.configure("Danger.TButton", background=COLORS["danger"], foreground="white", borderwidth=0)
        style.configure("Horizontal.TProgressbar", background=COLORS["primary"], troughcolor=COLORS["line"], bordercolor=COLORS["line"], lightcolor=COLORS["primary"], darkcolor=COLORS["primary"])
        style.configure("Treeview", background=COLORS["surface"], fieldbackground=COLORS["surface"], rowheight=34, borderwidth=0)
        style.configure("Treeview.Heading", background=COLORS["surface_alt"], foreground=COLORS["muted"], font=("Segoe UI", 10, "bold"))

    def setup_exam_guards(self):
        self.protocol("WM_DELETE_WINDOW", self.on_close)
        self.bind("<Alt-F4>", self.block_when_exam)
        self.bind("<Escape>", self.block_when_exam)
        self.bind("<FocusOut>", self.on_focus_lost)

    def setup_text_shortcuts(self):
        for sequence, action in {
            "<Control-v>": "paste",
            "<Control-V>": "paste",
            "<Control-c>": "copy",
            "<Control-C>": "copy",
            "<Control-x>": "cut",
            "<Control-X>": "cut",
            "<Control-a>": "select_all",
            "<Control-A>": "select_all",
        }.items():
            self.bind_all(sequence, lambda event, action=action: self.handle_text_shortcut(event, action))
        self.bind_all("<Control-KeyPress>", self.handle_control_keypress)

    def handle_control_keypress(self, event):
        key_actions = {65: "select_all", 67: "copy", 86: "paste", 88: "cut"}
        action = key_actions.get(getattr(event, "keycode", None))
        if not action:
            key = str(getattr(event, "keysym", "")).lower()
            action = {"a": "select_all", "c": "copy", "v": "paste", "x": "cut"}.get(key)
        if action:
            return self.handle_text_shortcut(event, action)
        return None

    def handle_text_shortcut(self, event, action):
        widget = event.widget
        if widget.winfo_class() not in {"Entry", "TEntry", "Spinbox", "TSpinbox", "Text"}:
            return None
        if action == "select_all":
            if widget.winfo_class() == "Text":
                widget.tag_add("sel", "1.0", "end-1c")
            else:
                widget.selection_range(0, "end")
            return "break"
        widget.event_generate(f"<<{action.capitalize()}>>")
        return "break"

    def clear(self):
        self.unbind_all("<MouseWheel>")
        self.timer_label = None
        self.progress_label = None
        self.progress_bar = None
        self.exam_canvas = None
        self.question_cards = {}
        self.question_nav_buttons = {}
        self.answer_widgets = {}
        self.question_status_labels = {}
        for child in self.winfo_children():
            child.destroy()

    def card(self, parent, padding=24):
        outer = tk.Frame(parent, bg=COLORS["line"])
        inner = ttk.Frame(outer, style="Card.TFrame", padding=padding)
        inner.pack(fill="both", expand=True, padx=1, pady=1)
        return outer, inner

    def page(self):
        self.clear()
        frame = ttk.Frame(self, style="Page.TFrame", padding=28)
        frame.pack(fill="both", expand=True)
        return frame

    def scrollable_page(self):
        self.clear()
        container = ttk.Frame(self, style="Page.TFrame")
        container.pack(fill="both", expand=True)

        canvas = tk.Canvas(container, bg=COLORS["bg"], highlightthickness=0)
        scrollbar = ttk.Scrollbar(container, orient="vertical", command=canvas.yview)
        content = ttk.Frame(canvas, style="Page.TFrame", padding=28)
        window_id = canvas.create_window((0, 0), window=content, anchor="nw")

        def update_scroll_region(_event=None):
            canvas.configure(scrollregion=canvas.bbox("all"))

        def fit_content(event):
            canvas.itemconfigure(window_id, width=event.width)

        def on_mousewheel(event):
            if event.delta:
                canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

        content.bind("<Configure>", update_scroll_region)
        canvas.bind("<Configure>", fit_content)
        canvas.bind_all("<MouseWheel>", on_mousewheel)
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        return content

    def shell(self, title, subtitle=None, show_logout=True):
        root = self.page()
        top = ttk.Frame(root, style="Page.TFrame")
        top.pack(fill="x", pady=(0, 18))
        left = ttk.Frame(top, style="Page.TFrame")
        left.pack(side="left")
        ttk.Label(left, text=title, style="Title.TLabel").pack(anchor="w")
        if subtitle:
            ttk.Label(left, text=subtitle, foreground=COLORS["muted"], background=COLORS["bg"]).pack(anchor="w", pady=(4, 0))
        if show_logout:
            ttk.Button(top, text="Выйти", style="Ghost.TButton", command=self.logout).pack(side="right")
        return root

    def show_login(self):
        self.exit_exam_mode()
        root = self.page()
        root.columnconfigure(0, weight=1)
        root.rowconfigure(0, weight=1)
        outer, box = self.card(root, padding=34)
        outer.grid(row=0, column=0)
        box.configure(width=440)

        ttk.Label(box, text=APP_TITLE, style="Hero.TLabel").pack(anchor="w")
        ttk.Label(box, text="Безопасная среда для прохождения теста", style="Muted.TLabel").pack(anchor="w", pady=(6, 26))

        ttk.Label(box, text="Логин", style="Card.TLabel").pack(anchor="w")
        username = ttk.Entry(box, width=38)
        username.pack(fill="x", pady=(6, 14))
        ttk.Label(box, text="Пароль", style="Card.TLabel").pack(anchor="w")
        password = ttk.Entry(box, width=38, show="*")
        password.pack(fill="x", pady=(6, 22))

        actions = ttk.Frame(box, style="Card.TFrame")
        actions.pack(fill="x")
        actions.columnconfigure((0, 1), weight=1)
        ttk.Button(actions, text="Войти", style="Primary.TButton", command=lambda: self.login(username.get(), password.get())).grid(row=0, column=0, sticky="ew", padx=(0, 6))
        ttk.Button(actions, text="Регистрация", style="Ghost.TButton", command=lambda: self.register(username.get(), password.get())).grid(row=0, column=1, sticky="ew", padx=(6, 0))

        username.focus_set()
        password.bind("<Return>", lambda _event: self.login(username.get(), password.get()))

    def login(self, username, password):
        user = database.authenticate(username, password)
        if not user:
            messagebox.showerror("Ошибка", "Неверный логин или пароль.")
            return
        self.user = user
        self.session_password = password
        self.show_tests()

    def register(self, username, password):
        try:
            database.register_user(username, password)
        except ValueError as exc:
            messagebox.showerror("Ошибка", str(exc))
            return
        messagebox.showinfo("Готово", "Аккаунт создан. Теперь можно войти.")

    def logout(self):
        if self.exam_active:
            return
        self.user = None
        self.session_password = None
        self.show_login()

    def show_tests(self):
        root = self.shell("Доступные тесты", f"Пользователь: {self.user['username']}")
        toolbar = ttk.Frame(root, style="Page.TFrame")
        toolbar.pack(fill="x", pady=(0, 14))
        ttk.Button(toolbar, text="Обновить", style="Ghost.TButton", command=self.show_tests).pack(side="left")
        ttk.Button(toolbar, text="Результаты", style="Ghost.TButton", command=self.show_results).pack(side="left", padx=8)
        if self.user["role"] == "admin":
            ttk.Button(toolbar, text="Создать тест", style="Primary.TButton", command=self.show_admin).pack(side="left")
            ttk.Button(toolbar, text="Управление тестами", style="Ghost.TButton", command=self.show_test_management).pack(side="left", padx=8)

        tests = database.list_tests()
        if not tests:
            outer, box = self.card(root)
            outer.pack(fill="both", expand=True)
            ttk.Label(box, text="Тестов пока нет", style="Header.TLabel").pack(anchor="w")
            return

        grid = ttk.Frame(root, style="Page.TFrame")
        grid.pack(fill="both", expand=True)
        grid.columnconfigure((0, 1), weight=1)
        for index, test in enumerate(tests):
            outer, box = self.card(grid, padding=22)
            outer.grid(row=index // 2, column=index % 2, sticky="nsew", padx=(0 if index % 2 == 0 else 10, 0), pady=(0, 14))
            ttk.Label(box, text=test["title"], style="Header.TLabel").pack(anchor="w")
            ttk.Label(box, text=test["description"] or "Описание не указано", style="Muted.TLabel", wraplength=420).pack(anchor="w", pady=(7, 16))

            metrics = ttk.Frame(box, style="Card.TFrame")
            metrics.pack(fill="x", pady=(0, 18))
            for label, value in (("Всего", test["question_count"]), ("На экзамене", test["exam_questions_count"]), ("Время", self.format_time(self.duration_for_test(test))), ("Проходной", f"{test['pass_score']}%")):
                block = ttk.Frame(metrics, style="Card.TFrame")
                block.pack(side="left", padx=(0, 24))
                ttk.Label(block, text=str(value), style="Metric.TLabel").pack(anchor="w")
                ttk.Label(block, text=label, style="Muted.TLabel").pack(anchor="w")

            ttk.Button(box, text="Открыть тест", style="Primary.TButton", command=lambda test_id=test["id"]: self.show_test_intro(test_id)).pack(anchor="e")

    def duration_for_test(self, test):
        duration = test.get("duration_seconds")
        if duration:
            return max(60, int(duration))
        return max(EXAM_MIN_SECONDS, int(test["question_count"]) * EXAM_SECONDS_PER_QUESTION)

    def show_test_intro(self, test_id):
        test = database.get_test(test_id)
        if not test or not test["questions"]:
            messagebox.showwarning("Тест", "В тесте нет вопросов.")
            return
        self.active_test = test
        root = self.shell(test["title"], "Перед началом внимательно прочитайте правила")
        outer, box = self.card(root, padding=30)
        outer.pack(fill="both", expand=True)

        ttk.Label(box, text="Безопасная среда для прохождения теста", style="Header.TLabel").pack(anchor="w")
        ttk.Label(box, text=test["description"] or "Описание не указано", style="Muted.TLabel", wraplength=840).pack(anchor="w", pady=(8, 22))

        stats = ttk.Frame(box, style="Card.TFrame")
        stats.pack(fill="x", pady=(0, 24))
        for label, value in (("Всего вопросов", len(test["questions"])), ("На экзамене", test["exam_questions_count"]), ("Время на тест", self.format_time(self.duration_for_test(test))), ("Проходной балл", f"{test['pass_score']}%")):
            metric = ttk.Frame(stats, style="Card.TFrame")
            metric.pack(side="left", padx=(0, 36))
            ttk.Label(metric, text=str(value), style="Metric.TLabel").pack(anchor="w")
            ttk.Label(metric, text=label, style="Muted.TLabel").pack(anchor="w")

        rules_outer = tk.Frame(box, bg=COLORS["warning_soft"])
        rules_outer.pack(fill="x", pady=(0, 26))
        rules = ttk.Frame(rules_outer, style="Soft.TFrame", padding=18)
        rules.pack(fill="x", padx=1, pady=1)
        for rule in (
            "Во время теста приложение переходит в полноэкранный режим.",
            "Нельзя закрывать окно или переключаться на другие приложения.",
            "При потере фокуса включается экран блокировки, разблокировка только паролем текущего пользователя.",
        ):
            ttk.Label(rules, text=f"• {rule}", style="Soft.TLabel").pack(anchor="w", pady=2)

        actions = ttk.Frame(box, style="Card.TFrame")
        actions.pack(fill="x")
        ttk.Button(actions, text="Назад", style="Ghost.TButton", command=self.show_tests).pack(side="left")
        ttk.Button(actions, text="Начать тест", style="Primary.TButton", command=self.start_test).pack(side="right")

    def start_test(self):
        self.answers = {}
        self.current_question_index = 0
        self.test_finished = False
        all_questions = list(self.active_test["questions"])
        exam_count = min(max(1, int(self.active_test.get("exam_questions_count") or len(all_questions))), len(all_questions))
        if self.active_test.get("shuffle_questions", 1):
            exam_questions = random.sample(all_questions, exam_count) if exam_count < len(all_questions) else all_questions.copy()
            random.shuffle(exam_questions)
        else:
            exam_questions = all_questions[:exam_count]
        if self.active_test.get("shuffle_answers", 0):
            exam_questions = [self.shuffle_question_answers(question) for question in exam_questions]
        else:
            exam_questions = [self.copy_exam_question(question) for question in exam_questions]
        self.active_test["all_questions"] = all_questions
        self.active_test["questions"] = exam_questions
        self.remaining_seconds = self.duration_for_test(self.active_test)
        self.enter_exam_mode()
        self.show_exam_screen()
        self.tick_timer()

    def copy_exam_question(self, question):
        item = dict(question)
        item["answers"] = list(question["answers"])
        return item

    def shuffle_question_answers(self, question):
        pairs = list(enumerate(question["answers"]))
        random.shuffle(pairs)
        item = dict(question)
        item["answers"] = [answer for _old_index, answer in pairs]
        item["correct_index"] = next(
            new_index
            for new_index, (old_index, _answer) in enumerate(pairs)
            if old_index == question["correct_index"]
        )
        return item

    def enter_exam_mode(self):
        self.exam_active = True
        self.locked = False
        self.attributes("-fullscreen", True)
        self.attributes("-topmost", True)
        self.lift()
        self.focus_force()
        self.schedule_focus_guard()

    def exit_exam_mode(self):
        self.exam_active = False
        self.locked = False
        self.ignore_focus_until = 0
        try:
            self.attributes("-topmost", False)
            self.attributes("-fullscreen", False)
            self.grab_release()
        except tk.TclError:
            pass
        if self.timer_job:
            try:
                self.after_cancel(self.timer_job)
            except tk.TclError:
                pass
            self.timer_job = None
        if self.focus_job:
            try:
                self.after_cancel(self.focus_job)
            except tk.TclError:
                pass
            self.focus_job = None
        self.cancel_pending_lock()

    def cancel_pending_lock(self):
        if self.lock_job:
            try:
                self.after_cancel(self.lock_job)
            except tk.TclError:
                pass
            self.lock_job = None

    def schedule_focus_guard(self):
        if self.focus_job:
            self.after_cancel(self.focus_job)
        if self.exam_active and not self.locked and not self.exam_dialog_active:
            self.lift()
            self.attributes("-topmost", True)
            self.focus_force()
            self.focus_job = self.after(1200, self.schedule_focus_guard)

    def on_focus_lost(self, _event):
        if time.monotonic() < self.ignore_focus_until:
            return
        if self.exam_active and not self.locked and not self.exam_dialog_active and not self.lock_job:
            self.lock_job = self.after(300, self.show_lock_screen)

    def show_lock_screen(self):
        self.lock_job = None
        if not self.exam_active or self.locked or self.exam_dialog_active:
            return
        self.locked = True
        self.clear()
        self.attributes("-fullscreen", True)
        self.attributes("-topmost", True)

        root = ttk.Frame(self, style="Page.TFrame", padding=36)
        root.pack(fill="both", expand=True)
        root.columnconfigure(0, weight=1)
        root.rowconfigure(0, weight=1)
        outer, box = self.card(root, padding=34)
        outer.grid(row=0, column=0)
        ttk.Label(box, text="Сеанс заблокирован", style="Hero.TLabel").pack(anchor="w")
        ttk.Label(box, text="Введите пароль текущего пользователя, чтобы продолжить тест.", style="Muted.TLabel").pack(anchor="w", pady=(8, 24))
        password = ttk.Entry(box, show="*", width=34)
        password.pack(fill="x", pady=(0, 18))

        def unlock():
            entered_password = password.get()
            if self.is_current_session_password(entered_password) or database.verify_user_password(self.user["id"], entered_password):
                self.cancel_pending_lock()
                self.locked = False
                self.ignore_focus_until = time.monotonic() + 1.5
                self.show_exam_screen()
                self.after(100, self.focus_force)
                self.after(1500, self.schedule_focus_guard)
                return
            messagebox.showerror("Ошибка", "Неверный пароль.")

        ttk.Button(box, text="Разблокировать", style="Primary.TButton", command=unlock).pack(anchor="e")
        password.focus_set()
        password.bind("<Return>", lambda _event: unlock())

    def is_current_session_password(self, password):
        if self.session_password is None:
            return False
        return password == self.session_password or password.strip() == self.session_password.strip()

    def block_when_exam(self, _event=None):
        return "break" if self.exam_active else None

    def on_close(self):
        if self.exam_active:
            self.show_lock_screen()
            return
        self.destroy()

    def tick_timer(self):
        if not self.exam_active:
            return
        self.update_timer_display()
        if self.remaining_seconds <= 0:
            self.finish_test(reason="timeout")
            return
        self.remaining_seconds -= 1
        self.timer_job = self.after(1000, self.tick_timer)

    def show_question(self, index):
        self.scroll_to_question(index)

    def show_exam_screen(self):
        self.clear()
        self.question_cards = {}
        self.question_nav_buttons = {}
        self.answer_widgets = {}
        self.question_status_labels = {}

        root = ttk.Frame(self, style="Page.TFrame")
        root.pack(fill="both", expand=True)
        root.rowconfigure(2, weight=1)
        root.columnconfigure(0, weight=1)

        header = ttk.Frame(root, style="Page.TFrame", padding=(28, 20, 28, 14))
        header.grid(row=0, column=0, sticky="ew")
        header.columnconfigure(0, weight=1)

        ttk.Label(header, text=self.active_test["title"], style="Title.TLabel").grid(row=0, column=0, sticky="w")
        self.progress_label = ttk.Label(header, text="", background=COLORS["bg"], foreground=COLORS["muted"], font=("Segoe UI", 11, "bold"))
        self.progress_label.grid(row=1, column=0, sticky="w", pady=(6, 0))
        self.timer_label = ttk.Label(header, text=self.format_time(self.remaining_seconds), background=COLORS["bg"], foreground=COLORS["primary"], font=("Segoe UI", 20, "bold"))
        self.timer_label.grid(row=0, column=1, rowspan=2, padx=(18, 18), sticky="e")
        ttk.Button(header, text="Завершить тест", style="Danger.TButton", command=self.request_finish_test).grid(row=0, column=2, rowspan=2, sticky="e")

        self.progress_bar = ttk.Progressbar(root, maximum=len(self.active_test["questions"]), value=0)
        self.progress_bar.grid(row=1, column=0, sticky="new", padx=28)

        body = ttk.Frame(root, style="Page.TFrame", padding=(28, 22, 28, 28))
        body.grid(row=2, column=0, sticky="nsew")
        body.rowconfigure(0, weight=1)
        body.columnconfigure(0, weight=1)

        canvas = tk.Canvas(body, bg=COLORS["bg"], highlightthickness=0)
        scrollbar = ttk.Scrollbar(body, orient="vertical", command=canvas.yview)
        content = ttk.Frame(canvas, style="Page.TFrame")
        window_id = canvas.create_window((0, 0), window=content, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.grid(row=0, column=0, sticky="nsew")
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.exam_canvas = canvas

        side_outer, side = self.card(body, padding=16)
        side_outer.grid(row=0, column=2, sticky="ne", padx=(20, 0))
        ttk.Label(side, text="Вопросы", style="Header.TLabel").pack(anchor="w")
        ttk.Label(side, text="Зеленые уже отвечены", style="Muted.TLabel").pack(anchor="w", pady=(2, 12))
        nav_canvas = tk.Canvas(side, width=196, height=430, bg=COLORS["surface"], highlightthickness=0)
        nav_scrollbar = ttk.Scrollbar(side, orient="vertical", command=nav_canvas.yview)
        nav_frame = ttk.Frame(nav_canvas, style="Card.TFrame")
        nav_window = nav_canvas.create_window((0, 0), window=nav_frame, anchor="nw")
        nav_canvas.configure(yscrollcommand=nav_scrollbar.set)
        nav_canvas.pack(side="left", fill="both", expand=True)
        nav_scrollbar.pack(side="right", fill="y")

        def update_scroll_region(_event=None):
            canvas.configure(scrollregion=canvas.bbox("all"))
            self.update_current_question_from_scroll()

        def fit_content(event):
            canvas.itemconfigure(window_id, width=event.width)

        def fit_nav(_event=None):
            nav_canvas.configure(scrollregion=nav_canvas.bbox("all"))
            nav_canvas.itemconfigure(nav_window, width=nav_canvas.winfo_width())

        def on_mousewheel(event):
            target = nav_canvas if self.is_child_of(event.widget, side) else canvas
            if event.delta:
                target.yview_scroll(int(-1 * (event.delta / 120)), "units")
                self.after_idle(self.update_current_question_from_scroll)
            return "break"

        content.bind("<Configure>", update_scroll_region)
        canvas.bind("<Configure>", fit_content)
        canvas.bind_all("<MouseWheel>", on_mousewheel)
        nav_frame.bind("<Configure>", fit_nav)
        nav_canvas.bind("<Configure>", fit_nav)

        for index, question in enumerate(self.active_test["questions"]):
            self.render_question_card(content, index, question)
            row = index // 5
            column = index % 5
            button = tk.Button(
                nav_frame,
                text=str(index + 1),
                width=4,
                height=2,
                relief="flat",
                font=("Segoe UI", 10, "bold"),
                command=lambda index=index: self.scroll_to_question(index),
            )
            button.grid(row=row, column=column, padx=4, pady=4, sticky="nsew")
            self.question_nav_buttons[index] = button

        self.update_exam_progress()
        self.update_timer_display()
        self.after(80, lambda: self.scroll_to_question(self.current_question_index))

    def render_question_card(self, parent, index, question):
        outer, box = self.card(parent, padding=24)
        outer.pack(fill="x", pady=(0, 16))
        self.question_cards[index] = outer

        title = ttk.Frame(box, style="Card.TFrame")
        title.pack(fill="x", pady=(0, 14))
        ttk.Label(title, text=f"Вопрос {index + 1}", style="Header.TLabel").pack(side="left")
        status_label = ttk.Label(title, text="не отвечен" if index not in self.answers else "отвечен", style="Muted.TLabel")
        status_label.pack(side="right")
        self.question_status_labels[index] = status_label
        ttk.Label(box, text=question["text"], style="Question.TLabel", wraplength=820).pack(anchor="w", pady=(0, 18))

        self.answer_widgets[index] = []
        selected = self.answers.get(index, -1)
        for answer_index, answer in enumerate(question["answers"]):
            border = tk.Frame(box, bg=COLORS["primary"] if selected == answer_index else COLORS["line"])
            border.pack(fill="x", pady=5)
            button = tk.Button(
                border,
                text=f"{answer_index + 1}. {answer}",
                anchor="w",
                justify="left",
                bg=COLORS["primary_soft"] if selected == answer_index else COLORS["surface"],
                fg=COLORS["text"],
                activebackground=COLORS["primary_soft"],
                relief="flat",
                padx=16,
                pady=12,
                font=("Segoe UI", 12),
                command=lambda index=index, answer_index=answer_index: self.choose_answer(index, answer_index),
                wraplength=800,
            )
            button.pack(fill="x", padx=1, pady=1)
            self.answer_widgets[index].append((border, button))

    def choose_answer(self, question_index, answer_index):
        self.answers[question_index] = answer_index
        self.current_question_index = question_index
        self.update_answer_styles(question_index)
        self.update_exam_progress()

    def update_answer_styles(self, question_index):
        selected = self.answers.get(question_index, -1)
        for answer_index, (border, button) in enumerate(self.answer_widgets.get(question_index, [])):
            is_selected = answer_index == selected
            border.configure(bg=COLORS["primary"] if is_selected else COLORS["line"])
            button.configure(bg=COLORS["primary_soft"] if is_selected else COLORS["surface"])

    def update_exam_progress(self):
        total = len(self.active_test["questions"]) if self.active_test else 0
        answered = len(self.answers)
        if self.progress_label:
            self.progress_label.configure(text=f"Отвечено {answered} из {total}")
        if self.progress_bar:
            self.progress_bar.configure(maximum=total, value=answered)
        for index, label in self.question_status_labels.items():
            label.configure(text="отвечен" if index in self.answers else "не отвечен")
        for index, button in self.question_nav_buttons.items():
            answered_color = COLORS["success_soft"] if index in self.answers else COLORS["surface_alt"]
            border_color = COLORS["success"] if index in self.answers else COLORS["line"]
            if index == self.current_question_index:
                answered_color = COLORS["primary_soft"]
                border_color = COLORS["primary"]
            button.configure(bg=answered_color, fg=border_color, activebackground=answered_color)

    def update_timer_display(self):
        if not self.timer_label:
            return
        color = COLORS["danger"] if self.remaining_seconds <= 60 else COLORS["primary"]
        self.timer_label.configure(text=self.format_time(self.remaining_seconds), foreground=color)

    def scroll_to_question(self, index):
        if not self.exam_canvas or index not in self.question_cards:
            return
        self.current_question_index = max(0, min(index, len(self.active_test["questions"]) - 1))
        self.exam_canvas.update_idletasks()
        card = self.question_cards[self.current_question_index]
        bbox = self.exam_canvas.bbox("all")
        if bbox:
            total_height = max(1, bbox[3] - bbox[1])
            y = max(0, card.winfo_y() - 10)
            self.exam_canvas.yview_moveto(min(1, y / total_height))
        self.update_exam_progress()

    def update_current_question_from_scroll(self):
        if not self.exam_canvas or not self.question_cards:
            return
        top = self.exam_canvas.canvasy(0)
        closest = min(self.question_cards, key=lambda index: abs(self.question_cards[index].winfo_y() - top))
        if closest != self.current_question_index:
            self.current_question_index = closest
            self.update_exam_progress()

    def is_child_of(self, widget, parent):
        while widget:
            if widget == parent:
                return True
            widget = widget.master
        return False

    def request_finish_test(self):
        if not self.active_test:
            return
        total = len(self.active_test["questions"])
        answered = len(self.answers)
        unanswered = total - answered
        message = (
            "Вы уверены, что хотите завершить тест?\n\n"
            f"Всего вопросов: {total}\n"
            f"Отвечено вопросов: {answered}\n"
            f"Не отвечено вопросов: {unanswered}\n\n"
            "Неотвеченные вопросы будут засчитаны как неправильные."
        )
        self.exam_dialog_active = True
        if self.focus_job:
            try:
                self.after_cancel(self.focus_job)
            except tk.TclError:
                pass
            self.focus_job = None
        try:
            should_finish = messagebox.askyesno("Завершить тест", message)
        finally:
            self.exam_dialog_active = False
        if should_finish:
            self.finish_test(reason="manual")
        elif self.exam_active and not self.locked:
            self.lift()
            self.focus_force()
            self.schedule_focus_guard()

    def finish_test(self, reason="manual", auto=None):
        if auto is not None:
            reason = "timeout" if auto else "manual"
        if self.test_finished or not self.active_test:
            return
        self.test_finished = True
        if self.timer_job:
            try:
                self.after_cancel(self.timer_job)
            except tk.TclError:
                pass
            self.timer_job = None
        total = len(self.active_test["questions"])
        correct = sum(
            1
            for index, question in enumerate(self.active_test["questions"])
            if self.answers.get(index) == question["correct_index"]
        )
        score = round(correct / total * 100) if total else 0
        passed = score >= self.active_test["pass_score"]
        database.save_result(self.user["id"], self.active_test["id"], correct, total, score, passed)
        test_title = self.active_test["title"]
        self.exit_exam_mode()
        if reason == "timeout":
            messagebox.showinfo("Время истекло", "Время истекло. Тест автоматически завершён.")
        self.show_result_card(test_title, correct, total, score, passed, reason)

    def show_result_card(self, test_title, correct, total, score, passed, reason="manual"):
        root = self.shell("Результат теста", test_title, show_logout=False)
        outer, box = self.card(root, padding=34)
        outer.pack(fill="both", expand=True)

        status_color = COLORS["success"] if passed else COLORS["danger"]
        status_soft = COLORS["success_soft"] if passed else COLORS["danger_soft"]
        ttk.Label(box, text="Сдано" if passed else "Не сдано", style="Hero.TLabel").pack(anchor="w")
        ttk.Label(box, text="Время вышло, тест завершен автоматически." if reason == "timeout" else "Тест завершен. Результат сохранен.", style="Muted.TLabel").pack(anchor="w", pady=(8, 26))

        badge = tk.Frame(box, bg=status_soft)
        badge.pack(fill="x", pady=(0, 24))
        tk.Label(badge, text=f"{score}%", bg=status_soft, fg=status_color, font=("Segoe UI", 42, "bold"), padx=18, pady=18).pack(side="left")
        tk.Label(badge, text=f"Правильных ответов: {correct} из {total}\nПроходной балл: {self.active_test['pass_score']}%", bg=status_soft, fg=COLORS["text"], font=("Segoe UI", 13), justify="left", padx=18).pack(side="left")

        ttk.Button(box, text="Вернуться к тестам", style="Primary.TButton", command=self.show_tests).pack(anchor="e")
        self.active_test = None

    def show_results(self):
        root = self.shell("История результатов", f"Пользователь: {self.user['username']}")
        outer, box = self.card(root, padding=16)
        outer.pack(fill="both", expand=True)
        columns = ("date", "user", "test", "correct", "score", "status")
        table = ttk.Treeview(box, columns=columns, show="headings")
        for column, title in zip(columns, ("Дата", "Пользователь", "Тест", "Правильно", "Балл", "Статус")):
            table.heading(column, text=title)
        table.column("date", width=160)
        table.column("user", width=150)
        table.column("test", width=320)
        table.column("correct", width=100, anchor="center")
        table.column("score", width=100, anchor="center")
        table.column("status", width=110, anchor="center")
        table.pack(fill="both", expand=True)
        for row in database.list_results():
            table.insert("", "end", values=(row["created_at"], row["username"], row["title"], f"{row['correct']}/{row['total']}", f"{row['score']}%", "Сдано" if row["passed"] else "Не сдано"))
        ttk.Button(root, text="Назад", style="Ghost.TButton", command=self.show_tests).pack(anchor="e", pady=(14, 0))

    def show_test_management(self):
        root = self.scrollable_page()
        top = ttk.Frame(root, style="Page.TFrame")
        top.pack(fill="x", pady=(0, 18))
        left = ttk.Frame(top, style="Page.TFrame")
        left.pack(side="left")
        ttk.Label(left, text="Управление тестами", style="Title.TLabel").pack(anchor="w")
        ttk.Label(left, text="Открывайте, редактируйте и удаляйте созданные тесты", foreground=COLORS["muted"], background=COLORS["bg"]).pack(anchor="w", pady=(4, 0))
        ttk.Button(top, text="Назад", style="Ghost.TButton", command=self.show_tests).pack(side="right")
        ttk.Button(top, text="Создать тест", style="Primary.TButton", command=self.show_admin).pack(side="right", padx=(0, 8))

        tests = database.list_tests()
        if not tests:
            outer, box = self.card(root, padding=22)
            outer.pack(fill="x")
            ttk.Label(box, text="Тестов пока нет", style="Header.TLabel").pack(anchor="w")
            return

        def delete_existing_test(test_id, title):
            message = f"Вы уверены, что хотите удалить тест «{title}»?\n\nЭто действие нельзя отменить."
            if not messagebox.askyesno("Удалить тест", message):
                return
            try:
                database.delete_test(test_id)
            except Exception as exc:
                messagebox.showerror("Ошибка", str(exc))
                return
            messagebox.showinfo("Готово", "Тест успешно удалён.")
            self.show_test_management()

        for test in tests:
            outer, box = self.card(root, padding=20)
            outer.pack(fill="x", pady=(0, 12))
            header = ttk.Frame(box, style="Card.TFrame")
            header.pack(fill="x")
            ttk.Label(header, text=test["title"], style="Header.TLabel").pack(side="left")
            ttk.Label(header, text=test.get("created_at", ""), style="Muted.TLabel").pack(side="right")
            ttk.Label(box, text=test["description"] or "Описание не указано", style="Muted.TLabel", wraplength=860).pack(anchor="w", pady=(6, 12))
            metrics = ttk.Frame(box, style="Card.TFrame")
            metrics.pack(fill="x", pady=(0, 14))
            for label, value in (
                ("Всего вопросов", test["question_count"]),
                ("На экзамене", test["exam_questions_count"]),
                ("Проходной балл", f"{test['pass_score']}%"),
                ("Время", self.format_time(self.duration_for_test(test))),
            ):
                block = ttk.Frame(metrics, style="Card.TFrame")
                block.pack(side="left", padx=(0, 26))
                ttk.Label(block, text=str(value), style="Metric.TLabel").pack(anchor="w")
                ttk.Label(block, text=label, style="Muted.TLabel").pack(anchor="w")

            actions = ttk.Frame(box, style="Card.TFrame")
            actions.pack(fill="x")
            ttk.Button(actions, text="Открыть", style="Primary.TButton", command=lambda test_id=test["id"]: self.show_test_intro(test_id)).pack(side="left")
            ttk.Button(actions, text="Редактировать", style="Ghost.TButton", command=lambda test_id=test["id"]: self.show_admin(test_id)).pack(side="left", padx=8)
            ttk.Button(actions, text="Удалить", style="Danger.TButton", command=lambda test_id=test["id"], title=test["title"]: delete_existing_test(test_id, title)).pack(side="right")

    def show_admin(self, edit_test_id=None):
        edit_test = database.get_test(edit_test_id) if edit_test_id else None
        if edit_test_id and not edit_test:
            messagebox.showerror("Ошибка", "Тест не найден.")
            self.show_test_management()
            return
        root = self.scrollable_page()
        top = ttk.Frame(root, style="Page.TFrame")
        top.pack(fill="x", pady=(0, 18))
        left = ttk.Frame(top, style="Page.TFrame")
        left.pack(side="left")
        ttk.Label(left, text="Редактировать тест" if edit_test else "Создать тест", style="Title.TLabel").pack(anchor="w")
        ttk.Label(
            left,
            text="Измените данные теста, импортируйте вопросы или добавьте их вручную, затем сохраните изменения" if edit_test else "Импортируйте вопросы или добавьте их вручную, проверьте список и только потом сохраните тест",
            foreground=COLORS["muted"],
            background=COLORS["bg"],
        ).pack(anchor="w", pady=(4, 0))
        ttk.Button(top, text="К списку тестов", style="Ghost.TButton", command=self.show_test_management if edit_test else self.show_tests).pack(side="right")

        questions = [
            {
                "text": question["text"],
                "answers": list(question["answers"]),
                "correct_index": int(question["correct_index"]),
            }
            for question in (edit_test["questions"] if edit_test else [])
        ]
        selected_index = {"value": None}
        question_cards = {"frame": None}
        question_page = {"value": 0}
        page_size = 50
        question_search = tk.StringVar(value="")
        import_status = tk.StringVar(value="Вопросы еще не импортированы")
        editor_mode = tk.StringVar(value="Добавить вопрос")
        shuffle_questions = tk.BooleanVar(value=True)
        shuffle_answers = tk.BooleanVar(value=False)

        info_outer, info = self.card(root, padding=22)
        info_outer.pack(fill="x", pady=(0, 14))
        ttk.Label(info, text="Основная информация", style="Header.TLabel").pack(anchor="w", pady=(0, 12))

        form = ttk.Frame(info, style="Card.TFrame")
        form.pack(fill="x")
        form.columnconfigure(1, weight=1)
        form.columnconfigure(3, weight=1)

        ttk.Label(form, text="Название теста", style="Card.TLabel").grid(row=0, column=0, sticky="w", padx=(0, 10), pady=(0, 8))
        title = ttk.Entry(form)
        title.grid(row=0, column=1, columnspan=3, sticky="ew", pady=(0, 8))

        ttk.Label(form, text="Описание", style="Card.TLabel").grid(row=1, column=0, sticky="w", padx=(0, 10), pady=(0, 8))
        description = ttk.Entry(form)
        description.grid(row=1, column=1, columnspan=3, sticky="ew", pady=(0, 8))

        ttk.Label(form, text="Проходной балл, %", style="Card.TLabel").grid(row=2, column=0, sticky="w", padx=(0, 10))
        pass_score = ttk.Spinbox(form, from_=1, to=100, width=8)
        pass_score.set(60)
        pass_score.grid(row=2, column=1, sticky="w")

        ttk.Label(form, text="Время прохождения, минут", style="Card.TLabel").grid(row=2, column=2, sticky="w", padx=(24, 10))
        duration_minutes = ttk.Spinbox(form, from_=1, to=300, width=8)
        duration_minutes.set(10)
        duration_minutes.grid(row=2, column=3, sticky="w")

        ttk.Label(form, text="Вопросов на экзамене", style="Card.TLabel").grid(row=3, column=0, sticky="w", padx=(0, 10), pady=(10, 0))
        exam_questions_count = ttk.Spinbox(form, from_=1, to=1, width=8)
        exam_questions_count.set(1)
        exam_questions_count.grid(row=3, column=1, sticky="w", pady=(10, 0))
        ttk.Checkbutton(form, text="Перемешивать вопросы", variable=shuffle_questions).grid(row=3, column=2, columnspan=2, sticky="w", padx=(24, 0), pady=(10, 0))
        ttk.Checkbutton(form, text="Перемешивать ответы", variable=shuffle_answers).grid(row=4, column=2, columnspan=2, sticky="w", padx=(24, 0), pady=(8, 0))
        if edit_test:
            title.insert(0, edit_test["title"])
            description.insert(0, edit_test["description"] or "")
            pass_score.set(int(edit_test["pass_score"]))
            duration_minutes.set(max(1, int(edit_test.get("duration_seconds") or 60) // 60))
            exam_questions_count.configure(to=max(1, len(questions)))
            exam_questions_count.set(int(edit_test.get("exam_questions_count") or len(questions) or 1))
            shuffle_questions.set(bool(edit_test.get("shuffle_questions", 1)))
            shuffle_answers.set(bool(edit_test.get("shuffle_answers", 0)))
            import_status.set(f"Загружен существующий тест. Вопросов: {len(questions)}")

        import_outer, import_box = self.card(root, padding=22)
        import_outer.pack(fill="x", pady=(0, 14))
        import_header = ttk.Frame(import_box, style="Card.TFrame")
        import_header.pack(fill="x")
        ttk.Label(import_header, text="Импорт", style="Header.TLabel").pack(side="left")
        ttk.Button(import_header, text="Импорт из файла", style="Primary.TButton", command=lambda: import_file()).pack(side="right")
        ttk.Label(import_box, textvariable=import_status, style="Muted.TLabel").pack(anchor="w", pady=(8, 0))

        list_outer, list_box = self.card(root, padding=22)
        list_outer.pack(fill="x", pady=(0, 14))
        list_header = ttk.Frame(list_box, style="Card.TFrame")
        list_header.pack(fill="x", pady=(0, 12))
        ttk.Label(list_header, text="Список вопросов", style="Header.TLabel").pack(side="left")
        question_count = ttk.Label(list_header, text="0 вопросов", style="Muted.TLabel")
        question_count.pack(side="right")
        pager = ttk.Frame(list_box, style="Card.TFrame")
        pager.pack(fill="x", pady=(0, 12))
        pager_label = ttk.Label(pager, text="", style="Muted.TLabel")
        pager_label.pack(side="left")
        pager_buttons = ttk.Frame(pager, style="Card.TFrame")
        pager_buttons.pack(side="right")
        search_row = ttk.Frame(list_box, style="Card.TFrame")
        search_row.pack(fill="x", pady=(0, 12))
        ttk.Label(search_row, text="Поиск", style="Card.TLabel").pack(side="left", padx=(0, 10))
        search_entry = ttk.Entry(search_row, textvariable=question_search)
        search_entry.pack(side="left", fill="x", expand=True)

        question_cards["frame"] = ttk.Frame(list_box, style="Card.TFrame")
        question_cards["frame"].pack(fill="x")

        editor_outer, editor = self.card(root, padding=22)
        editor_outer.pack(fill="x", pady=(0, 14))
        editor.columnconfigure(1, weight=1)
        ttk.Label(editor, textvariable=editor_mode, style="Header.TLabel").grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 12))

        ttk.Label(editor, text="Вопрос", style="Card.TLabel").grid(row=1, column=0, sticky="w", padx=(0, 10), pady=(0, 8))
        question_text = ttk.Entry(editor)
        question_text.grid(row=1, column=1, sticky="ew", pady=(0, 8))

        answer_entries = []
        for index in range(4):
            ttk.Label(editor, text=f"Ответ {index + 1}", style="Card.TLabel").grid(row=index + 2, column=0, sticky="w", padx=(0, 10), pady=4)
            entry = ttk.Entry(editor)
            entry.grid(row=index + 2, column=1, sticky="ew", pady=4)
            answer_entries.append(entry)

        ttk.Label(editor, text="Правильный ответ", style="Card.TLabel").grid(row=6, column=0, sticky="w", padx=(0, 10), pady=(10, 0))
        correct = ttk.Spinbox(editor, from_=1, to=4, width=8)
        correct.set(1)
        correct.grid(row=6, column=1, sticky="w", pady=(10, 0))

        editor_actions = ttk.Frame(editor, style="Card.TFrame")
        editor_actions.grid(row=7, column=0, columnspan=2, sticky="ew", pady=(18, 0))

        save_outer, save_box = self.card(root, padding=22)
        save_outer.pack(fill="x")
        save_actions = ttk.Frame(save_box, style="Card.TFrame")
        save_actions.pack(fill="x")
        ttk.Label(save_actions, text="Сохранение", style="Header.TLabel").pack(side="left")
        ttk.Button(save_actions, text="Сохранить изменения" if edit_test else "Сохранить тест", style="Primary.TButton", command=lambda: save_test()).pack(side="right")

        def normalize_question(item):
            text = (item.get("text") or item.get("question") or "").strip()
            answers = [str(answer).strip() for answer in item.get("answers", [])]
            correct_index = item.get("correct_index", item.get("correct", 0))
            return {"text": text, "answers": answers, "correct_index": int(correct_index)}

        def validate_question(item):
            if not item["text"]:
                raise ValueError("Нельзя добавить пустой вопрос.")
            if len(item["answers"]) != 4 or any(not answer for answer in item["answers"]):
                raise ValueError("У вопроса должны быть четыре заполненных варианта ответа.")
            if item["correct_index"] not in range(4):
                raise ValueError("Выберите правильный ответ от 1 до 4.")

        def sync_exam_question_limit(prefer_default=False):
            total = max(1, len(questions))
            exam_questions_count.configure(to=total)
            current = exam_questions_count.get().strip()
            if prefer_default or not current.isdigit() or int(current) > total:
                exam_questions_count.set(min(50, total))

        def refresh_cards():
            frame = question_cards["frame"]
            for child in frame.winfo_children():
                child.destroy()
            for child in pager_buttons.winfo_children():
                child.destroy()
            sync_exam_question_limit()
            question_count.configure(text=f"{len(questions)} вопросов")
            if not questions:
                pager_label.configure(text="")
                ttk.Label(frame, text="Пока нет вопросов. Импортируйте файл или добавьте вопрос вручную.", style="Muted.TLabel").pack(anchor="w")
                return

            query = question_search.get().strip().lower()
            if query:
                visible_indices = [
                    index
                    for index, question in enumerate(questions)
                    if query in question["text"].lower() or any(query in answer.lower() for answer in question["answers"])
                ]
            else:
                visible_indices = list(range(len(questions)))
            if not visible_indices:
                pager_label.configure(text=f"Найдено 0 из {len(questions)}. На экзамене будет: {exam_questions_count.get()}")
                ttk.Label(frame, text="По этому запросу вопросов не найдено.", style="Muted.TLabel").pack(anchor="w")
                return

            total_pages = max(1, (len(visible_indices) + page_size - 1) // page_size)
            question_page["value"] = max(0, min(question_page["value"], total_pages - 1))
            start = question_page["value"] * page_size
            page_indices = visible_indices[start:start + page_size]
            end = start + len(page_indices)
            found_text = f"Найдено {len(visible_indices)} из {len(questions)}" if query else f"Всего {len(questions)}"
            pager_label.configure(text=f"Показаны {start + 1}-{end}. {found_text}. На экзамене будет: {exam_questions_count.get()}")
            ttk.Button(
                pager_buttons,
                text="Назад",
                style="Ghost.TButton",
                command=lambda: change_page(-1),
                state="normal" if question_page["value"] > 0 else "disabled",
            ).pack(side="left", padx=(0, 8))
            ttk.Button(
                pager_buttons,
                text="Далее",
                style="Ghost.TButton",
                command=lambda: change_page(1),
                state="normal" if question_page["value"] < total_pages - 1 else "disabled",
            ).pack(side="left")

            for index in page_indices:
                question = questions[index]
                border = tk.Frame(frame, bg=COLORS["line"])
                border.pack(fill="x", pady=(0, 10))
                card = ttk.Frame(border, style="Card.TFrame", padding=14)
                card.pack(fill="x", padx=1, pady=1)
                card.columnconfigure(0, weight=1)

                title_text = f"{index + 1}. {question['text']}"
                ttk.Label(card, text=title_text, style="Card.TLabel", wraplength=900, font=("Segoe UI", 11, "bold")).grid(row=0, column=0, sticky="ew")

                answer_lines = []
                for answer_index, answer in enumerate(question["answers"]):
                    marker = "(верно)" if answer_index == question["correct_index"] else ""
                    answer_lines.append(f"{answer_index + 1}. {answer} {marker}".strip())
                ttk.Label(card, text="\n".join(answer_lines), style="Muted.TLabel", wraplength=860, justify="left").grid(row=1, column=0, sticky="ew", pady=(8, 0))

                buttons = ttk.Frame(card, style="Card.TFrame")
                buttons.grid(row=0, column=1, rowspan=2, sticky="ne", padx=(14, 0))
                ttk.Button(buttons, text="Редактировать", style="Ghost.TButton", command=lambda i=index: load_question(i)).pack(fill="x", pady=(0, 6))
                ttk.Button(buttons, text="Удалить", style="Danger.TButton", command=lambda i=index: delete_question(i)).pack(fill="x")

        def change_page(delta):
            question_page["value"] += delta
            refresh_cards()

        def search_questions(_event=None):
            question_page["value"] = 0
            refresh_cards()

        def clear_editor():
            selected_index["value"] = None
            editor_mode.set("Добавить вопрос")
            question_text.delete(0, "end")
            for entry in answer_entries:
                entry.delete(0, "end")
            correct.set(1)
            question_text.focus_set()

        def collect_editor_question():
            raw_correct = correct.get().strip()
            if not raw_correct.isdigit():
                raise ValueError("Выберите правильный ответ от 1 до 4.")
            item = {
                "text": question_text.get().strip(),
                "answers": [entry.get().strip() for entry in answer_entries],
                "correct_index": int(raw_correct) - 1,
            }
            validate_question(item)
            return item

        def load_question(index):
            selected_index["value"] = index
            editor_mode.set("Сохранить изменения")
            question = questions[index]
            question_text.delete(0, "end")
            question_text.insert(0, question["text"])
            for entry, answer in zip(answer_entries, question["answers"]):
                entry.delete(0, "end")
                entry.insert(0, answer)
            correct.set(int(question["correct_index"]) + 1)
            question_text.focus_set()

        def add_or_update_question():
            try:
                item = collect_editor_question()
            except ValueError as exc:
                messagebox.showerror("Ошибка", str(exc))
                return
            if selected_index["value"] is None:
                questions.append(item)
            else:
                questions[selected_index["value"]] = item
            refresh_cards()
            clear_editor()

        def delete_question(index):
            if index < 0 or index >= len(questions):
                return
            del questions[index]
            refresh_cards()
            clear_editor()

        def import_file():
            file_path = filedialog.askopenfilename(
                title="Импорт теста",
                filetypes=(
                    ("Файлы тестов", "*.txt *.xlsx"),
                    ("Текстовые файлы", "*.txt"),
                    ("Excel файлы", "*.xlsx"),
                    ("Все файлы", "*.*"),
                ),
            )
            if not file_path:
                return
            try:
                import_result = importer.import_questions_with_report(file_path)
                imported_questions = [normalize_question(item) for item in import_result.questions]
                for item in imported_questions:
                    validate_question(item)
            except Exception as exc:
                messagebox.showerror("Ошибка импорта", str(exc))
                return

            source = Path(file_path)
            if not title.get().strip():
                title.insert(0, source.stem)
            if not description.get().strip():
                description.insert(0, f"Импортировано из файла {source.name}")
            questions.extend(imported_questions)
            question_page["value"] = max(0, (len(questions) - 1) // page_size)
            sync_exam_question_limit(prefer_default=True)
            refresh_cards()
            report = import_result.report
            error_preview = "\n".join(report.errors[:5])
            status = (
                f"Импорт завершён. Найдено строк: {report.found_rows}. "
                f"Импортировано: {report.imported_count}. Пропущено: {report.skipped_count}."
            )
            if error_preview:
                status += f"\nОшибки:\n{error_preview}"
            import_status.set(status)
            if imported_questions:
                load_question(len(questions) - len(imported_questions))
            messagebox.showinfo("Импорт завершён", status)

        def validate_test_settings():
            title_text = title.get().strip()
            if not title_text:
                raise ValueError("Название теста не может быть пустым.")
            try:
                score = int(pass_score.get())
            except ValueError as exc:
                raise ValueError("Проходной балл должен быть числом от 1 до 100.") from exc
            if score < 1 or score > 100:
                raise ValueError("Проходной балл должен быть от 1 до 100.")
            try:
                minutes = int(duration_minutes.get())
            except ValueError as exc:
                raise ValueError("Время прохождения должно быть числом минут.") from exc
            if minutes < 1 or minutes > 300:
                raise ValueError("Время прохождения должно быть от 1 до 300 минут.")
            if not questions:
                raise ValueError("Добавьте хотя бы один вопрос.")
            raw_exam_count = exam_questions_count.get().strip()
            if not raw_exam_count:
                raise ValueError("Количество вопросов на экзамене не может быть пустым.")
            try:
                exam_count = int(raw_exam_count)
            except ValueError as exc:
                raise ValueError("Количество вопросов на экзамене должно быть числом.") from exc
            if exam_count < 1:
                raise ValueError("Количество вопросов на экзамене должно быть больше 0.")
            if exam_count > len(questions):
                raise ValueError("Количество вопросов на экзамене не может быть больше общего количества вопросов.")
            for index, question in enumerate(questions, start=1):
                try:
                    validate_question(question)
                except ValueError as exc:
                    raise ValueError(f"Вопрос {index}: {exc}") from exc
            return title_text, description.get().strip(), score, minutes * 60, exam_count, shuffle_questions.get(), shuffle_answers.get()

        def save_test():
            try:
                title_text, description_text, score, duration_seconds, exam_count, should_shuffle, should_shuffle_answers = validate_test_settings()
                if edit_test:
                    database.update_test(edit_test["id"], title_text, description_text, score, questions, duration_seconds, exam_count, should_shuffle, should_shuffle_answers)
                else:
                    database.create_test(title_text, description_text, score, questions, duration_seconds, exam_count, should_shuffle, should_shuffle_answers)
            except Exception as exc:
                messagebox.showerror("Ошибка", str(exc))
                return
            messagebox.showinfo("Готово", f"Тест сохранен. Всего вопросов: {len(questions)}. На экзамене: {exam_count}")
            self.show_test_management() if edit_test else self.show_tests()

        ttk.Button(editor_actions, text="Добавить вопрос", style="Primary.TButton", command=add_or_update_question).pack(side="left")
        ttk.Button(editor_actions, text="Новый вопрос", style="Ghost.TButton", command=clear_editor).pack(side="left", padx=(10, 0))
        search_entry.bind("<KeyRelease>", search_questions)
        refresh_cards()

    @staticmethod
    def format_time(seconds):
        minutes, seconds = divmod(max(0, int(seconds)), 60)
        hours, minutes = divmod(minutes, 60)
        if hours:
            return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
        return f"{minutes:02d}:{seconds:02d}"


if __name__ == "__main__":
    DesktopApp().mainloop()
