import sys
import matplotlib.pyplot as plt
import numpy as np
import math
import torch
import os

# Import the existing setup
sys.path.insert(0, r'c:\amttp\research\neural-stability')
from run_rnn_adam_failure import ExplodingRNN, make_rnn_data
from colab_bsdt_gradient_stability import AdamWOptimiser, BSDTOptimiser, MFLSOptimiser, SignedLROptimiser, CanonicalEngineOptimiser, train, DEVICE

def get_gradient_tracking_data():
    X, y = make_rnn_data(2000, 150, 42)
    X, y = X.to(DEVICE), y.to(DEVICE)
    Xtr, Xte = X[:1600], X[1600:]
    ytr, yte = y[:1600], y[1600:]

    opt_list = [
        ('AdamW', AdamWOptimiser()), 
        ('BSDT', BSDTOptimiser()), 
        ('MFLS', MFLSOptimiser()), 
        ('SignedLR', SignedLROptimiser()), 
        ('Canonical', CanonicalEngineOptimiser(rho=0.05))
    ]

    results = {}

    for name, opt in opt_list:
        net = ExplodingRNN(input_dim=1, hidden_dim=64).to(DEVICE)
        # Deep pathological start point
        net.init_weights(seed=42, hh_scale=4.5)
        opt.reset()
        
        for w in net.W: w.requires_grad_(False)
        for b in net.b: b.requires_grad_(False)

        def custom_backward(Xb, yb, y_pred, acts, net=net):
            for w in net.W: w.requires_grad_(True)
            for b in net.b: b.requires_grad_(True)
            y_pred, _ = net.forward(Xb)
            loss = -(yb * (y_pred + 1e-12).log() + (1 - yb) * (1 - y_pred + 1e-12).log()).mean()
            loss.backward()
            with torch.no_grad():
                dW = [w.grad.clone() for w in net.W]
                db = [b.grad.clone() for b in net.b]
            for w in net.W: w.grad = None; w.requires_grad_(False)
            for b in net.b: b.grad = None; b.requires_grad_(False)
            return dW, db

        net.backward = custom_backward
        
        print(f"Tracking run for {name}...")
        try:
            # We train for 15 epochs to see it stabilise
            logs = train(net, opt, Xtr, ytr, Xte, yte, lr=0.01, n_epochs=15, batch_size=128, seed=42)
            results[name] = logs
        except Exception as e:
            print(f"{name} blew up: {e}")
            results[name] = []
            
    return results

def plot_tracking(results):
    plt.figure(figsize=(14, 5))
    
    # 1. Plot the Gradient Norm over time
    plt.subplot(1, 2, 1)
    for name, logs in results.items():
        if not logs: continue
        gnorms = [math.log10(l.grad_norm + 1e-12) if l.grad_norm > 0 and math.isfinite(l.grad_norm) else np.nan for l in logs[:15]]
        plt.plot(range(len(gnorms)), gnorms, label=name, marker='o' if name == 'Canonical' else 'x', linewidth=2)
    plt.axhline(y=10.0, color='r', linestyle='--', alpha=0.5, label='Typical NaN threshold')
    plt.title('Log10(Gradient Norm) during RNN BPTT')
    plt.xlabel('Epoch')
    plt.ylabel('Log10(||∇W||)')
    plt.grid(True, alpha=0.3)
    plt.legend()

    # 2. Plot the Friction (Geometric Dampening) kicking in
    plt.subplot(1, 2, 2)
    for name, logs in results.items():
        if not logs or name == 'AdamW': continue # AdamW doesn't output 'friction'
        frictions = [math.log10(l.friction + 1e-12) if l.friction > 0 and math.isfinite(l.friction) else np.nan for l in logs[:15]]
        plt.plot(range(len(frictions)), frictions, label=name, marker='s', linewidth=2)
        
    plt.title('Log10(Applied Friction γ) over Time')
    plt.xlabel('Epoch')
    plt.ylabel('Log10(Friction Multiplier)')
    plt.grid(True, alpha=0.3)
    plt.legend()
    
    plt.tight_layout()
    output_path = r'c:\amttp\research\neural-stability\rnn_gradient_tracking_plot.png'
    plt.savefig(output_path, dpi=300)
    print(f"\nSaved tracking graph to {output_path}")

if __name__ == '__main__':
    data = get_gradient_tracking_data()
    plot_tracking(data)