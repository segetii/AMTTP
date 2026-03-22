"""
plot_critical_manifold_geometry.py
===================================
Generates the "Geometry of Systemic Collapse" figure for the grand
unification paper.

The critical manifold C* is the spectral boundary **ellipsoid**
    λ_max(D²Φ_pair(X)) = α
in the state space ℝ^{N×d}.  The ellipsoid is anisotropic because each
BSDT channel (δ_C, δ_G, δ_A, δ_T) has a different weight w_k and the
Hessian D²Φ has unequal eigenvalues along each axis.  Inside, constant
friction γ > 0 stabilises; outside, only adaptive γ* = α/λ_max succeeds.

The figure shows:
  - The critical manifold C* as a translucent **ellipsoid**
  - Inside: a stable trajectory spiralling to equilibrium (constant γ works)
  - Outside: an unstable trajectory diverging under constant γ
  - The adaptive-friction trajectory pulled back inside from outside
  - Six domain labels at representative positions on/beyond the ellipsoid
  - The double-well energy landscape on a cross-section
  - Semi-axis annotations showing spectral anisotropy
"""

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d import Axes3D
from mpl_toolkits.mplot3d.art3d import Poly3DCollection
from matplotlib.patches import FancyArrowPatch
from mpl_toolkits.mplot3d import proj3d
import matplotlib.patheffects as pe
import os

# ─── Output directory ────────────────────────────────────────
FIGDIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "figures")
os.makedirs(FIGDIR, exist_ok=True)


# ─── Ellipsoid semi-axes (anisotropic spectral radii) ─────
# The BSDT channels have different weights w_k, so the critical
# manifold C* stretches differently along each axis:
#   a_k = sqrt(α / w_k)   where w_k is the channel weight
# Camouflage (δ_C) is hardest to detect → largest semi-axis
# Activity   (δ_A) is easiest          → shortest semi-axis
ELLIPSOID_A = 1.40   # δ_C  (Camouflage)  — hardest, widest
ELLIPSOID_B = 1.00   # δ_G  (Feature Gap)  — medium
ELLIPSOID_C = 0.70   # δ_A  (Activity)     — easiest, narrowest


def ellipsoid_radius(direction):
    """Return the C* radius along a unit direction (for hit-testing)."""
    dx, dy, dz = direction
    # Parametric ellipsoid: (x/a)² + (y/b)² + (z/c)² = 1
    # radius along direction d is  1 / sqrt((dx/a)²+(dy/b)²+(dz/c)²)
    inv_sq = (dx/ELLIPSOID_A)**2 + (dy/ELLIPSOID_B)**2 + (dz/ELLIPSOID_C)**2
    if inv_sq < 1e-12:
        return 1.0
    return 1.0 / np.sqrt(inv_sq)


def point_outside_ellipsoid(x, y, z):
    """True if (x,y,z) lies outside C*."""
    return (x/ELLIPSOID_A)**2 + (y/ELLIPSOID_B)**2 + (z/ELLIPSOID_C)**2 > 1.0


