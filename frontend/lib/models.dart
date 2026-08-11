/// Data models and the UI state machine.
library;

/// High-level UI phase driving the whole dashboard.
enum AppPhase {
  idle, // nothing selected yet
  selected, // a local file is selected, not uploaded
  uploading, // uploading local file
  uploaded, // upload finished, ready to create
  preparing, // youtube download / source prep
  analyzing, // transcription
  processing, // highlight selection
  generating, // rendering shorts
  completed, // shorts ready
  error, // something went wrong
}

extension AppPhaseX on AppPhase {
  /// True while a long-running job is in flight (blocks duplicate actions).
  bool get isBusy => const {
        AppPhase.uploading,
        AppPhase.preparing,
        AppPhase.analyzing,
        AppPhase.processing,
        AppPhase.generating,
      }.contains(this);
}

/// Which input method the user picked.
enum InputMethod { youtube, upload }

/// A single generated Short.
class ShortItem {
  final String filename;
  final String url;
  final String downloadUrl;
  final int rank;
  final String? title;
  final double? duration;

  ShortItem({
    required this.filename,
    required this.url,
    required this.downloadUrl,
    required this.rank,
    this.title,
    this.duration,
  });

  factory ShortItem.fromJson(Map<String, dynamic> json, {int fallbackRank = 0}) {
    return ShortItem(
      filename: json['filename']?.toString() ?? '',
      url: json['url']?.toString() ?? '',
      downloadUrl: json['download_url']?.toString() ??
          '/download/${json['filename']}',
      rank: (json['rank'] as num?)?.toInt() ?? fallbackRank,
      title: json['title']?.toString(),
      duration: (json['duration'] as num?)?.toDouble(),
    );
  }
}

/// Snapshot of a backend job (from GET /status/{id}).
class JobStatus {
  final String state;
  final String message;
  final String stage;
  final double? progress; // 0..1 or null (indeterminate)
  final String? error;
  final String? title;
  final String? highlightSource;
  final double elapsed;
  final List<ShortItem> shorts;

  JobStatus({
    required this.state,
    required this.message,
    required this.stage,
    required this.progress,
    required this.error,
    required this.title,
    required this.highlightSource,
    required this.elapsed,
    required this.shorts,
  });

  bool get isCompleted => state == 'COMPLETED';
  bool get isError => state == 'ERROR';

  factory JobStatus.fromJson(Map<String, dynamic> json) {
    final rawShorts = (json['shorts'] as List?) ?? const [];
    return JobStatus(
      state: json['state']?.toString() ?? 'QUEUED',
      message: json['message']?.toString() ?? '',
      stage: json['stage']?.toString() ?? '',
      progress: (json['progress'] as num?)?.toDouble(),
      error: json['error']?.toString(),
      title: json['title']?.toString(),
      highlightSource: json['highlight_source']?.toString(),
      elapsed: (json['elapsed'] as num?)?.toDouble() ?? 0,
      shorts: rawShorts
          .whereType<Map<String, dynamic>>()
          .map((e) => ShortItem.fromJson(e))
          .toList(),
    );
  }

  AppPhase get phase {
    switch (state) {
      case 'PREPARING':
      case 'QUEUED':
        return AppPhase.preparing;
      case 'ANALYZING':
        return AppPhase.analyzing;
      case 'PROCESSING':
        return AppPhase.processing;
      case 'GENERATING':
        return AppPhase.generating;
      case 'COMPLETED':
        return AppPhase.completed;
      case 'ERROR':
        return AppPhase.error;
      default:
        return AppPhase.processing;
    }
  }
}

/// YouTube metadata (from POST /youtube/analyze).
class YoutubeInfo {
  final String title;
  final int duration;
  final String channel;
  final String thumbnail;

  YoutubeInfo({
    required this.title,
    required this.duration,
    required this.channel,
    required this.thumbnail,
  });

  factory YoutubeInfo.fromJson(Map<String, dynamic> json) {
    return YoutubeInfo(
      title: json['title']?.toString() ?? 'YouTube video',
      duration: (json['duration'] as num?)?.toInt() ?? 0,
      channel: json['channel']?.toString() ?? '',
      thumbnail: json['thumbnail']?.toString() ?? '',
    );
  }
}

/// Result wrapper so callers get either data or a friendly message.
class ApiResult<T> {
  final T? data;
  final String? error;
  ApiResult.ok(this.data) : error = null;
  ApiResult.fail(this.error) : data = null;
  bool get isOk => error == null;
}
