#!/usr/bin/env python3
"""
AMTTP System Architecture — IEEE-Format Vector PDF Export
=========================================================
Generates a high-resolution, infinitely-zoomable vector PDF of all
architecture diagrams.  Every element is drawn with matplotlib's
patch / annotation API so the output is pure vector art (no raster).

Usage:
    python docs/export_architecture_pdf.py          # → docs/AMTTP_System_Architecture.pdf
    python docs/export_architecture_pdf.py -o out.pdf

Requirements:
    pip install matplotlib numpy
"""

from __future__ import annotations
import argparse, textwrap, os, sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch, Rectangle, Patch
from matplotlib.backends.backend_pdf import PdfPages
import matplotlib.patheffects as pe
import numpy as np

# ── IEEE page geometry ────────────────────────────────────────────────────────
PAGE_W, PAGE_H = 8.5, 11        # US-Letter
MARGIN_L, MARGIN_R = 0.75, 0.75
MARGIN_T, MARGIN_B = 0.90, 0.75
CONTENT_W = PAGE_W - MARGIN_L - MARGIN_R
CONTENT_H = PAGE_H - MARGIN_T - MARGIN_B
DPI = 300  # metadata only; actual PDF is vector

# ── Colour palette ────────────────────────────────────────────────────────────
C = dict(
    bg        = "#ffffff",
    primary   = "#1a237e",   # deep indigo
    secondary = "#283593",
    accent    = "#0d47a1",
    header_bg = "#e8eaf6",
    layer_presentation = "#e3f2fd",
    layer_proxy        = "#fff3e0",
    layer_backend      = "#e8f5e9",
    layer_blockchain   = "#fce4ec",
    layer_data         = "#f3e5f5",
    layer_zknaf        = "#fff8e1",
    box_fe    = "#42a5f5",
    box_be    = "#66bb6a",
    box_bc    = "#ef5350",
    box_db    = "#ab47bc",
    box_proxy = "#ffa726",
    box_ml    = "#26c6da",
    box_infra = "#78909c",
    text      = "#212121",
    text_light= "#ffffff",
    border    = "#37474f",
    arrow     = "#455a64",
    decision_allow  = "#4caf50",
    decision_review = "#ff9800",
    decision_escrow = "#ff5722",
    decision_block  = "#f44336",
    rbac1 = "#bbdefb", rbac2 = "#90caf9", rbac3 = "#64b5f6",
    rbac4 = "#42a5f5", rbac5 = "#1e88e5", rbac6 = "#1565c0",
)

# ── Font config (IEEE uses Times; fallback to serif) ──────────────────────────
FONT_FAMILY = "serif"
plt.rcParams.update({
    "font.family": FONT_FAMILY,
    "font.serif": ["DejaVu Serif", "Times New Roman", "Times", "serif"],
    "mathtext.fontset": "cm",
    "pdf.fonttype": 3,        # Type 3 (PostScript outlines) — avoids fontTools subsetting bugs
    "ps.fonttype": 3,
    "axes.unicode_minus": False,
})

TITLE_SIZE   = 16
SECTION_SIZE = 12
LABEL_SIZE   = 7.5
SMALL_SIZE   = 6.5
TINY_SIZE    = 5.5
CAPTION_SIZE = 8.5

# ── Helpers ───────────────────────────────────────────────────────────────────

def _new_fig(title: str = "", *, landscape: bool = False):
    """Return (fig, ax) sized exactly to IEEE page with invisible axes."""
    if landscape:
        fig = plt.figure(figsize=(PAGE_H, PAGE_W), dpi=DPI)
    else:
        fig = plt.figure(figsize=(PAGE_W, PAGE_H), dpi=DPI)
    fig.patch.set_facecolor(C["bg"])
    ax = fig.add_axes([0, 0, 1, 1])
    ax.set_xlim(0, PAGE_W if not landscape else PAGE_H)
    ax.set_ylim(0, PAGE_H if not landscape else PAGE_W)
    ax.axis("off")
    ax.set_facecolor(C["bg"])
    if title:
        ax.text(PAGE_W / 2 if not landscape else PAGE_H / 2,
                (PAGE_H if not landscape else PAGE_W) - 0.5,
                title, ha="center", va="top",
                fontsize=SECTION_SIZE, fontweight="bold", color=C["primary"])
    return fig, ax


def _box(ax, x, y, w, h, label, *, color="#ffffff", border=None,
         fontsize=LABEL_SIZE, text_color=None, alpha=1.0, fontstyle="normal",
         sublabels=None, radius=0.02, lw=0.8):
    """Draw a rounded box with centred label and optional sub-labels."""
    border = border or C["border"]
    text_color = text_color or C["text"]
    bx = FancyBboxPatch((x, y), w, h, boxstyle=f"round,pad=0,rounding_size={radius}",
                        facecolor=color, edgecolor=border, linewidth=lw, alpha=alpha,
                        zorder=2)
    ax.add_patch(bx)
    # main label
    ty = y + h / 2 if not sublabels else y + h - h * 0.22
    ax.text(x + w / 2, ty, label, ha="center", va="center",
            fontsize=fontsize, fontweight="bold", color=text_color,
            fontstyle=fontstyle, zorder=3)
    if sublabels:
        for i, sl in enumerate(sublabels):
            ax.text(x + w / 2, ty - (i + 1) * (fontsize * 0.016),
                    sl, ha="center", va="center",
                    fontsize=fontsize * 0.82, color=text_color, zorder=3)
    return bx


def _layer_band(ax, x, y, w, h, label, *, color, label_color=None):
    """Semi-transparent horizontal band spanning content area."""
    label_color = label_color or C["primary"]
    rect = Rectangle((x, y), w, h, facecolor=color, edgecolor="none",
                      alpha=0.45, zorder=0)
    ax.add_patch(rect)
    ax.text(x + 0.12, y + h - 0.12, label, fontsize=SMALL_SIZE,
            fontweight="bold", color=label_color, va="top", zorder=1)


def _arrow(ax, x1, y1, x2, y2, *, color=None, style="-|>", lw=0.8, zorder=4):
    color = color or C["arrow"]
    ax.annotate("", xy=(x2, y2), xytext=(x1, y1),
                arrowprops=dict(arrowstyle=style, color=color, lw=lw),
                zorder=zorder)


def _multiline(ax, x, y, lines, *, fontsize=LABEL_SIZE, color=None,
               ha="left", va="top", spacing=1.35):
    color = color or C["text"]
    ax.text(x, y, "\n".join(lines), ha=ha, va=va, fontsize=fontsize,
            color=color, linespacing=spacing, zorder=5)


# ══════════════════════════════════════════════════════════════════════════════
#  PAGE 1 — Title page
# ══════════════════════════════════════════════════════════════════════════════

def page_title(pdf):
    fig, ax = _new_fig()
    cx = PAGE_W / 2

    # IEEE-style title block
    ax.text(cx, 8.8, "AMTTP System Architecture", ha="center", va="center",
            fontsize=20, fontweight="bold", color=C["primary"])
    ax.text(cx, 8.35, "Anti-Money Laundering Transaction Trust Protocol",
            ha="center", va="center", fontsize=11, color=C["secondary"])

    ax.plot([cx - 2.5, cx + 2.5], [8.05, 8.05], color=C["primary"], lw=0.8)

    ax.text(cx, 7.75, "Version 3.0  —  February 2026", ha="center",
            fontsize=9, color=C["text"])
    ax.text(cx, 7.45, "DevOps Engineering", ha="center",
            fontsize=9, fontstyle="italic", color=C["text"])

    ax.plot([cx - 2.5, cx + 2.5], [7.15, 7.15], color=C["primary"], lw=0.8)

    # Abstract-style summary
    abstract = textwrap.fill(
        "AMTTP is a comprehensive compliance and risk-management platform for "
        "blockchain transactions.  It combines a stacked-ensemble ML pipeline "
        "(GraphSAGE + LGBM + XGBoost + Linear Meta-Learner), real-time sanctions "
        "screening (OFAC, HMT, EU, UN), geographic risk assessment (FATF), "
        "zero-knowledge proofs (zkNAF), FCA/AMLD6 regulatory compliance, and "
        "on-chain smart-contract enforcement via Ethereum.  The platform supports "
        "multiple deployment modes including unified Docker containers, full-stack "
        "microservices with Cloudflare tunnels, and bare-metal gateway configurations.",
        width=80)
    ax.text(cx, 6.75, "Abstract", ha="center", fontsize=9,
            fontweight="bold", color=C["primary"])
    ax.text(cx, 6.50, abstract, ha="center", va="top", fontsize=7.5,
            color=C["text"], fontstyle="italic", linespacing=1.4,
            family="serif")

    # Table of figures
    tof_y = 4.6
    ax.text(cx, tof_y, "Figures", ha="center", fontsize=10,
            fontweight="bold", color=C["primary"])
    figures = [
        "Fig. 1   System Overview — Layered Architecture",
        "Fig. 2   Backend Services & Port Map",
        "Fig. 3   Transaction Evaluation Flow",
        "Fig. 4   ML Stacked-Ensemble Pipeline",
        "Fig. 5   Compliance Decision Engine",
        "Fig. 6   Smart Contract Architecture",
        "Fig. 7   Full-Stack Docker Deployment",
        "Fig. 8   Production Deployment (Cloudflare Tunnel)",
        "Fig. 9   RBAC Role Hierarchy",
        "Fig. 10  Security Layers",
    ]
    for i, f in enumerate(figures):
        ax.text(cx, tof_y - 0.30 - i * 0.22, f, ha="center",
                fontsize=7.5, color=C["text"])

    # Footer
    ax.text(cx, 0.4, "© 2026 AMTTP Project  ·  All rights reserved  ·  Vector PDF — no raster content",
            ha="center", fontsize=6, color="#9e9e9e")

    pdf.savefig(fig)
    plt.close(fig)


