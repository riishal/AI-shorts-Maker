import 'package:flutter/material.dart';
import 'package:video_player/video_player.dart';

import '../models.dart';

/// Responsive, YouTube-style grid of generated Shorts.
///
/// Behaviour:
///  * Columns adapt to width: 1 (mobile) / 2 (tablet) / 3 / 4 (desktop).
///  * Tapping a card selects it and plays the video INSIDE that card.
///  * Only one card ever plays at a time — the parent owns a single
///    [VideoPlayerController]; selecting another card switches playback to it.
///  * Non-selected cards show a poster with a play affordance.
class ShortsGallery extends StatelessWidget {
  final List<ShortItem> shorts;
  final String? selectedFilename;
  final VideoPlayerController? controller;
  final bool isLoading;
  final String? errorText;
  final void Function(ShortItem) onSelect;
  final void Function(ShortItem) onDownload;
  final VoidCallback onTogglePlay;

  const ShortsGallery({
    super.key,
    required this.shorts,
    required this.selectedFilename,
    required this.controller,
    required this.isLoading,
    required this.errorText,
    required this.onSelect,
    required this.onDownload,
    required this.onTogglePlay,
  });

  int _columns(double width) {
    if (width >= 1200) return 4;
    if (width >= 900) return 3;
    if (width >= 600) return 2;
    return 1;
  }

  @override
  Widget build(BuildContext context) {
    if (shorts.isEmpty) return const SizedBox.shrink();

    return LayoutBuilder(
      builder: (context, constraints) {
        const spacing = 16.0;
        final columns = _columns(constraints.maxWidth);
        final cardWidth =
            ((constraints.maxWidth - spacing * (columns - 1)) / columns)
                .floorToDouble();

        return Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                const Text('Generated Shorts',
                    style:
                        TextStyle(fontSize: 22, fontWeight: FontWeight.bold)),
                const SizedBox(width: 10),
                Container(
                  padding:
                      const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
                  decoration: BoxDecoration(
                    color: Colors.deepPurple.withValues(alpha: 0.25),
                    borderRadius: BorderRadius.circular(20),
                  ),
                  child: Text('${shorts.length} ready',
                      style: const TextStyle(
                          color: Colors.deepPurpleAccent,
                          fontWeight: FontWeight.bold)),
                ),
                const Spacer(),
                const Text('Tap a Short to play',
                    style: TextStyle(fontSize: 12, color: Colors.white38)),
              ],
            ),
            const SizedBox(height: 16),
            Wrap(
              spacing: spacing,
              runSpacing: spacing,
              children: [
                for (var i = 0; i < shorts.length; i++)
                  SizedBox(
                    width: cardWidth,
                    child: _ShortCard(
                      short: shorts[i],
                      index: i,
                      selected: shorts[i].filename == selectedFilename,
                      controller: controller,
                      isLoading: isLoading,
                      errorText: errorText,
                      onSelect: () => onSelect(shorts[i]),
                      onDownload: () => onDownload(shorts[i]),
                      onTogglePlay: onTogglePlay,
                    ),
                  ),
              ],
            ),
          ],
        );
      },
    );
  }
}

class _ShortCard extends StatelessWidget {
  final ShortItem short;
  final int index;
  final bool selected;
  final VideoPlayerController? controller;
  final bool isLoading;
  final String? errorText;
  final VoidCallback onSelect;
  final VoidCallback onDownload;
  final VoidCallback onTogglePlay;

  const _ShortCard({
    required this.short,
    required this.index,
    required this.selected,
    required this.controller,
    required this.isLoading,
    required this.errorText,
    required this.onSelect,
    required this.onDownload,
    required this.onTogglePlay,
  });

  int get _rank => short.rank == 0 ? index + 1 : short.rank;

