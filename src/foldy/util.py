"""Small math/colour helpers."""
from PyQt6.QtGui import QColor


def clamp(v, lo, hi):
    return lo if v < lo else hi if v > hi else v


def smooth(t):
    return t * t * (3 - 2 * t)


def mix(a, b, t):
    return QColor(int(a[0] + (b[0] - a[0]) * t), int(a[1] + (b[1] - a[1]) * t), int(a[2] + (b[2] - a[2]) * t))