# ══════════════════════════════════════════════════════════════════════════════
#  PAGE 2 — Fig 1: System Overview (Layered Architecture)
# ══════════════════════════════════════════════════════════════════════════════

def page_system_overview(pdf):
    fig, ax = _new_fig("Fig. 1 — AMTTP Platform: Layered Architecture Overview")

    LX = 0.6     # left x
    RW = 7.3     # total width
    RX = LX + RW # right x

    # ── Layer 1: Presentation ──
    ly = 9.2; lh = 1.55
    _layer_band(ax, LX, ly, RW, lh, "PRESENTATION LAYER", color=C["layer_presentation"])
    bw, bh = 2.1, 1.1
    gap = (RW - 3 * bw) / 4
    for i, (name, port, bullets) in enumerate([
        ("Flutter Consumer", "Port 3010", ["MetaMask Wallet", "Transfer / Balance", "zkNAF Proofs", "Safe Wallet", "Cross-Chain"]),
        ("Next.js War Room", "Port 3006", ["Login / Auth", "Compliance View", "Detection Studio", "Graph Explorer", "Vault / Escrow"]),
        ("External Clients", "SDK / REST", ["TypeScript SDK", "REST / JSON API", "WebSocket Events", "Webhooks / SSE"]),
    ]):
        bx = LX + gap + i * (bw + gap)
        by = ly + (lh - bh) / 2
        _box(ax, bx, by, bw, bh, name, color=C["box_fe"],
             text_color=C["text_light"], fontsize=LABEL_SIZE)
        ax.text(bx + bw / 2, by + bh - 0.14, port, ha="center",
                fontsize=TINY_SIZE, color="#e3f2fd", zorder=5)
        for j, b in enumerate(bullets):
            ax.text(bx + bw / 2, by + bh * 0.52 - j * 0.135,
                    f"• {b}", ha="center", fontsize=TINY_SIZE,
                    color="#e3f2fd", zorder=5)

    # ── Layer 2: Nginx Proxy ──
    ly2 = 8.4; lh2 = 0.7
    _layer_band(ax, LX, ly2, RW, lh2, "NGINX REVERSE PROXY / GATEWAY",
                color=C["layer_proxy"])
    routes_l = "/  → Flutter    /api/ → Orchestrator    /ml/ → Risk Engine    /zknaf/ → zkNAF"
    routes_r = "/warroom/ → Next.js   /sanctions/  /monitoring/  /geo/  /policy/  /explain/  /graph/  /fca/"
    ax.text(LX + RW / 2, ly2 + lh2 * 0.65, routes_l, ha="center",
            fontsize=TINY_SIZE, color=C["text"], zorder=3)
    ax.text(LX + RW / 2, ly2 + lh2 * 0.28, routes_r, ha="center",
            fontsize=TINY_SIZE, color=C["text"], zorder=3)
    ax.text(RX - 0.15, ly2 + lh2 / 2, "Port 80 / 8888", ha="right", va="center",
            fontsize=TINY_SIZE, color=C["text"], fontstyle="italic", zorder=3)

    # Arrow: Presentation → Proxy
    _arrow(ax, LX + RW / 2, ly, LX + RW / 2, ly2 + lh2)

    # ── Layer 3: Backend Services ──
    ly3 = 5.2; lh3 = 3.05
    _layer_band(ax, LX, ly3, RW, lh3, "BACKEND SERVICES LAYER",
                color=C["layer_backend"])
    _arrow(ax, LX + RW / 2, ly2, LX + RW / 2, ly3 + lh3)

    services = [
        # row 1
        [("Orchestrator", "8007", ["Profile Mgmt", "Tx Evaluate", "API Keys"]),
         ("ML Risk Engine", "8000", ["GraphSAGE", "LGBM + XGBoost", "Meta-Learner"]),
         ("Sanctions", "8004", ["OFAC / HMT", "EU / UN Lists", "Batch Check"]),
         ("Monitoring", "8005", ["6 AML Rules", "Alert Mgmt", "Statistics"])],
        # row 2
        [("Geographic Risk", "8006", ["FATF Lists", "Country / IP", "Tax Havens"]),
         ("Integrity", "8008", ["UI Verify", "Tamper Detect", "Hash Check"]),
         ("Explainability", "8009", ["XAI Engine", "Typologies", "Tx Explain"]),
         ("zkNAF Demo", "8010", ["ZK Proofs", "KYC Creds", "Risk Range"])],
        # row 3
        [("FCA Compliance", "8002", ["SAR Submit", "Travel Rule", "FCA Reports"]),
         ("Policy Service", "8003", ["Policy CRUD", "White/Blacklist", "Evaluate"]),
         ("Oracle Service", "3001", ["KYC / Risk", "PEP / EDD", "Bulk Score"]),
         ("Graph API", "8001", ["Entity Rel", "Clustering", "Memgraph"])],
    ]
    sbw, sbh = 1.6, 0.78
    sgap = (RW - 4 * sbw) / 5
    for row_i, row in enumerate(services):
        for col_i, (sname, sport, sbul) in enumerate(row):
            sx = LX + sgap + col_i * (sbw + sgap)
            sy = ly3 + lh3 - 0.35 - row_i * (sbh + 0.15)
            _box(ax, sx, sy, sbw, sbh, sname, color=C["box_be"],
                 text_color=C["text_light"], fontsize=TINY_SIZE + 0.5)
            ax.text(sx + sbw / 2, sy + sbh - 0.10, f":{sport}",
                    ha="center", fontsize=TINY_SIZE - 0.5,
                    color="#c8e6c9", zorder=5)
            for j, b in enumerate(sbul):
                ax.text(sx + sbw / 2, sy + sbh * 0.48 - j * 0.115,
                        f"• {b}", ha="center", fontsize=TINY_SIZE - 0.5,
                        color="#e8f5e9", zorder=5)

    # ── Layer 4: Blockchain ──
    ly4 = 3.35; lh4 = 1.7
    _layer_band(ax, LX, ly4, RW, lh4, "BLOCKCHAIN LAYER — Ethereum",
                color=C["layer_blockchain"])
    _arrow(ax, LX + RW / 2, ly3, LX + RW / 2, ly4 + lh4)

    contracts_r1 = [
        ("AMTTPCore\n(+ Secure,\nStreamlined)", C["box_bc"]),
        ("PolicyMgr\n+ Engine", C["box_bc"]),
        ("Dispute\nResolver", C["box_bc"]),
        ("AMTTPNFT", C["box_bc"]),
    ]
    contracts_r2 = [
        ("CrossChain\n(LayerZero)", C["box_bc"]),
        ("RiskRouter\n+ Router", C["box_bc"]),
        ("CoreZkNAF\n+ Verifiers", "#ff8a65"),
        ("SafeModule\n+ Biconomy", "#ff8a65"),
    ]
    cbw, cbh = 1.5, 0.55
    cgap = (RW - 4 * cbw) / 5
    for row_i, crow in enumerate([contracts_r1, contracts_r2]):
        for col_i, (cname, ccol) in enumerate(crow):
            cx_ = LX + cgap + col_i * (cbw + cgap)
            cy_ = ly4 + lh4 - 0.18 - row_i * (cbh + 0.12)
            _box(ax, cx_, cy_, cbw, cbh, cname, color=ccol,
                 text_color=C["text_light"], fontsize=TINY_SIZE)

    # ── Layer 5: Data Storage ──
    ly5 = 1.6; lh5 = 1.6
    _layer_band(ax, LX, ly5, RW, lh5, "DATA STORAGE LAYER",
                color=C["layer_data"])
    _arrow(ax, LX + RW / 2, ly4, LX + RW / 2, ly5 + lh5)

    stores = [
        ("MongoDB\n:27017", C["box_db"]),
        ("MinIO (S3)\n:9000", C["box_db"]),
        ("Redis\n:6379", C["box_db"]),
        ("Helia (IPFS)\n:5001", C["box_db"]),
        ("Memgraph\n:7687", C["box_db"]),
        ("Vault\n:8200", C["box_infra"]),
        ("Hardhat\n:8545", C["box_infra"]),
    ]
    dbw, dbh = 0.88, 0.55
    dgap = (RW - 7 * dbw) / 8
    for row_i in range(2):
        items = stores[:4] if row_i == 0 else stores[4:]
        rw_items = len(items)
        row_dgap = (RW - rw_items * dbw) / (rw_items + 1)
        for col_i, (dname, dcol) in enumerate(items):
            dx = LX + row_dgap + col_i * (dbw + row_dgap)
            dy = ly5 + lh5 - 0.2 - row_i * (dbh + 0.18)
            _box(ax, dx, dy, dbw, dbh, dname, color=dcol,
                 text_color=C["text_light"], fontsize=TINY_SIZE)

    # Caption
    ax.text(PAGE_W / 2, 1.15,
            "Fig. 1. Five-layer AMTTP platform architecture.  12 backend micro-services,\n"
            "15 smart contracts, and 7 data stores, fronted by Flutter and Next.js UIs.",
            ha="center", va="top", fontsize=CAPTION_SIZE, fontstyle="italic",
            color=C["text"])

    pdf.savefig(fig)
    plt.close(fig)


