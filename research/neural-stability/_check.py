import sys; sys.path.insert(0, '.')
from nn_engine import BlowUpNet, spectral_radius_approx, BSDTOptimiser, make_spiral_data, grad_norm

net = BlowUpNet(); net.init_weights(42)
lam = spectral_radius_approx(net.W, seed=0)
print(f"lambda_eff (geom mean) = {lam:.4f}")

lr, alpha = 0.01, 0.1
gamma_spec = lr * lam / alpha
print(f"gamma_spec = lr*lambda/alpha = {gamma_spec:.4f}")
print(f"effective_lr = lr/(1+gamma) = {lr/(1+gamma_spec):.6f}")
print()

X, y = make_spiral_data(256, seed=42)
yp, acts = net.forward(X)
dW, db = net.backward(X, y, yp, acts)
gn = grad_norm(dW, db)
print(f"grad_norm at init = {gn:.4f}")

opt = BSDTOptimiser()
info = opt.step(net, dW, db, epoch=0, lr=0.01)
print(f"BSDT friction    = {info['friction']:.4f}x")
print(f"BSDT gamma_star  = {info['gamma_star']:.4f}")
