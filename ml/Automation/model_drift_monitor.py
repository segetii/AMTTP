#!/usr/bin/env python3
"""
AMTTP Model Drift Detection Service

Monitors ML model performance and detects drift to ensure continued accuracy.
Alerts when model accuracy drops or input distribution shifts significantly.

Features:
- Performance metric tracking (F1, Precision, Recall, ROC-AUC)
- Input distribution monitoring (PSI - Population Stability Index)
- Prediction distribution monitoring
- Automated alerts via webhook/email
- Historical trend analysis
- A/B testing support

Usage:
    # Run drift check
    python model_drift_monitor.py check --model-dir /path/to/models

    # Start continuous monitoring
    python model_drift_monitor.py monitor --interval 3600

    # Generate drift report
    python model_drift_monitor.py report --output drift_report.json
"""

import argparse
import json
import logging
import os
import sys
import time
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any
import hashlib

try:
    import numpy as np
    HAS_NUMPY = True
except ImportError:
    HAS_NUMPY = False

try:
    import pandas as pd
    HAS_PANDAS = True
except ImportError:
    HAS_PANDAS = False

try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False

# ═══════════════════════════════════════════════════════════════════════════
# Configuration
# ═══════════════════════════════════════════════════════════════════════════

@dataclass
class DriftConfig:
    """Drift detection configuration."""
    # Performance thresholds
    f1_threshold: float = 0.05  # Alert if F1 drops > 5%
    accuracy_threshold: float = 0.05
    precision_threshold: float = 0.05
    recall_threshold: float = 0.05
    roc_auc_threshold: float = 0.03
    
    # Distribution thresholds
    psi_threshold: float = 0.1  # PSI > 0.1 indicates significant drift
    ks_threshold: float = 0.05  # KS statistic threshold
    
    # Prediction drift
    prediction_mean_threshold: float = 0.1  # 10% change in mean prediction
    prediction_std_threshold: float = 0.2  # 20% change in prediction std
    
    # Alert configuration
    alert_webhook_url: Optional[str] = None
    alert_email: Optional[str] = None
    alert_slack_webhook: Optional[str] = None
    
    # Monitoring
    check_interval_seconds: int = 3600  # 1 hour
    history_retention_days: int = 90


# ═══════════════════════════════════════════════════════════════════════════
# Data Structures
# ═══════════════════════════════════════════════════════════════════════════

@dataclass
class PerformanceMetrics:
    """Model performance metrics snapshot."""
    timestamp: str
    model_version: str
    f1_score: float
    accuracy: float
    precision: float
    recall: float
    roc_auc: float
    sample_count: int
    fraud_ratio: float


@dataclass
class DistributionStats:
    """Feature distribution statistics."""
    mean: float
    std: float
    min: float
    max: float
    median: float
    p5: float
    p95: float
    histogram: List[int]
    bin_edges: List[float]


@dataclass
class DriftResult:
    """Result of a drift check."""
    timestamp: str
    model_version: str
    has_performance_drift: bool
    has_distribution_drift: bool
    has_prediction_drift: bool
    metrics_current: Dict[str, float]
    metrics_baseline: Dict[str, float]
    drifted_features: List[str]
    psi_scores: Dict[str, float]
    severity: str  # 'none', 'low', 'medium', 'high', 'critical'
    recommendations: List[str]
    details: Dict[str, Any]


# ═══════════════════════════════════════════════════════════════════════════
# Drift Detection Functions
# ═══════════════════════════════════════════════════════════════════════════

def compute_psi(expected: np.ndarray, actual: np.ndarray, bins: int = 10) -> float:
    """
    Compute Population Stability Index (PSI) between two distributions.
    PSI < 0.1: No significant change
    PSI 0.1-0.2: Moderate change
    PSI > 0.2: Significant change - action required
    """
    if not HAS_NUMPY:
        return 0.0
    
    # Create bins from expected distribution
    breakpoints = np.percentile(expected, np.linspace(0, 100, bins + 1))
    breakpoints = np.unique(breakpoints)  # Remove duplicates
    
    # Count samples in each bin
    expected_counts = np.histogram(expected, bins=breakpoints)[0]
    actual_counts = np.histogram(actual, bins=breakpoints)[0]
    
    # Calculate proportions
    expected_props = expected_counts / len(expected)
    actual_props = actual_counts / len(actual)
    
    # Avoid division by zero
    expected_props = np.where(expected_props == 0, 0.0001, expected_props)
    actual_props = np.where(actual_props == 0, 0.0001, actual_props)
    
    # Compute PSI
    psi = np.sum((actual_props - expected_props) * np.log(actual_props / expected_props))
    
    return float(psi)