# ══════════════════════════════════════════════════════════════════════════════
#  PAGE 3 — Fig 2: Backend Services Port Map
# ══════════════════════════════════════════════════════════════════════════════

def page_services_portmap(pdf):
    fig, ax = _new_fig("Fig. 2 — Backend Services & Port Map")

    # Table header
    cols = ["Service", "Technology", "Port", "Health", "Description"]
    col_x = [1.0, 2.8, 4.2, 5.0, 6.1]
    col_w = [1.7, 1.3, 0.7, 1.0, 2.2]
    ty = 9.4
    row_h = 0.30

    # Header row
    for cx_, cw, cl in zip(col_x, col_w, cols):
        rect = Rectangle((cx_, ty), cw, row_h, facecolor=C["primary"],
                          edgecolor=C["border"], lw=0.5, zorder=2)
        ax.add_patch(rect)
        ax.text(cx_ + cw / 2, ty + row_h / 2, cl, ha="center", va="center",
                fontsize=SMALL_SIZE, fontweight="bold", color="white", zorder=3)

    services = [
        ("ML Risk Engine",     "Python / FastAPI", "8000", "/health", "Stacked ensemble scoring"),
        ("Graph API",          "Python / FastAPI", "8001", "/health", "Memgraph entity relationships"),
        ("FCA Compliance",     "Python / FastAPI", "8002", "/compliance/health", "SAR, Travel Rule, FCA reports"),
        ("Policy Service",     "Python / FastAPI", "8003", "/health", "Policy CRUD, whitelist/blacklist"),
        ("Sanctions",          "Python / FastAPI", "8004", "/health", "OFAC/HMT/EU/UN screening"),
        ("Monitoring",         "Python / FastAPI", "8005", "/health", "6 AML rules, alert management"),
        ("Geographic Risk",    "Python / FastAPI", "8006", "/health", "FATF, country / IP risk"),
        ("Orchestrator",       "Python / FastAPI", "8007", "/health", "Central compliance coordinator"),
        ("Integrity",          "Python / FastAPI", "8008", "/health", "UI tamper detection"),
        ("Explainability",     "Python / FastAPI", "8009", "/health", "ML XAI, typology analysis"),
        ("zkNAF Demo",         "Python / FastAPI", "8010", "/zknaf/health", "Zero-knowledge proofs"),
        ("Oracle Service",     "Node.js / Express","3001", "/health", "KYC, PEP, EDD, bulk scoring"),
    ]

    for i, (sn, st, sp, sh, sd) in enumerate(services):
        ry = ty - (i + 1) * row_h
        bg = C["header_bg"] if i % 2 == 0 else C["bg"]
        for cx_, cw in zip(col_x, col_w):
            rect = Rectangle((cx_, ry), cw, row_h, facecolor=bg,
                              edgecolor="#bdbdbd", lw=0.3, zorder=2)
            ax.add_patch(rect)
        vals = [sn, st, sp, sh, sd]
        for cx_, cw, v in zip(col_x, col_w, vals):
            ax.text(cx_ + cw / 2, ry + row_h / 2, v, ha="center", va="center",
                    fontsize=TINY_SIZE, color=C["text"], zorder=3)

    # Infrastructure table
    iy = ty - (len(services) + 1) * row_h - 0.5
    ax.text(PAGE_W / 2, iy + 0.35, "Infrastructure Services", ha="center",
            fontsize=LABEL_SIZE, fontweight="bold", color=C["primary"])

    infra_cols = ["Service", "Port(s)", "Credentials (Dev)"]
    infra_x = [1.8, 3.8, 5.3]
    infra_w = [1.8, 1.3, 2.5]
    for cx_, cw, cl in zip(infra_x, infra_w, infra_cols):
        rect = Rectangle((cx_, iy), cw, row_h, facecolor=C["primary"],
                          edgecolor=C["border"], lw=0.5, zorder=2)
        ax.add_patch(rect)
        ax.text(cx_ + cw / 2, iy + row_h / 2, cl, ha="center", va="center",
                fontsize=SMALL_SIZE, fontweight="bold", color="white", zorder=3)

    infra = [
        ("MongoDB",         "27017",       "admin : changeme"),
        ("Redis",           "6379",        "(none)"),
        ("MinIO (S3-compat)","9000, 9001", "localtest : localtest123"),
        ("Helia / IPFS",    "5001, 8080",  "(none)"),
        ("Memgraph",        "7687",        "(none)"),
        ("Memgraph Lab",    "3000",        "(none)"),
        ("HashiCorp Vault", "8200",        "root token: root"),
        ("Hardhat Node",    "8545",        "(none)"),
    ]
    for i, (sn, sp, sc) in enumerate(infra):
        ry = iy - (i + 1) * row_h
        bg = C["header_bg"] if i % 2 == 0 else C["bg"]
        for cx_, cw in zip(infra_x, infra_w):
            rect = Rectangle((cx_, ry), cw, row_h, facecolor=bg,
                              edgecolor="#bdbdbd", lw=0.3, zorder=2)
            ax.add_patch(rect)
        for cx_, cw, v in zip(infra_x, infra_w, [sn, sp, sc]):
            ax.text(cx_ + cw / 2, ry + row_h / 2, v, ha="center", va="center",
                    fontsize=TINY_SIZE, color=C["text"], zorder=3)

    # Nginx routes table
    ny = iy - (len(infra) + 1) * row_h - 0.5
    ax.text(PAGE_W / 2, ny + 0.35, "Nginx Gateway Route Map", ha="center",
            fontsize=LABEL_SIZE, fontweight="bold", color=C["primary"])

    route_cols = ["Route", "Upstream", "Route", "Upstream"]
    route_x = [1.2, 2.5, 4.7, 6.0]
    route_w = [1.2, 1.8, 1.2, 1.8]
    for cx_, cw, cl in zip(route_x, route_w, route_cols):
        rect = Rectangle((cx_, ny), cw, row_h, facecolor=C["box_proxy"],
                          edgecolor=C["border"], lw=0.5, zorder=2)
        ax.add_patch(rect)
        ax.text(cx_ + cw / 2, ny + row_h / 2, cl, ha="center", va="center",
                fontsize=SMALL_SIZE, fontweight="bold", color="white", zorder=3)

    routes_left = [
        ("/", "Flutter (static)"),
        ("/warroom/", "Next.js War Room"),
        ("/api/", "Orchestrator :8007"),
        ("/ml/", "Risk Engine :8000"),
        ("/sanctions/", "Sanctions :8004"),
        ("/monitoring/", "Monitoring :8005"),
        ("/geo/", "Geographic Risk :8006"),
    ]
    routes_right = [
        ("/zknaf/", "zkNAF :8010"),
        ("/policy/", "Policy :8003"),
        ("/integrity/", "Integrity :8008"),
        ("/fca/", "FCA Compliance :8002"),
        ("/explain/", "Explainability :8009"),
        ("/graph/", "Graph API :8001"),
        ("/_next/", "Next.js Assets"),
    ]
    for i in range(max(len(routes_left), len(routes_right))):
        ry = ny - (i + 1) * row_h
        bg = C["header_bg"] if i % 2 == 0 else C["bg"]
        for cx_, cw in zip(route_x, route_w):
            rect = Rectangle((cx_, ry), cw, row_h, facecolor=bg,
                              edgecolor="#bdbdbd", lw=0.3, zorder=2)
            ax.add_patch(rect)
        if i < len(routes_left):
            ax.text(route_x[0] + route_w[0] / 2, ry + row_h / 2,
                    routes_left[i][0], ha="center", va="center",
                    fontsize=TINY_SIZE, fontweight="bold", color=C["text"], zorder=3)
            ax.text(route_x[1] + route_w[1] / 2, ry + row_h / 2,
                    routes_left[i][1], ha="center", va="center",
                    fontsize=TINY_SIZE, color=C["text"], zorder=3)
        if i < len(routes_right):
            ax.text(route_x[2] + route_w[2] / 2, ry + row_h / 2,
                    routes_right[i][0], ha="center", va="center",
                    fontsize=TINY_SIZE, fontweight="bold", color=C["text"], zorder=3)
            ax.text(route_x[3] + route_w[3] / 2, ry + row_h / 2,
                    routes_right[i][1], ha="center", va="center",
                    fontsize=TINY_SIZE, color=C["text"], zorder=3)

    ax.text(PAGE_W / 2, 0.6,
            "Fig. 2. Complete service catalog with ports, health endpoints,\n"
            "infrastructure credentials, and nginx gateway routing.",
            ha="center", va="top", fontsize=CAPTION_SIZE, fontstyle="italic",
            color=C["text"])

    pdf.savefig(fig)
    plt.close(fig)


