"""
plot_ellipsoid_geometry_extended.py
=====================================
Extended "Geometry of Systemic Collapse" figures for the grand
unification paper.  Uses the EllipsoidGeometry class to show:

  Figure 4 — Gaussian curvature heatmap on the C* ellipsoid surface
  Figure 5 — Geodesic paths between all six domain positions on C*
  Figure 6 — Great elliptic cross-sections (three principal planes)
  Figure 7 — Eccentricity / anisotropy bar chart + shape classification
  Figure 8 — Domain footprint overlay (Mahalanobis contours at r=0.5,1,1.5)
  Figure 9 — Curvature vs latitude profile (meridian sweep)
  Figure 10 — Fisher information metric field (tangent vectors on C*)

All figures saved as PNG + PDF to research/supply-chain/figures/.

Author: Odeyemi Olusegun Israel
"""

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d import Axes3D
import matplotlib.patheffects as pe
from matplotlib.patches import FancyArrowPatch
from matplotlib.collections import LineCollection
from matplotlib.colors import Normalize
import matplotlib.cm as cm
import os
import sys

# ─── Ensure UDL importable ────────────────────────────────────
_udl_root = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'udl')
sys.path.insert(0, _udl_root)
try:
    from udl.ellipsoid_geometry import EllipsoidGeometry
except ImportError:
    # Direct import as fallback
    import importlib.util
    _spec = importlib.util.spec_from_file_location(
        'ellipsoid_geometry',
        os.path.join(_udl_root, 'udl', 'ellipsoid_geometry.py'))
    _mod = importlib.util.module_from_spec(_spec)
    _spec.loader.exec_module(_mod)
    EllipsoidGeometry = _mod.EllipsoidGeometry


FIGDIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "figures")
os.makedirs(FIGDIR, exist_ok=True)

# ─── BSDT channel weights (Fisher VR) → critical manifold C* ──
# w_C < w_G < w_A → a_C > a_G > a_A  (harder = wider axis)
FISHER_WEIGHTS = np.array([0.15, 0.30, 0.55])  # δ_C, δ_G, δ_A
ALPHA = 0.30  # spectral threshold
ELLIPSOID = EllipsoidGeometry.from_fisher_weights(FISHER_WEIGHTS, alpha=ALPHA)

# Semi-axes: a_k = sqrt(α / w_k)
A, B, C = ELLIPSOID.semi_axes
print(f"Critical manifold C*:  a={A:.3f}  b={B:.3f}  c={C:.3f}")
print(f"Volume = {ELLIPSOID.volume():.4f}")
print(f"Surface area = {ELLIPSOID.surface_area():.4f}")
ecc = ELLIPSOID.eccentricities()
print(f"Eccentricity e₁ = {ecc['e1']:.4f},  flattening f = {ecc['flattening']:.4f}")

# ─── Six domain positions on/near C* ──────────────────────────
# Each domain has a characteristic BSDT channel signature
# Coordinates are (δ_C, δ_G, δ_A) — projected to C* surface
DOMAIN_POSITIONS_RAW = {
    'Fraud\nDetection':    np.array([1.2,   0.3,   0.15]),
    'Systemic\nFinance':   np.array([0.25,  0.85,  0.30]),
    'Navier–\nStokes':     np.array([0.20,  0.20,  0.65]),
    'Neural\nNetworks':    np.array([-0.90, -0.35, 0.15]),
    '3-SAT':               np.array([0.60,  0.70, -0.25]),
    'Supply\nChain':       np.array([-0.40, 0.15, -0.55]),
}
DOMAIN_COLORS = {
    'Fraud\nDetection':    '#9b59b6',
    'Systemic\nFinance':   '#e67e22',
    'Navier–\nStokes':     '#3498db',
    'Neural\nNetworks':    '#e74c3c',
    '3-SAT':               '#1abc9c',
    'Supply\nChain':       '#f1c40f',
}

# Project each domain position onto C* surface
DOMAIN_POSITIONS = {}
for name, pos in DOMAIN_POSITIONS_RAW.items():
    DOMAIN_POSITIONS[name] = ELLIPSOID.project_to_surface(pos.reshape(1, -1))[0]


def _save(fig, name):
    for ext in ['png', 'pdf']:
        path = os.path.join(FIGDIR, f'{name}.{ext}')
        fig.savefig(path, dpi=300, bbox_inches='tight',
                    facecolor='white', edgecolor='none')
    print(f"  Saved: {name}.png/pdf")
    plt.close(fig)


# ═══════════════════════════════════════════════════════════════
#  FIGURE 4 — Gaussian Curvature Heatmap on C* Ellipsoid
# ═══════════════════════════════════════════════════════════════