def draw_ellipsoid(ax, a=ELLIPSOID_A, b=ELLIPSOID_B, c=ELLIPSOID_C,
                   color='#3498db', alpha=0.08, n=50):
    """Draw a translucent ellipsoid representing the critical manifold C*."""
    u = np.linspace(0, 2 * np.pi, n)
    v = np.linspace(0, np.pi, n)
    x = a * np.outer(np.cos(u), np.sin(v))
    y = b * np.outer(np.sin(u), np.sin(v))
    z = c * np.outer(np.ones_like(u), np.cos(v))
    ax.plot_surface(x, y, z, alpha=alpha, color=color,
                    edgecolor=color, linewidth=0.08, shade=True)

    # Draw equatorial and meridian ellipses for structure
    theta = np.linspace(0, 2 * np.pi, 200)
    # Equator  (XY-plane, z=0)
    ax.plot(a * np.cos(theta), b * np.sin(theta),
            np.zeros_like(theta), color=color, alpha=0.35, linewidth=1.0)
    # Meridian XZ  (y=0)
    ax.plot(a * np.cos(theta), np.zeros_like(theta),
            c * np.sin(theta), color=color, alpha=0.35, linewidth=1.0)
    # Meridian YZ  (x=0)
    ax.plot(np.zeros_like(theta), b * np.cos(theta),
            c * np.sin(theta), color=color, alpha=0.35, linewidth=1.0)

    # ── Semi-axis arrows with labels ──────────────────────────
    arrow_kw = dict(color='#2c3e50', linewidth=1.2, linestyle='--', alpha=0.5)
    ax.plot([0, a], [0, 0], [0, 0], **arrow_kw)
    ax.plot([0, 0], [0, b], [0, 0], **arrow_kw)
    ax.plot([0, 0], [0, 0], [0, c], **arrow_kw)
    fs = 8
    ax.text(a + 0.08, 0, 0, f'$a = {a:.2f}$', fontsize=fs, color='#2c3e50',
            ha='left', va='center',
            path_effects=[pe.withStroke(linewidth=2, foreground='white')])
    ax.text(0, b + 0.08, 0, f'$b = {b:.2f}$', fontsize=fs, color='#2c3e50',
            ha='left', va='center',
            path_effects=[pe.withStroke(linewidth=2, foreground='white')])
    ax.text(0, 0, c + 0.08, f'$c = {c:.2f}$', fontsize=fs, color='#2c3e50',
            ha='left', va='bottom',
            path_effects=[pe.withStroke(linewidth=2, foreground='white')])


def stable_spiral(n_points=400, decay=0.025, n_turns=3.5):
    """Trajectory spiralling inward to equilibrium (inside C*).
    Scaled to stay inside the ellipsoid."""
    t = np.linspace(0, n_turns * 2 * np.pi, n_points)
    r = 0.65 * np.exp(-decay * t)
    # Scale each axis proportionally to ellipsoid semi-axes
    x = r * ELLIPSOID_A * np.cos(t)
    y = r * ELLIPSOID_B * np.sin(t)
    z = r * ELLIPSOID_C * np.sin(t * 0.7) * 0.7
    return x, y, z


def unstable_trajectory(n_points=250, growth=0.012):
    """Trajectory diverging outward from C* (constant γ fails).
    Starts just outside the ellipsoid and grows."""
    t = np.linspace(0, 4 * np.pi, n_points)
    r = 1.05 * np.exp(growth * t)
    x = r * ELLIPSOID_A * np.cos(t * 0.8) * 0.55
    y = r * ELLIPSOID_B * np.sin(t * 0.8)
    z = r * ELLIPSOID_C * (0.4 * np.sin(t * 0.5) + 0.3 * (r - 1.05))
    return x, y, z


def adaptive_trajectory(n_points=400, start_r=1.5, target_r=0.25):
    """Trajectory starting outside C*, pulled back inside by adaptive γ*.
    Scaled to the ellipsoid geometry."""
    t = np.linspace(0, 5 * np.pi, n_points)
    r_env = start_r * np.exp(-0.15 * t) + target_r * (1 - np.exp(-0.15 * t))
    x = r_env * ELLIPSOID_A * np.cos(t * 0.9) * 0.6
    y = r_env * ELLIPSOID_B * np.sin(t * 0.9)
    z = r_env * ELLIPSOID_C * 0.4 * np.sin(t * 0.6)
    return x, y, z


