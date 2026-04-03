'use client';

import React, { useEffect, useState, useRef } from 'react';
import Link from 'next/link';

/* ═══════════════════════════════════════════════════════════════════════════════
 * AMTTP Landing Page — Market-Grade
 *
 * Sections:
 *   1. Navbar (sticky, glass)
 *   2. Hero (tagline + animated glow + CTAs)
 *   3. Live Stats Strip
 *   4. Feature Cards (4 pillars)
 *   5. Architecture Map (visual)
 *   6. How It Works (3-step)
 *   7. Trust & Compliance
 *   8. CTA Banner
 *   9. Footer
 * ═══════════════════════════════════════════════════════════════════════════════ */

// ── Animated counter ────────────────────────────────────────────────────────
function AnimatedNumber({ target, suffix = '' }: { target: number; suffix?: string }) {
  const [val, setVal] = useState(0);
  const ref = useRef<HTMLSpanElement>(null);

  useEffect(() => {
    const observer = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting) {
          let start = 0;
          const step = Math.max(1, Math.floor(target / 60));
          const timer = setInterval(() => {
            start += step;
            if (start >= target) {
              start = target;
              clearInterval(timer);
            }
            setVal(start);
          }, 16);
          observer.disconnect();
        }
      },
      { threshold: 0.3 },
    );
    if (ref.current) observer.observe(ref.current);
    return () => observer.disconnect();
  }, [target]);

  return (
    <span ref={ref}>
      {val.toLocaleString()}
      {suffix}
    </span>
  );
}

// ── Section wrapper ─────────────────────────────────────────────────────────
function Section({
  children,
  className = '',
  id,
}: {
  children: React.ReactNode;
  className?: string;
  id?: string;
}) {
  return (
    <section id={id} className={`px-6 md:px-12 lg:px-24 py-20 ${className}`}>
      <div className="max-w-7xl mx-auto">{children}</div>
    </section>
  );
}

// ── Feature card ────────────────────────────────────────────────────────────
function FeatureCard({
  icon,
  title,
  description,
  accent,
}: {
  icon: React.ReactNode;
  title: string;
  description: string;
  accent: string;
}) {
  return (
    <div className="group relative rounded-2xl border border-white/[0.06] bg-white/[0.02] p-8 transition-all duration-300 hover:border-white/[0.12] hover:bg-white/[0.04]">
      <div
        className={`mb-5 flex h-12 w-12 items-center justify-center rounded-xl ${accent}`}
      >
        {icon}
      </div>
      <h3 className="mb-3 text-lg font-semibold text-white">{title}</h3>
      <p className="text-sm leading-relaxed text-gray-400">{description}</p>
    </div>
  );
}