def plot_curvature_heatmap():
    """3D ellipsoid coloured by Gaussian curvature K.
    High curvature (poles/shortest axis) = tight detection.
    Low curvature (equator/longest axis) = blind-spot region."""

    fig = plt.figure(figsize=(12, 9))
    ax = fig.add_subplot(111, projection='3d')
    ax.set_facecolor('white')

    n = 60
    u = np.linspace(0, 2 * np.pi, n)
    v = np.linspace(0, np.pi, n)
    uu, vv = np.meshgrid(u, v)

    x = A * np.cos(uu) * np.sin(vv)
    y = B * np.sin(uu) * np.sin(vv)
    z = C * np.cos(vv)

    # Compute Gaussian curvature at each surface point
    pts = np.column_stack([x.ravel(), y.ravel(), z.ravel()])
    K = ELLIPSOID.gaussian_curvature(pts).reshape(n, n)

    # Log scale for better colour contrast
    K_log = np.log10(K + 1e-10)

    # Plot surface
    norm = Normalize(vmin=K_log.min(), vmax=K_log.max())
    cmap = plt.get_cmap('inferno')
    colors = cmap(norm(K_log))

    surf = ax.plot_surface(x, y, z, facecolors=colors, alpha=0.85,
                           shade=True, linewidth=0.1, edgecolor='gray',
                           antialiased=True)

    # Colourbar
    sm = cm.ScalarMappable(cmap=plt.get_cmap('inferno'), norm=norm)
    sm.set_array([])
    cbar = fig.colorbar(sm, ax=ax, shrink=0.5, aspect=15, pad=0.08)
    cbar.set_label('$\\log_{10}\\, K$ (Gaussian curvature)', fontsize=10)

    # Mark curvature extremes
    # Max K at poles (z-axis, shortest axis c)
    K_pole = ELLIPSOID.gaussian_curvature(np.array([[0, 0, C]]))[0]
    K_equator = ELLIPSOID.gaussian_curvature(np.array([[A, 0, 0]]))[0]
    ax.scatter([0], [0], [C + 0.08], color='#e74c3c', s=100, marker='^',
               edgecolors='black', linewidths=0.8, zorder=15)
    ax.text(0, 0, C + 0.18, f'$K_{{\\max}} = {K_pole:.3f}$\n(easiest to detect)',
            fontsize=8, ha='center', color='#e74c3c', fontweight='bold',
            path_effects=[pe.withStroke(linewidth=2, foreground='white')])

    ax.scatter([A + 0.08], [0], [0], color='#2ecc71', s=100, marker='v',
               edgecolors='black', linewidths=0.8, zorder=15)
    ax.text(A + 0.2, 0, -0.15, f'$K_{{\\min}} = {K_equator:.3f}$\n(blind-spot region)',
            fontsize=8, ha='left', color='#2ecc71', fontweight='bold',
            path_effects=[pe.withStroke(linewidth=2, foreground='white')])

    # Domain labels on surface
    for name, pos in DOMAIN_POSITIONS.items():
        color = DOMAIN_COLORS[name]
        ax.scatter([pos[0]], [pos[1]], [pos[2]], color=color, s=60,
                   edgecolors='black', linewidths=0.8, zorder=15)
        ax.text(pos[0]*1.15, pos[1]*1.15, pos[2]*1.15, name.replace('\n', ' '),
                fontsize=7, color=color, fontweight='bold',
                path_effects=[pe.withStroke(linewidth=2, foreground='white')])

    ax.set_xlabel('$\\delta_C$ (Camouflage)', fontsize=10, labelpad=8)
    ax.set_ylabel('$\\delta_G$ (Feature Gap)', fontsize=10, labelpad=8)
    ax.set_zlabel('$\\delta_A$ (Activity)', fontsize=10, labelpad=8)
    ax.set_title('Gaussian Curvature on Critical Manifold $\\mathcal{C}^*$\n'
                 'High curvature = tight detection boundary | Low = blind-spot region',
                 fontsize=12, fontweight='bold', pad=18)
    ax.view_init(elev=25, azim=-50)

    lim = max(A, B, C) * 1.3
    ax.set_xlim(-lim, lim)
    ax.set_ylim(-lim, lim)
    ax.set_zlim(-lim, lim)
    ax.xaxis.pane.fill = False
    ax.yaxis.pane.fill = False
    ax.zaxis.pane.fill = False
    ax.grid(True, alpha=0.15)

    _save(fig, 'curvature_heatmap_ellipsoid')


# ═══════════════════════════════════════════════════════════════
#  FIGURE 5 — Geodesic Paths Between All Six Domains on C*
# ═══════════════════════════════════════════════════════════════

def plot_geodesic_paths():
    """Show geodesic (shortest) paths along the C* ellipsoid surface
    connecting all six domains.  Pairwise geodesic distance matrix."""

    fig = plt.figure(figsize=(16, 7))

    # ── Panel (a): 3D ellipsoid with geodesic paths ──
    ax1 = fig.add_subplot(121, projection='3d')
    ax1.set_facecolor('white')

    # Draw translucent ellipsoid
    n = 40
    u = np.linspace(0, 2 * np.pi, n)
    v = np.linspace(0, np.pi, n)
    x = A * np.outer(np.cos(u), np.sin(v))
    y = B * np.outer(np.sin(u), np.sin(v))
    z = C * np.outer(np.ones_like(u), np.cos(v))
    ax1.plot_surface(x, y, z, alpha=0.06, color='#3498db',
                     edgecolor='#3498db', linewidth=0.05, shade=True)

    # Equator and meridians
    theta = np.linspace(0, 2 * np.pi, 200)
    ax1.plot(A * np.cos(theta), B * np.sin(theta),
             np.zeros_like(theta), color='#3498db', alpha=0.25, lw=0.8)

    names = list(DOMAIN_POSITIONS.keys())
    positions = list(DOMAIN_POSITIONS.values())
    n_domains = len(names)

    # Draw all pairwise geodesic paths
    dist_matrix = np.zeros((n_domains, n_domains))
    n_interp = 80  # points on each geodesic

    for i in range(n_domains):
        for j in range(i + 1, n_domains):
            p1, p2 = positions[i], positions[j]
            # Compute discrete geodesic path on surface
            path = np.zeros((n_interp + 1, 3))
            for k in range(n_interp + 1):
                t = k / n_interp
                p_interp = (1 - t) * p1 + t * p2
                path[k] = ELLIPSOID.project_to_surface(p_interp.reshape(1, -1))[0]

            # Geodesic distance
            chords = np.diff(path, axis=0)
            d_geo = np.sum(np.linalg.norm(chords, axis=1))
            dist_matrix[i, j] = d_geo
            dist_matrix[j, i] = d_geo

            # Color by average of the two domain colours
            c1 = matplotlib.colors.to_rgba(DOMAIN_COLORS[names[i]])
            c2 = matplotlib.colors.to_rgba(DOMAIN_COLORS[names[j]])
            avg_color = tuple((np.array(c1) + np.array(c2)) / 2)

            ax1.plot(path[:, 0], path[:, 1], path[:, 2],
                     color=avg_color, linewidth=1.5, alpha=0.6, zorder=5)

    # Domain markers and labels
    for name, pos in DOMAIN_POSITIONS.items():
        color = DOMAIN_COLORS[name]
        ax1.scatter([pos[0]], [pos[1]], [pos[2]], color=color, s=100,
                    edgecolors='black', linewidths=1, zorder=15)
        ax1.text(pos[0]*1.2, pos[1]*1.2, pos[2]*1.2,
                 name.replace('\n', ' '), fontsize=7.5, color=color,
                 fontweight='bold',
                 path_effects=[pe.withStroke(linewidth=2, foreground='white')])

    ax1.set_xlabel('$\\delta_C$', fontsize=10, labelpad=6)
    ax1.set_ylabel('$\\delta_G$', fontsize=10, labelpad=6)
    ax1.set_zlabel('$\\delta_A$', fontsize=10, labelpad=6)
    ax1.set_title('(a) Geodesic Paths on $\\mathcal{C}^*$',
                  fontsize=11, fontweight='bold', pad=12)
    ax1.view_init(elev=20, azim=-45)
    lim = max(A, B, C) * 1.4
    ax1.set_xlim(-lim, lim)
    ax1.set_ylim(-lim, lim)
    ax1.set_zlim(-lim, lim)
    ax1.xaxis.pane.fill = False
    ax1.yaxis.pane.fill = False
    ax1.zaxis.pane.fill = False
    ax1.grid(True, alpha=0.15)

    # ── Panel (b): Geodesic distance matrix heatmap ──
    ax2 = fig.add_subplot(122)

    short_names = [n.replace('\n', ' ') for n in names]
    im = ax2.imshow(dist_matrix, cmap='YlOrRd', interpolation='nearest')
    ax2.set_xticks(range(n_domains))
    ax2.set_yticks(range(n_domains))
    ax2.set_xticklabels(short_names, fontsize=8, rotation=45, ha='right')
    ax2.set_yticklabels(short_names, fontsize=8)

    # Annotate each cell with the distance value
    for i in range(n_domains):
        for j in range(n_domains):
            val = dist_matrix[i, j]
            color = 'white' if val > dist_matrix.max() * 0.6 else 'black'
            ax2.text(j, i, f'{val:.2f}', ha='center', va='center',
                     fontsize=8, color=color, fontweight='bold')

    cbar = fig.colorbar(im, ax=ax2, shrink=0.8)
    cbar.set_label('Geodesic distance on $\\mathcal{C}^*$', fontsize=10)

    ax2.set_title('(b) Cross-Domain Geodesic Distance Matrix',
                  fontsize=11, fontweight='bold')

    plt.tight_layout()
    _save(fig, 'geodesic_paths_domains')


