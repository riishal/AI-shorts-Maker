import 'dart:async';
import 'dart:typed_data';

import 'package:file_picker/file_picker.dart';
import 'package:flutter/material.dart';
import 'package:url_launcher/url_launcher.dart';
import 'package:video_player/video_player.dart';

import 'api_service.dart';
import 'config.dart';
import 'models.dart';
import 'widgets/shorts_gallery.dart';

void main() {
  runApp(const AIShortsMakerApp());
}

class AIShortsMakerApp extends StatelessWidget {
  const AIShortsMakerApp({super.key});

  @override
  Widget build(BuildContext context) {
    final base = ThemeData.dark(useMaterial3: true);
    return MaterialApp(
      debugShowCheckedModeBanner: false,
      title: 'AI Shorts Maker',
      theme: base.copyWith(
        colorScheme: ColorScheme.fromSeed(
          seedColor: Colors.deepPurple,
          brightness: Brightness.dark,
        ),
        scaffoldBackgroundColor: const Color(0xFF0B0B10),
        filledButtonTheme: FilledButtonThemeData(
          style: FilledButton.styleFrom(
            minimumSize: const Size.fromHeight(52),
            shape: RoundedRectangleBorder(
                borderRadius: BorderRadius.circular(12)),
            textStyle:
                const TextStyle(fontSize: 16, fontWeight: FontWeight.bold),
          ),
        ),
      ),
      home: const DashboardPage(),
    );
  }
}

class DashboardPage extends StatefulWidget {
  const DashboardPage({super.key});

  @override
  State<DashboardPage> createState() => _DashboardPageState();
}

class _DashboardPageState extends State<DashboardPage> {
  final ApiService _api = ApiService();
  final TextEditingController _urlController = TextEditingController();

  // ------- input state -------
  InputMethod _method = InputMethod.youtube;
  String? _selectedFile;
  Uint8List? _selectedBytes;
  String? _uploadedFilename;

  // ------- job state -------
  AppPhase _phase = AppPhase.idle;
  String _statusMessage = 'Choose YouTube or upload a video to begin.';
  String _stage = '';
  double? _progress;
  String? _sourceTitle;
  String? _highlightSource;
  String? _jobId;
  Timer? _pollTimer;

  // ------- results -------
  List<ShortItem> _shorts = [];

  // ------- preview (single controller) -------
  VideoPlayerController? _previewController;
  String? _previewFilename;
  bool _previewLoading = false;
  String? _previewError;

  @override
  void dispose() {
    _pollTimer?.cancel();
    _previewController?.dispose();
    _urlController.dispose();
    super.dispose();
  }

  // ========================================================================
  // HELPERS
  // ========================================================================

  bool get _busy => _phase.isBusy;

  void _snack(String message, {bool error = false}) {
    if (!mounted) return;
    ScaffoldMessenger.of(context)
      ..hideCurrentSnackBar()
      ..showSnackBar(SnackBar(
        content: Text(message),
        backgroundColor: error ? Colors.redAccent : Colors.green,
      ));
  }

  void _setStatus(AppPhase phase, String message,
      {String stage = '', double? progress}) {
    setState(() {
      _phase = phase;
      _statusMessage = message;
      _stage = stage;
      _progress = progress;
    });
  }

  // ========================================================================
  // LOCAL UPLOAD FLOW
  // ========================================================================

  Future<void> _pickVideo() async {
    try {
      final result =
          await FilePicker.pickFiles(type: FileType.video, withData: true);
      if (result == null) return;
      final file = result.files.single;
      if (file.bytes == null) {
        _snack('Could not read the selected video.', error: true);
        return;
      }
      await _disposePreview();
      setState(() {
        _selectedFile = file.name;
        _selectedBytes = file.bytes;
        _uploadedFilename = null;
        _shorts = [];
        _phase = AppPhase.selected;
        _statusMessage = 'Video selected. Ready to upload.';
      });
    } catch (e) {
      _snack('Error selecting video.', error: true);
    }
  }

