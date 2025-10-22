# AMTTP Flutter App

A cross-platform mobile and web application for the AMTTP protocol with DQN-powered fraud detection.

## 🚀 Features

- **Cross-Platform**: iOS, Android, Web, Windows, macOS, Linux
- **Web3 Integration**: WalletConnect, MetaMask, smart contract interaction
- **DQN Analytics**: Real-time fraud detection visualization
- **Beautiful UI**: Material Design 3 with custom AMTTP theme
- **Real-time Updates**: Live transaction monitoring and risk scoring

## 📱 Screenshots

### Dashboard
- Wallet connection with balance display
- Secure transfer interface with risk analysis
- Transaction history with risk visualization
- Real-time DQN analytics

### Admin Panel
- System health monitoring
- DQN model performance metrics
- Transaction feed and filtering
- Policy management interface

## 🛠️ Setup Instructions

### Prerequisites

1. **Install Flutter SDK**
   ```bash
   # Download Flutter from https://flutter.dev/docs/get-started/install
   # Add to PATH and verify installation
   flutter doctor
   ```

2. **Platform-specific Setup**
   ```bash
   # For web development
   flutter config --enable-web
   
   # For Windows desktop
   flutter config --enable-windows-desktop
   
   # For macOS desktop
   flutter config --enable-macos-desktop
   
   # For Linux desktop
   flutter config --enable-linux-desktop
   ```

### Installation

1. **Navigate to the Flutter app directory**
   ```bash
   cd c:\amttp\frontend\amttp_app
   ```

2. **Install dependencies**
   ```bash
   flutter pub get
   ```

3. **Configure Environment Variables**
   
   Update `lib/core/constants/app_constants.dart`:
   ```dart
   // Contract addresses (after deployment)
   static const String amttpStreamlinedAddress = '0xYOUR_DEPLOYED_ADDRESS';
   static const String amttpPolicyManagerAddress = '0xYOUR_DEPLOYED_ADDRESS';
   static const String amttpPolicyEngineAddress = '0xYOUR_DEPLOYED_ADDRESS';
   
   // API endpoints
   static const String baseApiUrl = 'http://localhost:3001/api';
   ```

   Update `lib/core/web3/wallet_provider.dart`:
   ```dart
   // WalletConnect Project ID
   core: Core(
     projectId: 'YOUR_WALLET_CONNECT_PROJECT_ID', // Get from https://cloud.walletconnect.com
   ),
   ```

## 🚀 Running the App

### Development Mode

```bash
# Run on web (Chrome)
flutter run -d chrome

# Run on iOS simulator
flutter run -d ios

# Run on Android emulator
flutter run -d android

# Run on Windows
flutter run -d windows

# Run on macOS
flutter run -d macos

# Run on Linux
flutter run -d linux
```

### Production Build

```bash
# Build for web
flutter build web

# Build for Android APK
flutter build apk

# Build for iOS (requires macOS)
flutter build ios

# Build for Windows
flutter build windows

# Build for macOS
flutter build macos

# Build for Linux
flutter build linux
```

## 📁 Project Structure

```
lib/
├── core/                     # Core functionality
│   ├── constants/            # App constants and configuration
│   ├── router/               # Navigation routing
│   ├── services/             # API and external services
│   ├── theme/                # App theme and styling
│   └── web3/                 # Blockchain integration
├── features/                 # Feature modules
│   ├── admin/                # Admin dashboard
│   ├── history/              # Transaction history
│   ├── home/                 # Main dashboard
│   ├── settings/             # App settings
│   ├── transfer/             # Transfer functionality
│   └── wallet/               # Wallet management
├── shared/                   # Shared components
│   └── widgets/              # Reusable widgets
└── main.dart                 # App entry point
```

## 🔧 Key Components

### SecureTransferWidget
- **File**: `lib/shared/widgets/secure_transfer_widget.dart`
- **Features**: 
  - Form validation for recipient and amount
  - Real-time DQN risk analysis
  - Visual risk scoring with color coding
  - Smart approval workflow (auto-approve/monitor/escrow/block)