# ═══════════════════════════════════════════════════════════════
#  FIGURE 6 — Great Elliptic Cross-Sections (Three Principal Planes)
# ═══════════════════════════════════════════════════════════════

def plot_cross_section_gallery():
    """Show all three principal cross-sections and one oblique section
    through the ellipsoid.  Each is an ellipse with labelled semi-axes."""

    fig, axes = plt.subplots(1, 4, figsize=(20, 5))
    fig.suptitle('Great Elliptic Cross-Sections of $\\mathcal{C}^*$',
                 fontsize=14, fontweight='bold', y=1.02)

    sections = [
        {
            'normal': np.array([0, 0, 1]),
            'title': '$\\delta_C$–$\\delta_G$ plane\n(equatorial)',
            'xlabel': '$\\delta_C$ (Camouflage)',
            'ylabel': '$\\delta_G$ (Feature Gap)',
            'semi_x': A, 'semi_y': B,
        },
        {
            'normal': np.array([0, 1, 0]),
            'title': '$\\delta_C$–$\\delta_A$ plane\n(meridional)',
            'xlabel': '$\\delta_C$ (Camouflage)',
            'ylabel': '$\\delta_A$ (Activity)',
            'semi_x': A, 'semi_y': C,
        },
        {
            'normal': np.array([1, 0, 0]),
            'title': '$\\delta_G$–$\\delta_A$ plane\n(meridional)',
            'xlabel': '$\\delta_G$ (Feature Gap)',
            'ylabel': '$\\delta_A$ (Activity)',
            'semi_x': B, 'semi_y': C,
        },
        {
            'normal': np.array([1, 1, 1]) / np.sqrt(3),
            'title': 'Oblique section\n$(1,1,1)/\\sqrt{3}$ normal',
            'xlabel': '$u_1$ (oblique)',
            'ylabel': '$u_2$ (oblique)',
            'semi_x': None, 'semi_y': None,  # computed from section
        },
    ]

    for idx, sec in enumerate(sections):
        ax = axes[idx]

        # Get the cross-section curve
        curve = ELLIPSOID.great_elliptic_section(sec['normal'], n_points=300)

        if idx < 3:
            # Principal sections — use analytic ellipse
            theta = np.linspace(0, 2 * np.pi, 300)
            sx, sy = sec['semi_x'], sec['semi_y']
            ex, ey = sx * np.cos(theta), sy * np.sin(theta)

            # Fill regions
            ax.fill(ex, ey, color='#2ecc71', alpha=0.08)
            ax.plot(ex, ey, color='#3498db', linewidth=2.5, zorder=5)

            # Semi-axis arrows
            ax.annotate('', xy=(sx, 0), xytext=(0, 0),
                        arrowprops=dict(arrowstyle='<->', color='#2980b9',
                                        lw=1.5, ls='--'))
            ax.text(sx * 0.5, -0.12, f'$a = {sx:.3f}$', fontsize=9,
                    color='#2980b9', ha='center', fontweight='bold')

            ax.annotate('', xy=(0, sy), xytext=(0, 0),
                        arrowprops=dict(arrowstyle='<->', color='#8e44ad',
                                        lw=1.5, ls='--'))
            ax.text(-0.15, sy * 0.5, f'$b = {sy:.3f}$', fontsize=9,
                    color='#8e44ad', ha='center', fontweight='bold',
                    rotation=90)

            # Area annotation
            area = np.pi * sx * sy
            ax.text(0, -0.8 * sy, f'Area = $\\pi ab$ = {area:.3f}',
                    fontsize=8, ha='center', color='#34495e',
                    bbox=dict(boxstyle='round', facecolor='#eaf2f8',
                              edgecolor='#aed6f1', alpha=0.9))

            # Eccentricity of this 2D ellipse
            e_2d = np.sqrt(1 - (min(sx, sy) / max(sx, sy))**2)
            ax.text(0, -0.95 * sy, f'$e$ = {e_2d:.3f}',
                    fontsize=8, ha='center', color='#7f8c8d')

            # Mark domain projections onto this plane
            for name, pos_3d in DOMAIN_POSITIONS.items():
                color = DOMAIN_COLORS[name]
                # Project depending on which plane
                if idx == 0:
                    px, py = pos_3d[0], pos_3d[1]
                elif idx == 1:
                    px, py = pos_3d[0], pos_3d[2]
                else:
                    px, py = pos_3d[1], pos_3d[2]

                ax.scatter([px], [py], color=color, s=40, edgecolors='black',
                           linewidths=0.6, zorder=10)
                label = name.split('\n')[0]
                ax.text(px + 0.06, py + 0.04, label, fontsize=6,
                        color=color, fontweight='bold',
                        path_effects=[pe.withStroke(linewidth=1.5,
                                                    foreground='white')])

            lim = max(sx, sy) * 1.4
            ax.set_xlim(-lim, lim)
            ax.set_ylim(-lim, lim)
        else:
            # Oblique section — project curve to 2D
            normal = sec['normal']
            # Build 2D basis in the cutting plane
            u1 = np.array([1, -1, 0]) / np.sqrt(2)
            u2 = np.cross(normal, u1)
            u2 = u2 / (np.linalg.norm(u2) + 1e-10)

            c_2d = curve - ELLIPSOID.centre
            px = c_2d @ u1
            py = c_2d @ u2

            ax.fill(px, py, color='#f39c12', alpha=0.08)
            ax.plot(px, py, color='#e67e22', linewidth=2.5, zorder=5)

            # Semi-axes of the oblique ellipse
            from scipy.optimize import minimize_scalar
            r_max = np.max(np.sqrt(px**2 + py**2))
            r_min = np.min(np.sqrt(px**2 + py**2))
            ax.text(0, -0.9 * r_max, f'$r_{{max}}$ = {r_max:.3f}',
                    fontsize=8, ha='center', color='#e67e22')

            lim = r_max * 1.4
            ax.set_xlim(-lim, lim)
            ax.set_ylim(-lim, lim)

        ax.set_aspect('equal')
        ax.set_xlabel(sec['xlabel'], fontsize=9)
        ax.set_ylabel(sec['ylabel'], fontsize=9)
        ax.set_title(sec['title'], fontsize=10, fontweight='bold')
        ax.grid(True, alpha=0.15)

        # Stable/unstable labels
        ax.text(0, 0.15, 'STABLE', fontsize=8, ha='center',
                color='#27ae60', fontweight='bold', alpha=0.5)

    plt.tight_layout()
    _save(fig, 'cross_section_gallery')