# ══════════════════════════════════════════════════════════════════════════════
#  PAGE 4 — Fig 3: Transaction Evaluation Flow
# ══════════════════════════════════════════════════════════════════════════════

def page_tx_flow(pdf):
    fig, ax = _new_fig("Fig. 3 — Transaction Evaluation Sequence")

    # Actors (columns)
    actors = ["User", "Flutter\nApp", "Nginx\nProxy", "Orchestrator\n:8007",
              "Risk / Sanc /\nGeo / Monitor", "Ethereum\nChain"]
    n = len(actors)
    ax_margin = 1.0
    ax_right = PAGE_W - 0.5
    spacing = (ax_right - ax_margin) / (n - 1)
    xs = [ax_margin + i * spacing for i in range(n)]
    top_y = 9.5
    bot_y = 1.8

    # Actor boxes
    for x, name in zip(xs, actors):
        _box(ax, x - 0.5, top_y, 1.0, 0.5, name,
             color=C["primary"], text_color="white", fontsize=TINY_SIZE)
        ax.plot([x, x], [top_y, bot_y], color="#bdbdbd", lw=0.4,
                linestyle="--", zorder=1)

    # Messages
    msgs = [
        (0, 1, "1. Initiate Transfer",         8.8),
        (1, 2, "2. POST /api/evaluate",         8.4),
        (2, 3, "3. Forward → /evaluate",         8.0),
        (3, 4, "4. Fan-out to services",        7.6),
        (4, 3, "5. Risk + Sanctions + Geo",     7.0, True),
        (3, 3, "6. Aggregate Decision",         6.5, False, True),
        (3, 2, "7. Decision response",          6.1, True),
        (2, 1, "8. Response",                   5.7, True),
        (1, 0, "9. Show Decision",              5.3, True),
        (0, 0, "[If ALLOW]",                    4.8, False, True),
        (0, 5, "10. Sign & Submit TX",          4.4),
        (5, 3, "11. On-chain verify",           3.8, True),
        (3, 5, "12. Confirm / reject",          3.3),
        (5, 0, "13. TX receipt",                2.8, True),
    ]
    for msg in msgs:
        from_i, to_i = msg[0], msg[1]
        label, y = msg[2], msg[3]
        is_return = msg[4] if len(msg) > 4 else False
        is_note = msg[5] if len(msg) > 5 else False

        x1, x2 = xs[from_i], xs[to_i]
        if is_note:
            ax.text(x1, y, label, fontsize=TINY_SIZE, color=C["accent"],
                    fontstyle="italic", fontweight="bold", ha="center", zorder=5)
            continue
        if from_i == to_i:
            continue

        style = "->" if not is_return else "->"
        color = C["arrow"] if not is_return else "#78909c"
        lw = 0.8 if not is_return else 0.6

        mid_x = (x1 + x2) / 2
        ax.annotate("", xy=(x2, y), xytext=(x1, y),
                    arrowprops=dict(arrowstyle="->", color=color, lw=lw,
                                    linestyle="--" if is_return else "-"),
                    zorder=4)
        ax.text(mid_x, y + 0.12, label, ha="center", fontsize=TINY_SIZE,
                color=C["text"], zorder=5)

    ax.text(PAGE_W / 2, 1.3,
            "Fig. 3. End-to-end transaction evaluation sequence diagram.\n"
            "Orchestrator fans out to Risk Engine, Sanctions, Monitoring, and Geographic Risk in parallel.",
            ha="center", va="top", fontsize=CAPTION_SIZE, fontstyle="italic",
            color=C["text"])

    pdf.savefig(fig)
    plt.close(fig)


# ══════════════════════════════════════════════════════════════════════════════
#  PAGE 5 — Fig 4: ML Pipeline
# ══════════════════════════════════════════════════════════════════════════════

def page_ml_pipeline(pdf):
    fig, ax = _new_fig("Fig. 4 — ML Stacked-Ensemble Risk Scoring Pipeline")

    cx = PAGE_W / 2
    bw, bh = 2.8, 0.45

    # Pipeline stages (top to bottom)
    stages = [
        ("Kaggle ETH Fraud Dataset", 9.2, C["box_ml"], None),
        ("XGBoost v1 → Predict on fresh data", 8.5, C["box_ml"], None),
        ("+ Custom Rules + Memgraph Graph Properties", 7.8, "#ffb74d", None),
        ("Enriched Dataset", 7.1, "#ffb74d", None),
        ("VAE Latent Features → GraphSAGE Embeddings", 6.4, C["box_ml"], None),
    ]
    for label, y, color, _ in stages:
        _box(ax, cx - bw / 2, y, bw, bh, label, color=color,
             text_color="white", fontsize=SMALL_SIZE)

    # Arrows between stages
    for i in range(len(stages) - 1):
        _arrow(ax, cx, stages[i][1], cx, stages[i + 1][1] + stages[i + 1][2] if isinstance(stages[i+1][2], (int,float)) else stages[i+1][1] + bh)

    # Fix arrows
    for i in range(len(stages) - 1):
        _arrow(ax, cx, stages[i][1], cx, stages[i + 1][1] + bh)

    # Three parallel models
    model_y = 5.3
    mbw, mbh = 1.8, 0.65
    models = [
        ("GraphSAGE\nEmbedding Model", C["box_be"]),
        ("LightGBM\nGradient Boosting", C["box_be"]),
        ("XGBoost v2\nBoosted Trees", C["box_be"]),
    ]
    mxs = [cx - mbw * 1.55, cx - mbw / 2, cx + mbw * 0.55]
    for mx, (mname, mcolor) in zip(mxs, models):
        _box(ax, mx, model_y, mbw, mbh, mname, color=mcolor,
             text_color="white", fontsize=SMALL_SIZE)
        _arrow(ax, cx, stages[-1][1], mx + mbw / 2, model_y + mbh)

    # Meta-learner
    meta_y = 4.2
    _box(ax, cx - bw / 2, meta_y, bw, bh + 0.1, "Linear Meta-Learner\n(Stacking)",
         color=C["primary"], text_color="white", fontsize=SMALL_SIZE + 0.5)
    for mx, (_, _) in zip(mxs, models):
        _arrow(ax, mx + mbw / 2, model_y, cx, meta_y + bh + 0.1)

    # Final score
    score_y = 3.3
    _box(ax, cx - bw / 2, score_y, bw, bh + 0.1, "Final Risk Score (0.0 – 1.0)",
         color="#d32f2f", text_color="white", fontsize=SMALL_SIZE + 0.5)
    _arrow(ax, cx, meta_y, cx, score_y + bh + 0.1)

    # Key insight box
    insight_y = 2.0
    _box(ax, cx - 3.0, insight_y, 6.0, 0.8,
         "Key Insight", color="#fff3e0", border="#e65100",
         text_color="#e65100", fontsize=LABEL_SIZE)
    ax.text(cx, insight_y + 0.25,
            "The final model has rules, graph detection, and base XGBoost\n"
            "patterns 'baked in' through the training data enrichment process.",
            ha="center", va="center", fontsize=SMALL_SIZE, color=C["text"],
            fontstyle="italic", zorder=5)

    ax.text(PAGE_W / 2, 1.3,
            "Fig. 4. Stacked-ensemble ML pipeline with knowledge distillation.\n"
            "Three base learners (GraphSAGE, LGBM, XGBoost) feed a linear meta-learner for final scoring.",
            ha="center", va="top", fontsize=CAPTION_SIZE, fontstyle="italic",
            color=C["text"])

    pdf.savefig(fig)
    plt.close(fig)


