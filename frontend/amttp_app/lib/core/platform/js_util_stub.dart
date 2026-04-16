// Stub for dart:js_util on non-web platforms.
// Provides no-op JS interop so web3_service.dart compiles on iOS/Android.

bool hasProperty(dynamic o, String name) => false;
dynamic getProperty(dynamic o, String name) => null;
dynamic callMethod(dynamic o, String method, List<dynamic> args) => null;
dynamic callConstructor(dynamic constr, List<dynamic>? args) => null;
void setProperty(dynamic o, String name, dynamic value) {}
F allowInterop<F extends Function>(F f) => f;
Future<T> promiseToFuture<T>(dynamic jsPromise) => Future.value(null as T);