# ═══════════════════════════════════════════════════════════════
#  FIGURE 7 — Eccentricity & Anisotropy Analysis
# ═══════════════════════════════════════════════════════════════

def plot_eccentricity_analysis():
    """Bar chart of eccentricity measures plus shape classification."""

    fig, axes = plt.subplots(1, 3, figsize=(18, 6))
    fig.suptitle('Shape Analysis of Critical Manifold $\\mathcal{C}^*$',
                 fontsize=14, fontweight='bold', y=1.02)

    ecc = ELLIPSOID.eccentricities()
    aniso = ELLIPSOID.domain_anisotropy()

    # ── Panel (a): Semi-axes bar chart ──
    ax = axes[0]
    labels = ['$a$\n($\\delta_C$, Camouflage)', '$b$\n($\\delta_G$, Feature Gap)',
              '$c$\n($\\delta_A$, Activity)']
    values = [A, B, C]
    colors = ['#9b59b6', '#3498db', '#e74c3c']
    bars = ax.bar(labels, values, color=colors, edgecolor='#2c3e50',
                  linewidth=0.8, alpha=0.85, width=0.6)

    # Value annotations
    for bar, val in zip(bars, values):
        ax.text(bar.get_x() + bar.get_width()/2, val + 0.03,
                f'{val:.3f}', ha='center', fontsize=10, fontweight='bold')

    ax.set_ylabel('Semi-axis length $a_k = \\sqrt{\\alpha / w_k}$', fontsize=10)
    ax.set_title('(a) Semi-Axes of $\\mathcal{C}^*$\n'
                 '(longer = harder to detect)', fontsize=11, fontweight='bold')
    ax.set_ylim(0, max(values) * 1.3)
    ax.grid(axis='y', alpha=0.2)

    # Interpretation annotation
    ax.text(0.5, 0.92, f'Condition number: {aniso["condition_number"]:.2f}\n'
            f'Camouflage is {aniso["condition_number"]:.1f}× harder\n'
            f'to detect than Activity',
            transform=ax.transAxes, fontsize=8.5, va='top', ha='center',
            bbox=dict(boxstyle='round', facecolor='#fef9e7',
                      edgecolor='#f9e79f', alpha=0.9))

    # ── Panel (b): Eccentricity measures ──
    ax = axes[1]
    ecc_labels = ['$e_1$\n(primary)', '$e_2$\n(secondary)', '$e_3$\n(tertiary)',
                  '$f$\n(flattening)', '$\\eta$\n(anisotropy)']
    ecc_vals = [ecc['e1'], min(ecc['e2'], 3.0), ecc['e3'],
                ecc['flattening'], ecc['anisotropy']]
    ecc_colors = ['#e74c3c', '#e67e22', '#f1c40f', '#2ecc71', '#3498db']

    bars = ax.bar(ecc_labels, ecc_vals, color=ecc_colors,
                  edgecolor='#2c3e50', linewidth=0.8, alpha=0.85, width=0.55)

    for bar, val in zip(bars, ecc_vals):
        ax.text(bar.get_x() + bar.get_width()/2, val + 0.02,
                f'{val:.3f}', ha='center', fontsize=9, fontweight='bold')

    ax.set_ylabel('Value', fontsize=10)
    ax.set_title('(b) Eccentricity Measures\n'
                 '(0 = sphere, 1 = maximally deformed)', fontsize=11,
                 fontweight='bold')
    ax.set_ylim(0, max(ecc_vals) * 1.3)
    ax.grid(axis='y', alpha=0.2)

    # Shape classification
    if ecc['e1'] < 0.3:
        shape = 'Near-spherical'
    elif abs(A - B) < 0.1 * A:
        shape = 'Oblate spheroid'
    elif abs(B - C) < 0.1 * B:
        shape = 'Prolate spheroid'
    else:
        shape = 'Triaxial (scalene)'

    ax.text(0.5, 0.92, f'Shape class: {shape}\n'
            f'Axis ratios: {ecc["axis_ratios"][0]:.2f} : '
            f'{ecc["axis_ratios"][1]:.2f} : {ecc["axis_ratios"][2]:.2f}',
            transform=ax.transAxes, fontsize=8.5, va='top', ha='center',
            bbox=dict(boxstyle='round', facecolor='#eaf2f8',
                      edgecolor='#aed6f1', alpha=0.9))

    # ── Panel (c): Fisher weight → semi-axis inverse relationship ──
    ax = axes[2]
    w_range = np.linspace(0.05, 1.0, 100)
    a_range = np.sqrt(ALPHA / w_range)

    ax.plot(w_range, a_range, color='#2c3e50', linewidth=2.5, zorder=5)
    ax.fill_between(w_range, 0, a_range, color='#3498db', alpha=0.08)

    # Mark actual channel weights → axes
    channel_labels = ['$\\delta_C$', '$\\delta_G$', '$\\delta_A$']
    channel_colors = ['#9b59b6', '#3498db', '#e74c3c']
    for i, (w, a_val) in enumerate(zip(FISHER_WEIGHTS,
                                        ELLIPSOID.semi_axes)):
        ax.scatter([w], [a_val], color=channel_colors[i], s=120,
                   edgecolors='black', linewidths=1, zorder=15)
        ax.plot([w, w], [0, a_val], color=channel_colors[i], ls='--',
                alpha=0.5, lw=1)
        ax.plot([0, w], [a_val, a_val], color=channel_colors[i], ls='--',
                alpha=0.5, lw=1)
        ax.text(w + 0.02, a_val + 0.06, f'{channel_labels[i]}\n$w={w:.2f}$\n$a={a_val:.3f}$',
                fontsize=7.5, color=channel_colors[i], fontweight='bold',
                path_effects=[pe.withStroke(linewidth=1.5, foreground='white')])

    ax.set_xlabel('Fisher VR weight $w_k$', fontsize=10)
    ax.set_ylabel('Semi-axis $a_k = \\sqrt{\\alpha / w_k}$', fontsize=10)
    ax.set_title('(c) Weight → Axis Mapping\n'
                 '($a_k = \\sqrt{\\alpha / w_k}$, $\\alpha =' f'{ALPHA}$)',
                 fontsize=11, fontweight='bold')
    ax.set_xlim(0, 1.05)
    ax.set_ylim(0, max(a_range) * 1.1)
    ax.grid(True, alpha=0.15)

    plt.tight_layout()
    _save(fig, 'eccentricity_anisotropy_analysis')