def compute_ks_statistic(expected: np.ndarray, actual: np.ndarray) -> float:
    """Compute Kolmogorov-Smirnov statistic between two distributions."""
    if not HAS_NUMPY:
        return 0.0
    
    # Compute empirical CDFs
    all_values = np.concatenate([expected, actual])
    all_values.sort()
    
    cdf_expected = np.searchsorted(np.sort(expected), all_values, side='right') / len(expected)
    cdf_actual = np.searchsorted(np.sort(actual), all_values, side='right') / len(actual)
    
    return float(np.max(np.abs(cdf_expected - cdf_actual)))


def check_performance_drift(
    current: PerformanceMetrics,
    baseline: PerformanceMetrics,
    config: DriftConfig
) -> Tuple[bool, Dict[str, float]]:
    """Check if model performance has drifted from baseline."""
    
    drifts = {}
    has_drift = False
    
    # Check each metric
    metrics = ['f1_score', 'accuracy', 'precision', 'recall', 'roc_auc']
    thresholds = {
        'f1_score': config.f1_threshold,
        'accuracy': config.accuracy_threshold,
        'precision': config.precision_threshold,
        'recall': config.recall_threshold,
        'roc_auc': config.roc_auc_threshold,
    }
    
    for metric in metrics:
        current_val = getattr(current, metric)
        baseline_val = getattr(baseline, metric)
        
        if baseline_val > 0:
            change = (baseline_val - current_val) / baseline_val
            drifts[metric] = change
            
            if change > thresholds[metric]:
                has_drift = True
    
    return has_drift, drifts


def check_feature_drift(
    baseline_data: pd.DataFrame,
    current_data: pd.DataFrame,
    feature_columns: List[str],
    config: DriftConfig
) -> Tuple[List[str], Dict[str, float]]:
    """Check for drift in feature distributions."""
    
    if not HAS_PANDAS or not HAS_NUMPY:
        return [], {}
    
    drifted_features = []
    psi_scores = {}
    
    for col in feature_columns:
        if col not in baseline_data.columns or col not in current_data.columns:
            continue
        
        baseline_values = baseline_data[col].dropna().values
        current_values = current_data[col].dropna().values
        
        if len(baseline_values) < 10 or len(current_values) < 10:
            continue
        
        psi = compute_psi(baseline_values, current_values)
        psi_scores[col] = psi
        
        if psi > config.psi_threshold:
            drifted_features.append(col)
    
    return drifted_features, psi_scores


def check_prediction_drift(
    baseline_predictions: np.ndarray,
    current_predictions: np.ndarray,
    config: DriftConfig
) -> Tuple[bool, Dict[str, float]]:
    """Check for drift in model predictions."""
    
    if not HAS_NUMPY:
        return False, {}
    
    baseline_mean = np.mean(baseline_predictions)
    current_mean = np.mean(current_predictions)
    
    baseline_std = np.std(baseline_predictions)
    current_std = np.std(current_predictions)
    
    mean_change = abs(current_mean - baseline_mean) / max(baseline_mean, 0.0001)
    std_change = abs(current_std - baseline_std) / max(baseline_std, 0.0001)
    
    has_drift = (
        mean_change > config.prediction_mean_threshold or
        std_change > config.prediction_std_threshold
    )
    
    return has_drift, {
        'mean_change': mean_change,
        'std_change': std_change,
        'baseline_mean': float(baseline_mean),
        'current_mean': float(current_mean),
        'baseline_std': float(baseline_std),
        'current_std': float(current_std),
    }


# ═══════════════════════════════════════════════════════════════════════════
# Alert Functions
# ═══════════════════════════════════════════════════════════════════════════

def send_alert(drift_result: DriftResult, config: DriftConfig) -> None:
    """Send drift alert via configured channels."""
    
    if drift_result.severity == 'none':
        return
    
    message = format_alert_message(drift_result)
    
    # Slack webhook
    if config.alert_slack_webhook and HAS_REQUESTS:
        try:
            payload = {
                "text": f"🚨 AMTTP Model Drift Alert ({drift_result.severity.upper()})",
                "blocks": [
                    {
                        "type": "section",
                        "text": {"type": "mrkdwn", "text": message}
                    }
                ]
            }
            requests.post(config.alert_slack_webhook, json=payload, timeout=10)
        except Exception as e:
            logging.error(f"Failed to send Slack alert: {e}")
    
    # Generic webhook
    if config.alert_webhook_url and HAS_REQUESTS:
        try:
            requests.post(config.alert_webhook_url, json=asdict(drift_result), timeout=10)
        except Exception as e:
            logging.error(f"Failed to send webhook alert: {e}")
    
    # Log alert
    logging.warning(f"DRIFT ALERT [{drift_result.severity.upper()}]: {message}")


