// Stub for dart:html on non-web platforms.
// Provides the minimal API surface used by AMTTP Flutter app so it compiles
// on iOS / Android. Runtime code is guarded by kIsWeb checks.
// ignore_for_file: library_private_types_in_public_api

class _StubCssStyleDeclaration {
  String border = '';
  String width = '';
  String height = '';
}

class _StubElementStream<T> {
  void listen(void Function(T event)? onData) {}
}

class IFrameElement {
  String src = '';
  String allow = '';
  final _StubCssStyleDeclaration style = _StubCssStyleDeclaration();
  _StubElementStream get onLoad => _StubElementStream();
  _StubElementStream get onError => _StubElementStream();
  void setAttribute(String name, String value) {}
}

class _StubLocation {
  String get port => '';
  String get href => '';
  set href(String value) {}
  String get host => 'localhost';
  String get hostname => 'localhost';
  String get protocol => 'https:';
}

class _StubWindow {
  final _StubLocation location = _StubLocation();
  void open(String url, String name, [String? options]) {}
}

class _StubDocument {
  String cookie = '';
}

final window = _StubWindow();
final document = _StubDocument();