# ═══════════════════════════════════════════════════════════════
#  FIGURE 8 — Nested Mahalanobis Contour Ellipsoids
# ═══════════════════════════════════════════════════════════════

def plot_nested_contours():
    """Nested ellipsoids at r = 0.5, 1.0 (C*), 1.5 with domain
    positions showing which domains are inside/outside C*."""

    fig = plt.figure(figsize=(12, 9))
    ax = fig.add_subplot(111, projection='3d')
    ax.set_facecolor('white')

    levels = [0.5, 1.0, 1.5]
    level_colors = ['#2ecc71', '#3498db', '#e74c3c']
    level_alphas = [0.04, 0.07, 0.03]
    level_labels = ['$r = 0.5$ (inner safe zone)',
                    '$r = 1.0$ ($\\mathcal{C}^*$ boundary)',
                    '$r = 1.5$ (danger zone)']

    n = 40
    u = np.linspace(0, 2 * np.pi, n)
    v = np.linspace(0, np.pi, n)

    for level, col, alph, label in zip(levels, level_colors,
                                       level_alphas, level_labels):
        x = level * A * np.outer(np.cos(u), np.sin(v))
        y = level * B * np.outer(np.sin(u), np.sin(v))
        z = level * C * np.outer(np.ones_like(u), np.cos(v))
        ax.plot_surface(x, y, z, alpha=alph, color=col,
                        edgecolor=col, linewidth=0.03, shade=True)

        # Equatorial ring
        theta = np.linspace(0, 2 * np.pi, 200)
        ax.plot(level * A * np.cos(theta),
                level * B * np.sin(theta),
                np.zeros_like(theta), color=col, alpha=0.3, lw=1.0,
                label=label)

    # Domain markers with inside/outside classification
    for name, pos in DOMAIN_POSITIONS.items():
        color = DOMAIN_COLORS[name]
        Q = ELLIPSOID.quadric_value(pos.reshape(1, -1))[0]
        marker = 'o' if Q <= 1.0 + 0.01 else '^'  # circle if inside
        label_suffix = ' (on $\\mathcal{C}^*$)' if abs(Q - 1.0) < 0.05 else ''

        ax.scatter([pos[0]], [pos[1]], [pos[2]], color=color, s=100,
                   marker=marker, edgecolors='black', linewidths=1, zorder=15)
        ax.text(pos[0]*1.25, pos[1]*1.25, pos[2]*1.25,
                name.replace('\n', ' ') + label_suffix,
                fontsize=7.5, color=color, fontweight='bold',
                path_effects=[pe.withStroke(linewidth=2, foreground='white')])

    # Equilibrium at origin
    ax.scatter([0], [0], [0], color='white', s=150, marker='o',
               edgecolors='#2c3e50', linewidths=2, zorder=20)
    ax.text(0.05, 0.05, -0.1, '$X^*$', fontsize=12, fontweight='bold',
            color='#2c3e50')

    ax.set_xlabel('$\\delta_C$', fontsize=10, labelpad=6)
    ax.set_ylabel('$\\delta_G$', fontsize=10, labelpad=6)
    ax.set_zlabel('$\\delta_A$', fontsize=10, labelpad=6)
    ax.set_title('Nested Mahalanobis Contour Ellipsoids\n'
                 'Inner safe zone → $\\mathcal{C}^*$ boundary → danger zone',
                 fontsize=12, fontweight='bold', pad=15)
    ax.view_init(elev=22, azim=-55)
    lim = 1.5 * max(A, B, C) * 1.2
    ax.set_xlim(-lim, lim)
    ax.set_ylim(-lim, lim)
    ax.set_zlim(-lim, lim)
    ax.xaxis.pane.fill = False
    ax.yaxis.pane.fill = False
    ax.zaxis.pane.fill = False
    ax.grid(True, alpha=0.15)
    ax.legend(fontsize=9, loc='upper left', framealpha=0.92)

    _save(fig, 'nested_contour_ellipsoids')


# ═══════════════════════════════════════════════════════════════
#  FIGURE 9 — Curvature Profile Along Meridians
# ═══════════════════════════════════════════════════════════════

