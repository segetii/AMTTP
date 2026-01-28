# Flutter ↔ Next.js Bridge Architecture

## Overview

AMTTP uses a **hybrid architecture** combining Flutter's cross-platform capabilities with Next.js's rich analytics ecosystem.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                        FLUTTER APP (Main Shell)                              │
│                    iOS, Android, Web, Windows, macOS, Linux                  │
│                              Port: 3010                                      │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ┌──────────────────────────────┐   ┌──────────────────────────────────────┐│
│  │     NATIVE FLUTTER VIEWS     │   │      EMBEDDED NEXT.JS (WebView)      ││
│  │     ───────────────────      │   │      ────────────────────────        ││
│  │                              │   │                                      ││
│  │  • Login / Registration      │   │  • Detection Studio (Charts)         ││
│  │  • Wallet Connection         │   │  • Graph Explorer (Memgraph)         ││
│  │  • Transfer / Send           │   │  • Velocity Heatmap                  ││
│  │  • Transaction History       │   │  • Sankey Flow Diagrams              ││
│  │  • Trust Check Interstitial  │   │  • ML Explainability                 ││
│  │  • Settings / Profile        │   │  • Compliance Dashboard              ││
│  │  • Escrow Management         │   │                                      ││
│  │  • Multisig Approval (WYA)   │   │  ┌────────────────────────────────┐  ││
│  │                              │   │  │   "Open Full Screen" Button    │  ││
│  │                              │   │  │   Opens Next.js in Browser     │  ││
│  │                              │   │  └────────────────────────────────┘  ││
│  └──────────────────────────────┘   └──────────────────────────────────────┘│
│              │                                      │                        │
│              └────────────── BRIDGE ────────────────┘                        │
│                        (Bidirectional Sync)                                  │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Why This Architecture?

| Requirement | Solution |
|-------------|----------|
| Cross-platform (6 platforms) | Flutter handles iOS, Android, Web, Windows, macOS, Linux |
| Rich analytics/charts | Next.js + Recharts/D3 embedded in WebView |
| Native performance | Core features (auth, transfers) are native Flutter |
| Full-screen analytics | One click opens browser with full dashboard |
| Session sync | Bridge passes auth tokens bidirectionally |

## Components

### Flutter Side

```
frontend/amttp_app/lib/services/bridge/
├── bridge.dart                    # Library export
├── flutter_nextjs_bridge.dart     # Main bridge service
└── embedded_analytics.dart        # WebView widget
```

### Next.js Side

```
frontend/frontend/src/lib/
└── flutter-bridge.tsx             # Bridge provider & hooks
```

---

## Flutter Usage

### 1. Initialize Bridge After Login

```dart
import 'package:amttp_app/services/bridge/bridge.dart';

// After successful login
final bridge = FlutterNextJSBridge();
bridge.setSession(
  sessionToken: authToken,
  userId: user.id,
  userRole: 'R3_INSTITUTION_OPS',
  walletAddress: user.walletAddress,
);
```

### 2. Embed Analytics in a Screen

```dart
import 'package:amttp_app/services/bridge/bridge.dart';

class MyAnalyticsPage extends StatelessWidget {
  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: EmbeddedAnalytics(
        route: '/war-room/detection-studio',
        showFullScreenButton: true,
        onRiskScoreUpdate: (score, address) {
          print('Risk: $score for $address');
        },
      ),
    );
  }
}
```

### 3. Open Full-Screen Analytics

```dart
final bridge = FlutterNextJSBridge();

// Open Detection Studio in browser
bridge.openFullScreen('/war-room/detection-studio');

// Or analyze a specific transaction
bridge.analyzeTransaction('0xabc123...');

// Or show wallet graph
bridge.showWalletGraph('0xdef456...');
```

### 4. Handle Messages from Next.js

```dart
final bridge = FlutterNextJSBridge();

// Risk score updates from analytics
bridge.onRiskScoreUpdate = (data) {
  final score = data['score'] as double;
  if (score > 0.7) {
    showHighRiskAlert();
  }
};

// Alerts from compliance dashboard
bridge.onAlertReceived = (data) {
  showNotification(data['title'], data['message']);
};
```

---

## Next.js Usage

