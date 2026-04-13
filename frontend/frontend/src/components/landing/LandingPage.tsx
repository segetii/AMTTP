'use client';

import React, { useEffect, useState, useRef } from 'react';
import Link from 'next/link';

/* ═══════════════════════════════════════════════════════════════════════════════
 * AMTTP Landing Page — SaaS-Grade
 *
 * Sections:
 *   1. Navbar (sticky, glass)
 *   2. Hero (outcome-focused tagline + CTAs)
 *   3. Supported Networks Bar
 *   4. Performance Stats Strip
 *   5. Feature Cards (4 pillars — outcome-focused)
 *   6. Platform Overview (abstract layers)
 *   7. How It Works (3-step)
 *   8. Built For (industry segments)
 *   9. Compliance & Trust
 *  10. Why AMTTP (differentiators)
 *  11. CTA Banner
 *  12. Footer
 * ═══════════════════════════════════════════════════════════════════════════════ */

// ── Animated counter ────────────────────────────────────────────────────────
function AnimatedNumber({ target, suffix = '', prefix = '' }: { target: number; suffix?: string; prefix?: string }) {
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
      {prefix}{val.toLocaleString()}
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
  const [flutterUrl, setFlutterUrl] = useState('/app/#/sign-out');

  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 40);
    window.addEventListener('scroll', onScroll, { passive: true });
    const port = window.location.port;
    if (port === '3006' || port === '3000') {
      setFlutterUrl('http://localhost:3010/#/sign-out');
    } else {
      setFlutterUrl('/app/#/sign-out');
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
            <a href="#platform" className="text-sm text-gray-400 transition hover:text-white">
              Platform
            </a>
            <a href="#how-it-works" className="text-sm text-gray-400 transition hover:text-white">
              How It Works
            </a>
            <a href="#solutions" className="text-sm text-gray-400 transition hover:text-white">
              Solutions
            </a>
            <a href="#compliance" className="text-sm text-gray-400 transition hover:text-white">
              Compliance
            </a>
          </div>

          {/* CTA */}
          <div className="flex items-center gap-3">
            <a
              href={flutterUrl}
              className="rounded-lg px-4 py-2 text-sm font-medium text-gray-300 transition hover:text-white"
            >
              Sign In
            </a>
            <a
              href={flutterUrl}
              className="rounded-lg bg-indigo-600 px-5 py-2 text-sm font-semibold text-white shadow-lg shadow-indigo-500/25 transition hover:bg-indigo-500"
            >
              Get Started
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
            Enterprise DeFi Compliance Platform
          </div>

          <h1 className="mb-6 text-5xl font-extrabold leading-[1.1] tracking-tight md:text-7xl">
            Stop Illicit Flows{' '}
            <span className="bg-gradient-to-r from-indigo-400 via-violet-400 to-cyan-400 bg-clip-text text-transparent">
              Before They Settle.
            </span>
          </h1>

          <p className="mx-auto mb-10 max-w-2xl text-lg leading-relaxed text-gray-400 md:text-xl">
            AMTTP combines real-time machine learning, cross-chain intelligence, and on-chain
            enforcement to protect decentralised finance from money laundering, fraud,
            and sanctions violations — in under 200 milliseconds.
          </p>

          {/* CTA Buttons */}
          <div className="mt-4 flex flex-col items-center justify-center gap-4 sm:flex-row">
            <a
              href={flutterUrl}
              className="inline-flex items-center gap-2 rounded-xl bg-indigo-600 px-8 py-3.5 text-base font-semibold text-white shadow-2xl shadow-indigo-500/30 transition-all hover:bg-indigo-500"
            >
              Get Started Free
              <svg width="18" height="18" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" viewBox="0 0 24 24">
                <path d="M5 12h14M12 5l7 7-7 7" />
              </svg>
            </a>
            <a
              href="#platform"
              className="inline-flex items-center gap-2 rounded-xl border border-white/[0.12] bg-white/[0.04] px-8 py-3.5 text-base font-semibold text-white transition-all hover:bg-white/[0.08]"
            >
              Explore Platform
            </a>
          </div>

          <div className="mt-8">
            <p className="text-sm text-gray-600">
              No credit card required · Deploy in minutes · Self-hosted or cloud
            </p>
          </div>
        </div>
      </section>

      {/* ── SUPPORTED NETWORKS ───────────────────────────────────────── */}
      <section className="border-y border-white/[0.06] bg-white/[0.01] py-8">
        <div className="mx-auto max-w-5xl px-6">
          <p className="mb-6 text-center text-xs font-semibold uppercase tracking-widest text-gray-600">
            Deployed &amp; Verified On
          </p>
          <div className="flex flex-wrap items-center justify-center gap-8 md:gap-14">
            {[
              { name: 'Ethereum', icon: '⟠' },
              { name: 'Base', icon: '🔵' },
              { name: 'Arbitrum', icon: '🔷' },
              { name: 'LayerZero', icon: '◎' },
            ].map((chain) => (
              <div key={chain.name} className="flex items-center gap-2 text-gray-500">
                <span className="text-lg">{chain.icon}</span>
                <span className="text-sm font-medium">{chain.name}</span>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ── PERFORMANCE STATS ────────────────────────────────────────── */}
      <section className="border-b border-white/[0.06] bg-white/[0.015]">
        <div className="mx-auto grid max-w-7xl grid-cols-2 gap-px md:grid-cols-4">
          {[
            { label: 'Risk Scoring Latency', value: 200, prefix: '<', suffix: 'ms' },
            { label: 'Detection Accuracy', value: 99, suffix: '.99%' },
            { label: 'Integrated Services', value: 12, suffix: '+' },
            { label: 'Supported Networks', value: 3, suffix: ' Chains' },
          ].map((stat) => (
            <div key={stat.label} className="px-6 py-8 text-center md:px-10">
              <div className="mb-1 text-3xl font-bold text-white md:text-4xl">
                <AnimatedNumber target={stat.value} prefix={stat.prefix} suffix={stat.suffix} />
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
            title="Real-Time Risk Detection"
            description="Every transaction is scored by an ensemble of machine learning models in under 200ms — catching structuring, layering, and anomalous patterns before settlement."
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
            title="Entity Graph Intelligence"
            description="Automatically maps wallet clusters, transaction chains, and counterparty networks in real-time — surfacing hidden connections human analysts would miss."
          />
          <FeatureCard
            accent="bg-amber-500/20 text-amber-400"
            icon={
              <svg width="22" height="22" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" viewBox="0 0 24 24">
                <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
              </svg>
            }
            title="On-Chain Enforcement"
            description="Smart contracts enforce policy gates, adaptive friction, and multi-signature approvals — creating an immutable, auditable compliance trail directly on the blockchain."
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
            title="Compliance Command Centre"
            description="A purpose-built operations dashboard for compliance teams — real-time KPI monitoring, flagged transaction triage, policy configuration, and regulatory reporting."
          />
        </div>
      </Section>

      {/* ── PLATFORM OVERVIEW ──────────────────────────────────────── */}
      <Section id="platform" className="border-y border-white/[0.06] bg-white/[0.015]">
        <div className="mb-16 text-center">
          <p className="mb-3 text-sm font-semibold uppercase tracking-widest text-indigo-400">
            Platform
          </p>
          <h2 className="text-3xl font-bold md:text-4xl">Intelligent Compliance Infrastructure</h2>
          <p className="mt-4 mx-auto max-w-2xl text-gray-400">
            Three integrated layers working together — from client applications through
            an intelligence engine to on-chain enforcement.
          </p>
        </div>

        {/* Abstract 3-layer diagram */}
        <div className="mx-auto max-w-3xl space-y-4">
          {/* Layer 1 — Client */}
          <div className="rounded-2xl border border-emerald-500/20 bg-emerald-500/[0.03] p-6">
            <div className="flex items-center gap-4 mb-3">
              <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-emerald-500/20">
                <svg width="20" height="20" fill="none" stroke="currentColor" className="text-emerald-400" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" viewBox="0 0 24 24">
                  <rect x="2" y="3" width="20" height="14" rx="2" /><path d="M12 17v4M8 21h8" />
                </svg>
              </div>
              <div>
                <h3 className="text-base font-semibold text-white">Client Layer</h3>
                <p className="text-xs text-gray-500">Web app, mobile wallet, API integrations</p>
              </div>
            </div>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
              {['Wallet Management', 'Transfer Screening', 'Trust Verification', 'Compliance Dashboard'].map((f) => (
                <div key={f} className="rounded-lg bg-white/[0.04] px-3 py-2 text-xs text-gray-400 text-center">{f}</div>
              ))}
            </div>
          </div>

          {/* Connector */}
          <div className="flex justify-center">
            <div className="h-6 w-px bg-gradient-to-b from-emerald-500/30 to-indigo-500/30" />
          </div>

          {/* Layer 2 — Intelligence */}
          <div className="rounded-2xl border border-indigo-500/20 bg-indigo-500/[0.03] p-6">
            <div className="flex items-center gap-4 mb-3">
              <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-indigo-500/20">
                <svg width="20" height="20" fill="none" stroke="currentColor" className="text-indigo-400" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" viewBox="0 0 24 24">
                  <path d="M12 2a10 10 0 1 0 0 20 10 10 0 0 0 0-20z" /><path d="M12 6v6l4 2" />
                </svg>
              </div>
              <div>
                <h3 className="text-base font-semibold text-white">Intelligence Engine</h3>
                <p className="text-xs text-gray-500">ML risk scoring, graph analytics, sanctions screening</p>
              </div>
            </div>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
              {['Risk Scoring', 'Entity Resolution', 'Sanctions Check', 'Explainable AI'].map((f) => (
                <div key={f} className="rounded-lg bg-white/[0.04] px-3 py-2 text-xs text-gray-400 text-center">{f}</div>
              ))}
            </div>
          </div>

          {/* Connector */}
          <div className="flex justify-center">
            <div className="h-6 w-px bg-gradient-to-b from-indigo-500/30 to-amber-500/30" />
          </div>

          {/* Layer 3 — Blockchain */}
          <div className="rounded-2xl border border-amber-500/20 bg-amber-500/[0.03] p-6">
            <div className="flex items-center gap-4 mb-3">
              <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-amber-500/20">
                <svg width="20" height="20" fill="none" stroke="currentColor" className="text-amber-400" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" viewBox="0 0 24 24">
                  <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
                </svg>
              </div>
              <div>
                <h3 className="text-base font-semibold text-white">Blockchain Layer</h3>
                <p className="text-xs text-gray-500">Multi-chain smart contracts, cross-chain messaging</p>
              </div>
            </div>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
              {['Policy Enforcement', 'Adaptive Friction', 'Cross-Chain Relay', 'Privacy Proofs'].map((f) => (
                <div key={f} className="rounded-lg bg-white/[0.04] px-3 py-2 text-xs text-gray-400 text-center">{f}</div>
              ))}
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

      {/* ── BUILT FOR ────────────────────────────────────────────────── */}
      <Section id="solutions">
        <div className="mb-16 text-center">
          <p className="mb-3 text-sm font-semibold uppercase tracking-widest text-indigo-400">
            Solutions
          </p>
          <h2 className="text-3xl font-bold md:text-4xl">Built for Every Stakeholder</h2>
          <p className="mt-4 text-gray-400 max-w-2xl mx-auto">
            Whether you&apos;re building a DeFi protocol, running a compliant exchange, or overseeing
            regulatory obligations — AMTTP fits your workflow.
          </p>
        </div>

        <div className="grid gap-6 md:grid-cols-2 lg:grid-cols-4">
          {[
            {
              title: 'DeFi Protocols',
              description: 'Embed compliance directly into smart contract transactions. Screen users and enforce policies without sacrificing decentralisation.',
              icon: (
                <svg width="22" height="22" fill="none" stroke="currentColor" className="text-cyan-400" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" viewBox="0 0 24 24">
                  <path d="M12 2L2 7l10 5 10-5-10-5z" /><path d="M2 17l10 5 10-5" /><path d="M2 12l10 5 10-5" />
                </svg>
              ),
              accent: 'bg-cyan-500/20',
            },
            {
              title: 'Financial Institutions',
              description: 'Extend your AML/KYC programme to digital assets with enterprise-grade controls, audit trails, and integrations with existing compliance tooling.',
              icon: (
                <svg width="22" height="22" fill="none" stroke="currentColor" className="text-violet-400" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" viewBox="0 0 24 24">
                  <rect x="3" y="3" width="18" height="18" rx="2" /><line x1="3" y1="9" x2="21" y2="9" /><line x1="9" y1="21" x2="9" y2="9" />
                </svg>
              ),
              accent: 'bg-violet-500/20',
            },
            {
              title: 'Compliance Teams',
              description: 'Investigate flagged transactions with explainable AI risk factors, entity graphs, and one-click regulatory reporting — all from a single dashboard.',
              icon: (
                <svg width="22" height="22" fill="none" stroke="currentColor" className="text-amber-400" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" viewBox="0 0 24 24">
                  <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
                </svg>
              ),
              accent: 'bg-amber-500/20',
            },
            {
              title: 'Regulators',
              description: 'Access transparent, immutable compliance records. Verify policy enforcement and transaction history without compromising user privacy.',
              icon: (
                <svg width="22" height="22" fill="none" stroke="currentColor" className="text-rose-400" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" viewBox="0 0 24 24">
                  <circle cx="12" cy="12" r="10" /><line x1="12" y1="8" x2="12" y2="12" /><line x1="12" y1="16" x2="12.01" y2="16" />
                </svg>
              ),
              accent: 'bg-rose-500/20',
            },
          ].map((item) => (
            <div key={item.title} className="group rounded-2xl border border-white/[0.06] bg-white/[0.02] p-8 transition-all duration-300 hover:border-white/[0.12] hover:bg-white/[0.04]">
              <div className={`mb-5 flex h-12 w-12 items-center justify-center rounded-xl ${item.accent}`}>
                {item.icon}
              </div>
              <h3 className="mb-3 text-lg font-semibold text-white">{item.title}</h3>
              <p className="text-sm leading-relaxed text-gray-400">{item.description}</p>
            </div>
          ))}
        </div>
      </Section>

      {/* ── WHY AMTTP ────────────────────────────────────────────────── */}
      <Section>
        <div className="mb-16 text-center">
          <p className="mb-3 text-sm font-semibold uppercase tracking-widest text-indigo-400">
            Why AMTTP
          </p>
          <h2 className="text-3xl font-bold md:text-4xl">What Sets Us Apart</h2>
        </div>

        <div className="grid gap-6 md:grid-cols-2 lg:grid-cols-3">
          {[
            { title: 'Pre-Settlement Blocking', desc: 'Risk scores are computed and enforced before transactions settle — not after the damage is done.' },
            { title: 'Self-Hosted Option', desc: 'Deploy on your own infrastructure. Your data never leaves your environment. Full sovereignty over compliance operations.' },
            { title: 'Parallel Processing', desc: 'Multiple intelligence services run concurrently — sanctions, risk scoring, graph analysis — delivering results in under 200ms.' },
            { title: 'Explainable Decisions', desc: 'Every risk score comes with human-readable explanations and contributing factors, satisfying regulator audit requirements.' },
            { title: 'Cross-Chain Native', desc: 'Built-in cross-chain messaging via LayerZero. Share risk intelligence across Ethereum, Base, and Arbitrum seamlessly.' },
            { title: 'Privacy by Design', desc: 'Zero-knowledge proofs allow compliance verification without revealing sensitive transaction details or wallet identities.' },
          ].map((item) => (
            <div key={item.title} className="flex gap-4 rounded-xl border border-white/[0.06] bg-white/[0.02] p-6 transition-all hover:border-white/[0.12]">
              <div className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-indigo-500/20">
                <svg width="16" height="16" fill="none" stroke="currentColor" className="text-indigo-400" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" viewBox="0 0 24 24">
                  <path d="M20 6L9 17l-5-5" />
                </svg>
              </div>
              <div>
                <h3 className="mb-1 text-sm font-semibold text-white">{item.title}</h3>
                <p className="text-sm leading-relaxed text-gray-500">{item.desc}</p>
              </div>
            </div>
          ))}
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
            Get started in minutes — deploy AMTTP on your infrastructure or use our hosted platform.
            No credit card required.
          </p>
          <div className="flex flex-col items-center justify-center gap-4 sm:flex-row">
            <a
              href={flutterUrl}
              className="inline-flex items-center gap-2 rounded-xl bg-indigo-600 px-8 py-3.5 text-base font-semibold text-white shadow-2xl shadow-indigo-500/30 transition-all hover:bg-indigo-500"
            >
              Get Started Free
              <svg width="18" height="18" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" viewBox="0 0 24 24">
                <path d="M5 12h14M12 5l7 7-7 7" />
              </svg>
            </a>
            <a
              href="#platform"
              className="inline-flex items-center gap-2 rounded-xl border border-white/[0.12] bg-white/[0.04] px-8 py-3.5 text-base font-semibold text-white transition-all hover:bg-white/[0.08]"
            >
              Explore Platform
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
                Anti-Money Laundering Transaction Transfer Protocol for decentralised finance.
              </p>
            </div>

            {/* Product */}
            <div>
              <h4 className="mb-3 text-sm font-semibold text-gray-300">Product</h4>
              <ul className="space-y-2 text-sm text-gray-500">
                <li><a href="#features" className="hover:text-white transition">Features</a></li>
                <li><a href="#platform" className="hover:text-white transition">Platform</a></li>
                <li><a href="#solutions" className="hover:text-white transition">Solutions</a></li>
                <li><a href="#compliance" className="hover:text-white transition">Compliance</a></li>
              </ul>
            </div>

            {/* Resources */}
            <div>
              <h4 className="mb-3 text-sm font-semibold text-gray-300">Resources</h4>
              <ul className="space-y-2 text-sm text-gray-500">
                <li><a href={flutterUrl} className="hover:text-white transition">Get Started</a></li>
                <li><span className="cursor-default">Documentation</span></li>
                <li><span className="cursor-default">API Reference</span></li>
                <li><span className="cursor-default">Status Page</span></li>
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
          </div>
        </div>
      </footer>
    </div>
  );
}