def plot_curvature_profiles():
    """Plot Gaussian and mean curvature as a function of geodetic
    latitude along three principal meridians."""

    fig, axes = plt.subplots(1, 3, figsize=(18, 5.5))
    fig.suptitle('Curvature Profiles Along Principal Meridians of $\\mathcal{C}^*$',
                 fontsize=14, fontweight='bold', y=1.02)

    phi_range = np.linspace(-np.pi / 2, np.pi / 2, 200)

    meridian_configs = [
        {'lam': 0.0, 'label': '$\\lambda = 0$ (δ_C axis)',
         'color': '#9b59b6'},
        {'lam': np.pi / 2, 'label': '$\\lambda = \\pi/2$ (δ_G axis)',
         'color': '#3498db'},
        {'lam': np.pi / 4, 'label': '$\\lambda = \\pi/4$ (oblique)',
         'color': '#e67e22'},
    ]

    for idx, mc in enumerate(meridian_configs):
        ax = axes[idx]
        lam = mc['lam']

        # Generate surface points along this meridian
        pts = np.zeros((len(phi_range), 3))
        for i, phi in enumerate(phi_range):
            beta = np.arctan2(C * np.sin(phi), A * np.cos(phi))
            pts[i] = [A * np.cos(beta) * np.cos(lam),
                      B * np.cos(beta) * np.sin(lam),
                      C * np.sin(beta)]

        K = ELLIPSOID.gaussian_curvature(pts)
        H = ELLIPSOID.mean_curvature(pts)

        # Gaussian curvature
        ax.plot(np.degrees(phi_range), K, color=mc['color'], linewidth=2.5,
                label='Gaussian $K$', zorder=5)
        # Mean curvature
        ax.plot(np.degrees(phi_range), H, color=mc['color'], linewidth=2,
                linestyle='--', alpha=0.7, label='Mean $H$')

        # Mark poles and equator
        ax.axvline(0, color='gray', ls=':', alpha=0.3)
        ax.axvline(90, color='gray', ls=':', alpha=0.3)
        ax.axvline(-90, color='gray', ls=':', alpha=0.3)
        ax.text(0, ax.get_ylim()[1] * 0.02, 'equator', fontsize=7,
                ha='center', color='gray')
        ax.text(90, ax.get_ylim()[1] * 0.02, 'N pole', fontsize=7,
                ha='center', color='gray')
        ax.text(-90, ax.get_ylim()[1] * 0.02, 'S pole', fontsize=7,
                ha='center', color='gray')

        ax.set_xlabel('Geodetic latitude $\\phi$ (degrees)', fontsize=10)
        ax.set_ylabel('Curvature', fontsize=10)
        ax.set_title(f'({chr(97 + idx)}) Meridian {mc["label"]}',
                     fontsize=10, fontweight='bold')
        ax.legend(fontsize=8, loc='upper left')
        ax.grid(True, alpha=0.15)

        # Annotate K_max and K_min
        K_max = np.max(K)
        K_min = np.min(K)
        phi_max = phi_range[np.argmax(K)]
        phi_min = phi_range[np.argmin(K)]
        ax.scatter([np.degrees(phi_max)], [K_max], color='#e74c3c', s=60,
                   zorder=10, edgecolors='black', linewidths=0.5)
        ax.scatter([np.degrees(phi_min)], [K_min], color='#2ecc71', s=60,
                   zorder=10, edgecolors='black', linewidths=0.5)
        ax.annotate(f'$K_{{max}}={K_max:.3f}$',
                    xy=(np.degrees(phi_max), K_max),
                    xytext=(np.degrees(phi_max) - 25, K_max * 0.9),
                    fontsize=8, color='#e74c3c',
                    arrowprops=dict(arrowstyle='->', color='#e74c3c', lw=1))

    plt.tight_layout()
    _save(fig, 'curvature_profiles_meridians')


# ═══════════════════════════════════════════════════════════════
#  FIGURE 10 — Surface Normal Field + Principal Curvature Directions
# ═══════════════════════════════════════════════════════════════

def plot_normal_field():
    """2D projected view of the surface normal vectors and principal
    curvature directions on the equatorial cross-section."""

    fig, axes = plt.subplots(1, 2, figsize=(14, 6.5))
    fig.suptitle('Surface Geometry of $\\mathcal{C}^*$: Normals & Curvature Directions',
                 fontsize=14, fontweight='bold', y=1.02)

    # ── Panel (a): Normal vectors on the equatorial ellipse ──
    ax = axes[0]
    theta = np.linspace(0, 2 * np.pi, 200)
    ex, ey = A * np.cos(theta), B * np.sin(theta)
    ax.plot(ex, ey, color='#3498db', linewidth=2.5)
    ax.fill(ex, ey, color='#3498db', alpha=0.04)

    # Sample normal vectors at intervals
    n_normals = 20
    theta_n = np.linspace(0, 2 * np.pi, n_normals, endpoint=False)
    for th in theta_n:
        px = A * np.cos(th)
        py = B * np.sin(th)
        pt = np.array([px, py, 0.0])
        normal = ELLIPSOID.surface_normal(pt.reshape(1, -1))[0]
        nx, ny = normal[0], normal[1]
        scale = 0.25
        ax.arrow(px, py, scale * nx, scale * ny,
                 head_width=0.04, head_length=0.02,
                 fc='#e74c3c', ec='#c0392b', linewidth=1.2, zorder=10)

    # Draw curvature circles at key points for intuition
    # At the end of the long axis (x = a): radius of curvature = b²/a
    R_a = B**2 / A
    circle_a = plt.Circle((A - R_a, 0), R_a, fill=False,
                           color='#8e44ad', linewidth=1.5, linestyle='--',
                           alpha=0.5)
    ax.add_patch(circle_a)
    ax.text(A - R_a, R_a + 0.08, f'$R = b^2/a = {R_a:.3f}$',
            fontsize=7.5, color='#8e44ad', ha='center')

    # At the end of the short axis (y = b): radius of curvature = a²/b
    R_b = A**2 / B
    circle_b = plt.Circle((0, B - R_b), R_b, fill=False,
                           color='#27ae60', linewidth=1.5, linestyle='--',
                           alpha=0.5)
    ax.add_patch(circle_b)
    ax.text(-R_b - 0.08, B - R_b, f'$R = a^2/b = {R_b:.3f}$',
            fontsize=7.5, color='#27ae60', ha='right')

    ax.set_xlim(-2.0, 2.0)
    ax.set_ylim(-1.5, 1.5)
    ax.set_aspect('equal')
    ax.set_xlabel('$\\delta_C$ (Camouflage)', fontsize=10)
    ax.set_ylabel('$\\delta_G$ (Feature Gap)', fontsize=10)
    ax.set_title('(a) Surface Normals on Equatorial Section\n'
                 'Normal direction = gradient of detection',
                 fontsize=10, fontweight='bold')
    ax.grid(True, alpha=0.15)

    # Annotation
    ax.text(0.02, 0.97, 'Red arrows: $\\hat{n} = \\nabla Q / \\|\\nabla Q\\|$\n'
            'Dashed circles: radii of curvature\n'
            'Tight curvature → sensitive detection\n'
            'Flat curvature → blind-spot zone',
            transform=ax.transAxes, fontsize=7.5, va='top',
            bbox=dict(boxstyle='round', facecolor='#fef9e7',
                      edgecolor='#f9e79f', alpha=0.9))

    # ── Panel (b): Curvature κ as a function of angle ──
    ax2 = axes[1]
    n_pts = 300
    theta_c = np.linspace(0, 2 * np.pi, n_pts)
    kappa = np.zeros(n_pts)
    for i, th in enumerate(theta_c):
        px = A * np.cos(th)
        py = B * np.sin(th)
        # 2D curvature of ellipse: κ = ab / (a²sin²θ + b²cos²θ)^(3/2)
        denom = (A**2 * np.sin(th)**2 + B**2 * np.cos(th)**2)**(1.5)
        kappa[i] = A * B / (denom + 1e-30)

    ax2.plot(np.degrees(theta_c), kappa, color='#2c3e50', linewidth=2.5)
    ax2.fill_between(np.degrees(theta_c), 0, kappa, color='#3498db', alpha=0.08)

    # Mark maxima (at ends of short axis) and minima (at ends of long axis)
    idx_max = np.argmax(kappa)
    idx_min = np.argmin(kappa)
    ax2.scatter([np.degrees(theta_c[idx_max])], [kappa[idx_max]],
                color='#e74c3c', s=80, zorder=10, edgecolors='black', lw=0.8)
    ax2.scatter([np.degrees(theta_c[idx_min])], [kappa[idx_min]],
                color='#2ecc71', s=80, zorder=10, edgecolors='black', lw=0.8)

    ax2.annotate(f'$\\kappa_{{max}} = a/b^2 = {kappa[idx_max]:.3f}$\n(tight detection)',
                 xy=(np.degrees(theta_c[idx_max]), kappa[idx_max]),
                 xytext=(180, kappa[idx_max] * 0.85),
                 fontsize=8.5, color='#e74c3c', fontweight='bold',
                 arrowprops=dict(arrowstyle='->', color='#e74c3c', lw=1.2))

    ax2.annotate(f'$\\kappa_{{min}} = b/a^2 = {kappa[idx_min]:.3f}$\n(blind-spot zone)',
                 xy=(np.degrees(theta_c[idx_min]), kappa[idx_min]),
                 xytext=(90, kappa[idx_min] + (kappa[idx_max] - kappa[idx_min]) * 0.3),
                 fontsize=8.5, color='#2ecc71', fontweight='bold',
                 arrowprops=dict(arrowstyle='->', color='#2ecc71', lw=1.2))

    # θ labels
    ax2.set_xticks([0, 90, 180, 270, 360])
    ax2.set_xticklabels(['$0$\n($\\delta_C$ axis)', '$90$\n($\\delta_G$ axis)',
                         '$180$', '$270$', '$360$'])
    ax2.set_xlabel('Parametric angle $\\theta$ (degrees)', fontsize=10)
    ax2.set_ylabel('Curvature $\\kappa(\\theta)$', fontsize=10)
    ax2.set_title('(b) Curvature vs Angle on Equatorial Section\n'
                  '$\\kappa = ab / (a^2\\sin^2\\theta + b^2\\cos^2\\theta)^{3/2}$',
                  fontsize=10, fontweight='bold')
    ax2.grid(True, alpha=0.15)

    # κ ratio annotation
    k_ratio = kappa[idx_max] / (kappa[idx_min] + 1e-10)
    ax2.text(0.5, 0.15, f'Curvature ratio: $\\kappa_{{max}}/\\kappa_{{min}}$ = {k_ratio:.2f}\n'
             f'Detection sensitivity varies {k_ratio:.1f}× around $\\mathcal{{C}}^*$',
             transform=ax2.transAxes, fontsize=8.5, ha='center',
             bbox=dict(boxstyle='round', facecolor='#fadbd8',
                       edgecolor='#e74c3c', alpha=0.9))

    plt.tight_layout()
    _save(fig, 'surface_normals_curvature')