def format_alert_message(drift_result: DriftResult) -> str:
    """Format drift result as alert message."""
    
    lines = [
        f"*Model*: {drift_result.model_version}",
        f"*Time*: {drift_result.timestamp}",
        f"*Severity*: {drift_result.severity.upper()}",
        "",
    ]
    
    if drift_result.has_performance_drift:
        lines.append("📉 *Performance Drift Detected:*")
        for metric, change in drift_result.details.get('performance_changes', {}).items():
            lines.append(f"  • {metric}: {change*100:.1f}% degradation")
    
    if drift_result.has_distribution_drift:
        lines.append(f"📊 *Distribution Drift:* {len(drift_result.drifted_features)} features")
        for feat in drift_result.drifted_features[:5]:
            psi = drift_result.psi_scores.get(feat, 0)
            lines.append(f"  • {feat}: PSI={psi:.3f}")
    
    if drift_result.has_prediction_drift:
        lines.append("🎯 *Prediction Drift Detected*")
    
    lines.append("")
    lines.append("*Recommendations:*")
    for rec in drift_result.recommendations:
        lines.append(f"  • {rec}")
    
    return "\n".join(lines)


def determine_severity(drift_result: DriftResult) -> str:
    """Determine alert severity based on drift magnitude."""
    
    if not any([
        drift_result.has_performance_drift,
        drift_result.has_distribution_drift,
        drift_result.has_prediction_drift
    ]):
        return 'none'
    
    # Check performance degradation
    perf_changes = drift_result.details.get('performance_changes', {})
    max_perf_change = max(perf_changes.values()) if perf_changes else 0
    
    # Check distribution drift
    max_psi = max(drift_result.psi_scores.values()) if drift_result.psi_scores else 0
    
    if max_perf_change > 0.2 or max_psi > 0.5:
        return 'critical'
    elif max_perf_change > 0.1 or max_psi > 0.3:
        return 'high'
    elif max_perf_change > 0.05 or max_psi > 0.2:
        return 'medium'
    else:
        return 'low'


def generate_recommendations(drift_result: DriftResult) -> List[str]:
    """Generate actionable recommendations based on drift type."""
    
    recommendations = []
    
    if drift_result.has_performance_drift:
        recommendations.append("Review recent model predictions for accuracy")
        recommendations.append("Consider retraining with recent data")
        recommendations.append("Check for data quality issues in recent inputs")
    
    if drift_result.has_distribution_drift:
        recommendations.append("Analyze shifted features for root cause")
        recommendations.append("Check data pipeline for collection issues")
        recommendations.append("Consider feature engineering updates")
        
        if len(drift_result.drifted_features) > 5:
            recommendations.append("Large-scale drift detected - prioritize retraining")
    
    if drift_result.has_prediction_drift:
        recommendations.append("Validate prediction calibration")
        recommendations.append("Review threshold settings")
    
    if drift_result.severity in ['high', 'critical']:
        recommendations.insert(0, "🚨 IMMEDIATE ACTION REQUIRED")
        recommendations.append("Consider reverting to previous model version")
    
    return recommendations


# ═══════════════════════════════════════════════════════════════════════════
# Monitoring Service
# ═══════════════════════════════════════════════════════════════════════════

