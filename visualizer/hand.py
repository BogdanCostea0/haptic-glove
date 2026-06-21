"""OpenGL hand geometry — fixed-function pipeline (GL 1.x), no external meshes."""

from OpenGL.GL import *

# ── Colours ───────────────────────────────────────────────────────────────────
_PALM_COLOR    = (0.82, 0.65, 0.47)
_FINGER_COLORS = [
    (0.80, 0.62, 0.45),   # index
    (0.78, 0.60, 0.43),   # middle
    (0.76, 0.58, 0.41),   # ring
    (0.73, 0.55, 0.38),   # little (mirrors ring)
    (0.74, 0.56, 0.39),   # thumb
]

# ── Layout (all in world units, 1 unit ≈ "comfortable viewing size") ──────────
# Palm: flat box in the XY plane, fingers extend upward (+Y), palm faces camera
_PALM_W, _PALM_H, _PALM_D = 1.20, 0.80, 0.14
_FINGER_X   = [-0.46, -0.23, 0.00, 0.23, 0.46]   # X offset: index, middle, ring, little, thumb
_FINGER_Y0  =  0.32                                # Y where fingers leave the palm top

# Phalanx lengths: [proximal, middle, distal]
_SEG_LENS    = [0.46, 0.36, 0.26]
# Fraction of total flex angle assigned to each joint
_SEG_WEIGHTS = [0.50, 0.35, 0.15]
_SEG_W, _SEG_D = 0.13, 0.11   # segment cross-section (width × depth)

FINGER_NAMES = ["Index", "Middle", "Ring", "Little", "Thumb"]


# ── Primitives ────────────────────────────────────────────────────────────────

def _draw_box(w, h, d):
    """Solid box centred at the current origin with correct normals for lighting."""
    hw, hh, hd = w / 2, h / 2, d / 2
    glBegin(GL_QUADS)
    # Top
    glNormal3f(0, 1, 0)
    glVertex3f(-hw, hh, -hd); glVertex3f( hw, hh, -hd)
    glVertex3f( hw, hh,  hd); glVertex3f(-hw, hh,  hd)
    # Bottom
    glNormal3f(0, -1, 0)
    glVertex3f(-hw, -hh,  hd); glVertex3f( hw, -hh,  hd)
    glVertex3f( hw, -hh, -hd); glVertex3f(-hw, -hh, -hd)
    # Front (+Z)
    glNormal3f(0, 0, 1)
    glVertex3f(-hw, -hh, hd); glVertex3f( hw, -hh, hd)
    glVertex3f( hw,  hh, hd); glVertex3f(-hw,  hh, hd)
    # Back (-Z)
    glNormal3f(0, 0, -1)
    glVertex3f( hw, -hh, -hd); glVertex3f(-hw, -hh, -hd)
    glVertex3f(-hw,  hh, -hd); glVertex3f( hw,  hh, -hd)
    # Right (+X)
    glNormal3f(1, 0, 0)
    glVertex3f(hw, -hh,  hd); glVertex3f(hw, -hh, -hd)
    glVertex3f(hw,  hh, -hd); glVertex3f(hw,  hh,  hd)
    # Left (-X)
    glNormal3f(-1, 0, 0)
    glVertex3f(-hw, -hh, -hd); glVertex3f(-hw, -hh,  hd)
    glVertex3f(-hw,  hh,  hd); glVertex3f(-hw,  hh, -hd)
    glEnd()


def _draw_finger(flex_deg, color):
    """Three-segment finger, total bend = flex_deg, curling toward +Z (viewer)."""
    glColor3f(*color)
    glPushMatrix()
    for length, weight in zip(_SEG_LENS, _SEG_WEIGHTS):
        glTranslatef(0, length / 2, 0)
        _draw_box(_SEG_W, length, _SEG_D)
        glTranslatef(0, length / 2, 0)
        glRotatef(flex_deg * weight, 1, 0, 0)   # positive = curl forward (+Z)
    glPopMatrix()


# ── Public ────────────────────────────────────────────────────────────────────

def draw_hand(flex_degs: list[float]):
    """Draw palm + 5 fingers. flex_degs = [index, middle, ring, little, thumb]."""
    glColor3f(*_PALM_COLOR)
    _draw_box(_PALM_W, _PALM_H, _PALM_D)

    for i, (x, flex) in enumerate(zip(_FINGER_X, flex_degs)):
        glPushMatrix()
        glTranslatef(x, _FINGER_Y0, 0)
        _draw_finger(flex, _FINGER_COLORS[i])
        glPopMatrix()


def draw_axes(length: float = 1.0):
    """RGB XYZ axes for orientation debugging."""
    glDisable(GL_LIGHTING)
    glLineWidth(2.0)
    glBegin(GL_LINES)
    glColor3f(1, 0, 0); glVertex3f(0, 0, 0); glVertex3f(length, 0, 0)   # X red
    glColor3f(0, 1, 0); glVertex3f(0, 0, 0); glVertex3f(0, length, 0)   # Y green
    glColor3f(0, 0, 1); glVertex3f(0, 0, 0); glVertex3f(0, 0, length)   # Z blue
    glEnd()
    glLineWidth(1.0)
    glEnable(GL_LIGHTING)


def quat_to_gl_matrix(w: float, x: float, y: float, z: float) -> tuple:
    """Return a 16-element column-major float tuple for glMultMatrixf."""
    xx, yy, zz = x*x, y*y, z*z
    xy, xz, yz = x*y, x*z, y*z
    wx, wy, wz = w*x, w*y, w*z
    return (
        1-2*(yy+zz),  2*(xy+wz),   2*(xz-wy),  0,
          2*(xy-wz), 1-2*(xx+zz),  2*(yz+wx),  0,
          2*(xz+wy),  2*(yz-wx),  1-2*(xx+yy), 0,
        0,            0,           0,           1,
    )


def quat_multiply(a: list, b: list) -> list:
    """Hamilton product: a * b (both [w, x, y, z])."""
    aw, ax, ay, az = a
    bw, bx, by, bz = b
    return [
        aw*bw - ax*bx - ay*by - az*bz,
        aw*bx + ax*bw + ay*bz - az*by,
        aw*by - ax*bz + ay*bw + az*bx,
        aw*bz + ax*by - ay*bx + az*bw,
    ]


def quat_conjugate(q: list) -> list:
    """Conjugate (= inverse for unit quaternion)."""
    return [q[0], -q[1], -q[2], -q[3]]


def quat_relative(ref: list, current: list) -> list:
    """Rotation of 'current' relative to 'ref': q_rel = ref^-1 * current."""
    return quat_multiply(quat_conjugate(ref), current)
