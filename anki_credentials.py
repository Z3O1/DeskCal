# SPDX-License-Identifier: AGPL-3.0-or-later
"""User-bound Windows DPAPI storage. Never stores an AnkiWeb password.

Other platforms deliberately have no plaintext fallback: sessions remain in
memory. This module does not import or initialize Anki or any desktop UI.
"""
import ctypes
import json
import os
from pathlib import Path


class CredentialError(Exception):
    pass


class _Blob(ctypes.Structure):
    _fields_ = [('size', ctypes.c_uint32), ('data', ctypes.POINTER(ctypes.c_ubyte))]


def _crypt(data, decrypt=False):
    if os.name != 'nt':
        raise CredentialError('此系统不支持 Windows 安全存储；请使用仅本次登录')
    crypt32 = ctypes.WinDLL('crypt32', use_last_error=True)
    kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)
    # Keep the source buffer alive until the native call returns.
    buffer = (ctypes.c_ubyte * len(data)).from_buffer_copy(data)
    source = _Blob(len(data), buffer)
    result = _Blob()
    if decrypt:
        function = crypt32.CryptUnprotectData
        description_type, description = ctypes.c_void_p, None
    else:
        function = crypt32.CryptProtectData
        description_type, description = ctypes.c_wchar_p, 'DeskCal AnkiWeb session'
    function.argtypes = [ctypes.POINTER(_Blob), description_type, ctypes.POINTER(_Blob),
                         ctypes.c_void_p, ctypes.c_void_p, ctypes.c_uint32, ctypes.POINTER(_Blob)]
    function.restype = ctypes.c_int
    kernel32.LocalFree.argtypes = [ctypes.c_void_p]
    kernel32.LocalFree.restype = ctypes.c_void_p
    # CRYPTPROTECT_UI_FORBIDDEN; do NOT set LOCAL_MACHINE (would weaken user binding).
    if not function(ctypes.byref(source), description, None, None, None, 1, ctypes.byref(result)):
        raise CredentialError('无法使用 Windows 安全存储，请重新登录或取消“记住登录”')
    try:
        return ctypes.string_at(result.data, result.size)
    finally:
        if result.data:
            ctypes.memset(result.data, 0, result.size)
            kernel32.LocalFree(ctypes.cast(result.data, ctypes.c_void_p))


class CredentialStore:
    def __init__(self, directory):
        self.path = Path(directory) / 'ankiweb-auth.bin'

    def load(self):
        if not self.path.is_file():
            return None
        try:
            if self.path.stat().st_size > 65536:
                raise ValueError('invalid credential file')
            value = json.loads(_crypt(self.path.read_bytes(), decrypt=True).decode('utf-8'))
            if not isinstance(value, dict) or not isinstance(value.get('hkey'), str) or not value['hkey']:
                raise ValueError('invalid credential payload')
            return value
        except (OSError, ValueError, CredentialError) as error:
            raise CredentialError('已保存的登录无法读取，请重新登录（不会保存密码）') from error

    def save(self, value):
        if os.name != 'nt':
            return False
        content = _crypt(json.dumps(value, ensure_ascii=False).encode('utf-8'))
        temporary = self.path.with_suffix('.tmp')
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            temporary.write_bytes(content)
            temporary.chmod(0o600)
            temporary.replace(self.path)
        except OSError as error:
            raise CredentialError('无法保存登录令牌；当前登录仍可使用') from error
        finally:
            temporary.unlink(missing_ok=True)
        return True

    def clear(self):
        try:
            self.path.unlink(missing_ok=True)
        except OSError as error:
            raise CredentialError('无法删除已保存的登录，请检查数据目录权限') from error