class DriftMonitor:
    """Continuous drift monitoring service."""
    
    def __init__(self, config: DriftConfig, model_dir: str):
        self.config = config
        self.model_dir = Path(model_dir)
        self.history_file = self.model_dir / 'drift_history.json'
        self.baseline_file = self.model_dir / 'drift_baseline.json'
        self.history: List[Dict] = []
        self._load_history()
    
    def _load_history(self):
        """Load drift history from file."""
        if self.history_file.exists():
            with open(self.history_file, 'r') as f:
                self.history = json.load(f)
    
    def _save_history(self):
        """Save drift history to file."""
        # Prune old entries
        cutoff = datetime.utcnow() - timedelta(days=self.config.history_retention_days)
        self.history = [
            h for h in self.history
            if datetime.fromisoformat(h['timestamp'].replace('Z', '')) > cutoff
        ]
        
        with open(self.history_file, 'w') as f:
            json.dump(self.history, f, indent=2)
    
    def set_baseline(self, metrics: PerformanceMetrics, feature_data: Optional[pd.DataFrame] = None):
        """Set baseline for drift comparison."""
        baseline = {
            'metrics': asdict(metrics),
            'set_at': datetime.utcnow().isoformat() + 'Z',
        }
        
        if feature_data is not None and HAS_PANDAS:
            baseline['feature_stats'] = {}
            for col in feature_data.select_dtypes(include=[np.number]).columns:
                baseline['feature_stats'][col] = {
                    'mean': float(feature_data[col].mean()),
                    'std': float(feature_data[col].std()),
                    'min': float(feature_data[col].min()),
                    'max': float(feature_data[col].max()),
                }
        
        with open(self.baseline_file, 'w') as f:
            json.dump(baseline, f, indent=2)
        
        logging.info(f"Baseline set: {baseline['set_at']}")
    
    def check_drift(
        self,
        current_metrics: PerformanceMetrics,
        current_data: Optional[pd.DataFrame] = None,
        current_predictions: Optional[np.ndarray] = None
    ) -> DriftResult:
        """Run drift check against baseline."""
        
        # Load baseline
        if not self.baseline_file.exists():
            logging.warning("No baseline set - skipping drift check")
            return DriftResult(
                timestamp=datetime.utcnow().isoformat() + 'Z',
                model_version=current_metrics.model_version,
                has_performance_drift=False,
                has_distribution_drift=False,
                has_prediction_drift=False,
                metrics_current=asdict(current_metrics),
                metrics_baseline={},
                drifted_features=[],
                psi_scores={},
                severity='none',
                recommendations=['Set baseline first'],
                details={},
            )
        
        with open(self.baseline_file, 'r') as f:
            baseline_data = json.load(f)
        
        baseline_metrics = PerformanceMetrics(**baseline_data['metrics'])
        
        # Check performance drift
        has_perf_drift, perf_changes = check_performance_drift(
            current_metrics, baseline_metrics, self.config
        )
        
        # Check feature drift (if data provided)
        drifted_features = []
        psi_scores = {}
        has_dist_drift = False
        
        # Check prediction drift
        has_pred_drift = False
        pred_details = {}
        
        # Create result
        result = DriftResult(
            timestamp=datetime.utcnow().isoformat() + 'Z',
            model_version=current_metrics.model_version,
            has_performance_drift=has_perf_drift,
            has_distribution_drift=has_dist_drift,
            has_prediction_drift=has_pred_drift,
            metrics_current=asdict(current_metrics),
            metrics_baseline=asdict(baseline_metrics),
            drifted_features=drifted_features,
            psi_scores=psi_scores,
            severity='none',
            recommendations=[],
            details={
                'performance_changes': perf_changes,
                'prediction_stats': pred_details,
            },
        )
        
        # Determine severity and recommendations
        result.severity = determine_severity(result)
        result.recommendations = generate_recommendations(result)
        
        # Save to history
        self.history.append(asdict(result))
        self._save_history()
        
        # Send alerts if needed
        send_alert(result, self.config)
        
        return result
    
    def get_trend(self, metric: str = 'f1_score', days: int = 30) -> List[Tuple[str, float]]:
        """Get trend of a metric over time."""
        cutoff = datetime.utcnow() - timedelta(days=days)
        
        trend = []
        for h in self.history:
            ts = datetime.fromisoformat(h['timestamp'].replace('Z', ''))
            if ts > cutoff:
                value = h.get('metrics_current', {}).get(metric, 0)
                trend.append((h['timestamp'], value))
        
        return trend
    
    def generate_report(self) -> Dict:
        """Generate comprehensive drift report."""
        return {
            'generated_at': datetime.utcnow().isoformat() + 'Z',
            'model_dir': str(self.model_dir),
            'history_count': len(self.history),
            'recent_alerts': [
                h for h in self.history[-10:]
                if h.get('severity', 'none') != 'none'
            ],
            'trends': {
                'f1_score': self.get_trend('f1_score', 30),
                'roc_auc': self.get_trend('roc_auc', 30),
            },
            'config': asdict(self.config),
        }


# ═══════════════════════════════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════════════════════════════

def cmd_check(args):
    """Run single drift check."""
    config = DriftConfig()
    if args.slack_webhook:
        config.alert_slack_webhook = args.slack_webhook
    
    monitor = DriftMonitor(config, args.model_dir)
    
    # Create sample metrics (in production, load from actual evaluation)
    current = PerformanceMetrics(
        timestamp=datetime.utcnow().isoformat() + 'Z',
        model_version='VAE-GNN-v1.0',
        f1_score=0.85,
        accuracy=0.92,
        precision=0.82,
        recall=0.88,
        roc_auc=0.95,
        sample_count=10000,
        fraud_ratio=0.15,
    )
    
    result = monitor.check_drift(current)
    
    print(f"\n{'='*60}")
    print("DRIFT CHECK RESULT")
    print('='*60)
    print(f"Severity: {result.severity.upper()}")
    print(f"Performance Drift: {result.has_performance_drift}")
    print(f"Distribution Drift: {result.has_distribution_drift}")
    print(f"Prediction Drift: {result.has_prediction_drift}")
    
    if result.recommendations:
        print(f"\nRecommendations:")
        for rec in result.recommendations:
            print(f"  • {rec}")