# ══════════════════════════════════════════════════════════════════════════════
#  PAGE 6 — Fig 5: Compliance Decision Engine
# ══════════════════════════════════════════════════════════════════════════════

def page_decision_engine(pdf):
    fig, ax = _new_fig("Fig. 5 — Compliance Decision Engine")

    cx = PAGE_W / 2

    # Top: Decision Engine box
    _box(ax, cx - 2.0, 9.4, 4.0, 0.5, "COMPLIANCE DECISION ENGINE",
         color=C["primary"], text_color="white", fontsize=LABEL_SIZE)

    # Three check branches
    checks = [
        ("RISK SCORING", 1.7, C["box_be"],
         ["GraphSAGE Embeddings", "LGBM + XGBoost", "Linear Meta-Learner", "",
          "Output: score 0.0–1.0"]),
        ("SANCTIONS CHECK", 4.25, C["box_bc"],
         ["OFAC (7,800+ entities)", "HMT (UK Treasury)", "EU Sanctions",
          "UN Sanctions", "Crypto Addr (22 known)", "",
          "Output: is_sanctioned"]),
        ("GEO RISK CHECK", 6.8, C["box_ml"],
         ["FATF Black (3 countries)", "FATF Grey (19 countries)",
          "EU High Risk (14 countries)", "Tax Havens", "",
          "Output: risk_level"]),
    ]
    for label, x, color, bullets in checks:
        _arrow(ax, cx, 9.4, x, 8.7)
        _box(ax, x - 0.9, 8.0, 1.8, 0.55, label, color=color,
             text_color="white", fontsize=TINY_SIZE + 0.5)
        for i, b in enumerate(bullets):
            ax.text(x, 7.85 - i * 0.2, b, ha="center",
                    fontsize=TINY_SIZE, color=C["text"], zorder=5)

    # Decision matrix
    dm_y = 5.5
    _box(ax, cx - 3.2, dm_y, 6.4, 1.6, "", color="#fafafa",
         border=C["primary"], fontsize=LABEL_SIZE)
    ax.text(cx, dm_y + 1.45, "DECISION MATRIX", ha="center",
            fontsize=LABEL_SIZE, fontweight="bold", color=C["primary"], zorder=5)

    matrix_data = [
        ("Risk < 0.4",   "No",  "Low",    "ALLOW",  C["decision_allow"]),
        ("0.4 – 0.7",    "No",  "Medium", "REVIEW", C["decision_review"]),
        ("Risk > 0.7",   "No",  "High",   "ESCROW", C["decision_escrow"]),
        ("Any",          "Yes", "Any",    "BLOCK",  C["decision_block"]),
        ("Any",          "Any", "FATF BL","BLOCK",  C["decision_block"]),
    ]
    headers = ["Risk Score", "Sanctions", "Geo Risk", "Action"]
    hx = [cx - 2.5, cx - 1.2, cx + 0.0, cx + 1.3]
    hy = dm_y + 1.15
    for hxx, hl in zip(hx, headers):
        ax.text(hxx, hy, hl, ha="center", fontsize=TINY_SIZE,
                fontweight="bold", color=C["primary"], zorder=5)

    for i, (rs, sa, gr, act, acol) in enumerate(matrix_data):
        ry = hy - (i + 1) * 0.2
        ax.text(hx[0], ry, rs, ha="center", fontsize=TINY_SIZE, color=C["text"], zorder=5)
        ax.text(hx[1], ry, sa, ha="center", fontsize=TINY_SIZE, color=C["text"], zorder=5)
        ax.text(hx[2], ry, gr, ha="center", fontsize=TINY_SIZE, color=C["text"], zorder=5)
        ax.text(hx[3], ry, f"→ {act}", ha="center", fontsize=TINY_SIZE,
                fontweight="bold", color=acol, zorder=5)

    # Merge arrows from checks to matrix
    for _, x, _, _ in checks:
        _arrow(ax, x, 5.6, cx, dm_y + 1.6)

    # Output box
    _box(ax, cx - 2.5, 3.8, 5.0, 1.3, "", color="#e8eaf6",
         border=C["primary"], fontsize=LABEL_SIZE)
    ax.text(cx, 5.0, "COMPLIANCE DECISION OUTPUT", ha="center",
            fontsize=LABEL_SIZE, fontweight="bold", color=C["primary"], zorder=5)
    _arrow(ax, cx, dm_y, cx, 3.8 + 1.3)
    output_lines = [
        'action: "ALLOW | REVIEW | ESCROW | BLOCK | MANUAL_REVIEW"',
        "risk_score: 0.0 – 1.0",
        "reasons: [...]",
        "requires_travel_rule: bool",
        "requires_sar: bool",
        "escrow_duration_hours: int",
    ]
    for i, line in enumerate(output_lines):
        ax.text(cx, 4.85 - i * 0.17, line, ha="center",
                fontsize=TINY_SIZE, color=C["text"], family="monospace", zorder=5)

    ax.text(PAGE_W / 2, 3.3,
            "Fig. 5. Compliance decision engine. Risk scoring, sanctions screening,\n"
            "and geographic risk assessment feed a rule-based decision matrix.",
            ha="center", va="top", fontsize=CAPTION_SIZE, fontstyle="italic",
            color=C["text"])

    pdf.savefig(fig)
    plt.close(fig)


# ══════════════════════════════════════════════════════════════════════════════
#  PAGE 7 — Fig 6: Smart Contract Architecture
# ══════════════════════════════════════════════════════════════════════════════

