import sys
import math
import torch
import torch.nn as nn

# Import the existing optimisers and functions from your main script
sys.path.insert(0, r'c:\amttp\research\neural-stability')
from colab_bsdt_gradient_stability import (
    Optimiser, AdamWOptimiser, BSDTOptimiser, MFLSOptimiser,
    CanonicalEngineOptimiser, train, DEVICE
)

# 1. Provide a Dataset designed for BPTT (Backprop Through Time)
def make_rnn_data(n_samples=2000, seq_len=100, seed=42):
    """
    Creates sequences of length `seq_len`.
    Target is 1 if the sum of the sequence is positive, else 0.
    """
    torch.manual_seed(seed)
    X = torch.randn(n_samples, seq_len, 1, dtype=torch.float64)
    y = (X.sum(dim=1).squeeze(-1) > 0).long()
    return X, y

# 2. Define an RNN with pathological hidden-to-hidden transition
class ExplodingRNN(nn.Module):
    """
    A Vanilla RNN operating over a long sequence.
    If the hidden-to-hidden matrix has eigenvalues > 1, the gradient
    will explode exponentially during backpropagation through time.
    """
    def __init__(self, input_dim=1, hidden_dim=64):
        super().__init__()
        self.W_ih = nn.Parameter(torch.empty(input_dim, hidden_dim, dtype=torch.float64))
        self.W_hh = nn.Parameter(torch.empty(hidden_dim, hidden_dim, dtype=torch.float64))
        # The main script uses a 20-layer net ending with out_dim=1 and applies a sigmoid internally. Wait, BlowUpNet returns logits? No, binary_cross_entropy_t does -(y*log(p)) so it expects p in [0,1].
        self.W_ho = nn.Parameter(torch.empty(hidden_dim, 1, dtype=torch.float64))
        
        self.b_ih = nn.Parameter(torch.zeros(hidden_dim, dtype=torch.float64))
        self.b_hh = nn.Parameter(torch.zeros(hidden_dim, dtype=torch.float64))
        self.b_ho = nn.Parameter(torch.zeros(1, dtype=torch.float64))

        # Train loop in colab_bsdt_gradient_stability manually assumes CrossEntropy expects logits and argmax, 
        # but binary_cross_entropy_t expects (batch, 2) shaped outputs mapped to log-softmax or typical sigmoid.
        # Let's check how the main script handles binary labels. It expects output shape to match yb.

        # Expose lists mapped exactly to how your optimisers expect them:
        self.W = [self.W_ih, self.W_hh, self.W_ho]
        self.b = [self.b_ih, self.b_hh, self.b_ho]
        self.n_layers = len(self.W)

    def init_weights(self, seed=42, hh_scale=1.5):
        torch.manual_seed(seed)
        nn.init.xavier_normal_(self.W_ih)
        # Pathological hidden transition! Std scale > 1 causes exponential explosion over time.
        nn.init.normal_(self.W_hh, mean=0.0, std=hh_scale / math.sqrt(self.W_hh.size(0)))
        nn.init.xavier_normal_(self.W_ho)

    def backward(self, Xb, yb, y_pred, acts):
        loss = -(yb * (y_pred + 1e-12).log() + (1 - yb) * (1 - y_pred + 1e-12).log()).mean()
        self.zero_grad()
        loss.backward()
        
        with torch.no_grad():
            dW_list = [w.grad.clone() if w.grad is not None else torch.zeros_like(w) for w in self.W]
            db_list = [b.grad.clone() if b.grad is not None else torch.zeros_like(b) for b in self.b]
        return dW_list, db_list

    def forward(self, x):
        batch_size, seq_len, _ = x.shape
        h = torch.zeros(batch_size, self.W_hh.size(0), device=x.device, dtype=x.dtype)
        
        for t in range(seq_len):
            # h_t = tanh(x_t W_ih + b_ih + h_{t-1} W_hh + b_hh)
            h = torch.tanh(x[:, t, :] @ self.W_ih + self.b_ih + h @ self.W_hh + self.b_hh)
            
        out = h @ self.W_ho + self.b_ho
        return torch.sigmoid(out.squeeze(-1)), None
        h = torch.zeros(batch_size, self.W_hh.size(0), device=x.device, dtype=x.dtype)
        
        for t in range(seq_len):
            # h_t = tanh(x_t W_ih + b_ih + h_{t-1} W_hh + b_hh)
            h = torch.tanh(x[:, t, :] @ self.W_ih + self.b_ih + h @ self.W_hh + self.b_hh)
            
        out = h @ self.W_ho + self.b_ho
        return torch.sigmoid(out.squeeze(-1)), None


def run_experiment():
    seq_len = 100
    print(f"Generating sequence data (Seq Len: {seq_len})...")
    X, y = make_rnn_data(2000, seq_len, 42)
    X = X.to(DEVICE)
    y = y.to(DEVICE)
    Xtr, Xte = X[:1600], X[1600:]
    ytr, yte = y[:1600], y[1600:]

    optimisers_to_test = [
        ('AdamW', AdamWOptimiser()),
        ('BSDT', BSDTOptimiser()),
        ('MFLS', MFLSOptimiser()),
        ('Canonical', CanonicalEngineOptimiser(rho=0.05))
    ]

    print("\nStarting RNN Pathological BPTT Sweep")
    print("====================================")
    for name, opt in optimisers_to_test:
        net = ExplodingRNN(input_dim=1, hidden_dim=64).to(DEVICE)
        # Initialise W_hh with scale=1.5 (spectral radius > 1) to force BPTT explosion
        net.init_weights(seed=42, hh_scale=1.5)
        opt.reset()
        
        # Train for 20 epochs
        logs = train(net, opt, Xtr, ytr, Xte, yte, lr=0.01, n_epochs=20, batch_size=128, seed=42)
        
        last = [l for l in logs if not l.blew_up]
        if last:
            peak_g = max(l.friction for l in last)
            final = last[-1]
            print(f"[{name:<10}] Survived {len(last)}/20 ep | Loss={final.train_loss:.4f} | Acc={final.test_acc:.3f} | Peak γ={peak_g:.2f}")
        else:
            print(f"[{name:<10}] BLOW-UP at Epoch 0")

if __name__ == '__main__':
    run_experiment()
