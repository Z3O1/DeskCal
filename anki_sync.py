# SPDX-License-Identifier: AGPL-3.0-or-later
"""Official AnkiWeb sync for DeskCal's independent collection.

Login/collection/media operations execute on the collection worker. A monitor
uses ONLY the backend's documented thread-safe progress/abort RPCs, as Anki's Qt
client does; it never reads a database or mutates Python collection state.
"""
from contextlib import contextmanager
from datetime import datetime
import threading
import time
from urllib.parse import urlsplit
from uuid import uuid4

from anki_credentials import CredentialError, CredentialStore


class SyncProblem(Exception):
    pass


class AnkiSync:
    def __init__(self, core):
        self.core = core
        self.store = CredentialStore(core.directory)
        self.auth = None
        self.username = ''
        self.remembered = False
        self.warning = ''
        self.pending = None
        self.report = lambda text: None
        self.cancel = threading.Event()
        self.phase = ''

    @staticmethod
    def _endpoint(endpoint):
        if not endpoint:
            return None
        try:
            url = urlsplit(endpoint)
            host = (url.hostname or '').lower()
            valid = (url.scheme == 'https' and not url.username and not url.password
                     and url.port in (None, 443)
                     and (host == 'ankiweb.net' or host.endswith('.ankiweb.net')))
        except (TypeError, ValueError):
            valid = False
        if not valid:
            raise SyncProblem('AnkiWeb 返回的同步地址不受支持，已停止传递登录令牌')
        return endpoint

    def load(self):
        from anki.sync_pb2 import SyncAuth
        try:
            record = self.store.load()
            if record:
                endpoint = self._endpoint(record.get('endpoint'))
                username = record.get('username', '')
                if not isinstance(username, str):
                    raise SyncProblem('登录记录无效，请重新登录')
                self.auth = SyncAuth(hkey=record['hkey'], endpoint=endpoint, io_timeout_secs=30)
                self.username = username
                self.remembered = True
        except (CredentialError, SyncProblem) as error:
            self.warning = str(error)

    def public_state(self):
        pending = None
        if self.pending:
            pending = {'token': self.pending['token'], 'allowed': list(self.pending['allowed'])}
        return {'signedIn': self.auth is not None, 'username': self.username,
                'remembered': self.remembered, 'warning': self.warning, 'pending': pending,
                'boundAccount': self.core.settings.get('sync_account', ''),
                'lastSync': self.core.settings.get('last_sync', '')}

    def _persist_auth(self):
        if not self.remembered or self.auth is None:
            return
        try:
            self.remembered = self.store.save({'username': self.username, 'hkey': self.auth.hkey,
                                              'endpoint': self.auth.endpoint})
        except CredentialError as error:
            self.remembered = False
            self.warning = str(error)
            # An old encrypted token must not silently replace this session next launch.
            try:
                self.store.clear()
            except CredentialError:
                self.warning += '；旧登录文件也无法删除，请检查数据目录权限'

    def invalidate_pending(self):
        self.pending = None

    def prepare(self):
        """UI calls before enqueueing, so an early Cancel is never lost."""
        self.cancel.clear()

    def request_cancel(self):
        """Safe from UI thread; the monitor performs the native abort calls."""
        self.cancel.set()

    def _check_cancel(self):
        if self.cancel.is_set():
            raise SyncProblem('同步已取消')

    def _stage(self, text):
        self.phase = text
        self.report(text)

    @contextmanager
    def _operation(self, label):
        self._check_cancel()
        self._stage(label)
        backend = self.core.col._backend
        stop = threading.Event()

        def monitor():
            previous = None
            while not stop.wait(.2):
                try:
                    if self.cancel.is_set():
                        # Repeat until finished: a cancellation can precede native
                        # registration of the new network request's abort handle.
                        backend.abort_sync()
                        backend.abort_media_sync()
                        backend.set_wants_abort()
                        text = '正在取消同步…'
                    else:
                        progress = backend.latest_progress()
                        if self.phase == '正在同步媒体…':
                            text = None  # worker reports media-specific counters
                        elif progress.HasField('full_sync'):
                            p = progress.full_sync
                            text = '%s（%.1f / %.1f MiB）' % (self.phase, p.transferred/1048576, p.total/1048576)
                        elif progress.HasField('normal_sync'):
                            p = progress.normal_sync
                            text = ' · '.join(part for part in (p.stage, p.added, p.removed) if part)
                        else:
                            text = self.phase
                    if text and text != previous:
                        previous = text
                        self.report(text)
                except Exception:
                    # Progress is advisory; never expose native error context or keys.
                    pass

        thread = threading.Thread(target=monitor, name='anki-sync-progress', daemon=True)
        thread.start()
        failed = True
        try:
            yield
            failed = False
        finally:
            if failed or self.cancel.is_set():
                # A cancelled media wait can return before the monitor's next tick.
                # Stop and drain native background media before allowing study/close.
                try:
                    backend.abort_sync()
                    backend.abort_media_sync()
                    while self.core.col.media_sync_status().active:
                        time.sleep(.1)
                except Exception:
                    pass
            stop.set()
            thread.join()
            self.phase = ''

    def _response(self, error=''):
        try:
            library = self.core._result()
        except Exception:
            library = None
            error = (error + '；' if error else '') + '请重新读取内置牌库；未自动重试覆盖操作'
        return {'library': library, 'error': error}

    def _error(self, error, collection_done=False):
        from anki.errors import Interrupted, NetworkError, SyncError, SyncErrorKind
        if isinstance(error, SyncError) and error.kind == SyncErrorKind.AUTH:
            self.auth = None
            self.username = ''
            self.remembered = False
            try:
                self.store.clear()
            except CredentialError as removal:
                self.warning = str(removal)
            text = 'AnkiWeb 登录已失效或账号密码不正确，请重新登录'
        elif isinstance(error, Interrupted) or self.cancel.is_set():
            text = '同步已取消'
        elif isinstance(error, (SyncProblem, CredentialError)):
            text = str(error)
        elif isinstance(error, NetworkError):
            text = '网络连接失败，请检查网络后重试'
        elif isinstance(error, SyncError):
            text = 'AnkiWeb 拒绝此次同步，请稍后重试或检查客户端版本'
        else:
            text = '同步未完成（%s），请重试；未自动重试任何覆盖操作' % type(error).__name__
        if collection_done:
            text = '牌库已同步，但媒体尚未全部完成。' + text
        return text

    def sign_in(self, session, username, password, remember, allow_account_change=False):
        self.core._check(session)
        username = username.strip()
        if not username or not password:
            return self._response('请输入 AnkiWeb 邮箱和密码')
        bound = self.core.settings.get('sync_account', '')
        if bound and bound.casefold() != username.casefold() and not allow_account_change:
            return self._response('此牌库曾用于另一账号，请先确认更换账号')
        error = ''
        try:
            with self._operation('正在登录 AnkiWeb…'):
                auth = self.core.col.sync_login(username=username, password=password, endpoint=None)
                self._endpoint(auth.endpoint)
                self._check_cancel()
                # Login never starts a sync. A first/different account forces an
                # explicit full-sync decision instead of reusing another server's USNs.
                if not bound or bound.casefold() != username.casefold():
                    self._stage('正在备份内置牌库…')
                    self.core._backup(force=True)
                    self.core.col.mod_schema(check=False)
                self._check_cancel()
                self.core._reset()
                self.store.clear()
                self.auth, self.username = auth, username
                self.auth.io_timeout_secs = 30
                self.warning = ''
                self.remembered = bool(remember)
                self._persist_auth()
                self.core.settings['sync_account'] = username
                self.core._save_settings()
                self.core.notice = '登录成功；点击“立即同步”开始同步'
        except Exception as problem:
            error = self._error(problem)
        finally:
            # Python strings cannot promise secure erasure; do not retain a password
            # in instance state, settings, logs, queued results, or renderer messages.
            password = ''
        return self._response(error)

    def sign_out(self, session):
        self.core._check(session)
        try:
            self.store.clear()
        except CredentialError as error:
            return self._response(str(error))
        self.auth = None
        self.username = ''
        self.remembered = False
        self.warning = ''
        self.core._reset()
        self.core.notice = '已退出本机登录；内置牌库保留'
        return self._response()

    def _wait_media(self):
        self._stage('正在同步媒体…')
        while True:
            self._check_cancel()
            status = self.core.col.media_sync_status()
            if not status.active:
                return
            if status.HasField('progress'):
                p = status.progress
                self.report('媒体 · ' + ' · '.join(part for part in (p.checked, p.added, p.removed) if part))
            time.sleep(.2)

    def _finish(self):
        self.core.settings['last_sync'] = datetime.now().astimezone().isoformat(timespec='seconds')
        try:
            self.core._save_settings()
            self.core.notice = 'AnkiWeb 牌库与媒体同步完成'
        except OSError:
            self.core.notice = '牌库与媒体同步完成，但无法保存本机同步时间，请检查数据目录权限'

    def start(self, session):
        from anki.sync import SyncOutput
        self.core._check(session)
        if self.auth is None:
            return self._response('请先在设置中登录 AnkiWeb')
        self.core._reset()
        error, collection_done = '', False
        try:
            with self._operation('正在备份内置牌库…'):
                self.core._backup(force=True)
                self._check_cancel()
                self._stage('正在同步牌库…')
                try:
                    out = self.core.col.sync_collection(self.auth, sync_media=True)
                finally:
                    self.core.col._load_scheduler()
                if out.new_endpoint:
                    self.auth.endpoint = self._endpoint(out.new_endpoint)
                    self._persist_auth()
                self._check_cancel()
                if out.required in (SyncOutput.FULL_SYNC, SyncOutput.FULL_UPLOAD, SyncOutput.FULL_DOWNLOAD):
                    allowed = ('upload', 'download') if out.required == SyncOutput.FULL_SYNC else (
                        ('upload',) if out.required == SyncOutput.FULL_UPLOAD else ('download',))
                    self.pending = {'token': uuid4().hex, 'allowed': allowed,
                                    'server_usn': out.server_media_usn}
                    self.core.notice = '需要全量同步；请选择保留哪一端的数据，或取消'
                elif out.required == SyncOutput.NO_CHANGES:
                    collection_done = True
                    self._wait_media()
                    self._finish()
                else:
                    raise SyncProblem('未知的同步状态，已停止；未选择任何覆盖方向')
        except Exception as problem:
            error = self._error(problem, collection_done)
        finally:
            self.core.card = self.core.states = None
            self.core.token = uuid4().hex
        return self._response(error)

    def continue_full(self, session, token, direction):
        self.core._check(session)
        pending = self.pending
        if not pending or token != pending['token'] or direction not in pending['allowed'] or self.auth is None:
            return self._response('同步确认已失效，请重新发起同步')
        self.core._reset()  # consume the confirmation before any network write
        error, collection_done = '', False
        try:
            with self._operation('正在备份内置牌库…'):
                self.core._backup(force=True)
                self._check_cancel()
                self._stage('正在上传到 AnkiWeb…' if direction == 'upload' else '正在从 AnkiWeb 下载…')
                self.core.col.close_for_full_sync()
                try:
                    self.core.col.full_upload_or_download(auth=self.auth, server_usn=pending['server_usn'],
                                                          upload=direction == 'upload')
                    collection_done = True
                finally:
                    # Rust reopens the collection even after full-sync errors. Restore
                    # Python DBProxy/scheduler exactly as the official Qt client does.
                    self.core.col.reopen(after_full_sync=True)
                    self.core.session = uuid4().hex
                self._wait_media()
                self._finish()
        except Exception as problem:
            error = self._error(problem, collection_done)
        finally:
            self.core._reset()
        return self._response(error)

    def cancel_pending(self, session):
        self.core._check(session)
        self.core._reset()
        self.core.notice = '已取消全量同步；未执行覆盖'
        return self._response()