### 1. Wrap App with Provider

```tsx
// app/layout.tsx
import { FlutterBridgeProvider } from '@/lib/flutter-bridge';

export default function RootLayout({ children }) {
  return (
    <html>
      <body>
        <FlutterBridgeProvider>
          {children}
        </FlutterBridgeProvider>
      </body>
    </html>
  );
}
```

### 2. Use Bridge in Components

```tsx
import { useFlutterBridge } from '@/lib/flutter-bridge';

function RiskAnalysis() {
  const { isEmbedded, userContext, sendToFlutter } = useFlutterBridge();

  // Check if running inside Flutter
  if (isEmbedded) {
    console.log('Running in Flutter WebView');
  }

  // Send risk score to Flutter
  const handleRiskCalculated = (score: number, address: string) => {
    sendToFlutter('RISK_SCORE_UPDATE', { score, address });
  };

  // Request full-screen mode
  const openFullScreen = () => {
    sendToFlutter('OPEN_FULL_SCREEN', { route: '/war-room' });
  };

  return (
    <div>
      <p>User: {userContext.userId}</p>
      <p>Role: {userContext.userRole}</p>
      <button onClick={openFullScreen}>Open Full Screen</button>
    </div>
  );
}
```

### 3. Utility Functions

```tsx
import { notifyRiskScore, notifyAlert } from '@/lib/flutter-bridge';

// Send risk score update
notifyRiskScore('0xabc...', 0.85, ['High velocity', 'Mixer detected']);

// Send alert
notifyAlert('High Risk', 'Transaction flagged for review', 'critical');
```

---

## Message Types

### Flutter → Next.js

| Type | Payload | Description |
|------|---------|-------------|
| `FLUTTER_USER_CONTEXT` | `{ sessionToken, userId, userRole, walletAddress }` | Session sync |
| `ANALYZE_TRANSACTION` | `{ txHash }` | Navigate to tx analysis |
| `SHOW_WALLET_GRAPH` | `{ walletAddress }` | Show wallet in graph explorer |
| `NAVIGATE_TO` | `{ route }` | Navigate to specific route |
| `REQUEST_RISK_CHECK` | `{ counterpartyAddress, amount }` | Request risk scoring |
| `SESSION_CLEARED` | `{}` | User logged out |

### Next.js → Flutter

| Type | Payload | Description |
|------|---------|-------------|
| `RISK_SCORE_UPDATE` | `{ address, score, factors }` | Risk score calculated |
| `ALERT_RECEIVED` | `{ title, message, severity }` | New alert |
| `NAVIGATION_REQUEST` | `{ route }` | Request Flutter navigation |
| `OPEN_FULL_SCREEN` | `{ route }` | Open in browser |
| `READY` | `{ route }` | Next.js WebView ready |

---

## Full-Screen Mode

When user clicks "Open Full Screen", the Flutter app:

1. Builds URL with session token as query param
2. Opens system browser
3. Next.js reads token and restores session
4. User has full analytics experience

```
URL: http://localhost:3006/war-room?token=xyz&source=flutter&userId=123&role=R3
```

---

## Security Considerations

1. **Session tokens** are passed via URL params - use short-lived tokens
2. **WebView sandboxing** - Flutter WebView isolates Next.js
3. **Origin validation** - Next.js checks `source=flutter` param
4. **HTTPS in production** - Always use HTTPS for bridge communication

---

## Development Workflow

### Running Both Apps

```powershell
# Terminal 1: Flutter app (port 3010)
cd frontend/amttp_app
flutter run -d chrome --web-port=3010

# Terminal 2: Next.js analytics (port 3006)
cd frontend/frontend
npm run dev -- -p 3006
```

### Testing Bridge

1. Login in Flutter app
2. Navigate to Analytics Hub
3. Verify Next.js loads in embedded WebView
4. Click "Full Screen" to open in browser
5. Verify session is preserved

---

## Troubleshooting

| Issue | Solution |
|-------|----------|
| WebView blank | Check Next.js is running on port 3006 |
| Session not syncing | Verify `setSession()` called after login |
| Full screen not working | Check `url_launcher` package installed |
| Bridge messages not received | Check JavaScript channel name matches |