// ── Step card ───────────────────────────────────────────────────────────────
function StepCard({
  number,
  title,
  description,
}: {
  number: string;
  title: string;
  description: string;
}) {
  return (
    <div className="relative flex flex-col items-center text-center">
      <div className="mb-4 flex h-14 w-14 items-center justify-center rounded-full bg-indigo-500/20 text-xl font-bold text-indigo-400 ring-1 ring-indigo-500/30">
        {number}
      </div>
      <h3 className="mb-2 text-lg font-semibold text-white">{title}</h3>
      <p className="max-w-xs text-sm leading-relaxed text-gray-400">{description}</p>
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════════════════
// MAIN COMPONENT
// ═══════════════════════════════════════════════════════════════════════════════

export function LandingPage() {
  const [scrolled, setScrolled] = useState(false);
  const [flutterUrl, setFlutterUrl] = useState('http://localhost:3010/#/sign-out');

  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 40);
    window.addEventListener('scroll', onScroll, { passive: true });
    // Determine Flutter URL based on environment
    // Always route through /#/sign-out so stale sessions are cleared
    const port = window.location.port;
    if (port === '3006' || port === '3000') {
      // Dev mode — Flutter on separate port
      setFlutterUrl('http://localhost:3010/#/sign-out');
    } else {
      // Production (nginx) — Flutter at root on same origin
      setFlutterUrl('/#/sign-out');
    }
    return () => window.removeEventListener('scroll', onScroll);
  }, []);

  return (
    <div className="min-h-screen bg-[#0A0A0F] text-white antialiased">
      {/* ── NAVBAR ────────────────────────────────────────────────────── */}
      <nav
        className={`fixed inset-x-0 top-0 z-50 transition-all duration-300 ${
          scrolled
            ? 'border-b border-white/[0.06] bg-[#0A0A0F]/80 backdrop-blur-xl'
            : 'bg-transparent'
        }`}
      >
        <div className="mx-auto flex max-w-7xl items-center justify-between px-6 py-4 md:px-12">
          {/* Logo */}
          <Link href="/" className="flex items-center gap-3">
            <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-gradient-to-br from-indigo-500 to-violet-600">
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="white" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                <path d="M12 2L2 7l10 5 10-5-10-5z" />
                <path d="M2 17l10 5 10-5" />
                <path d="M2 12l10 5 10-5" />
              </svg>
            </div>
            <span className="text-lg font-bold tracking-tight">AMTTP</span>
          </Link>

          {/* Nav links */}
          <div className="hidden items-center gap-8 md:flex">
            <a href="#features" className="text-sm text-gray-400 transition hover:text-white">
              Features
            </a>
            <a href="#architecture" className="text-sm text-gray-400 transition hover:text-white">
              Architecture
            </a>
            <a href="#how-it-works" className="text-sm text-gray-400 transition hover:text-white">
              How It Works
            </a>
            <a href="#compliance" className="text-sm text-gray-400 transition hover:text-white">
              Compliance
            </a>
          </div>

          {/* CTA — Dual Entry */}
          <div className="flex items-center gap-3">
            <a
              href={flutterUrl}
              className="rounded-lg px-4 py-2 text-sm font-medium text-gray-300 transition hover:text-white"
            >
              Consumer Login
            </a>
            <a
              href={flutterUrl}
              className="rounded-lg bg-indigo-600 px-5 py-2 text-sm font-semibold text-white shadow-lg shadow-indigo-500/25 transition hover:bg-indigo-500"
            >
              Institutional Login
            </a>
          </div>
        </div>
      </nav>

      {/* ── HERO ─────────────────────────────────────────────────────── */}
      <section className="relative flex min-h-[92vh] items-center justify-center overflow-hidden px-6 pt-20">
        {/* Glow orbs */}
        <div className="pointer-events-none absolute inset-0 overflow-hidden">
          <div className="absolute -top-48 left-1/2 h-[600px] w-[600px] -translate-x-1/2 rounded-full bg-indigo-600/20 blur-[120px]" />
          <div className="absolute -bottom-32 left-1/4 h-[400px] w-[400px] rounded-full bg-violet-600/15 blur-[100px]" />
          <div className="absolute -right-20 top-1/3 h-[300px] w-[300px] rounded-full bg-cyan-500/10 blur-[80px]" />
        </div>

        {/* Grid pattern */}
        <div
          className="pointer-events-none absolute inset-0 opacity-[0.03]"
          style={{
            backgroundImage:
              'linear-gradient(rgba(255,255,255,0.1) 1px, transparent 1px), linear-gradient(90deg, rgba(255,255,255,0.1) 1px, transparent 1px)',
            backgroundSize: '60px 60px',
          }}
        />

        {/* Content */}
        <div className="relative z-10 mx-auto max-w-4xl text-center">
          {/* Badge */}
          <div className="mb-8 inline-flex items-center gap-2 rounded-full border border-indigo-500/30 bg-indigo-500/10 px-4 py-1.5 text-sm text-indigo-300">
            <span className="inline-block h-1.5 w-1.5 rounded-full bg-indigo-400 animate-pulse" />
            ML-Powered DeFi Compliance Protocol
          </div>

          <h1 className="mb-6 text-5xl font-extrabold leading-[1.1] tracking-tight md:text-7xl">
            Detect Fraud.{' '}
            <span className="bg-gradient-to-r from-indigo-400 via-violet-400 to-cyan-400 bg-clip-text text-transparent">
              Protect Assets.
            </span>
            <br />
            Stay Compliant.
          </h1>

          <p className="mx-auto mb-10 max-w-2xl text-lg leading-relaxed text-gray-400 md:text-xl">
            AMTTP is the enterprise-grade Anti-Money Laundering Transaction Transfer Protocol
            for decentralised finance — combining real-time machine learning, graph analytics,
            and on-chain smart contracts to stop illicit flows before they settle.
          </p>

          {/* CTA — Dual Entry Cards */}
          <div className="mt-4 grid gap-5 sm:grid-cols-2 max-w-2xl mx-auto">
            {/* Retail / Consumer Path */}
            <a
              href={flutterUrl}
              className="group relative flex flex-col items-center gap-3 rounded-2xl border border-emerald-500/20 bg-emerald-500/[0.04] p-6 transition-all hover:border-emerald-500/40 hover:bg-emerald-500/[0.08]"
            >
              <div className="flex h-12 w-12 items-center justify-center rounded-xl bg-emerald-500/20">
                <svg width="24" height="24" fill="none" stroke="currentColor" className="text-emerald-400" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" viewBox="0 0 24 24">
                  <rect x="2" y="3" width="20" height="14" rx="2" />
                  <path d="M12 17v4M8 21h8" />
                </svg>
              </div>
              <div className="text-center">
                <div className="text-base font-semibold text-white">Consumer App</div>
                <div className="mt-1 text-sm text-gray-400">Wallet, transfers &amp; trust checks</div>
                <div className="mt-2 inline-flex items-center gap-1 text-xs font-medium text-emerald-400">
                  R1 End User · R2 PEP
                </div>
              </div>
              <svg width="18" height="18" fill="none" stroke="currentColor" className="absolute right-4 top-4 text-emerald-500/50 transition group-hover:text-emerald-400" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" viewBox="0 0 24 24">
                <path d="M5 12h14M12 5l7 7-7 7" />
              </svg>
            </a>

            {/* Institutional / War Room Path */}
            <a
              href={flutterUrl}
              className="group relative flex flex-col items-center gap-3 rounded-2xl border border-indigo-500/20 bg-indigo-500/[0.04] p-6 transition-all hover:border-indigo-500/40 hover:bg-indigo-500/[0.08]"
            >
              <div className="flex h-12 w-12 items-center justify-center rounded-xl bg-indigo-500/20">
                <svg width="24" height="24" fill="none" stroke="currentColor" className="text-indigo-400" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" viewBox="0 0 24 24">
                  <rect x="3" y="3" width="18" height="18" rx="2" ry="2" />
                  <line x1="3" y1="9" x2="21" y2="9" />
                  <line x1="9" y1="21" x2="9" y2="9" />
                </svg>
              </div>
              <div className="text-center">
                <div className="text-base font-semibold text-white">Institutional War Room</div>
                <div className="mt-1 text-sm text-gray-400">Sign in with R3–R6 credentials to enter</div>
                <div className="mt-2 inline-flex items-center gap-1 text-xs font-medium text-indigo-400">
                  R3 Ops · R4 Compliance · R5 Admin · R6 Super
                </div>
              </div>
              <svg width="18" height="18" fill="none" stroke="currentColor" className="absolute right-4 top-4 text-indigo-500/50 transition group-hover:text-indigo-400" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" viewBox="0 0 24 24">
                <path d="M5 12h14M12 5l7 7-7 7" />
              </svg>
            </a>
          </div>

          <div className="mt-6">
            <a
              href="#architecture"
              className="inline-flex items-center gap-2 text-sm text-gray-500 transition-all hover:text-gray-300"
            >
              Or explore the architecture below
              <svg width="14" height="14" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" viewBox="0 0 24 24">
                <path d="M12 5v14M5 12l7 7 7-7" />
              </svg>
            </a>
          </div>
        </div>
      </section>

      {/* ── LIVE STATS STRIP ─────────────────────────────────────────── */}
      <section className="border-y border-white/[0.06] bg-white/[0.015]">
        <div className="mx-auto grid max-w-7xl grid-cols-2 gap-px md:grid-cols-4">
          {[
            { label: 'Transactions Analysed', value: 920848, suffix: '+' },
            { label: 'Flagged & Investigated', value: 420848, suffix: '' },
            { label: 'Wallet Profiles', value: 451594, suffix: '+' },
            { label: 'ML Model Accuracy', value: 97, suffix: '%' },
          ].map((stat) => (
            <div key={stat.label} className="px-6 py-8 text-center md:px-10">
              <div className="mb-1 text-3xl font-bold text-white md:text-4xl">
                <AnimatedNumber target={stat.value} suffix={stat.suffix} />
              </div>
              <div className="text-sm text-gray-500">{stat.label}</div>
            </div>
          ))}
        </div>
      </section>

      {/* ── FEATURES ─────────────────────────────────────────────────── */}
      <Section id="features">
        <div className="mb-16 text-center">
          <p className="mb-3 text-sm font-semibold uppercase tracking-widest text-indigo-400">
            Capabilities
          </p>
          <h2 className="text-3xl font-bold md:text-4xl">
            Four Pillars of DeFi Compliance
          </h2>
        </div>

        <div className="grid gap-6 md:grid-cols-2 lg:grid-cols-4">
          <FeatureCard
            accent="bg-cyan-500/20 text-cyan-400"
            icon={
              <svg width="22" height="22" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" viewBox="0 0 24 24">
                <path d="M12 2a10 10 0 1 0 0 20 10 10 0 0 0 0-20z" />
                <path d="M12 6v6l4 2" />
              </svg>
            }
            title="Real-Time ML Detection"
            description="XGBoost → VAE → GNN ensemble stack analyses every transaction in under 100ms, catching structuring, layering, and anomalous patterns before settlement."
          />
          <FeatureCard
            accent="bg-violet-500/20 text-violet-400"
            icon={
              <svg width="22" height="22" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" viewBox="0 0 24 24">
                <circle cx="12" cy="12" r="3" />
                <line x1="3" y1="12" x2="9" y2="12" />
                <line x1="15" y1="12" x2="21" y2="12" />
                <line x1="12" y1="3" x2="12" y2="9" />
                <line x1="12" y1="15" x2="12" y2="21" />
              </svg>
            }
            title="Graph Intelligence"
            description="Memgraph-powered entity graph maps wallet clusters, transaction chains, and counterparty networks in real-time across 6 blockchain networks."
          />
          <FeatureCard
            accent="bg-amber-500/20 text-amber-400"
            icon={
              <svg width="22" height="22" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" viewBox="0 0 24 24">
                <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
              </svg>
            }
            title="On-Chain Enforcement"
            description="UUPS upgradeable smart contracts enforce policy gates, adaptive friction, and multi-sig approvals — all auditable on-chain with zkSNARK privacy."
          />
          <FeatureCard
            accent="bg-rose-500/20 text-rose-400"
            icon={
              <svg width="22" height="22" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" viewBox="0 0 24 24">
                <rect x="3" y="3" width="18" height="18" rx="2" ry="2" />
                <line x1="3" y1="9" x2="21" y2="9" />
                <line x1="9" y1="21" x2="9" y2="9" />
              </svg>
            }
            title="Regulatory Dashboard"
            description="War Room for compliance officers with RBAC-gated access, real-time KPI monitoring, policy editing, and FCA/FATF-compliant reporting."
          />
        </div>
      </Section>

      {/* ── ARCHITECTURE ─────────────────────────────────────────────── */}
      <Section id="architecture" className="border-y border-white/[0.06] bg-white/[0.015]">
        <div className="mb-16 text-center">
          <p className="mb-3 text-sm font-semibold uppercase tracking-widest text-indigo-400">
            System Design
          </p>
          <h2 className="text-3xl font-bold md:text-4xl">Enterprise-Grade Architecture</h2>
        </div>

        {/* Architecture diagram — styled code block */}
        <div className="mx-auto max-w-4xl overflow-hidden rounded-2xl border border-white/[0.08] bg-[#12121A]">
          {/* Window header */}
          <div className="flex items-center gap-2 border-b border-white/[0.06] px-5 py-3">
            <div className="h-3 w-3 rounded-full bg-red-500/80" />
            <div className="h-3 w-3 rounded-full bg-amber-500/80" />
            <div className="h-3 w-3 rounded-full bg-green-500/80" />
            <span className="ml-3 text-xs text-gray-500 font-mono">amttp-architecture.yml</span>
          </div>
          {/* Content */}
          <div className="p-6 md:p-8 font-mono text-[13px] leading-7 text-gray-400 overflow-x-auto">
            <div>
              <span className="text-gray-500"># Client Layer</span>
            </div>
            <div>
              <span className="text-indigo-400">flutter_app</span>
              <span className="text-gray-600">:</span>
              <span className="text-gray-500"> # Consumer Wallet (R1/R2)</span>
            </div>
            <div className="pl-6">
              <span className="text-cyan-400">port</span>
              <span className="text-gray-600">:</span>
              <span className="text-amber-300"> 3010</span>
            </div>
            <div className="pl-6">
              <span className="text-cyan-400">features</span>
              <span className="text-gray-600">:</span>
              <span className="text-green-400"> [wallet, transfer, trust_check, zk_privacy]</span>
            </div>
            <div className="mt-2">
              <span className="text-indigo-400">nextjs_dashboard</span>
              <span className="text-gray-600">:</span>
              <span className="text-gray-500"> # War Room (R3–R6)</span>
            </div>
            <div className="pl-6">
              <span className="text-cyan-400">port</span>
              <span className="text-gray-600">:</span>
              <span className="text-amber-300"> 3006</span>
            </div>
            <div className="pl-6">
              <span className="text-cyan-400">features</span>
              <span className="text-gray-600">:</span>
              <span className="text-green-400"> [flagged_queue, graph_explorer, policy_editor, analytics]</span>
            </div>
            <div className="mt-4">
              <span className="text-gray-500"># Intelligence Layer</span>
            </div>
            <div>
              <span className="text-indigo-400">orchestrator</span>
              <span className="text-gray-600">:</span>
              <span className="text-amber-300"> 8007</span>
              <span className="text-gray-500"> # Fan-out to all ML services</span>
            </div>
            <div>
              <span className="text-indigo-400">ml_risk_api</span>
              <span className="text-gray-600">:</span>
              <span className="text-amber-300"> 8000</span>
              <span className="text-gray-500"> # XGBoost → VAE → GNN ensemble</span>
            </div>
            <div>
              <span className="text-indigo-400">graph_service</span>
              <span className="text-gray-600">:</span>
              <span className="text-amber-300"> 8001</span>
              <span className="text-gray-500"> # Memgraph entity resolution</span>
            </div>
            <div>
              <span className="text-indigo-400">sanctions_api</span>
              <span className="text-gray-600">:</span>
              <span className="text-amber-300"> 8004</span>
              <span className="text-gray-500"> # OFAC, UN, EU screening</span>
            </div>
            <div>
              <span className="text-indigo-400">explainability</span>
              <span className="text-gray-600">:</span>
              <span className="text-amber-300"> 8009</span>
              <span className="text-gray-500"> # SHAP + counterfactual reasoning</span>
            </div>
            <div>
              <span className="text-indigo-400">zk_naf</span>
              <span className="text-gray-600">:</span>
              <span className="text-amber-300"> 8010</span>
              <span className="text-gray-500"> # Zero-knowledge compliance proofs</span>
            </div>
            <div className="mt-4">
              <span className="text-gray-500"># Data Layer</span>
            </div>
            <div>
              <span className="text-indigo-400">mongodb</span>
              <span className="text-gray-600">:</span>
              <span className="text-amber-300"> 27017</span>
              <span className="text-gray-500"> # Transactions, profiles, audit</span>
            </div>
            <div>
              <span className="text-indigo-400">redis</span>
              <span className="text-gray-600">:</span>
              <span className="text-amber-300"> 6379</span>
              <span className="text-gray-500"> # Session cache, rate limiting</span>
            </div>
            <div>
              <span className="text-indigo-400">memgraph</span>
              <span className="text-gray-600">:</span>
              <span className="text-amber-300"> 7687</span>
              <span className="text-gray-500"> # Graph DB for entity networks</span>
            </div>
            <div className="mt-4">
              <span className="text-gray-500"># Blockchain Layer</span>
            </div>
            <div>
              <span className="text-indigo-400">smart_contracts</span>
              <span className="text-gray-600">:</span>
              <span className="text-green-400"> Solidity ^0.8.24</span>
            </div>
            <div className="pl-6">
              <span className="text-cyan-400">pattern</span>
              <span className="text-gray-600">:</span>
              <span className="text-green-400"> UUPS Upgradeable Proxy</span>
            </div>
            <div className="pl-6">
              <span className="text-cyan-400">modules</span>
              <span className="text-gray-600">:</span>
              <span className="text-green-400"> [PolicyManager, RiskOracle, DisputeResolver, NFTSwap]</span>
            </div>
          </div>
        </div>
      </Section>

      {/* ── HOW IT WORKS ─────────────────────────────────────────────── */}
      <Section id="how-it-works">
        <div className="mb-16 text-center">
          <p className="mb-3 text-sm font-semibold uppercase tracking-widest text-indigo-400">
            Workflow
          </p>
          <h2 className="text-3xl font-bold md:text-4xl">Three Steps to Compliance</h2>
        </div>

        <div className="relative grid gap-12 md:grid-cols-3 md:gap-8">
          {/* Connector lines (desktop only) */}
          <div className="pointer-events-none absolute top-7 left-[16.67%] right-[16.67%] hidden h-px bg-gradient-to-r from-transparent via-indigo-500/30 to-transparent md:block" />

          <StepCard
            number="01"
            title="Ingest & Score"
            description="Every on-chain transaction is ingested in real-time, scored by the ML ensemble, and enriched with graph context — all in under 100ms."
          />
          <StepCard
            number="02"
            title="Flag & Investigate"
            description="High-risk transactions are routed to the War Room flagged queue. Compliance officers see explainable risk factors, entity graphs, and policy violations."
          />
          <StepCard
            number="03"
            title="Enforce & Report"
            description="Approved actions trigger on-chain enforcement — adaptive friction, transfer freezes, or STR filing. Every decision is immutably audited."
          />
        </div>
      </Section>

      {/* ── COMPLIANCE & TRUST ───────────────────────────────────────── */}
      <Section id="compliance" className="border-y border-white/[0.06] bg-white/[0.015]">
        <div className="mb-16 text-center">
          <p className="mb-3 text-sm font-semibold uppercase tracking-widest text-indigo-400">
            Trust & Compliance
          </p>
          <h2 className="text-3xl font-bold md:text-4xl">Built for Regulators</h2>
        </div>

        <div className="grid gap-8 md:grid-cols-3">
          {[
            {
              title: 'FCA Compliant',
              description:
                'Designed to meet UK Financial Conduct Authority requirements for crypto-asset businesses, including Travel Rule and STR obligations.',
              icon: '🇬🇧',
            },
            {
              title: 'FATF Travel Rule',
              description:
                'Built-in originator/beneficiary data collection and secure relay for cross-border virtual asset transfers per FATF Recommendation 16.',
              icon: '🌐',
            },
            {
              title: 'Zero-Knowledge Privacy',
              description:
                'zkSNARK-based Non-Attributable Fingerprints (zkNAF) prove compliance without revealing sensitive transaction details or wallet identities.',
              icon: '🔐',
            },
          ].map((item) => (
            <div
              key={item.title}
              className="rounded-2xl border border-white/[0.06] bg-white/[0.02] p-8 transition-all duration-300 hover:border-white/[0.12]"
            >
              <div className="mb-4 text-3xl">{item.icon}</div>
              <h3 className="mb-3 text-lg font-semibold text-white">{item.title}</h3>
              <p className="text-sm leading-relaxed text-gray-400">{item.description}</p>
            </div>
          ))}
        </div>
      </Section>

      {/* ── RBAC ROLES ───────────────────────────────────────────────── */}
      <Section>
        <div className="mb-16 text-center">
          <p className="mb-3 text-sm font-semibold uppercase tracking-widest text-indigo-400">
            Role-Based Access
          </p>
          <h2 className="text-3xl font-bold md:text-4xl">Six Roles, Two Interfaces</h2>
          <p className="mt-4 text-gray-400 max-w-2xl mx-auto">
            Retail users (R1–R2) use the <span className="text-emerald-400 font-medium">Consumer App</span> for wallet and transfer management.
            Institutional users (R3–R6) access the <span className="text-indigo-400 font-medium">War Room</span> for compliance operations.
          </p>
        </div>

        <div className="grid gap-8 md:grid-cols-2">
          {/* Consumer Group */}
          <a href={flutterUrl} className="group rounded-2xl border border-emerald-500/20 bg-emerald-500/[0.02] p-6 transition-all hover:border-emerald-500/40 hover:bg-emerald-500/[0.06]">
            <div className="mb-5 flex items-center justify-between">
              <div className="flex items-center gap-3">
                <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-emerald-500/20">
                  <svg width="20" height="20" fill="none" stroke="currentColor" className="text-emerald-400" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" viewBox="0 0 24 24">
                    <rect x="2" y="3" width="20" height="14" rx="2" />
                    <path d="M12 17v4M8 21h8" />
                  </svg>
                </div>
                <div>
                  <div className="text-base font-semibold text-white">Consumer App</div>
                  <div className="text-xs text-emerald-400/60">Focus Mode · Flutter</div>
                </div>
              </div>
              <svg width="20" height="20" fill="none" stroke="currentColor" className="text-emerald-500/40 transition group-hover:text-emerald-400 group-hover:translate-x-1" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" viewBox="0 0 24 24">
                <path d="M5 12h14M12 5l7 7-7 7" />
              </svg>
            </div>
            <div className="grid gap-3 sm:grid-cols-2">
              {[
                { role: 'R1', title: 'End User', desc: 'Wallet, transfers, trust checks' },
                { role: 'R2', title: 'PEP / High-Risk', desc: 'Enhanced due diligence view' },
              ].map((r) => (
                <div key={r.role} className="rounded-xl border border-emerald-500/10 bg-white/[0.02] p-4">
                  <div className="mb-2 flex items-center gap-2">
                    <span className="font-mono text-sm font-bold text-white">{r.role}</span>
                    <span className="rounded-full bg-emerald-500/20 px-2 py-0.5 text-xs font-medium text-emerald-400">Focus Mode</span>
                  </div>
                  <h3 className="mb-1 text-sm font-semibold text-white">{r.title}</h3>
                  <p className="text-xs text-gray-500">{r.desc}</p>
                </div>
              ))}
            </div>
          </a>

          {/* Institutional Group */}
          <a href={flutterUrl} className="group rounded-2xl border border-indigo-500/20 bg-indigo-500/[0.02] p-6 transition-all hover:border-indigo-500/40 hover:bg-indigo-500/[0.06]">
            <div className="mb-5 flex items-center justify-between">
              <div className="flex items-center gap-3">
                <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-indigo-500/20">
                  <svg width="20" height="20" fill="none" stroke="currentColor" className="text-indigo-400" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" viewBox="0 0 24 24">
                    <rect x="3" y="3" width="18" height="18" rx="2" ry="2" />
                    <line x1="3" y1="9" x2="21" y2="9" />
                    <line x1="9" y1="21" x2="9" y2="9" />
                  </svg>
                </div>
                <div>
                  <div className="text-base font-semibold text-white">War Room</div>
                  <div className="text-xs text-indigo-400/60">Command Centre · Next.js</div>
                </div>
              </div>
              <svg width="20" height="20" fill="none" stroke="currentColor" className="text-indigo-500/40 transition group-hover:text-indigo-400 group-hover:translate-x-1" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" viewBox="0 0 24 24">
                <path d="M5 12h14M12 5l7 7-7 7" />
              </svg>
            </div>
            <div className="grid gap-3 sm:grid-cols-2">
              {[
                { role: 'R3', title: 'Institution Ops', desc: 'Flagged queue triage, graphs' },
                { role: 'R4', title: 'Compliance Officer', desc: 'Policy editing, enforcement' },
                { role: 'R5', title: 'Platform Admin', desc: 'User management, ML models' },
                { role: 'R6', title: 'Super Admin', desc: 'Emergency override, full access' },
              ].map((r) => (
                <div key={r.role} className="rounded-xl border border-indigo-500/10 bg-white/[0.02] p-4">
                  <div className="mb-2 flex items-center gap-2">
                    <span className="font-mono text-sm font-bold text-white">{r.role}</span>
                    <span className="rounded-full bg-indigo-500/20 px-2 py-0.5 text-xs font-medium text-indigo-400">War Room</span>
                  </div>
                  <h3 className="mb-1 text-sm font-semibold text-white">{r.title}</h3>
                  <p className="text-xs text-gray-500">{r.desc}</p>
                </div>
              ))}
            </div>
          </a>
        </div>
      </Section>

      {/* ── CTA BANNER ───────────────────────────────────────────────── */}
      <section className="relative overflow-hidden px-6 py-24">
        <div className="pointer-events-none absolute inset-0">
          <div className="absolute left-1/2 top-1/2 h-[500px] w-[500px] -translate-x-1/2 -translate-y-1/2 rounded-full bg-indigo-600/20 blur-[120px]" />
        </div>
        <div className="relative z-10 mx-auto max-w-3xl text-center">
          <h2 className="mb-4 text-3xl font-bold md:text-4xl">
            Ready to Secure Your DeFi Operations?
          </h2>
          <p className="mb-8 text-lg text-gray-400">
            Choose your entry point — retail users get a streamlined wallet experience, institutions get full compliance command & control.
          </p>
          <div className="flex flex-col items-center justify-center gap-4 sm:flex-row">
            <a
              href={flutterUrl}
              className="inline-flex items-center gap-2 rounded-xl border border-emerald-500/30 bg-emerald-500/10 px-8 py-3.5 text-base font-semibold text-white transition-all hover:bg-emerald-500/20"
            >
              <svg width="18" height="18" fill="none" stroke="currentColor" className="text-emerald-400" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" viewBox="0 0 24 24">
                <rect x="2" y="3" width="20" height="14" rx="2" />
                <path d="M12 17v4M8 21h8" />
              </svg>
              Consumer App
            </a>
            <a
              href={flutterUrl}
              className="inline-flex items-center gap-2 rounded-xl bg-indigo-600 px-8 py-3.5 text-base font-semibold text-white shadow-2xl shadow-indigo-500/30 transition-all hover:bg-indigo-500"
            >
              Institutional War Room
              <svg width="18" height="18" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" viewBox="0 0 24 24">
                <path d="M5 12h14M12 5l7 7-7 7" />
              </svg>
            </a>
          </div>
        </div>
      </section>

      {/* ── FOOTER ───────────────────────────────────────────────────── */}
      <footer className="border-t border-white/[0.06] bg-[#0A0A0F]">
        <div className="mx-auto max-w-7xl px-6 py-12 md:px-12">
          <div className="grid gap-8 md:grid-cols-4">
            {/* Brand */}
            <div>
              <div className="mb-4 flex items-center gap-2">
                <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-gradient-to-br from-indigo-500 to-violet-600">
                  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="white" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                    <path d="M12 2L2 7l10 5 10-5-10-5z" />
                    <path d="M2 17l10 5 10-5" />
                    <path d="M2 12l10 5 10-5" />
                  </svg>
                </div>
                <span className="text-base font-bold">AMTTP</span>
              </div>
              <p className="text-sm text-gray-500">
                Anti-Money Laundering Transaction Transfer Protocol
              </p>
            </div>

            {/* Product */}
            <div>
              <h4 className="mb-3 text-sm font-semibold text-gray-300">Product</h4>
              <ul className="space-y-2 text-sm text-gray-500">
                <li><a href="#features" className="hover:text-white transition">Features</a></li>
                <li><a href="#architecture" className="hover:text-white transition">Architecture</a></li>
                <li><a href="#compliance" className="hover:text-white transition">Compliance</a></li>
                <li><a href={flutterUrl} className="hover:text-white transition">War Room</a></li>
                <li><a href={flutterUrl} className="hover:text-white transition">Consumer App</a></li>
              </ul>
            </div>

            {/* Research */}
            <div>
              <h4 className="mb-3 text-sm font-semibold text-gray-300">Research</h4>
              <ul className="space-y-2 text-sm text-gray-500">
                <li><span className="cursor-default">SIAM Publication</span></li>
                <li><span className="cursor-default">UDL Framework</span></li>
                <li><span className="cursor-default">BSDT Protocol</span></li>
                <li><span className="cursor-default">zkNAF Architecture</span></li>
              </ul>
            </div>

            {/* Legal */}
            <div>
              <h4 className="mb-3 text-sm font-semibold text-gray-300">Legal</h4>
              <ul className="space-y-2 text-sm text-gray-500">
                <li><span className="cursor-default">Privacy Policy</span></li>
                <li><span className="cursor-default">Terms of Service</span></li>
                <li><span className="cursor-default">Security</span></li>
              </ul>
            </div>
          </div>

          <div className="mt-12 flex flex-col items-center justify-between gap-4 border-t border-white/[0.06] pt-8 md:flex-row">
            <p className="text-sm text-gray-600">
              &copy; {new Date().getFullYear()} AMTTP Protocol. All rights reserved.
            </p>
            <div className="flex gap-4 text-gray-500">
              <span className="text-xs">
                Built with Next.js · Flutter · FastAPI · Solidity · XGBoost · Memgraph
              </span>
            </div>
          </div>
        </div>
      </footer>
    </div>
  );
}