def plot_main_figure():
    """Generate the main critical manifold sphere figure."""

    fig = plt.figure(figsize=(14, 10))

    # ═══════════════════════════════════════════════════════════
    # Panel A: 3D Critical Manifold Ellipsoid
    # ═══════════════════════════════════════════════════════════
    ax = fig.add_subplot(111, projection='3d')
    ax.set_facecolor('white')

    # Draw the critical manifold ellipsoid
    draw_ellipsoid(ax, color='#3498db', alpha=0.07)

    # ── Stable trajectory (inside C*) ─────────────────────────
    xs, ys, zs = stable_spiral()
    ax.plot(xs, ys, zs, color='#2ecc71', linewidth=2.0, alpha=0.9,
            label='Stable (inside $\\mathcal{C}^*$, constant $\\gamma$ works)',
            zorder=5)
    # Start marker
    ax.scatter([xs[0]], [ys[0]], [zs[0]], color='#2ecc71', s=60,
               edgecolors='black', linewidths=0.5, zorder=10)
    # End marker (equilibrium)
    ax.scatter([xs[-1]], [ys[-1]], [zs[-1]], color='#2ecc71', s=100,
               marker='*', edgecolors='black', linewidths=0.5, zorder=10)

    # ── Unstable trajectory (outside C*, constant γ fails) ────
    xu, yu, zu = unstable_trajectory()
    ax.plot(xu, yu, zu, color='#e74c3c', linewidth=2.0, alpha=0.85,
            label='Unstable (above $\\mathcal{C}^*$, constant $\\gamma$ fails)',
            linestyle='-', zorder=5)
    ax.scatter([xu[0]], [yu[0]], [zu[0]], color='#e74c3c', s=60,
               edgecolors='black', linewidths=0.5, zorder=10)
    # Divergence arrow at end
    ax.scatter([xu[-1]], [yu[-1]], [zu[-1]], color='#e74c3c', s=80,
               marker='^', edgecolors='black', linewidths=0.5, zorder=10)

    # ── Adaptive trajectory (starts outside, pulled back in) ──
    xa, ya, za = adaptive_trajectory()
    ax.plot(xa, ya, za, color='#f39c12', linewidth=2.2, alpha=0.9,
            label='Adaptive $\\gamma^* = \\alpha / \\lambda_{\\max}$ (recovers)',
            zorder=6)
    ax.scatter([xa[0]], [ya[0]], [za[0]], color='#f39c12', s=60,
               edgecolors='black', linewidths=0.5, zorder=10)
    ax.scatter([xa[-1]], [ya[-1]], [za[-1]], color='#f39c12', s=100,
               marker='*', edgecolors='black', linewidths=0.5, zorder=10)

    # ── Draw the crossing point where adaptive enters C* ──────
    # Find index where adaptive trajectory crosses the ellipsoid
    ra_ell = (xa/ELLIPSOID_A)**2 + (ya/ELLIPSOID_B)**2 + (za/ELLIPSOID_C)**2
    cross_idx = np.argmin(np.abs(ra_ell - 1.0))
    if ra_ell[0] > 1.0:
        ax.scatter([xa[cross_idx]], [ya[cross_idx]], [za[cross_idx]],
                   color='#f39c12', s=120, marker='o', facecolors='none',
                   edgecolors='#f39c12', linewidths=2.5, zorder=11)

    # ── Equilibrium point at origin ───────────────────────────
    ax.scatter([0], [0], [0], color='white', s=150, marker='o',
               edgecolors='#2c3e50', linewidths=2, zorder=15)
    ax.text(0.08, 0.08, -0.15, '$X^*$', fontsize=12, fontweight='bold',
            color='#2c3e50', zorder=15)

    # ── Domain labels positioned around and beyond the ellipsoid ─
    domains = [
        ("Fraud\ndetection",       (2.0,  0.3,  0.5),  '#9b59b6'),
        ("Systemic\nfinance",      (-0.3, 1.6,  0.4),  '#e67e22'),
        ("Navier–\nStokes",        (0.5, -0.5,  1.1),  '#3498db'),
        ("Neural\nnetworks",       (-1.8, -0.6, 0.2),  '#e74c3c'),
        ("3-SAT",                  (1.0,  1.2, -0.6),  '#1abc9c'),
        ("Supply\nchain",          (-0.8,  0.2, -1.0), '#f1c40f'),
    ]

    for label, pos, color in domains:
        ax.text(pos[0], pos[1], pos[2], label, fontsize=8.5,
                fontweight='bold', color=color,
                ha='center', va='center', zorder=20,
                path_effects=[pe.withStroke(linewidth=2, foreground='white')])
        # Thin line from ellipsoid surface to label
        p = np.array(pos)
        unit = p / (np.linalg.norm(p) + 1e-12)
        r_surf = ellipsoid_radius(unit)
        surf = unit * r_surf
        ax.plot([surf[0], pos[0]], [surf[1], pos[1]], [surf[2], pos[2]],
                color=color, alpha=0.4, linewidth=0.8, linestyle='--')
        # Small dot on ellipsoid surface
        ax.scatter([surf[0]], [surf[1]], [surf[2]], color=color, s=20,
                   alpha=0.6, zorder=12)

    # ── Labels ────────────────────────────────────────────────
    ax.set_xlabel('$\\delta_C$ (Camouflage)', fontsize=10, labelpad=8)
    ax.set_ylabel('$\\delta_G$ (Feature Gap)', fontsize=10, labelpad=8)
    ax.set_zlabel('$\\delta_A$ (Activity)', fontsize=10, labelpad=8)

    # Title and annotations
    ax.set_title(
        'Geometry of Systemic Collapse:\n'
        'Critical Manifold $\\mathcal{C}^*$ (Ellipsoid $\\sum w_k \\delta_k^2 / \\alpha = 1$)',
        fontsize=13, fontweight='bold', pad=20
    )

    # Region labels
    ax.text(0.0, 0.0, 0.35, 'STABLE\nREGION',
            fontsize=9, ha='center', va='center', color='#27ae60',
            fontweight='bold', alpha=0.7,
            path_effects=[pe.withStroke(linewidth=2, foreground='white')])

    ax.text(1.6, -1.2, -0.8,
            'UNSTABLE\nREGION\n($\\lambda_{\\max} > \\alpha$)',
            fontsize=8, ha='center', va='center', color='#c0392b',
            fontweight='bold', alpha=0.7,
            path_effects=[pe.withStroke(linewidth=2, foreground='white')])

    # Legend
    legend = ax.legend(loc='upper left', fontsize=8.5, framealpha=0.92,
                       edgecolor='#bdc3c7', fancybox=True)
    legend.get_frame().set_linewidth(0.8)

    # View angle
    ax.view_init(elev=22, azim=-55)

    # Axis limits
    lim = 2.0
    ax.set_xlim(-lim, lim)
    ax.set_ylim(-lim, lim)
    ax.set_zlim(-lim, lim)

    # Clean up grid
    ax.xaxis.pane.fill = False
    ax.yaxis.pane.fill = False
    ax.zaxis.pane.fill = False
    ax.xaxis.pane.set_edgecolor('lightgray')
    ax.yaxis.pane.set_edgecolor('lightgray')
    ax.zaxis.pane.set_edgecolor('lightgray')
    ax.grid(True, alpha=0.2)

    plt.tight_layout()

    # Save
    for ext in ['png', 'pdf']:
        path = os.path.join(FIGDIR, f'critical_manifold_ellipsoid.{ext}')
        plt.savefig(path, dpi=300, bbox_inches='tight',
                    facecolor='white', edgecolor='none')
        print(f"  Saved: {path}")
    plt.close(fig)