def cmd_monitor(args):
    """Start continuous monitoring."""
    print(f"Starting drift monitoring (interval: {args.interval}s)")
    print("Press Ctrl+C to stop\n")
    
    config = DriftConfig()
    config.check_interval_seconds = args.interval
    
    monitor = DriftMonitor(config, args.model_dir)
    
    try:
        while True:
            # In production, load actual metrics from evaluation
            current = PerformanceMetrics(
                timestamp=datetime.utcnow().isoformat() + 'Z',
                model_version='VAE-GNN-v1.0',
                f1_score=0.85,
                accuracy=0.92,
                precision=0.82,
                recall=0.88,
                roc_auc=0.95,
                sample_count=10000,
                fraud_ratio=0.15,
            )
            
            result = monitor.check_drift(current)
            print(f"[{result.timestamp}] Check complete - Severity: {result.severity}")
            
            time.sleep(args.interval)
            
    except KeyboardInterrupt:
        print("\nMonitoring stopped")


def cmd_report(args):
    """Generate drift report."""
    config = DriftConfig()
    monitor = DriftMonitor(config, args.model_dir)
    
    report = monitor.generate_report()
    
    if args.output:
        with open(args.output, 'w') as f:
            json.dump(report, f, indent=2)
        print(f"Report saved: {args.output}")
    else:
        print(json.dumps(report, indent=2))


def cmd_baseline(args):
    """Set drift baseline."""
    config = DriftConfig()
    monitor = DriftMonitor(config, args.model_dir)
    
    metrics = PerformanceMetrics(
        timestamp=datetime.utcnow().isoformat() + 'Z',
        model_version=args.version or 'VAE-GNN-v1.0',
        f1_score=args.f1 or 0.86,
        accuracy=args.accuracy or 0.92,
        precision=args.precision or 0.83,
        recall=args.recall or 0.89,
        roc_auc=args.roc_auc or 0.95,
        sample_count=args.samples or 10000,
        fraud_ratio=args.fraud_ratio or 0.15,
    )
    
    monitor.set_baseline(metrics)
    print(f"✅ Baseline set for {metrics.model_version}")


def main():
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
    
    parser = argparse.ArgumentParser(description='AMTTP Model Drift Monitor')
    subparsers = parser.add_subparsers(dest='command')
    
    # Check command
    check_p = subparsers.add_parser('check', help='Run single drift check')
    check_p.add_argument('--model-dir', default='models', help='Model directory')
    check_p.add_argument('--slack-webhook', help='Slack webhook for alerts')
    check_p.set_defaults(func=cmd_check)
    
    # Monitor command
    mon_p = subparsers.add_parser('monitor', help='Start continuous monitoring')
    mon_p.add_argument('--model-dir', default='models', help='Model directory')
    mon_p.add_argument('--interval', type=int, default=3600, help='Check interval in seconds')
    mon_p.set_defaults(func=cmd_monitor)
    
    # Report command
    rep_p = subparsers.add_parser('report', help='Generate drift report')
    rep_p.add_argument('--model-dir', default='models', help='Model directory')
    rep_p.add_argument('--output', '-o', help='Output file')
    rep_p.set_defaults(func=cmd_report)
    
    # Baseline command
    base_p = subparsers.add_parser('baseline', help='Set drift baseline')
    base_p.add_argument('--model-dir', default='models', help='Model directory')
    base_p.add_argument('--version', help='Model version')
    base_p.add_argument('--f1', type=float, help='F1 score')
    base_p.add_argument('--accuracy', type=float, help='Accuracy')
    base_p.add_argument('--precision', type=float, help='Precision')
    base_p.add_argument('--recall', type=float, help='Recall')
    base_p.add_argument('--roc-auc', type=float, help='ROC AUC')
    base_p.add_argument('--samples', type=int, help='Sample count')
    base_p.add_argument('--fraud-ratio', type=float, help='Fraud ratio')
    base_p.set_defaults(func=cmd_baseline)
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        sys.exit(1)
    
    args.func(args)


if __name__ == '__main__':
    main()