def page_smart_contracts(pdf):
    fig, ax = _new_fig("Fig. 6 — Smart Contract Architecture (Ethereum)")

    cx = PAGE_W / 2

    # Title banner
    _box(ax, cx - 3.5, 9.4, 7.0, 0.45, "ETHEREUM  —  Mainnet / Testnet / Hardhat :8545",
         color=C["primary"], text_color="white", fontsize=LABEL_SIZE)

    # Core contracts row 1
    contracts = [
        ("AMTTPCore", ["Risk Oracle", "Tx Validation", "Escrow Logic"], C["box_bc"]),
        ("AMTTPCoreSecure", ["Hardened Variant", "Extra Checks"], C["box_bc"]),
        ("AMTTPStreamlined", ["Optimized", "Lightweight"], C["box_bc"]),
    ]
    bw, bh = 2.1, 0.9
    gap = (7.0 - 3 * bw) / 4
    for i, (name, bullets, color) in enumerate(contracts):
        x = cx - 3.5 + gap + i * (bw + gap)
        y = 8.2
        _box(ax, x, y, bw, bh, name, color=color,
             text_color="white", fontsize=SMALL_SIZE)
        for j, b in enumerate(bullets):
            ax.text(x + bw / 2, y + bh * 0.4 - j * 0.16,
                    f"• {b}", ha="center", fontsize=TINY_SIZE,
                    color="#ffcdd2", zorder=5)

    # Row 2: Policy + Dispute + NFT
    contracts2 = [
        ("AMTTPPolicyManager\n+ PolicyEngine", ["Policy CRUD", "Threshold Mgmt", "Role Access"], C["box_bc"]),
        ("AMTTPDisputeResolver", ["Kleros Integration", "Arbitration", "MetaEvidence"], C["box_bc"]),
        ("AMTTPNFT", ["KYC Badges", "Compliance ID", "Soulbound"], C["box_bc"]),
    ]
    for i, (name, bullets, color) in enumerate(contracts2):
        x = cx - 3.5 + gap + i * (bw + gap)
        y = 7.0
        _box(ax, x, y, bw, bh, name, color=color,
             text_color="white", fontsize=SMALL_SIZE)
        for j, b in enumerate(bullets):
            ax.text(x + bw / 2, y + bh * 0.4 - j * 0.16,
                    f"• {b}", ha="center", fontsize=TINY_SIZE,
                    color="#ffcdd2", zorder=5)

    # Row 3: CrossChain + RiskRouter + SafeModule + Biconomy
    contracts3 = [
        ("AMTTPCrossChain", ["LayerZero", "Bridge Safety"]),
        ("AMTTPRiskRouter\n+ Router", ["ML Routing", "Score Relay"]),
        ("AMTTPSafeModule", ["Safe{Wallet}", "Multi-sig"]),
        ("AMTTPBiconomy", ["Account Abstraction", "Gasless TX"]),
    ]
    bw3 = 1.55
    gap3 = (7.0 - 4 * bw3) / 5
    for i, (name, bullets) in enumerate(contracts3):
        x = cx - 3.5 + gap3 + i * (bw3 + gap3)
        y = 5.8
        _box(ax, x, y, bw3, bh, name, color="#ff8a65",
             text_color="white", fontsize=TINY_SIZE + 0.5)
        for j, b in enumerate(bullets):
            ax.text(x + bw3 / 2, y + bh * 0.4 - j * 0.16,
                    f"• {b}", ha="center", fontsize=TINY_SIZE,
                    color="#fff3e0", zorder=5)

    # zkNAF section
    _box(ax, cx - 3.2, 4.2, 6.4, 1.2, "", color=C["layer_zknaf"],
         border="#f57f17", fontsize=LABEL_SIZE)
    ax.text(cx, 5.25, "zkNAF — Zero-Knowledge Compliance", ha="center",
            fontsize=LABEL_SIZE, fontweight="bold", color="#e65100", zorder=5)

    zk_items = [
        ("AMTTPCoreZkNAF", "Core + ZK Proofs"),
        ("AMTTPzkNAF", "ZK Verifier Contract"),
        ("ZkNAFVerifierRouter", "Proof Routing"),
    ]
    zbw = 1.8
    zgap = (6.4 - 3 * zbw) / 4
    for i, (name, desc) in enumerate(zk_items):
        zx = cx - 3.2 + zgap + i * (zbw + zgap)
        _box(ax, zx, 4.5, zbw, 0.55, name, color="#ffb74d",
             text_color="#3e2723", fontsize=TINY_SIZE + 0.5)
        ax.text(zx + zbw / 2, 4.5 + 0.12, desc, ha="center",
                fontsize=TINY_SIZE, color="#5d4037", zorder=5)

    # Circom circuits
    _box(ax, cx - 3.0, 3.0, 6.0, 0.8, "", color="#fff8e1",
         border="#f57f17", fontsize=SMALL_SIZE)
    ax.text(cx, 3.65, "Circom Circuits (snarkjs)", ha="center",
            fontsize=SMALL_SIZE, fontweight="bold", color="#e65100", zorder=5)
    circuits = [
        "kyc_credential.circom — Prove KYC without revealing PII",
        "risk_range_proof.circom — Prove risk score in acceptable range",
        "sanctions_non_membership.circom — Prove not on sanctions lists",
    ]
    for i, c in enumerate(circuits):
        ax.text(cx, 3.40 - i * 0.17, c, ha="center",
                fontsize=TINY_SIZE, color=C["text"], zorder=5)

    ax.text(PAGE_W / 2, 2.4,
            "Fig. 6. Smart contract architecture: 15 contracts across core protocol,\n"
            "policy, dispute resolution, NFT, cross-chain, and zkNAF zero-knowledge layers.",
            ha="center", va="top", fontsize=CAPTION_SIZE, fontstyle="italic",
            color=C["text"])

    pdf.savefig(fig)
    plt.close(fig)


# ══════════════════════════════════════════════════════════════════════════════
#  PAGE 8 — Fig 7: Full-Stack Docker Deployment
# ══════════════════════════════════════════════════════════════════════════════

def page_docker_fullstack(pdf):
    fig, ax = _new_fig("Fig. 7 — Full-Stack Docker Deployment (docker-compose.full.yml)")

    cx = PAGE_W / 2
    outer_x, outer_w = 0.4, 7.7
    outer_y, outer_h = 1.8, 8.0

    # Outer frame
    _box(ax, outer_x, outer_y, outer_w, outer_h, "",
         color="#fafafa", border=C["primary"], fontsize=1, lw=1.2)
    ax.text(outer_x + outer_w / 2, outer_y + outer_h - 0.1,
            "Docker Network: amttp-network", ha="center",
            fontsize=LABEL_SIZE, fontweight="bold", color=C["primary"], zorder=5)

    # Gateway box
    gw, gh = 6.8, 1.0
    gx = cx - gw / 2
    gy = outer_y + outer_h - 1.35
    _box(ax, gx, gy, gw, gh, "NGINX GATEWAY (amttp-gateway)  —  Port 8888:80",
         color=C["box_proxy"], text_color="white", fontsize=SMALL_SIZE + 0.5)

    routes_text = "/ → flutter   /warroom/ → nextjs   /api/ → orchestrator   /sanctions/   /ml/   /geo/   /zknaf/   /policy/   /explain/"
    ax.text(cx, gy + 0.25, routes_text, ha="center",
            fontsize=TINY_SIZE - 0.3, color="#fff3e0", zorder=5)

    # Service boxes - Row 1
    svc_bw, svc_bh = 1.25, 0.55
    row1_y = gy - 0.75
    row1_svcs = [
        ("Flutter\n:80", C["box_fe"]),
        ("Next.js\n:3000", C["box_fe"]),
        ("Orchestrator\n:8007", C["box_be"]),
        ("Sanctions\n:8004", C["box_be"]),
        ("Monitoring\n:8005", C["box_be"]),
    ]
    row1_gap = (gw - len(row1_svcs) * svc_bw) / (len(row1_svcs) + 1)
    for i, (name, color) in enumerate(row1_svcs):
        x = gx + row1_gap + i * (svc_bw + row1_gap)
        _box(ax, x, row1_y, svc_bw, svc_bh, name, color=color,
             text_color="white", fontsize=TINY_SIZE)
        _arrow(ax, x + svc_bw / 2, gy, x + svc_bw / 2, row1_y + svc_bh)

    # Row 2
    row2_y = row1_y - 0.75
    row2_svcs = [
        ("Geo Risk\n:8006", C["box_be"]),
        ("FCA Comply\n:8002", C["box_be"]),
        ("Policy\n:8003", C["box_be"]),
        ("Integrity\n:8008", C["box_be"]),
        ("Explain\n:8009", C["box_be"]),
    ]
    for i, (name, color) in enumerate(row2_svcs):
        x = gx + row1_gap + i * (svc_bw + row1_gap)
        _box(ax, x, row2_y, svc_bw, svc_bh, name, color=color,
             text_color="white", fontsize=TINY_SIZE)

    # Row 3
    row3_y = row2_y - 0.75
    row3_svcs = [
        ("ML Risk\n:8000", C["box_ml"]),
        ("Graph API\n:8001", C["box_ml"]),
        ("zkNAF\n:8010", "#ffb74d"),
    ]
    row3_gap = (gw - len(row3_svcs) * svc_bw) / (len(row3_svcs) + 1)
    for i, (name, color) in enumerate(row3_svcs):
        x = gx + row3_gap + i * (svc_bw + row3_gap)
        _box(ax, x, row3_y, svc_bw, svc_bh, name, color=color,
             text_color="white", fontsize=TINY_SIZE)

    # Infrastructure row
    infra_y = row3_y - 1.0
    _box(ax, gx, infra_y, gw, 0.75, "", color="#eceff1",
         border=C["box_infra"], fontsize=1)
    ax.text(gx + 0.15, infra_y + 0.65, "INFRASTRUCTURE",
            fontsize=TINY_SIZE, fontweight="bold", color=C["box_infra"],
            va="top", zorder=5)

    infra_svcs = [
        ("MongoDB\n:27017", C["box_db"]),
        ("Redis\n:6379", C["box_db"]),
        ("Memgraph\n:7687", C["box_db"]),
        ("Cloudflare\nTunnel", "#2196f3"),
    ]
    ibw = 1.3
    igap = (gw - len(infra_svcs) * ibw) / (len(infra_svcs) + 1)
    for i, (name, color) in enumerate(infra_svcs):
        x = gx + igap + i * (ibw + igap)
        _box(ax, x, infra_y + 0.08, ibw, 0.5, name, color=color,
             text_color="white", fontsize=TINY_SIZE)

    ax.text(PAGE_W / 2, 1.3,
            "Fig. 7. Full-stack Docker deployment with nginx gateway,\n"
            "17 containerised services, and Cloudflare tunnel for public exposure.",
            ha="center", va="top", fontsize=CAPTION_SIZE, fontstyle="italic",
            color=C["text"])

    pdf.savefig(fig)
    plt.close(fig)