def plot_cross_section():
    """2D cross-section showing the double-well energy landscape
    and the critical radius."""

    fig, axes = plt.subplots(1, 2, figsize=(14, 5.5))

    # ═══════════════════════════════════════════════════════════
    # Panel (a): Cross-section of C* with trajectories
    # ═══════════════════════════════════════════════════════════
    ax = axes[0]

    # Critical manifold ellipse (cross-section in δ_C – δ_G plane)
    theta = np.linspace(0, 2*np.pi, 200)
    a2d, b2d = ELLIPSOID_A, ELLIPSOID_B  # semi-axes in this cross-section
    ax.plot(a2d*np.cos(theta), b2d*np.sin(theta), color='#3498db',
            linewidth=2.5, linestyle='-',
            label='$\\mathcal{C}^*$: $\\frac{\\delta_C^2}{a^2}+\\frac{\\delta_G^2}{b^2}=1$',
            zorder=3)

    # Fill regions
    ax.fill(a2d*np.cos(theta), b2d*np.sin(theta), color='#2ecc71',
            alpha=0.08, zorder=1)
    ax.fill_between(np.linspace(-2.2, 2.2, 100),
                    -2.2, 2.2, color='#e74c3c', alpha=0.03, zorder=0)

    # Stable spiral (inside ellipse)
    t = np.linspace(0, 6*np.pi, 500)
    r_s = 0.55 * np.exp(-0.06 * t)
    ax.plot(r_s * a2d * np.cos(t), r_s * b2d * np.sin(t), color='#2ecc71',
            linewidth=1.8, alpha=0.8, zorder=4,
            label='Stable (constant $\\gamma$)')
    ax.annotate('', xy=(r_s[-1]*a2d*np.cos(t[-1]), r_s[-1]*b2d*np.sin(t[-1])),
                xytext=(r_s[-5]*a2d*np.cos(t[-5]), r_s[-5]*b2d*np.sin(t[-5])),
                arrowprops=dict(arrowstyle='->', color='#2ecc71', lw=1.5))

    # Unstable spiral (outside — diverges)
    r_u = 1.1 * np.exp(0.025 * t)
    mask = r_u < 2.0
    ax.plot(r_u[mask] * a2d * np.cos(t[mask]) * 0.6,
            r_u[mask] * b2d * np.sin(t[mask]),
            color='#e74c3c', linewidth=1.8, alpha=0.8, zorder=4,
            label='Unstable (constant $\\gamma$ fails)')

    # Adaptive (starts outside ellipse, returns)
    r_a = 1.6 * np.exp(-0.12 * t) + 0.12 * (1 - np.exp(-0.12 * t))
    ax.plot(r_a * a2d * np.cos(t*0.9 + 2.5) * 0.7,
            r_a * b2d * np.sin(t*0.9 + 2.5),
            color='#f39c12', linewidth=2.0, alpha=0.9, zorder=5,
            label='Adaptive $\\gamma^*$ (recovers)')

    # Equilibrium
    ax.scatter([0], [0], s=100, color='white', edgecolors='#2c3e50',
               linewidths=2, zorder=15)
    ax.text(0.08, -0.15, '$X^*$', fontsize=11, fontweight='bold',
            color='#2c3e50')

    # Region labels
    ax.text(0.0, 0.55, 'STABLE', fontsize=10, ha='center',
            color='#27ae60', fontweight='bold', alpha=0.6)
    ax.text(0.0, 0.35, '$\\lambda_{\\max} < \\alpha$', fontsize=9,
            ha='center', color='#27ae60', alpha=0.5)
    ax.text(1.55, 1.55, 'UNSTABLE', fontsize=10, ha='center',
            color='#c0392b', fontweight='bold', alpha=0.6)
    ax.text(1.55, 1.35, '$\\lambda_{\\max} > \\alpha$', fontsize=9,
            ha='center', color='#c0392b', alpha=0.5)

    # Semi-axis labels
    ax.annotate('', xy=(a2d - 0.05, 0), xytext=(0, 0),
                arrowprops=dict(arrowstyle='<->', color='#2980b9',
                                lw=1.2, ls='--'))
    ax.text(a2d * 0.5, -0.15, f'$a = {a2d:.2f}$',
            fontsize=8.5, color='#2980b9', ha='center', fontweight='bold')
    ax.annotate('', xy=(0, b2d - 0.05), xytext=(0, 0),
                arrowprops=dict(arrowstyle='<->', color='#8e44ad',
                                lw=1.2, ls='--'))
    ax.text(-0.20, b2d * 0.5, f'$b = {b2d:.2f}$',
            fontsize=8.5, color='#8e44ad', ha='center', fontweight='bold',
            rotation=90)

    ax.set_xlim(-2.4, 2.4)
    ax.set_ylim(-2.0, 2.0)
    ax.set_aspect('equal')
    ax.set_xlabel('BSDT channel $\\delta_C$ (Camouflage)', fontsize=10)
    ax.set_ylabel('BSDT channel $\\delta_G$ (Feature Gap)', fontsize=10)
    ax.set_title('(a) Cross-Section of Critical Manifold $\\mathcal{C}^*$ (Ellipse)',
                 fontsize=11, fontweight='bold')
    ax.legend(fontsize=8, loc='lower left', framealpha=0.9)
    ax.grid(True, alpha=0.15)

    # Annotation: semi-axis interpretation
    ax.text(a2d + 0.15, -0.8,
            '$a_k = \\sqrt{\\alpha / w_k}$\n'
            'Larger axis =\n'
            'harder to detect\n'
            '(weaker channel)',
            fontsize=7.5, color='#34495e',
            bbox=dict(boxstyle='round,pad=0.4', facecolor='#eaf2f8',
                      edgecolor='#aed6f1', alpha=0.9))

    # ─── skip the duplicate title/legend/grid below ───
    # ═══════════════════════════════════════════════════════════
    # Panel (b): Double-well energy landscape
    # ═══════════════════════════════════════════════════════════
    ax2 = axes[1]

    s = np.linspace(-1.5, 1.5, 500)

    # Different annealing stages (μ increasing)
    mu_values = [0.0, 0.3, 0.8, 2.0, 5.0]
    colors_mu = ['#bdc3c7', '#95a5a6', '#f39c12', '#e67e22', '#e74c3c']

    for mu, col in zip(mu_values, colors_mu):
        # V(s) = radial + double-well = 0.3*s² + μ(1-s²)²
        V = 0.3 * s**2 + mu * (1 - s**2)**2
        V -= V.min()  # normalise
        lw = 2.5 if mu == 5.0 else 1.5
        ls = '-' if mu > 0 else '--'
        ax2.plot(s, V, color=col, linewidth=lw, linestyle=ls,
                 label=f'$\\mu = {mu}$', alpha=0.85)

    # Mark the two wells at s = ±1
    ax2.scatter([-1, 1], [0, 0], s=80, color='#2ecc71', edgecolors='#2c3e50',
                linewidths=1.5, zorder=10)
    ax2.text(-1, -0.35, 'Stable\n$s = -1$', fontsize=8.5, ha='center',
             color='#27ae60', fontweight='bold')
    ax2.text(1, -0.35, 'Collapsed\n$s = +1$', fontsize=8.5, ha='center',
             color='#c0392b', fontweight='bold')

    # Barrier at s = 0
    V_barrier = 0.3 * 0 + 5.0 * (1 - 0)**2
    ax2.annotate('Barrier\n(phase transition)',
                 xy=(0, V_barrier - V.min()),
                 xytext=(0.6, V_barrier + 1.0),
                 fontsize=8, ha='center', color='#8e44ad',
                 arrowprops=dict(arrowstyle='->', color='#8e44ad', lw=1.2))

    # Delay-70 annotation
    ax2.annotate('delay70 schedule:\n$\\mu=0$ for 70%, then\ncosine ramp',
                 xy=(-1.3, 0.8), xytext=(-1.3, 0.8),
                 fontsize=7.5, color='#7f8c8d',
                 bbox=dict(boxstyle='round,pad=0.4', facecolor='#ecf0f1',
                           edgecolor='#bdc3c7', alpha=0.9))

    # Domain interpretations on the right
    domain_interp = [
        ('Fraud: score → flag', -0.85),
        ('Finance: leverage → collapse', -0.65),
        ('NS: viscosity → turbulent', -0.45),
        ('NN: gradient → blow-up', -0.25),
        ('SAT: relaxation → discrete', -0.05),
        ('SC: reliability → disrupted', 0.15),
    ]
    for text, y_pos in domain_interp:
        ax2.text(1.55, y_pos + 3.5, text, fontsize=6.8, color='#2c3e50',
                 va='center', fontfamily='monospace',
                 bbox=dict(boxstyle='round,pad=0.2', facecolor='#f8f9fa',
                           edgecolor='#dee2e6', alpha=0.8))

    ax2.set_xlim(-1.5, 1.5)
    ax2.set_ylim(-0.8, 8)
    ax2.set_xlabel('State variable $s$ (continuous relaxation)', fontsize=10)
    ax2.set_ylabel('$V(s) = \\frac{\\alpha}{2}s^2 + \\mu(1 - s^2)^2$', fontsize=10)
    ax2.set_title('(b) Double-Well Binarisation Potential', fontsize=11, fontweight='bold')
    ax2.legend(fontsize=8, loc='upper left', framealpha=0.9, title='Annealing $\\mu$',
               title_fontsize=8)
    ax2.grid(True, alpha=0.15)

    plt.tight_layout()

    for ext in ['png', 'pdf']:
        path = os.path.join(FIGDIR, f'critical_manifold_cross_section.{ext}')
        plt.savefig(path, dpi=300, bbox_inches='tight',
                    facecolor='white', edgecolor='none')
        print(f"  Saved: {path}")
    plt.close(fig)