  @override
  Widget build(BuildContext context) {
    return Container(
      decoration: BoxDecoration(
        color: const Color(0xFF15151C),
        borderRadius: BorderRadius.circular(14),
        border: Border.all(
          color: selected ? Colors.deepPurpleAccent : Colors.white10,
          width: selected ? 2 : 1,
        ),
      ),
      clipBehavior: Clip.antiAlias,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        mainAxisSize: MainAxisSize.min,
        children: [
          AspectRatio(
            aspectRatio: 9 / 16,
            child: _media(),
          ),
          _footer(),
        ],
      ),
    );
  }

  Widget _media() {
    if (selected) {
      return _selectedMedia();
    }
    // Poster for non-selected cards (no controller => never 10 players).
    return _Poster(rank: _rank, duration: short.duration, onTap: onSelect);
  }

  Widget _selectedMedia() {
    if (errorText != null) {
      return _MessageBox(
        icon: Icons.error_outline,
        color: Colors.redAccent,
        text: errorText!,
        onTap: onSelect,
      );
    }

    final c = controller;
    if (isLoading || c == null || !c.value.isInitialized) {
      return const _MessageBox(
        icon: null,
        color: Colors.white70,
        text: 'Loading...',
        spinner: true,
      );
    }

    return GestureDetector(
      onTap: onTogglePlay,
      child: Stack(
        fit: StackFit.expand,
        children: [
          VideoPlayer(c),
          Positioned(
            left: 0,
            right: 0,
            bottom: 0,
            child: VideoProgressIndicator(
              c,
              allowScrubbing: true,
              colors: const VideoProgressColors(
                playedColor: Colors.deepPurpleAccent,
              ),
            ),
          ),
          if (!c.value.isPlaying)
            const Center(
              child: Icon(Icons.play_circle_fill,
                  size: 56, color: Colors.white70),
            ),
          Positioned(
            top: 8,
            left: 8,
            child: _Badge(text: 'Short $_rank', highlighted: true),
          ),
        ],
      ),
    );
  }

  Widget _footer() {
    return Padding(
      padding: const EdgeInsets.fromLTRB(10, 8, 4, 6),
      child: Row(
        children: [
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              mainAxisSize: MainAxisSize.min,
              children: [
                Text(
                  short.title?.isNotEmpty == true
                      ? short.title!
                      : 'Short $_rank',
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: const TextStyle(
                      fontWeight: FontWeight.w600, fontSize: 13),
                ),
                if (selected)
                  const Text('Now playing',
                      style: TextStyle(
                          fontSize: 11, color: Colors.deepPurpleAccent)),
              ],
            ),
          ),
          IconButton(
            tooltip: 'Download',
            visualDensity: VisualDensity.compact,
            icon: const Icon(Icons.download,
                size: 20, color: Colors.greenAccent),
            onPressed: onDownload,
          ),
        ],
      ),
    );
  }
}

class _Poster extends StatelessWidget {
  final int rank;
  final double? duration;
  final VoidCallback onTap;

  const _Poster({required this.rank, required this.duration, required this.onTap});

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onTap: onTap,
      child: Stack(
        fit: StackFit.expand,
        children: [
          const DecoratedBox(
            decoration: BoxDecoration(
              gradient: LinearGradient(
                begin: Alignment.topLeft,
                end: Alignment.bottomRight,
                colors: [Color(0xFF2A2350), Color(0xFF15151C)],
              ),
            ),
          ),
          const Center(
            child: Icon(Icons.play_circle_outline,
                size: 52, color: Colors.white60),
          ),
          Positioned(top: 8, left: 8, child: _Badge(text: 'Short $rank')),
          if (duration != null)
            Positioned(
              bottom: 8,
              right: 8,
              child: _Badge(text: '${duration!.round()}s', dark: true),
            ),
        ],
      ),
    );
  }
}

class _MessageBox extends StatelessWidget {
  final IconData? icon;
  final Color color;
  final String text;
  final bool spinner;
  final VoidCallback? onTap;

  const _MessageBox({
    required this.icon,
    required this.color,
    required this.text,
    this.spinner = false,
    this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onTap: onTap,
      child: Container(
        color: Colors.black,
        alignment: Alignment.center,
        padding: const EdgeInsets.all(16),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            if (spinner)
              const CircularProgressIndicator(strokeWidth: 2)
            else if (icon != null)
              Icon(icon, color: color, size: 40),
            const SizedBox(height: 10),
            Text(text,
                textAlign: TextAlign.center,
                style: TextStyle(color: color, fontSize: 12)),
          ],
        ),
      ),
    );
  }
}

class _Badge extends StatelessWidget {
  final String text;
  final bool highlighted;
  final bool dark;

  const _Badge({required this.text, this.highlighted = false, this.dark = false});

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
      decoration: BoxDecoration(
        color: highlighted
            ? Colors.deepPurpleAccent
            : dark
                ? Colors.black54
                : Colors.black45,
        borderRadius: BorderRadius.circular(6),
      ),
      child: Text(text,
          style: const TextStyle(
              fontSize: 11, color: Colors.white, fontWeight: FontWeight.w600)),
    );
  }
}
