"""Capture only the test's own HWND, without desktop overlays or unrelated apps."""
import ctypes as c
import struct
from PIL import Image


def capture(hwnd, width, height):
    u, g = c.windll.user32, c.windll.gdi32
    H = c.c_void_p
    u.GetDC.argtypes, u.GetDC.restype = [H], H
    u.ReleaseDC.argtypes = [H, H]
    u.PrintWindow.argtypes = [H, H, c.c_uint]
    g.CreateCompatibleDC.argtypes, g.CreateCompatibleDC.restype = [H], H
    g.CreateCompatibleBitmap.argtypes, g.CreateCompatibleBitmap.restype = [H, c.c_int, c.c_int], H
    g.SelectObject.argtypes, g.SelectObject.restype = [H, H], H
    g.GetDIBits.argtypes = [H, H, c.c_uint, c.c_uint, H, H, c.c_uint]
    g.DeleteObject.argtypes = [H]
    g.DeleteDC.argtypes = [H]
    dc = u.GetDC(hwnd)
    mem = g.CreateCompatibleDC(dc)
    bitmap = g.CreateCompatibleBitmap(dc, width, height)
    old = g.SelectObject(mem, bitmap)
    try:
        assert u.PrintWindow(hwnd, mem, 2), 'PrintWindow failed'
        g.SelectObject(mem, old)
        pixels = c.create_string_buffer(width * height * 4)
        header = c.create_string_buffer(struct.pack('<IiiHHIIiiII', 40, width, -height, 1, 32, 0, width*height*4, 0, 0, 0, 0))
        assert g.GetDIBits(dc, bitmap, 0, height, pixels, header, 0) == height
        return Image.frombytes('RGB', (width, height), pixels.raw, 'raw', 'BGRX')
    finally:
        g.SelectObject(mem, old)
        g.DeleteObject(bitmap)
        g.DeleteDC(mem)
        u.ReleaseDC(hwnd, dc)
