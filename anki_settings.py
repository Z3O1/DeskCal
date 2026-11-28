# SPDX-License-Identifier: AGPL-3.0-or-later
"""Anki account/deck controls inside DeskCal's original gear settings panel."""
import json
import os
import tkinter as tk
from tkinter import messagebox, ttk


class AnkiSettings:
    def __init__(self, tab, parent):
        self.tab, self.app, self.d = tab, tab.app, tab.d
        self.frame = tk.Frame(parent, bg=self.d.CARD)
        self.frame.pack(fill='x', pady=(self.app.px(10), self.app.px(8)))
        self.body = None
        self.signature = None
        self.controls = []
        self.status = tk.StringVar(master=self.app)
        self.password = None
        self.render()

    def alive(self):
        try:
            return bool(self.frame.winfo_exists())
        except tk.TclError:
            return False

    def label(self, text, muted=False, bold=False):
        label = tk.Label(self.body, text=text, bg=self.d.CARD,
                         fg=self.d.MUTED if muted else self.d.FG,
                         font=self.app.f(10 if muted else 11, bold), anchor='w', justify='left',
                         wraplength=max(80, self.app.panel_w-self.app.px(24)))
        label.pack(fill='x', pady=(self.app.px(3), self.app.px(3)))
        return label

    def button(self, text, command, kind='normal'):
        button = tk.Button(self.body, text=text, command=command, relief='flat', bd=0,
                           highlightthickness=0, anchor='w', cursor='hand2',
                           bg=self.d.SEL_BG if kind == 'primary' else self.d.SUNK,
                           fg=self.d.FG, activebackground=self.d.LINE, activeforeground=self.d.FG,
                           disabledforeground=self.d.MUTED, font=self.app.f(11),
                           padx=self.app.px(8), pady=self.app.px(5), wraplength=max(80,self.app.panel_w-self.app.px(35)))
        button.pack(fill='x', pady=self.app.px(3))
        self.controls.append((button, kind))
        return button

    def render(self):
        if not self.alive():
            return
        state = self.tab.state or {}
        sync = state.get('sync', {})
        fingerprint = json.dumps([bool(self.tab.session), state.get('decks'), state.get('selectedDeck'),
                                  sync, self.tab.syncing, self.tab.library_error], sort_keys=True)
        if fingerprint != self.signature:
            self.signature = fingerprint
            if self.password is not None:
                self.password.set('')
            if self.body is not None:
                self.body.destroy()
            self.controls = []
            self.body = tk.Frame(self.frame, bg=self.d.CARD)
            self.body.pack(fill='x')
            self.label('Anki · 账户与牌组', bold=True)
            if self.tab.session is None:
                self.label(self.tab.library_error or '正在读取内置牌库…', muted=True)
                self.button('重新读取内置牌库', self.tab.load_library)
            else:
                self.label('仅操作 DeskCal 独立牌库。同步的是账号的全部牌组，不只是当前选择的牌组。', muted=True)
                if sync.get('signedIn'):
                    self.label('AnkiWeb：' + sync.get('username', ''))
                    self.label('已使用 Windows 加密保存登录' if sync.get('remembered') else '本次登录仅在当前进程内有效', muted=True)
                    self.button('立即同步牌库和媒体', self.tab.start_sync, 'primary')
                    self.button('退出本机登录', self.tab.sign_out)
                else:
                    self.label('AnkiWeb 邮箱', muted=True)
                    self.email = tk.StringVar(master=self.app, value=sync.get('boundAccount', ''))
                    email = tk.Entry(self.body, textvariable=self.email, font=self.app.f(11),
                                     bg=self.d.SUNK, fg=self.d.FG, insertbackground=self.d.FG,
                                     relief='flat', borderwidth=4)
                    email.pack(fill='x')
                    self.controls.append((email, 'normal'))
                    self.label('密码（不会保存）', muted=True)
                    self.password = tk.StringVar(master=self.app)
                    password = tk.Entry(self.body, textvariable=self.password, show='●', font=self.app.f(11),
                                        bg=self.d.SUNK, fg=self.d.FG, insertbackground=self.d.FG,
                                        relief='flat', borderwidth=4)
                    password.pack(fill='x')
                    self.controls.append((password, 'normal'))
                    password.bind('<Return>', lambda event: self.sign_in())
                    self.remember = tk.BooleanVar(master=self.app, value=os.name == 'nt')
                    remember = tk.Checkbutton(self.body, text='记住登录（Windows 加密令牌）',
                                               variable=self.remember, bg=self.d.CARD, fg=self.d.FG,
                                               activebackground=self.d.CARD, activeforeground=self.d.FG,
                                               selectcolor=self.d.SUNK, font=self.app.f(10), anchor='w')
                    remember.pack(fill='x', pady=self.app.px(4))
                    self.controls.append((remember, 'normal'))
                    self.button('登录 AnkiWeb', self.sign_in, 'primary')
                    self.label('登录本身不会上传或下载数据。', muted=True)
                if sync.get('warning'):
                    self.label(sync['warning'], muted=True)
                if sync.get('lastSync'):
                    self.label('上次完整同步：' + sync['lastSync'], muted=True)
                if self.tab.syncing:
                    self.button('取消正在进行的同步', self.tab.cancel_sync, 'cancel')
                pending = sync.get('pending')
                if pending:
                    self.label('需要全量同步：请选择保留哪一端。覆盖不是合并，取消不会执行覆盖。', bold=True)
                    if 'download' in pending['allowed']:
                        self.button('从 AnkiWeb 下载（覆盖 DeskCal）', lambda: self.confirm_full('download'), 'full')
                    if 'upload' in pending['allowed']:
                        self.button('上传 DeskCal（覆盖 AnkiWeb）', lambda: self.confirm_full('upload'), 'full')
                    self.button('取消本次全量同步', self.tab.cancel_pending_sync, 'full')
                self.label('学习牌组', bold=True)
                self.decks = list(state.get('decks', []))
                self.deck = ttk.Combobox(self.body, state='readonly',
                                         values=[deck['name'] for deck in self.decks], font=self.app.f(11))
                self.deck.pack(fill='x', pady=self.app.px(4))
                selected = next((i for i, deck in enumerate(self.decks)
                                 if deck['id'] == state.get('selectedDeck')), None)
                if selected is not None:
                    self.deck.current(selected)
                self.deck.bind('<<ComboboxSelected>>', self.select_deck)
                self.controls.append((self.deck, 'deck'))
                self.button('导入牌组 (.apkg)…', self.tab.import_package, 'library')
                self.button('导出全部牌组和学习进度…', self.tab.export_package, 'library')
                self.label('AnkiWeb 的变更会在其他客户端下次同步时生效。退出登录不删除本地牌库。', muted=True)
            status = self.label('', muted=True)
            status.configure(textvariable=self.status)
            tk.Frame(self.body, bg=self.d.LINE, height=1).pack(fill='x', pady=self.app.px(10))
        self.status.set(self.tab.sync_status_text or (state.get('notice') or ''))
        pending = bool(sync.get('pending'))
        for widget, kind in self.controls:
            enabled = not self.tab.busy and (not pending or kind in ('full', 'normal'))
            if kind == 'cancel':
                enabled = self.tab.syncing
            if kind == 'primary' and pending:
                enabled = False
            widget.configure(state=('readonly' if kind == 'deck' else 'normal') if enabled else 'disabled')

    def sign_in(self):
        if self.tab.busy or self.tab.session is None:
            return
        username, password = self.email.get().strip(), self.password.get()
        if not username or not password:
            self.tab.sync_status_text = '请输入 AnkiWeb 邮箱和密码'
            self.render()
            return
        bound = (self.tab.state or {}).get('sync', {}).get('boundAccount', '')
        changed = bool(bound and bound.casefold() != username.casefold())
        if changed and not messagebox.askokcancel('更换 AnkiWeb 账号',
                '此内置牌库曾用于 %s。\n\n更换账号后将要求重新选择全量同步方向，可能覆盖本地或另一账号的云端牌库。\n是否继续登录 %s？' % (bound, username),
                parent=self.app, default='cancel'):
            return
        self.password.set('')
        self.tab.sign_in(username, password, self.remember.get(), changed)

    def select_deck(self, event=None):
        if self.tab.busy:
            return
        index = self.deck.current()
        if 0 <= index < len(self.decks):
            self.tab.select_deck(self.decks[index]['id'])

    def confirm_full(self, direction):
        pending = (self.tab.state or {}).get('sync', {}).get('pending')
        if not pending or self.tab.busy or direction not in pending['allowed']:
            return
        if direction == 'upload':
            text = ('将用 DeskCal 的全部牌库覆盖 AnkiWeb，云端独有的卡片和学习进度可能丢失。'
                    '\n\n这也会影响手机和其他客户端的后续同步。建议先在其他客户端完成同步并备份。\n\n确定上传覆盖吗？')
        else:
            text = ('将用 AnkiWeb 的全部牌库覆盖 DeskCal，内置牌库独有的卡片和学习进度可能丢失。'
                    '\n\n操作前会备份本地牌库；自动备份不包含媒体，媒体仍按 Anki 的正常双向规则同步。\n\n确定下载覆盖吗？')
        if messagebox.askokcancel('确认全量同步方向', text, parent=self.app, default='cancel', icon='warning'):
            self.tab.continue_full_sync(pending['token'], direction)