  Future<void> _uploadVideo() async {
    if (_selectedBytes == null || _selectedFile == null) return;
    _setStatus(AppPhase.uploading, 'Uploading video...', progress: null);

    final result = await _api.uploadVideo(_selectedBytes!, _selectedFile!);
    if (!mounted) return;

    if (result.isOk) {
      setState(() {
        _uploadedFilename = result.data;
        _phase = AppPhase.uploaded;
        _statusMessage = 'Video uploaded. Ready to create Shorts.';
      });
    } else {
      _setStatus(AppPhase.error, result.error ?? 'Upload failed.');
      _snack(result.error ?? 'Upload failed.', error: true);
    }
  }

  Future<void> _createShortsFromUpload() async {
    final filename = _uploadedFilename;
    if (filename == null) return;
    _setStatus(AppPhase.processing, 'Starting AI pipeline...', progress: null);
    setState(() => _shorts = []);

    final result = await _api.createAiShorts(filename);
    if (!mounted) return;

    if (result.isOk && result.data != null) {
      _startPolling(result.data!);
    } else {
      _setStatus(AppPhase.error, result.error ?? 'Could not start processing.');
      _snack(result.error ?? 'Could not start processing.', error: true);
    }
  }

  // ========================================================================
  // YOUTUBE FLOW
  // ========================================================================

  Future<void> _startYoutube() async {
    final url = _urlController.text.trim();
    if (url.isEmpty) {
      _snack('Please paste a YouTube URL.', error: true);
      return;
    }

    await _disposePreview();
    setState(() => _shorts = []);
    _setStatus(AppPhase.preparing, 'Validating YouTube URL...', progress: null);

    // Step 1: validate + fetch metadata (fast, no download).
    final info = await _api.analyzeYoutube(url);
    if (!mounted) return;
    if (!info.isOk) {
      _setStatus(AppPhase.error, info.error ?? 'Unsupported YouTube URL.');
      _snack(info.error ?? 'Unsupported YouTube URL.', error: true);
      return;
    }

    setState(() => _sourceTitle = info.data!.title);
    _setStatus(AppPhase.preparing,
        'Found "${info.data!.title}". Preparing video...',
        progress: null);

    // Step 2: download + run the same pipeline as uploads.
    final result = await _api.processYoutube(url);
    if (!mounted) return;
    if (result.isOk && result.data != null) {
      _startPolling(result.data!);
    } else {
      _setStatus(
          AppPhase.error, result.error ?? 'Could not process this video.');
      _snack(result.error ?? 'Could not process this video.', error: true);
    }
  }

  // ========================================================================
  // JOB POLLING
  // ========================================================================

  void _startPolling(String jobId) {
    _pollTimer?.cancel();
    _jobId = jobId;
    _pollTimer = Timer.periodic(const Duration(milliseconds: 1300), (_) {
      _pollOnce(jobId);
    });
    _pollOnce(jobId);
  }

  Future<void> _pollOnce(String jobId) async {
    final result = await _api.getStatus(jobId);
    if (!mounted || _jobId != jobId) return;

    if (!result.isOk) {
      // Transient network hiccup: keep polling, don't crash the flow.
      return;
    }

    final job = result.data!;
    setState(() {
      _phase = job.phase;
      _statusMessage = job.isError
          ? (job.error ?? 'Video processing failed.')
          : job.message;
      _stage = job.stage;
      _progress = job.progress;
      if (job.title != null && job.title!.isNotEmpty) {
        _sourceTitle = job.title;
      }
      _highlightSource = job.highlightSource;
    });

    if (job.isCompleted) {
      _pollTimer?.cancel();
      final shorts =
          job.shorts.isNotEmpty ? job.shorts : (await _fetchShorts());
      if (!mounted) return;
      setState(() {
        _shorts = shorts;
        _phase = AppPhase.completed;
        _statusMessage = '${shorts.length} Shorts created successfully!';
      });
      if (shorts.isNotEmpty) {
        _loadPreview(shorts.first);
      }
    } else if (job.isError) {
      _pollTimer?.cancel();
      _snack(job.error ?? 'Video processing failed.', error: true);
    }
  }

  Future<List<ShortItem>> _fetchShorts() async {
    final result = await _api.listShorts();
    return result.isOk ? (result.data ?? []) : [];
  }

  // ========================================================================
  // PREVIEW
  // ========================================================================

  Future<void> _disposePreview() async {
    final old = _previewController;
    _previewController = null;
    await old?.dispose();
  }

