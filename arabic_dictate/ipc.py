"""النقل بين CLI والخفيّة.

- لينكس: مقبس AF_UNIX بصلاحيات 0600 (كما كان).
- ويندوز: AF_UNIX غير متاح في CPython الرسمي، فنستخدم TCP على 127.0.0.1 فقط
  مع توكن عشوائي يُحفظ في ملف الاتصال (يُمنع أي اتصال غير مصرّح).
"""
from __future__ import annotations

import json
import os
import secrets
import socket
import sys

from . import config as cfg_mod

IS_WINDOWS = sys.platform == "win32"
_WINDOWS_HOST = "127.0.0.1"

# يُضبط في عملية الخفيّة فقط (على ويندوز) عند إنشاء السيرفر
_server_token: str | None = None


class AlreadyRunningError(RuntimeError):
    """خفيّة أخرى تعمل بالفعل."""


def available() -> bool:
    """هل يوجد مقبس/ملف اتصال يمكن المحاولة عليه؟"""
    if IS_WINDOWS:
        return cfg_mod.IPC_INFO_PATH.exists()
    return cfg_mod.SOCKET_PATH.exists()


def read_info() -> dict | None:
    try:
        return json.loads(cfg_mod.IPC_INFO_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def start_server() -> socket.socket:
    """ينشئ مقبس الخفيّة (مع فحص نسخة واحدة) ويعيده جاهزاً للاستماع."""
    global _server_token
    if IS_WINDOWS:
        info = read_info()
        if info and _probe_windows(info):
            raise AlreadyRunningError("هناك خفيّة تعمل بالفعل")
        cfg_mod.IPC_INFO_PATH.unlink(missing_ok=True)
        server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server.bind((_WINDOWS_HOST, 0))
        server.listen(8)
        port = int(server.getsockname()[1])
        _server_token = secrets.token_urlsafe(32)
        cfg_mod.IPC_INFO_PATH.write_text(
            json.dumps({"port": port, "token": _server_token, "pid": os.getpid()}, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        return server

    if cfg_mod.SOCKET_PATH.exists():
        probe = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        probe.settimeout(1.0)
        alive = False
        try:
            probe.connect(str(cfg_mod.SOCKET_PATH))
            alive = True
        except OSError:
            pass
        finally:
            probe.close()
        if alive:
            raise AlreadyRunningError("هناك خفيّة تعمل بالفعل")
        cfg_mod.SOCKET_PATH.unlink(missing_ok=True)
    server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    server.bind(str(cfg_mod.SOCKET_PATH))
    os.chmod(cfg_mod.SOCKET_PATH, 0o600)
    server.listen(8)
    return server


def cleanup_server() -> None:
    if IS_WINDOWS:
        cfg_mod.IPC_INFO_PATH.unlink(missing_ok=True)
    else:
        cfg_mod.SOCKET_PATH.unlink(missing_ok=True)


def connect(timeout: float) -> socket.socket:
    """اتصال من CLI إلى الخفيّة — يرفع OSError/ConnectionError عند الفشل."""
    if IS_WINDOWS:
        info = read_info()
        if not info or "port" not in info:
            raise ConnectionError("ملف الاتصال غير موجود — الخفيّة لا تعمل")
        client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        client.settimeout(timeout)
        client.connect((_WINDOWS_HOST, int(info["port"])))
        return client
    client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    client.settimeout(timeout)
    client.connect(str(cfg_mod.SOCKET_PATH))
    return client


def sign(request: dict) -> dict:
    """يضيف التوكن إلى الطلب (ويندوز فقط؛ يقرأه من ملف الاتصال)."""
    if not IS_WINDOWS:
        return request
    info = read_info() or {}
    token = str(info.get("token", ""))
    if token:
        return {**request, "token": token}
    return request


def authorized(request: dict) -> bool:
    """يتحقق من التوكن في الخفيّة (ويندوز). على لينكس الصلاحيات الملفية تكفي."""
    if not IS_WINDOWS:
        return True
    if not _server_token:
        return False
    return secrets.compare_digest(str(request.get("token", "")), _server_token)


def _probe_windows(info: dict) -> bool:
    """يفحص إن كان منفذ ملف الاتصال يرد فعلاً (خفيّة حيّة)."""
    try:
        probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        probe.settimeout(1.0)
        probe.connect((_WINDOWS_HOST, int(info["port"])))
    except (OSError, KeyError, ValueError):
        return False
    try:
        payload = json.dumps({"command": "status", "token": info.get("token", "")}).encode() + b"\n"
        probe.sendall(payload)
        reply = probe.recv(4096)
        return bool(reply)
    except OSError:
        return False
    finally:
        probe.close()