# ══════════════════════════════════════════════════════════════════════════════
#  PAGE 9 — Fig 8: Production Deployment
# ══════════════════════════════════════════════════════════════════════════════

def page_production(pdf):
    fig, ax = _new_fig("Fig. 8 — Production Deployment with Cloudflare Tunnel")

    cx = PAGE_W / 2

    # Internet / Cloudflare
    _box(ax, cx - 2.5, 9.2, 5.0, 0.5, "INTERNET  ←  Cloudflare Edge Network",
         color="#2196f3", text_color="white", fontsize=LABEL_SIZE)

    # Tunnel
    _box(ax, cx - 2.0, 8.3, 4.0, 0.55, "cloudflared Tunnel",
         color="#1565c0", text_color="white", fontsize=SMALL_SIZE)
    _arrow(ax, cx, 9.2, cx, 8.85)

    tunnel_routes = [
        "amttp.domain.com → gateway:80",
        "api.amttp.domain.com → gateway:80/api",
        "dashboard.amttp.domain.com → gateway:80/dashboard",
    ]
    for i, r in enumerate(tunnel_routes):
        ax.text(cx, 8.15 - i * 0.14, r, ha="center",
                fontsize=TINY_SIZE, color=C["text"], family="monospace", zorder=5)

    # Nginx gateway (3 server blocks)
    _box(ax, cx - 3.0, 6.8, 6.0, 1.0, "", color=C["layer_proxy"],
         border="#e65100", fontsize=1)
    ax.text(cx, 7.65, "NGINX GATEWAY — 3 Server Blocks", ha="center",
            fontsize=LABEL_SIZE, fontweight="bold", color="#e65100", zorder=5)
    _arrow(ax, cx, 8.3, cx, 7.8)

    blocks = [
        ("Port 80", "Flutter SPA + API routing\n(rate limited: 100 req/s)"),
        ("Port 3005", "Next.js Dashboard\n(direct access)"),
        ("Port 8080", "API Gateway\n(/v1/, /zknaf/, /risk/)"),
    ]
    bbw = 1.7
    bgap = (6.0 - 3 * bbw) / 4
    for i, (port, desc) in enumerate(blocks):
        bx = cx - 3.0 + bgap + i * (bbw + bgap)
        by = 6.9
        _box(ax, bx, by, bbw, 0.65, port, color="white",
             border="#e65100", fontsize=SMALL_SIZE, text_color="#e65100")
        ax.text(bx + bbw / 2, by + 0.12, desc, ha="center",
                fontsize=TINY_SIZE - 0.5, color=C["text"], zorder=5)

    # Internal network
    _box(ax, cx - 3.3, 3.8, 6.6, 2.7, "", color="#e3f2fd",
         border=C["accent"], fontsize=1, lw=1.0)
    ax.text(cx, 6.35, "Internal Network: amttp-internal (172.28.0.0/16)",
            ha="center", fontsize=LABEL_SIZE, fontweight="bold",
            color=C["accent"], zorder=5)
    _arrow(ax, cx, 6.8, cx, 6.5)

    int_svcs = [
        "Orchestrator :8007   Sanctions :8004   Monitoring :8005   Geo-Risk :8006",
        "Integrity :8008   zkNAF :8010   Risk-Engine :8000   Oracle :3001   Next.js :3004",
    ]
    for i, line in enumerate(int_svcs):
        ax.text(cx, 6.1 - i * 0.22, line, ha="center",
                fontsize=TINY_SIZE, color=C["text"], zorder=5)

    # Storage row
    _box(ax, cx - 3.0, 4.0, 6.0, 0.8, "", color="#f3e5f5",
         border=C["box_db"], fontsize=1)
    ax.text(cx - 2.8, 4.65, "Storage", fontsize=TINY_SIZE + 0.5,
            fontweight="bold", color=C["box_db"], zorder=5)
    storage = "MongoDB 7  ·  Redis 7  ·  Memgraph  ·  MinIO  ·  Helia (IPFS)"
    ax.text(cx, 4.25, storage, ha="center",
            fontsize=SMALL_SIZE, color=C["text"], zorder=5)

    # Monitoring (optional)
    _box(ax, cx - 2.0, 3.0, 4.0, 0.55, "Monitoring Profile (optional):  Prometheus + Grafana",
         color="#e8f5e9", border=C["box_be"], fontsize=SMALL_SIZE,
         text_color=C["text"])

    # Deployment modes comparison table
    ty = 2.1
    ax.text(cx, ty + 0.25, "Deployment Modes Comparison", ha="center",
            fontsize=LABEL_SIZE, fontweight="bold", color=C["primary"])

    modes_cols = ["Mode", "Compose File", "Key Feature"]
    modes_x = [1.5, 3.2, 5.8]
    modes_w = [1.5, 2.0, 2.8]
    row_h = 0.22
    for mx, mw, ml in zip(modes_x, modes_w, modes_cols):
        rect = Rectangle((mx, ty), mw, row_h, facecolor=C["primary"],
                          edgecolor=C["border"], lw=0.4, zorder=2)
        ax.add_patch(rect)
        ax.text(mx + mw / 2, ty + row_h / 2, ml, ha="center",
                va="center", fontsize=TINY_SIZE, fontweight="bold",
                color="white", zorder=3)

    modes = [
        ("Development", "docker-compose.yml", "Individual containers, all ports"),
        ("Unified", "docker-compose.unified.yml", "Single container, supervisord"),
        ("Full-Stack", "docker-compose.full.yml", "All microservices + Cloudflare"),
        ("Production", "docker-compose.production.yml", "Hardened, Prometheus/Grafana"),
        ("Cloudflare", "docker-compose.cloudflare.yml", "Platform image + Cloudflare"),
        ("Gateway", "docker-compose.gateway.yml", "Nginx + ngrok (host services)"),
    ]
    for i, (mn, mf, mk) in enumerate(modes):
        ry = ty - (i + 1) * row_h
        bg = C["header_bg"] if i % 2 == 0 else C["bg"]
        for mx, mw in zip(modes_x, modes_w):
            rect = Rectangle((mx, ry), mw, row_h, facecolor=bg,
                              edgecolor="#bdbdbd", lw=0.3, zorder=2)
            ax.add_patch(rect)
        for mx, mw, v in zip(modes_x, modes_w, [mn, mf, mk]):
            ax.text(mx + mw / 2, ry + row_h / 2, v, ha="center",
                    va="center", fontsize=TINY_SIZE, color=C["text"], zorder=3)

    ax.text(PAGE_W / 2, 0.5,
            "Fig. 8. Production deployment architecture with Cloudflare tunnel, 3 nginx server blocks,\n"
            "internal network isolation, and optional Prometheus/Grafana monitoring stack.",
            ha="center", va="top", fontsize=CAPTION_SIZE, fontstyle="italic",
            color=C["text"])

    pdf.savefig(fig)
    plt.close(fig)


# ══════════════════════════════════════════════════════════════════════════════
#  PAGE 10 — Fig 9: RBAC Role Hierarchy
# ══════════════════════════════════════════════════════════════════════════════