  Future<void> _loadPreview(ShortItem short) async {
    await _disposePreview();
    if (!mounted) return;
    setState(() {
      _previewFilename = short.filename;
      _previewLoading = true;
      _previewError = null;
    });

    try {
      final controller = VideoPlayerController.networkUrl(
        Uri.parse(AppConfig.videoUrl(short.filename)),
      );
      await controller.initialize();
      controller.setLooping(true);
      if (!mounted) {
        await controller.dispose();
        return;
      }
      setState(() {
        _previewController = controller;
        _previewLoading = false;
      });
      await controller.play();
      setState(() {}); // reflect play state on the button
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _previewController = null;
        _previewLoading = false;
        _previewError =
            'This preview could not be played. The file may still be '
            'rendering, or your browser does not support it.';
      });
    }
  }

  void _togglePlay() {
    final c = _previewController;
    if (c == null || !c.value.isInitialized) return;
    setState(() {
      c.value.isPlaying ? c.pause() : c.play();
    });
  }

  Future<void> _download(ShortItem short) async {
    final uri = Uri.parse(AppConfig.downloadUrl(short.filename));
    try {
      if (await canLaunchUrl(uri)) {
        await launchUrl(uri, webOnlyWindowName: '_blank');
      } else {
        _snack('Could not start the download.', error: true);
      }
    } catch (_) {
      _snack('Could not start the download.', error: true);
    }
  }

  // ========================================================================
  // RESET
  // ========================================================================

  void _reset() {
    _pollTimer?.cancel();
    _previewController?.dispose();
    _urlController.clear();
    setState(() {
      _selectedFile = null;
      _selectedBytes = null;
      _uploadedFilename = null;
      _jobId = null;
      _shorts = [];
      _sourceTitle = null;
      _highlightSource = null;
      _previewController = null;
      _previewFilename = null;
      _previewLoading = false;
      _previewError = null;
      _phase = AppPhase.idle;
      _stage = '';
      _progress = null;
      _statusMessage = 'Choose YouTube or upload a video to begin.';
    });
  }

  // ========================================================================
  // BUILD
  // ========================================================================

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        titleSpacing: 20,
        title: Row(
          children: const [
            Icon(Icons.auto_awesome, color: Colors.deepPurpleAccent),
            SizedBox(width: 10),
            Text('AI Shorts Maker',
                style: TextStyle(fontWeight: FontWeight.bold)),
          ],
        ),
        actions: [
          Padding(
            padding: const EdgeInsets.only(right: 16),
            child: Center(child: _statusChip()),
          ),
        ],
      ),
      body: SafeArea(
        child: LayoutBuilder(
          builder: (context, constraints) {
            return SingleChildScrollView(
              padding: const EdgeInsets.all(20),
              child: Center(
                child: ConstrainedBox(
                  constraints: const BoxConstraints(maxWidth: 1200),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.stretch,
                    children: [
                      _header(),
                      const SizedBox(height: 24),
                      _inputCard(),
                      const SizedBox(height: 18),
                      _statusPanel(),
                      const SizedBox(height: 24),
                      _gallery(),
                      const SizedBox(height: 30),
                      if (_phase != AppPhase.idle) _resetButton(),
                      const SizedBox(height: 20),
                    ],
                  ),
                ),
              ),
            );
          },
        ),
      ),
    );
  }

  // ---------------------------------------------------------------- header
  Widget _header() {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: const [
        Text('AI Shorts Maker',
            style: TextStyle(fontSize: 30, fontWeight: FontWeight.bold)),
        SizedBox(height: 6),
        Text(
          'Turn videos and YouTube content into engaging Shorts with AI.',
          style: TextStyle(fontSize: 15, color: Colors.white60),
        ),
      ],
    );
  }

  // ------------------------------------------------------------- input card
  Widget _inputCard() {
    return Container(
      padding: const EdgeInsets.all(20),
      decoration: BoxDecoration(
        color: const Color(0xFF121218),
        borderRadius: BorderRadius.circular(16),
        border: Border.all(color: Colors.white10),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          // Segmented input-method selector.
          Align(
            alignment: Alignment.centerLeft,
            child: SegmentedButton<InputMethod>(
              segments: const [
                ButtonSegment(
                  value: InputMethod.youtube,
                  label: Text('YouTube'),
                  icon: Icon(Icons.smart_display),
                ),
                ButtonSegment(
                  value: InputMethod.upload,
                  label: Text('Upload Video'),
                  icon: Icon(Icons.upload_file),
                ),
              ],
              selected: {_method},
              onSelectionChanged: _busy
                  ? null
                  : (s) => setState(() => _method = s.first),
            ),
          ),
          const SizedBox(height: 20),
          if (_method == InputMethod.youtube)
            _youtubeInput()
          else
            _uploadInput(),
        ],
      ),
    );
  }

  Widget _youtubeInput() {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        TextField(
          controller: _urlController,
          enabled: !_busy,
          onSubmitted: (_) => _busy ? null : _startYoutube(),
          decoration: InputDecoration(
            hintText: 'https://www.youtube.com/watch?v=...',
            prefixIcon: const Icon(Icons.link),
            filled: true,
            fillColor: const Color(0xFF0E0E14),
            border: OutlineInputBorder(
              borderRadius: BorderRadius.circular(12),
              borderSide: BorderSide.none,
            ),
          ),
        ),
        const SizedBox(height: 8),
        const Text(
          'Supports watch, youtu.be, /live and /shorts links. '
          'Live streams can only be processed after they end.',
          style: TextStyle(fontSize: 12, color: Colors.white38),
        ),
        const SizedBox(height: 16),
        FilledButton.icon(
          onPressed: _busy ? null : _startYoutube,
          icon: const Icon(Icons.auto_awesome),
          label: const Text('Analyze & Create Shorts'),
        ),
      ],
    );
  }

  Widget _uploadInput() {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        OutlinedButton.icon(
          onPressed: _busy ? null : _pickVideo,
          style: OutlinedButton.styleFrom(
            minimumSize: const Size.fromHeight(52),
            shape: RoundedRectangleBorder(
                borderRadius: BorderRadius.circular(12)),
          ),
          icon: const Icon(Icons.folder_open),
          label: const Text('Select Video'),
        ),
        if (_selectedFile != null) ...[
          const SizedBox(height: 14),
          Container(
            padding: const EdgeInsets.all(14),
            decoration: BoxDecoration(
              color: const Color(0xFF0E0E14),
              borderRadius: BorderRadius.circular(12),
              border: Border.all(color: Colors.white10),
            ),
            child: Row(
              children: [
                const Icon(Icons.video_file, color: Colors.deepPurpleAccent),
                const SizedBox(width: 10),
                Expanded(
                  child: Text(_selectedFile!,
                      overflow: TextOverflow.ellipsis,
                      style: const TextStyle(fontWeight: FontWeight.w600)),
                ),
                if (_uploadedFilename != null)
                  const Icon(Icons.check_circle,
                      color: Colors.greenAccent, size: 20),
              ],
            ),
          ),
        ],
        const SizedBox(height: 16),
        if (_uploadedFilename == null)
          FilledButton.icon(
            onPressed: (_selectedBytes == null || _busy) ? null : _uploadVideo,
            icon: _phase == AppPhase.uploading
                ? const _SmallSpinner()
                : const Icon(Icons.cloud_upload),
            label: Text(
                _phase == AppPhase.uploading ? 'Uploading...' : 'Upload Video'),
          )
        else
          FilledButton.icon(
            onPressed: _busy ? null : _createShortsFromUpload,
            icon: const Icon(Icons.auto_awesome),
            label: const Text('Create AI Shorts'),
          ),
      ],
    );
  }

  // ---------------------------------------------------------- status panel
  Widget _statusPanel() {
    final showBar = _busy;
    final color = _phase == AppPhase.error
        ? Colors.redAccent
        : _phase == AppPhase.completed
            ? Colors.greenAccent
            : _busy
                ? Colors.orangeAccent
                : Colors.white54;

    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: const Color(0xFF121218),
        borderRadius: BorderRadius.circular(14),
        border: Border.all(color: Colors.white10),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          if (_sourceTitle != null && _sourceTitle!.isNotEmpty) ...[
            Row(
              children: [
                const Icon(Icons.movie_creation_outlined,
                    size: 16, color: Colors.white38),
                const SizedBox(width: 8),
                Expanded(
                  child: Text('Source: ${_sourceTitle!}',
                      overflow: TextOverflow.ellipsis,
                      style: const TextStyle(
                          fontSize: 12, color: Colors.white54)),
                ),
              ],
            ),
            const Divider(height: 18, color: Colors.white10),
          ],
          if (showBar)
            Padding(
              padding: const EdgeInsets.only(bottom: 12),
              child: ClipRRect(
                borderRadius: BorderRadius.circular(8),
                child: LinearProgressIndicator(
                  value: _progress, // null => indeterminate (never faked)
                  minHeight: 6,
                ),
              ),
            ),
          Row(
            children: [
              Icon(
                _phase == AppPhase.error
                    ? Icons.error_outline
                    : _phase == AppPhase.completed
                        ? Icons.check_circle
                        : Icons.info_outline,
                color: color,
                size: 20,
              ),
              const SizedBox(width: 10),
              Expanded(
                child: Text(
                  _stage.isNotEmpty ? _stage : _statusMessage,
                  style: TextStyle(color: color, fontWeight: FontWeight.w600),
                ),
              ),
            ],
          ),
          if (_stage.isNotEmpty && _statusMessage != _stage) ...[
            const SizedBox(height: 4),
            Padding(
              padding: const EdgeInsets.only(left: 30),
              child: Text(_statusMessage,
                  style: const TextStyle(
                      fontSize: 12, color: Colors.white38)),
            ),
          ],
          if (_highlightSource == 'heuristic' &&
              _phase == AppPhase.completed) ...[
            const SizedBox(height: 6),
            const Padding(
              padding: EdgeInsets.only(left: 30),
              child: Text(
                'Highlights were selected automatically (AI selector '
                'unavailable). Set GEMINI_API_KEY for smarter picks.',
                style: TextStyle(fontSize: 12, color: Colors.white38),
              ),
            ),
          ],
        ],
      ),
    );
  }

  // ------------------------------------------------------- generated shorts
  Widget _gallery() {
    return ShortsGallery(
      shorts: _shorts,
      selectedFilename: _previewFilename,
      controller: _previewController,
      isLoading: _previewLoading,
      errorText: _previewError,
      onSelect: _loadPreview,
      onDownload: _download,
      onTogglePlay: _togglePlay,
    );
  }

  // ------------------------------------------------------------- misc bits
  Widget _resetButton() {
    return Center(
      child: OutlinedButton.icon(
        onPressed: _busy ? null : _reset,
        icon: const Icon(Icons.refresh),
        label: const Text('Start New Project'),
      ),
    );
  }

  Widget _statusChip() {
    final label = _phaseLabel();
    final busy = _busy;
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
      decoration: BoxDecoration(
        color: const Color(0xFF1A1A22),
        borderRadius: BorderRadius.circular(20),
        border: Border.all(color: Colors.white10),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          if (busy)
            const SizedBox(
                width: 12,
                height: 12,
                child: CircularProgressIndicator(strokeWidth: 2))
          else
            Icon(
              _phase == AppPhase.error
                  ? Icons.error
                  : _phase == AppPhase.completed
                      ? Icons.check_circle
                      : Icons.circle,
              size: 12,
              color: _phase == AppPhase.error
                  ? Colors.redAccent
                  : _phase == AppPhase.completed
                      ? Colors.greenAccent
                      : Colors.white38,
            ),
          const SizedBox(width: 8),
          Text(label, style: const TextStyle(fontSize: 12)),
        ],
      ),
    );
  }

  String _phaseLabel() {
    switch (_phase) {
      case AppPhase.idle:
        return 'Idle';
      case AppPhase.selected:
        return 'Selected';
      case AppPhase.uploading:
        return 'Uploading';
      case AppPhase.uploaded:
        return 'Uploaded';
      case AppPhase.preparing:
        return 'Preparing';
      case AppPhase.analyzing:
        return 'Analyzing';
      case AppPhase.processing:
        return 'Processing';
      case AppPhase.generating:
        return 'Generating';
      case AppPhase.completed:
        return 'Completed';
      case AppPhase.error:
        return 'Error';
    }
  }
}

class _SmallSpinner extends StatelessWidget {
  const _SmallSpinner();
  @override
  Widget build(BuildContext context) => const SizedBox(
        width: 20,
        height: 20,
        child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white),
      );
}