# ═══════════════════════════════════════════════════════════════
#  FIGURE 11 — Angular Separation Between Domains
# ═══════════════════════════════════════════════════════════════

def plot_angular_separation():
    """Polar plot showing angular separation Δσ from each domain
    to all others — how "far apart" in instability space."""

    fig, axes = plt.subplots(1, 2, figsize=(14, 6.5))

    names = list(DOMAIN_POSITIONS.keys())
    short_names = [n.replace('\n', ' ') for n in names]
    colors = [DOMAIN_COLORS[n] for n in names]
    positions = [DOMAIN_POSITIONS[n] for n in names]
    n_domains = len(names)

    # Compute angular separation matrix
    sigma_matrix = np.zeros((n_domains, n_domains))
    for i in range(n_domains):
        for j in range(n_domains):
            sigma_matrix[i, j] = ELLIPSOID.angular_separation(
                positions[i].reshape(1, -1),
                positions[j].reshape(1, -1)
            )[0]

    # ── Panel (a): Angular separation heatmap ──
    ax = axes[0]
    im = ax.imshow(np.degrees(sigma_matrix), cmap='viridis',
                   interpolation='nearest')
    ax.set_xticks(range(n_domains))
    ax.set_yticks(range(n_domains))
    ax.set_xticklabels(short_names, fontsize=8, rotation=45, ha='right')
    ax.set_yticklabels(short_names, fontsize=8)

    for i in range(n_domains):
        for j in range(n_domains):
            val = np.degrees(sigma_matrix[i, j])
            color = 'white' if val > 90 else 'black'
            ax.text(j, i, f'{val:.1f}°', ha='center', va='center',
                    fontsize=8, color=color, fontweight='bold')

    cbar = fig.colorbar(im, ax=ax, shrink=0.8)
    cbar.set_label('Angular separation $\\Delta\\sigma$ (degrees)', fontsize=10)
    ax.set_title('(a) Angular Separation Matrix\n'
                 '(angle at centre of $\\mathcal{C}^*$ in quadric metric)',
                 fontsize=10, fontweight='bold')

    # ── Panel (b): Radar/polar chart for each domain ──
    ax2 = axes[1]

    # Stacked bar chart showing each domain's angular distances to others
    x = np.arange(n_domains)
    width = 0.12
    offsets = np.linspace(-(n_domains - 1) * width / 2,
                          (n_domains - 1) * width / 2, n_domains)

    for i in range(n_domains):
        # Sort by distance (skip self)
        dists = [(j, np.degrees(sigma_matrix[i, j]))
                 for j in range(n_domains) if j != i]
        dists.sort(key=lambda x: x[1])
        nearest_name = short_names[dists[0][0]]
        farthest_name = short_names[dists[-1][0]]

        # Bar for this domain showing distances to all others
        vals = [np.degrees(sigma_matrix[i, j]) for j in range(n_domains)]
        ax2.bar(x + offsets[i], vals, width, color=colors[i],
                alpha=0.7, edgecolor='#2c3e50', linewidth=0.5)

    ax2.set_xticks(x)
    ax2.set_xticklabels(short_names, fontsize=8, rotation=45, ha='right')
    ax2.set_ylabel('$\\Delta\\sigma$ (degrees)', fontsize=10)
    ax2.set_title('(b) Angular Distances from Each Domain\n'
                  '(colour = source domain)',
                  fontsize=10, fontweight='bold')
    ax2.grid(axis='y', alpha=0.2)

    # Legend
    from matplotlib.patches import Patch
    legend_elements = [Patch(facecolor=colors[i], edgecolor='#2c3e50',
                             label=short_names[i]) for i in range(n_domains)]
    ax2.legend(handles=legend_elements, fontsize=7, loc='upper right',
               ncol=2, framealpha=0.9)

    plt.tight_layout()
    _save(fig, 'angular_separation_domains')


