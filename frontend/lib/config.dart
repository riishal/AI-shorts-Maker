/// App configuration.
///
/// The backend URL is configurable at build time so the same code runs
/// locally and in production:
///
///   flutter run
///   flutter build web --release \
///       --dart-define=BACKEND_URL=https://YOUR-CLOUD-RUN-URL
class AppConfig {
  static const String backendUrl = String.fromEnvironment(
    'BACKEND_URL',
    defaultValue: 'http://127.0.0.1:8000',
  );

  /// Absolute URL for streaming a generated Short.
  static String videoUrl(String filename) =>
      '$backendUrl/video/${Uri.encodeComponent(filename)}';

  /// Absolute URL for downloading a generated Short.
  static String downloadUrl(String filename) =>
      '$backendUrl/download/${Uri.encodeComponent(filename)}';
}
