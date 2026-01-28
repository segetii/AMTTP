# AMTTP Visualization Stack Implementation Summary

## Date: Implementation Session 2

## Summary

Successfully implemented the correct visualization stack as per Ground Truth specification:

### ✅ Packages Installed (NPM)
1. **echarts** + **echarts-for-react** - Time series, distributions, heatmaps
2. **reagraph** - WebGL network graphs  
3. **@unovis/ts** + **@unovis/react** - Sankey diagrams
4. **@heroicons/react** - UI icons

### ✅ Detection Studio Components Created

| Component | Library | Purpose | File |
|-----------|---------|---------|------|
| `VelocityHeatmap` | ECharts | Hour×Day velocity patterns, bot detection | `src/components/detection/VelocityHeatmap.tsx` |
| `TimeSeriesChart` | ECharts | Time series with dataZoom, trend analysis | `src/components/detection/TimeSeriesChart.tsx` |
| `RiskDistributionChart` | ECharts | Risk score distribution histogram | `src/components/detection/RiskDistributionChart.tsx` |
| `GraphExplorer` | Reagraph | WebGL network graph, wallet relationships | `src/components/detection/GraphExplorer.tsx` |
| `SankeyAuditor` | Unovis | Value flow conservation, smurfing detection | `src/components/detection/SankeyAuditor.tsx` |

### ✅ Secure Bridge (CRITICAL for Compliance)

Implemented the critical Secure Bridge for regulatory compliance:

| File | Purpose |
|------|---------|
| `src/lib/secure-bridge.ts` | postMessage transport, EIP-712 intent building, Flutter communication |
| `src/lib/intent-signing.ts` | EIP-712 typed data structures, signature handling |

#### How Secure Bridge Works:
1. **Web builds TransferIntent** with UI state hash (captures what user saw)
2. **Bridge sends to Flutter** via postMessage
3. **Flutter signs EIP-712 typed data** (includes UI hash)
4. **Signature returned** to web for transaction submission
5. **Transaction includes hash** → Regulators can verify user saw correct info

### ✅ Detection Studio Page

Created fully functional Detection Studio page at `/war-room/detection-studio/` with:
- Overview mode (all visualizations)
- Velocity mode (heatmap + time series focus)
- Network mode (graph exploration)
- Flow mode (Sankey value conservation)
- Distribution mode (risk statistics)

### ✅ Transfer Page Updated

Updated Focus Mode transfer page (`/focus/transfer/`) to use Secure Bridge:
- Builds EIP-712 intent with UI snapshot hash
- Captures trust pillars shown, risk score displayed, warnings acknowledged
- Signs via Flutter wallet bridge
- Ensures "what user saw = what they signed"

---

## Visualization Stack Mapping (Ground Truth Alignment)

| Ground Truth Requirement | Implementation |
|--------------------------|----------------|
| ECharts for time/stats | ✅ TimeSeriesChart, RiskDistributionChart, VelocityHeatmap |
| Reagraph for graphs | ✅ GraphExplorer with WebGL |
| Unovis for Sankey | ✅ SankeyAuditor |
| fl_chart for Flutter trust | ⏳ Pending (Flutter-side) |
| Secure Bridge | ✅ secure-bridge.ts + intent-signing.ts |

---

## Files Created This Session

### Detection Components
- `src/components/detection/VelocityHeatmap.tsx`
- `src/components/detection/TimeSeriesChart.tsx`
- `src/components/detection/RiskDistributionChart.tsx`
- `src/components/detection/GraphExplorer.tsx`
- `src/components/detection/SankeyAuditor.tsx`
- `src/components/detection/index.ts`

### Detection Studio Page
- `src/app/war-room/detection-studio/page.tsx`

### Secure Bridge (Compliance)
- `src/lib/secure-bridge.ts`
- `src/lib/intent-signing.ts`

### Updated Files
- `src/app/focus/transfer/page.tsx` - Added Secure Bridge integration
- `src/components/trust/TrustCheckInterstitial.tsx` - Extended callbacks for EIP-712

---

## Remaining Work

### Flutter Side (Not in scope for Next.js)
1. Add `dart:js_interop` bridge receiver
2. Implement fl_chart trust visualization
3. Connect to web3dart for actual signing

### Package Updates
- Consider removing Recharts dependency (now replaced by ECharts)

---

## Compliance Note

**The Secure Bridge is the #1 compliance feature for regulators:**

> "Without the bridge, regulators cannot verify what user saw = what they signed"

The implementation ensures:
1. UI state is hashed before transaction
2. Hash is included in EIP-712 signed data
3. Audit trail can reconstruct exact UI state
4. Non-repudiation of user's informed consent

---

## Next Steps

1. Start the Next.js dev server: `npm run dev -- -p 3006`
2. Navigate to `/war-room/detection-studio` to see visualizations
3. Test `/focus/transfer` for Secure Bridge flow
4. Implement Flutter bridge receiver for full signing flow
