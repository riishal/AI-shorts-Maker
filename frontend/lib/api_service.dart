import 'dart:convert';

import 'package:flutter/foundation.dart';
import 'package:http/http.dart' as http;

import 'config.dart';
import 'models.dart';

/// Thin HTTP client for the AI Shorts Maker backend.
///
/// Every method returns an [ApiResult] carrying either the parsed value or a
/// user-friendly error string. Raw exceptions/tracebacks never reach the UI.
class ApiService {
  final String baseUrl;
  final http.Client _client;

  ApiService({String? baseUrl, http.Client? client})
      : baseUrl = baseUrl ?? AppConfig.backendUrl,
        _client = client ?? http.Client();

  static const _connErr =
      'Could not connect to the server. Make sure the backend is running.';

  /// Extract a friendly error message from a JSON error body.
  String _bodyError(String body, String fallback) {
    try {
      final decoded = jsonDecode(body);
      if (decoded is Map && decoded['error'] != null) {
        return decoded['error'].toString();
      }
    } catch (_) {}
    return fallback;
  }

  // ---------------------------------------------------------------- upload
  Future<ApiResult<String>> uploadVideo(
    Uint8List bytes,
    String filename,
  ) async {
    try {
      final request = http.MultipartRequest(
        'POST',
        Uri.parse('$baseUrl/upload'),
      )..files.add(
          http.MultipartFile.fromBytes('file', bytes, filename: filename),
        );

      final streamed = await request.send();
      final body = await streamed.stream.bytesToString();

      if (streamed.statusCode == 200) {
        final data = jsonDecode(body) as Map<String, dynamic>;
        return ApiResult.ok(data['filename']?.toString() ?? filename);
      }
      return ApiResult.fail(_bodyError(body, 'Upload failed.'));
    } catch (e) {
      debugPrint('uploadVideo error: $e');
      return ApiResult.fail(_connErr);
    }
  }

  // ------------------------------------------------ create shorts (upload)
  Future<ApiResult<String>> createAiShorts(String filename) async {
    try {
      final res = await _client.post(
        Uri.parse('$baseUrl/create-ai-shorts/${Uri.encodeComponent(filename)}'),
      );
      if (res.statusCode == 200) {
        final data = jsonDecode(res.body) as Map<String, dynamic>;
        return ApiResult.ok(data['job_id']?.toString());
      }
      return ApiResult.fail(
        _bodyError(res.body, 'Could not start processing.'),
      );
    } catch (e) {
      debugPrint('createAiShorts error: $e');
      return ApiResult.fail(_connErr);
    }
  }

  // ------------------------------------------------------- youtube analyze
  Future<ApiResult<YoutubeInfo>> analyzeYoutube(String url) async {
    try {
      final res = await _client.post(
        Uri.parse('$baseUrl/youtube/analyze'),
        headers: {'Content-Type': 'application/json'},
        body: jsonEncode({'url': url}),
      );
      if (res.statusCode == 200) {
        return ApiResult.ok(
          YoutubeInfo.fromJson(jsonDecode(res.body) as Map<String, dynamic>),
        );
      }
      return ApiResult.fail(
        _bodyError(res.body, 'Could not analyze this YouTube video.'),
      );
    } catch (e) {
      debugPrint('analyzeYoutube error: $e');
      return ApiResult.fail(_connErr);
    }
  }

  // ------------------------------------------------------- youtube process
  Future<ApiResult<String>> processYoutube(String url) async {
    try {
      final res = await _client.post(
        Uri.parse('$baseUrl/youtube/process'),
        headers: {'Content-Type': 'application/json'},
        body: jsonEncode({'url': url}),
      );
      if (res.statusCode == 200) {
        final data = jsonDecode(res.body) as Map<String, dynamic>;
        return ApiResult.ok(data['job_id']?.toString());
      }
      return ApiResult.fail(
        _bodyError(res.body, 'Could not process this YouTube video.'),
      );
    } catch (e) {
      debugPrint('processYoutube error: $e');
      return ApiResult.fail(_connErr);
    }
  }

  // ------------------------------------------------------------ job status
  Future<ApiResult<JobStatus>> getStatus(String jobId) async {
    try {
      final res = await _client.get(Uri.parse('$baseUrl/status/$jobId'));
      if (res.statusCode == 200) {
        return ApiResult.ok(
          JobStatus.fromJson(jsonDecode(res.body) as Map<String, dynamic>),
        );
      }
      return ApiResult.fail(_bodyError(res.body, 'Lost track of the job.'));
    } catch (e) {
      debugPrint('getStatus error: $e');
      return ApiResult.fail(_connErr);
    }
  }

  // ------------------------------------------------------------ list shorts
  Future<ApiResult<List<ShortItem>>> listShorts() async {
    try {
      final res = await _client.get(Uri.parse('$baseUrl/shorts'));
      if (res.statusCode == 200) {
        final data = jsonDecode(res.body) as Map<String, dynamic>;
        final list = (data['shorts'] as List?) ?? const [];
        final shorts = <ShortItem>[];
        for (var i = 0; i < list.length; i++) {
          shorts.add(ShortItem.fromJson(
            list[i] as Map<String, dynamic>,
            fallbackRank: i + 1,
          ));
        }
        return ApiResult.ok(shorts);
      }
      return ApiResult.fail(_bodyError(res.body, 'Could not load Shorts.'));
    } catch (e) {
      debugPrint('listShorts error: $e');
      return ApiResult.fail(_connErr);
    }
  }
}
