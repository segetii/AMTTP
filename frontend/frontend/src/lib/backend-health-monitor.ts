// frontend/frontend/src/lib/backend-health-monitor.ts
// Backend health monitor for Next.js — mirrors Flutter's BackendHealthMonitor

export type ServiceStatus = 'online' | 'degraded' | 'offline' | 'unknown';

export interface ServiceHealth {
  name: string;
  url: string;
  status: ServiceStatus;
  latencyMs: number | null;
  lastCheck: Date | null;
  error: string | null;
}

export interface BackendHealthState {
  services: Record<string, ServiceHealth>;
  isChecking: boolean;
  lastFullCheck: Date | null;
}

const POLL_INTERVAL_MS = 30_000;
const TIMEOUT_MS = 8_000;
const DEGRADED_THRESHOLD_MS = 3_000;

const SERVICE_ENDPOINTS: Record<string, { name: string; healthPath: string }> = {
  orchestrator: {
    name: 'Orchestrator',
    healthPath: '/health',
  },
  integrity: {
    name: 'Integrity Engine',
    healthPath: '/health',
  },
  riskEngine: {
    name: 'Risk Engine',
    healthPath: '/health',
  },
  explainability: {
    name: 'Explainability',
    healthPath: '/health',
  },
};

function resolveBaseUrl(serviceKey: string): string {
  const apiBase = process.env.NEXT_PUBLIC_API_URL || '';
  if (apiBase) {
    // Production: all services behind nginx reverse-proxy
    const prefix = serviceKey === 'orchestrator' ? '/api' :
                   serviceKey === 'integrity' ? '/api/integrity' :
                   serviceKey === 'riskEngine' ? '/api/risk' :
                   serviceKey === 'explainability' ? '/api/explain' : '/api';
    return `${apiBase}${prefix}`;
  }
  // Development: direct ports
  const devPorts: Record<string, number> = {
    orchestrator: 4000,
    integrity: 4001,
    riskEngine: 4002,
    explainability: 4003,
  };
  return `http://localhost:${devPorts[serviceKey] ?? 4000}`;
}

type Listener = (state: BackendHealthState) => void;

class BackendHealthMonitor {
  private _state: BackendHealthState;
  private _timer: ReturnType<typeof setInterval> | null = null;
  private _listeners = new Set<Listener>();

  constructor() {
    const services: Record<string, ServiceHealth> = {};
    for (const [key, cfg] of Object.entries(SERVICE_ENDPOINTS)) {
      services[key] = {
        name: cfg.name,
        url: `${resolveBaseUrl(key)}${cfg.healthPath}`,
        status: 'unknown',
        latencyMs: null,
        lastCheck: null,
        error: null,
      };
    }
    this._state = { services, isChecking: false, lastFullCheck: null };
  }

  get state(): Readonly<BackendHealthState> {
    return this._state;
  }

  get hasOutage(): boolean {
    return Object.values(this._state.services).some(s => s.status === 'offline');
  }

  get isFullyHealthy(): boolean {
    return Object.values(this._state.services).every(s => s.status === 'online');
  }

  get summary(): string {
    const down = Object.values(this._state.services).filter(s => s.status === 'offline');
    const degraded = Object.values(this._state.services).filter(s => s.status === 'degraded');
    if (down.length === 0 && degraded.length === 0) return 'All services operational';
    const parts: string[] = [];
    if (down.length > 0) parts.push(`${down.map(s => s.name).join(', ')} offline`);
    if (degraded.length > 0) parts.push(`${degraded.map(s => s.name).join(', ')} slow`);
    return parts.join(' · ');
  }

  subscribe(listener: Listener): () => void {
    this._listeners.add(listener);
    return () => this._listeners.delete(listener);
  }

  private _notify() {
    for (const l of this._listeners) {
      try { l(this._state); } catch (_) { /* ignore */ }
    }
  }

  start() {
    if (this._timer) return;
    this._checkAll();
    this._timer = setInterval(() => this._checkAll(), POLL_INTERVAL_MS);
  }

  stop() {
    if (this._timer) {
      clearInterval(this._timer);
      this._timer = null;
    }
  }

  async checkNow(): Promise<BackendHealthState> {
    await this._checkAll();
    return this._state;
  }

  private async _checkAll() {
    this._state = { ...this._state, isChecking: true };
    this._notify();

    const checks = Object.entries(this._state.services).map(async ([key, svc]) => {
      const start = performance.now();
      try {
        const controller = new AbortController();
        const timeout = setTimeout(() => controller.abort(), TIMEOUT_MS);
        const res = await fetch(svc.url, {
          method: 'GET',
          signal: controller.signal,
          cache: 'no-store',
        });
        clearTimeout(timeout);
        const latency = Math.round(performance.now() - start);
        const status: ServiceStatus =
          !res.ok ? 'offline' :
          latency > DEGRADED_THRESHOLD_MS ? 'degraded' : 'online';

        return [key, {
          ...svc,
          status,
          latencyMs: latency,
          lastCheck: new Date(),
          error: res.ok ? null : `HTTP ${res.status}`,
        }] as const;
      } catch (err: unknown) {
        return [key, {
          ...svc,
          status: 'offline' as ServiceStatus,
          latencyMs: null,
          lastCheck: new Date(),
          error: err instanceof Error ? err.message : 'Unknown error',
        }] as const;
      }
    });

    const results = await Promise.allSettled(checks);
    const services = { ...this._state.services };
    for (const r of results) {
      if (r.status === 'fulfilled') {
        const [key, health] = r.value;
        services[key] = health;
      }
    }
    this._state = { services, isChecking: false, lastFullCheck: new Date() };
    this._notify();
  }
}

// Singleton
let _instance: BackendHealthMonitor | null = null;

export function getBackendHealthMonitor(): BackendHealthMonitor {
  if (!_instance) {
    _instance = new BackendHealthMonitor();
  }
  return _instance;
}

export function startHealthMonitoring(): BackendHealthMonitor {
  const monitor = getBackendHealthMonitor();
  monitor.start();
  return monitor;
}

export function stopHealthMonitoring() {
  _instance?.stop();
}
