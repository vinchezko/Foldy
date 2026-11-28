"""Small math/colour helpers."""
import math
from PyQt6.QtGui import QColor


def clamp(v, lo, hi):
    return lo if v < lo else hi if v > hi else v


def smooth(t):
    return t * t * (3 - 2 * t)


def mix(a, b, t):
    return QColor(int(a[0] + (b[0] - a[0]) * t), int(a[1] + (b[1] - a[1]) * t), int(a[2] + (b[2] - a[2]) * t))


def spring_step(x, v, target, k, c, dt):
    """Advance a damped spring (stiffness k, damping c) by dt seconds with the exact analytic solution.
    Unlike stepping it in small Euler slices, it is stable and identical at any frame rate and any dt, and costs one
    evaluation instead of a loop. Returns (x, v)."""
    d = x - target
    w0 = math.sqrt(k)
    z = c / (2.0 * w0)
    if z < 0.9999:                                               # under-damped: overshoots a little (the springy open)
        a = z * w0
        wd = w0 * math.sqrt(1.0 - z * z)
        e = math.exp(-a * dt)
        cs, sn = math.cos(wd * dt), math.sin(wd * dt)
        return (target + e * (d * cs + (v + a * d) / wd * sn),
                e * (v * cs - (a * v + w0 * w0 * d) / wd * sn))
    if z > 1.0001:                                               # over-damped: creeps in, never overshoots
        s = w0 * math.sqrt(z * z - 1.0)
        r1, r2 = -z * w0 + s, -z * w0 - s
        c2 = (v - r1 * d) / (r2 - r1)
        c1 = d - c2
        e1, e2 = math.exp(r1 * dt), math.exp(r2 * dt)
        return target + c1 * e1 + c2 * e2, c1 * r1 * e1 + c2 * r2 * e2
    e = math.exp(-w0 * dt)                                       # critically damped: the fastest glide with no bounce
    b = v + w0 * d
    return target + (d + b * dt) * e, (v - w0 * b * dt) * e