def plot_phase_diagram():
    """Phase diagram: λ_max vs γ showing the stable/unstable regions
    and how each domain maps onto it."""

    fig, ax = plt.subplots(figsize=(10, 7))

    # The critical curve: γ* = α / λ_max
    alpha = 0.10
    lam = np.linspace(0.01, 2.0, 500)
    gamma_crit = alpha / lam

    # Regions
    ax.fill_between(lam, gamma_crit, 3.0, color='#2ecc71', alpha=0.08,
                    label='Stable region (γ > γ*)')
    ax.fill_between(lam, 0, gamma_crit, color='#e74c3c', alpha=0.08,
                    label='Unstable region (γ < γ*)')

    # Critical curve
    ax.plot(lam, gamma_crit, color='#3498db', linewidth=3,
            label='$\\mathcal{C}^*$: $\\gamma^* = \\alpha / \\lambda_{\\max}$',
            zorder=5)

    # Domain data points
    # (λ_max range, γ_constant, γ_adaptive) for each domain
    domain_data = {
        'Fraud Detection': {
            'lam': 0.25, 'gamma_const': 0.18, 'gamma_adapt': 0.50,
            'color': '#9b59b6', 'marker': 'o'
        },
        'Systemic Finance': {
            'lam': 0.80, 'gamma_const': 0.05, 'gamma_adapt': 0.15,
            'color': '#e67e22', 'marker': 's'
        },
        'Navier–Stokes': {
            'lam': 1.20, 'gamma_const': 0.03, 'gamma_adapt': 0.10,
            'color': '#3498db', 'marker': 'D'
        },
        'Neural Networks': {
            'lam': 1.50, 'gamma_const': 0.02, 'gamma_adapt': 0.08,
            'color': '#e74c3c', 'marker': '^'
        },
        '3-SAT ($\\alpha=4.0$)': {
            'lam': 0.60, 'gamma_const': 0.08, 'gamma_adapt': 0.20,
            'color': '#1abc9c', 'marker': 'v'
        },
        'Supply Chain': {
            'lam': 1.00, 'gamma_const': 0.03, 'gamma_adapt': 0.12,
            'color': '#f1c40f', 'marker': 'P'
        },
    }

    for name, d in domain_data.items():
        # Constant γ point (below critical → unstable ✗)
        ax.scatter(d['lam'], d['gamma_const'], s=120, color=d['color'],
                   marker=d['marker'], edgecolors='black', linewidths=0.8,
                   zorder=10, alpha=0.7)

        # Adaptive γ* point (above critical → stable ✓)
        ax.scatter(d['lam'], d['gamma_adapt'], s=120, color=d['color'],
                   marker=d['marker'], edgecolors='black', linewidths=0.8,
                   zorder=10)

        # Arrow from constant to adaptive
        ax.annotate('', xy=(d['lam'], d['gamma_adapt']),
                    xytext=(d['lam'], d['gamma_const']),
                    arrowprops=dict(arrowstyle='->', color=d['color'],
                                   lw=1.8, ls='-'))

        # Label
        offset_x = 0.05
        offset_y = 0.02
        ax.text(d['lam'] + offset_x, d['gamma_adapt'] + offset_y, name,
                fontsize=8, color=d['color'], fontweight='bold',
                path_effects=[pe.withStroke(linewidth=2, foreground='white')])

    # Legend entries for constant vs adaptive
    ax.scatter([], [], s=80, color='gray', marker='o', alpha=0.5,
               label='Constant γ (fails above $\\mathcal{C}^*$)')
    ax.scatter([], [], s=80, color='gray', marker='o',
               label='Adaptive γ* (succeeds)')

    ax.set_xlabel('Spectral radius $\\lambda_{\\max}(D^2\\Phi_{\\mathrm{pair}})$',
                  fontsize=11)
    ax.set_ylabel('Friction coefficient $\\gamma$', fontsize=11)
    ax.set_title('Phase Diagram: Universal Critical Manifold $\\mathcal{C}^*$\n'
                 'across Six Domains',
                 fontsize=13, fontweight='bold')
    ax.set_xlim(0, 2.0)
    ax.set_ylim(0, 1.5)
    ax.legend(fontsize=9, loc='upper right', framealpha=0.92)
    ax.grid(True, alpha=0.15)

    # Annotation: "constant γ always falls below C*"
    ax.annotate('All constant-γ points\nfall below $\\mathcal{C}^*$\n→ instability',
                xy=(1.0, 0.10), xytext=(1.4, 0.45),
                fontsize=9, color='#c0392b', fontweight='bold',
                arrowprops=dict(arrowstyle='->', color='#c0392b', lw=1.5),
                bbox=dict(boxstyle='round,pad=0.4', facecolor='#fadbd8',
                          edgecolor='#e74c3c', alpha=0.9))

    ax.annotate('Adaptive γ* places\neach domain above $\\mathcal{C}^*$\n→ stability',
                xy=(0.6, 0.20), xytext=(0.15, 0.80),
                fontsize=9, color='#27ae60', fontweight='bold',
                arrowprops=dict(arrowstyle='->', color='#27ae60', lw=1.5),
                bbox=dict(boxstyle='round,pad=0.4', facecolor='#d5f5e3',
                          edgecolor='#27ae60', alpha=0.9))

    plt.tight_layout()

    for ext in ['png', 'pdf']:
        path = os.path.join(FIGDIR, f'phase_diagram_universal.{ext}')
        plt.savefig(path, dpi=300, bbox_inches='tight',
                    facecolor='white', edgecolor='none')
        print(f"  Saved: {path}")
    plt.close(fig)


# ─────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("Generating critical manifold geometry figures...")
    print()
    print("Figure 1: 3D Critical Manifold Ellipsoid")
    plot_main_figure()
    print()
    print("Figure 2: Cross-section + Double-well potential")
    plot_cross_section()
    print()
    print("Figure 3: Universal phase diagram")
    plot_phase_diagram()
    print()
    print("Done.")