# ═══════════════════════════════════════════════════════════════
#  FIGURE 12 — Volume & Surface Area as f(α)
# ═══════════════════════════════════════════════════════════════

def plot_volume_surface_vs_alpha():
    """How the critical manifold C* swells as the spectral threshold
    α increases — illustrating why larger α tolerates more deviation."""

    fig, axes = plt.subplots(1, 2, figsize=(14, 5.5))
    fig.suptitle('Critical Manifold Size as a Function of Spectral Threshold $\\alpha$',
                 fontsize=14, fontweight='bold', y=1.02)

    alpha_range = np.linspace(0.05, 1.0, 80)
    volumes = np.zeros_like(alpha_range)
    areas = np.zeros_like(alpha_range)
    max_axes = np.zeros_like(alpha_range)
    min_axes = np.zeros_like(alpha_range)

    for i, al in enumerate(alpha_range):
        ell = EllipsoidGeometry.from_fisher_weights(FISHER_WEIGHTS, alpha=al)
        volumes[i] = ell.volume()
        areas[i] = ell.surface_area()
        max_axes[i] = ell.semi_axes.max()
        min_axes[i] = ell.semi_axes.min()

    # ── Panel (a): Volume + Surface area ──
    ax = axes[0]
    ln1 = ax.plot(alpha_range, volumes, color='#3498db', linewidth=2.5,
                  label='Volume $V = \\frac{4}{3}\\pi abc$')
    ax.fill_between(alpha_range, 0, volumes, color='#3498db', alpha=0.08)
    ax.set_xlabel('Spectral threshold $\\alpha$', fontsize=10)
    ax.set_ylabel('Volume', fontsize=10, color='#3498db')
    ax.tick_params(axis='y', labelcolor='#3498db')

    # Mark actual α
    v_actual = ELLIPSOID.volume()
    ax.axvline(ALPHA, color='#e74c3c', ls='--', alpha=0.5)
    ax.scatter([ALPHA], [v_actual], color='#e74c3c', s=80,
               edgecolors='black', zorder=10)
    ax.text(ALPHA + 0.02, v_actual, f'$\\alpha={ALPHA}$\n$V={v_actual:.3f}$',
            fontsize=8, color='#e74c3c', fontweight='bold')

    ax2 = ax.twinx()
    ln2 = ax2.plot(alpha_range, areas, color='#e67e22', linewidth=2.5,
                   linestyle='--', label='Surface area $S$')
    ax2.set_ylabel('Surface area', fontsize=10, color='#e67e22')
    ax2.tick_params(axis='y', labelcolor='#e67e22')

    lns = ln1 + ln2
    labs = [l.get_label() for l in lns]
    ax.legend(lns, labs, fontsize=9, loc='upper left')
    ax.set_title('(a) Volume & Surface Area vs $\\alpha$',
                 fontsize=11, fontweight='bold')
    ax.grid(True, alpha=0.15)

    # ── Panel (b): Semi-axis range (condition number) ──
    ax3 = axes[1]
    ax3.fill_between(alpha_range, min_axes, max_axes, color='#3498db',
                     alpha=0.15, label='Axis range $[a_{\\min}, a_{\\max}]$')
    ax3.plot(alpha_range, max_axes, color='#9b59b6', linewidth=2,
             label='$a_{\\max}$ ($\\delta_C$, Camouflage)')
    ax3.plot(alpha_range, min_axes, color='#e74c3c', linewidth=2,
             label='$a_{\\min}$ ($\\delta_A$, Activity)')

    # Condition number on twin axis
    cond = max_axes / (min_axes + 1e-10)
    ax4 = ax3.twinx()
    ax4.plot(alpha_range, cond, color='#7f8c8d', linewidth=2, linestyle=':',
             label='Condition number $a_{max}/a_{min}$')
    ax4.set_ylabel('Condition number', fontsize=10, color='#7f8c8d')
    ax4.tick_params(axis='y', labelcolor='#7f8c8d')

    ax3.axvline(ALPHA, color='#e74c3c', ls='--', alpha=0.5)

    ax3.set_xlabel('Spectral threshold $\\alpha$', fontsize=10)
    ax3.set_ylabel('Semi-axis length', fontsize=10)
    ax3.set_title('(b) Semi-Axis Range & Condition Number\n'
                  '(condition number is constant: depends only on weight ratios)',
                  fontsize=11, fontweight='bold')
    ax3.legend(fontsize=8, loc='upper left')
    ax3.grid(True, alpha=0.15)

    plt.tight_layout()
    _save(fig, 'volume_surface_vs_alpha')


# ─────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("=" * 60)
    print("  Generating Extended Geometry of Systemic Collapse Figures")
    print("=" * 60)
    print()

    print("Figure 4: Gaussian Curvature Heatmap on C*")
    plot_curvature_heatmap()
    print()

    print("Figure 5: Geodesic Paths Between Six Domains on C*")
    plot_geodesic_paths()
    print()

    print("Figure 6: Great Elliptic Cross-Section Gallery")
    plot_cross_section_gallery()
    print()

    print("Figure 7: Eccentricity & Anisotropy Analysis")
    plot_eccentricity_analysis()
    print()

    print("Figure 8: Nested Mahalanobis Contour Ellipsoids")
    plot_nested_contours()
    print()

    print("Figure 9: Curvature Profiles Along Meridians")
    plot_curvature_profiles()
    print()

    print("Figure 10: Surface Normals & Curvature Directions")
    plot_normal_field()
    print()

    print("Figure 11: Angular Separation Between Domains")
    plot_angular_separation()
    print()

    print("Figure 12: Volume & Surface Area vs α")
    plot_volume_surface_vs_alpha()
    print()

    print("=" * 60)
    print("  All extended geometry figures saved to:")
    print(f"  {FIGDIR}")
    print("=" * 60)