### RiskVisualizerWidget
- **File**: `lib/shared/widgets/risk_visualizer_widget.dart`
- **Features**:
  - Circular risk gauge display
  - Feature contribution bar charts
  - DQN model information panel
  - Interactive tooltips and analytics

### AdminPage
- **File**: `lib/features/admin/presentation/pages/admin_page.dart`
- **Features**:
  - System health monitoring
  - DQN performance metrics
  - Real-time transaction feed
  - Policy management interface

## 🌐 Web3 Integration

### Smart Contract Interaction
- **Web3Service**: Complete contract wrapper for AMTTP contracts
- **WalletProvider**: Riverpod state management for wallet connections
- **Transaction Handling**: Secure transaction signing and submission

### Supported Wallets
- MetaMask (web/mobile)
- WalletConnect (mobile wallets)
- Trust Wallet
- Rainbow Wallet
- Coinbase Wallet

## 📊 DQN Integration

### Real-time Risk Analysis
- **15 feature analysis**: Transaction amount, user frequency, geographic risk, etc.
- **Sub-100ms inference**: Fast risk scoring for real-time transactions
- **Visual feedback**: Color-coded risk levels and detailed explanations

### Performance Monitoring
- **F1 Score tracking**: Monitor model accuracy over time
- **Feature importance**: Understand which factors drive risk scores
- **Training metrics**: Dataset size, training time, model performance

## 🎨 Theming

### Material Design 3
- **Primary Blue**: `#2563EB` - Main brand color
- **Success Green**: `#10B981` - Low risk, success states
- **Warning Orange**: `#F59E0B` - Medium risk, warnings
- **Danger Red**: `#EF4444` - High risk, errors

### Risk Color Coding
- **0-39%**: Green (Low Risk, Auto-approved)
- **40-69%**: Orange (Medium Risk, Monitored)
- **70-79%**: Red (High Risk, Escrow)
- **80%+**: Dark Red (Very High Risk, Blocked)

## 🔧 Configuration

### Environment Setup

1. **Backend API**: Ensure your AMTTP backend is running on `localhost:3001`
2. **Smart Contracts**: Deploy contracts and update addresses in `app_constants.dart`
3. **WalletConnect**: Get project ID from WalletConnect Cloud
4. **Network Configuration**: Update RPC URLs for mainnet/testnet

### Development Tips

1. **Hot Reload**: Use `r` in terminal for hot reload during development
2. **Debug Mode**: Add breakpoints in VS Code for debugging
3. **Performance**: Use Flutter DevTools for performance profiling
4. **Testing**: Run `flutter test` for unit testing

## 📱 Platform-Specific Notes

### iOS
- Requires Xcode for building
- Add camera permissions for QR scanning in `Info.plist`
- Configure app signing for App Store distribution

### Android
- Update `android/app/build.gradle` for release builds
- Add internet permissions in `AndroidManifest.xml`
- Configure ProGuard for release optimization

### Web
- Works with any modern browser
- Progressive Web App (PWA) capabilities
- Can be hosted on Netlify, Vercel, or Firebase

### Desktop
- Native performance on Windows/macOS/Linux
- Smaller bundle size than Electron alternatives
- Full system integration capabilities

## 🚀 Deployment

### Web Deployment
```bash
flutter build web
# Deploy 'build/web' folder to your hosting provider
```

### Mobile App Stores
```bash
# iOS App Store
flutter build ios --release
# Upload to App Store Connect

# Google Play Store
flutter build appbundle
# Upload to Google Play Console
```

### Desktop Distribution
```bash
# Windows installer
flutter build windows --release

# macOS app bundle
flutter build macos --release

# Linux package
flutter build linux --release
```

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Test on multiple platforms
5. Submit a pull request

## 📞 Support

For questions or issues:
- Check Flutter documentation: https://flutter.dev/docs
- Review AMTTP protocol documentation
- Open an issue in the repository

## 📄 License

This project is part of the AMTTP protocol ecosystem.