def page_rbac(pdf):
    fig, ax = _new_fig("Fig. 9 — RBAC: Unified 6-Tier Role Hierarchy")

    cx = PAGE_W / 2
    bw, bh = 6.5, 0.85

    roles = [
        ("R1 — End User", "Focus Mode (bottom nav)",
         "Wallet · Transfer · History · Trust Check · NFT Swap",
         C["rbac1"], C["text"]),
        ("R2 — Power User / PEP", "Focus Mode + Pro Tools",
         "R1 + zkNAF · Safe Wallet · Session Keys · Cross-Chain · Disputes",
         C["rbac2"], C["text"]),
        ("R3 — Institution Ops", "War Room (sidebar nav)",
         "Compliance View · FATF Rules · War Room · Detection Studio",
         C["rbac3"], "white"),
        ("R4 — Institution Compliance", "War Room + Governance",
         "R3 + Graph Explorer · Transaction Approver",
         C["rbac4"], "white"),
        ("R5 — Platform Admin", "Admin Mode",
         "Admin Panel · Settings · Team Management",
         C["rbac5"], "white"),
        ("R6 — Super Admin / Auditor", "War Room (read-only)",
         "Full audit access · Read-only compliance views",
         C["rbac6"], "white"),
    ]

    top_y = 9.0
    gap = 0.18
    for i, (title, mode, perms, color, tcol) in enumerate(roles):
        y = top_y - i * (bh + gap)
        _box(ax, cx - bw / 2, y, bw, bh, "", color=color,
             text_color=tcol, fontsize=SMALL_SIZE, lw=0.6)
        ax.text(cx - bw / 2 + 0.15, y + bh - 0.15, title,
                fontsize=LABEL_SIZE, fontweight="bold", color=tcol,
                va="top", zorder=5)
        ax.text(cx + bw / 2 - 0.15, y + bh - 0.15, mode,
                fontsize=SMALL_SIZE, fontstyle="italic", color=tcol,
                ha="right", va="top", zorder=5)
        ax.text(cx - bw / 2 + 0.15, y + 0.15, perms,
                fontsize=TINY_SIZE + 0.5, color=tcol, va="bottom", zorder=5)

        if i > 0:
            _arrow(ax, cx, y + bh + gap, cx, y + bh, color="#78909c", lw=0.5)

    # Progression arrow on the side
    ax.annotate("", xy=(cx - bw / 2 - 0.35, roles[-1][0] and top_y - 5 * (bh + gap)),
                xytext=(cx - bw / 2 - 0.35, top_y + bh),
                arrowprops=dict(arrowstyle="->", color=C["primary"], lw=1.5))
    ax.text(cx - bw / 2 - 0.5, (top_y + top_y - 5 * (bh + gap) + bh) / 2,
            "Increasing\nPrivilege", ha="center", va="center", rotation=90,
            fontsize=SMALL_SIZE, color=C["primary"], fontweight="bold", zorder=5)

    # Flutter routes
    routes_y = 2.0
    ax.text(cx, routes_y + 0.3, "Key Flutter Routes by Role", ha="center",
            fontsize=LABEL_SIZE, fontweight="bold", color=C["primary"])
    routes = [
        "R1–R2:  /sign-in  /register  /  /wallet  /transfer  /history  /trust-check  /nft-swap",
        "R2:     /zknaf  /safe  /session-keys  /cross-chain  /disputes  /dispute/:id",
        "R3–R4:  /compliance  /fatf-rules  /war-room  /detection-studio  /graph-explorer  /approver",
        "R5:     /admin  /settings",
        "R6:     /audit  (read-only access to all above)",
    ]
    for i, r in enumerate(routes):
        ax.text(cx, routes_y - 0.02 - i * 0.2, r, ha="center",
                fontsize=TINY_SIZE, color=C["text"], family="monospace", zorder=5)

    ax.text(PAGE_W / 2, 0.8,
            "Fig. 9. Unified 6-tier RBAC hierarchy.  Roles determine UI mode\n"
            "(Focus vs War Room vs Admin) and available routes in both Flutter and Next.js.",
            ha="center", va="top", fontsize=CAPTION_SIZE, fontstyle="italic",
            color=C["text"])

    pdf.savefig(fig)
    plt.close(fig)


# ══════════════════════════════════════════════════════════════════════════════
#  PAGE 11 — Fig 10: Security Layers
# ══════════════════════════════════════════════════════════════════════════════

def page_security(pdf):
    fig, ax = _new_fig("Fig. 10 — Security Architecture: Defence in Depth")

    cx = PAGE_W / 2
    bw = 6.5
    top_y = 9.2

    layers = [
        ("Layer 1: Network Security", "#e3f2fd", [
            "TLS termination at nginx / Cloudflare edge",
            "Rate limiting per IP (100 req/s API, 50 req/s general)",
            "CORS headers and CSP for browser security",
            "No direct service exposure (all via nginx reverse proxy)",
            "Cloudflare trusted IP forwarding",
        ]),
        ("Layer 2: Application Security", "#e8f5e9", [
            "Wallet signature verification (EIP-712)",
            "Request integrity hashing (integrity service :8008)",
            "UI tamper detection with registered hash verification",
            "Input validation & sanitization on all endpoints",
            "API key authentication for external SDK clients",
        ]),
        ("Layer 3: Smart Contract Security", "#fce4ec", [
            "Role-based access control (RBAC) on-chain",
            "Escrow mechanisms for high-risk transactions",
            "On-chain risk score verification via oracle",
            "Emergency pause functionality (circuit breaker)",
            "Kleros arbitration for dispute resolution",
        ]),
        ("Layer 4: Zero-Knowledge Privacy", "#fff8e1", [
            "zkNAF proofs: KYC credentials without revealing PII",
            "Risk range proofs: prove score in range without exact value",
            "Sanctions non-membership proofs: prove clean without list exposure",
            "Circom circuits compiled with snarkjs (Groth16)",
        ]),
        ("Layer 5: Data Security", "#f3e5f5", [
            "Encrypted storage for sensitive data (Vault :8200)",
            "Audit logging to IPFS / Helia (immutable)",
            "PII minimisation (blockchain addresses only)",
            "GDPR-compliant data handling and right-to-erasure support",
            "FCA MLR-compliant record retention",
        ]),
    ]

    bh = 1.15
    gap = 0.18
    for i, (title, color, items) in enumerate(layers):
        y = top_y - i * (bh + gap)
        _box(ax, cx - bw / 2, y, bw, bh, "", color=color,
             border=C["border"], fontsize=1, lw=0.5)
        ax.text(cx - bw / 2 + 0.15, y + bh - 0.12, title,
                fontsize=LABEL_SIZE, fontweight="bold", color=C["primary"],
                va="top", zorder=5)
        for j, item in enumerate(items):
            ax.text(cx - bw / 2 + 0.25, y + bh - 0.30 - j * 0.155,
                    f"• {item}", fontsize=TINY_SIZE, color=C["text"], zorder=5)

        if i > 0:
            prev_y = top_y - (i - 1) * (bh + gap)
            _arrow(ax, cx, prev_y, cx, y + bh, color="#78909c", lw=0.5)

    # Side label
    total_h = 5 * bh + 4 * gap
    ax.annotate("", xy=(cx + bw / 2 + 0.35, top_y - total_h),
                xytext=(cx + bw / 2 + 0.35, top_y + bh),
                arrowprops=dict(arrowstyle="<->", color=C["primary"], lw=1.2))
    ax.text(cx + bw / 2 + 0.55, top_y + bh / 2 - total_h / 2,
            "Defence\nin\nDepth", ha="center", va="center",
            fontsize=SMALL_SIZE, color=C["primary"], fontweight="bold",
            rotation=0, zorder=5)

    ax.text(PAGE_W / 2, 2.2,
            "Fig. 10. Five-layer defence-in-depth security architecture.\n"
            "Includes network, application, smart-contract, ZK-privacy, and data security controls.",
            ha="center", va="top", fontsize=CAPTION_SIZE, fontstyle="italic",
            color=C["text"])

    pdf.savefig(fig)
    plt.close(fig)


# ══════════════════════════════════════════════════════════════════════════════
#  Main — assemble all pages into one PDF
# ══════════════════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(
        description="Export AMTTP architecture as IEEE-format vector PDF")
    parser.add_argument("-o", "--output",
                        default=str(Path(__file__).parent / "AMTTP_System_Architecture.pdf"),
                        help="Output PDF path")
    args = parser.parse_args()

    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)

    print(f"Generating IEEE-format vector PDF → {out}")

    with PdfPages(str(out)) as pdf:
        page_title(pdf)
        print("  ✓ Title page")

        page_system_overview(pdf)
        print("  ✓ Fig. 1 — System Overview")

        page_services_portmap(pdf)
        print("  ✓ Fig. 2 — Services & Port Map")

        page_tx_flow(pdf)
        print("  ✓ Fig. 3 — Transaction Flow")

        page_ml_pipeline(pdf)
        print("  ✓ Fig. 4 — ML Pipeline")

        page_decision_engine(pdf)
        print("  ✓ Fig. 5 — Decision Engine")

        page_smart_contracts(pdf)
        print("  ✓ Fig. 6 — Smart Contracts")

        page_docker_fullstack(pdf)
        print("  ✓ Fig. 7 — Docker Full-Stack")

        page_production(pdf)
        print("  ✓ Fig. 8 — Production Deployment")

        page_rbac(pdf)
        print("  ✓ Fig. 9 — RBAC Hierarchy")

        page_security(pdf)
        print("  ✓ Fig. 10 — Security Layers")

        # PDF metadata
        d = pdf.infodict()
        d["Title"] = "AMTTP System Architecture"
        d["Author"] = "DevOps Engineering"
        d["Subject"] = "Anti-Money Laundering Transaction Trust Protocol"
        d["Keywords"] = "AMTTP AML blockchain compliance risk ML zkNAF"
        d["Creator"] = "matplotlib (vector PDF — no raster content)"

    size_mb = out.stat().st_size / 1024 / 1024
    print(f"\n✅ Done! {out}  ({size_mb:.1f} MB)")
    print("   Pure vector PDF — infinite zoom, no blur.")


if __name__ == "__main__":
    main()
