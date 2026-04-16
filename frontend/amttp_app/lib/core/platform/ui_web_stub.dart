// Stub for dart:ui_web on non-web platforms.
// Provides no-op platformViewRegistry so iframe pages compile on iOS/Android.

class _StubPlatformViewRegistry {
  void registerViewFactory(
    String viewType,
    dynamic Function(int viewId) viewFactory, {
    bool isVisible = true,
  }) {}
}

final platformViewRegistry = _StubPlatformViewRegistry();
