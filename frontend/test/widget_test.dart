// Widget tests for the AI Shorts Maker dashboard and gallery.

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:frontend/main.dart';
import 'package:frontend/models.dart';
import 'package:frontend/widgets/shorts_gallery.dart';

ShortItem _short(int rank) => ShortItem(
      filename: 'short_0$rank.mp4',
      url: '/video/short_0$rank.mp4',
      downloadUrl: '/download/short_0$rank.mp4',
      rank: rank,
      title: 'Short $rank',
      duration: 30,
    );

void main() {
  testWidgets('Dashboard renders heading and input selector',
      (WidgetTester tester) async {
    await tester.pumpWidget(const AIShortsMakerApp());
    await tester.pump();

    expect(find.text('AI Shorts Maker'), findsWidgets);
    expect(find.text('YouTube'), findsOneWidget);
    expect(find.text('Upload Video'), findsWidgets);
    expect(find.text('Analyze & Create Shorts'), findsOneWidget);
  });

  testWidgets('Gallery: only the selected card is "Now playing" and tapping '
      'another card switches selection', (WidgetTester tester) async {
    final shorts = [_short(1), _short(2), _short(3)];
    ShortItem? selectedByTap;

    await tester.pumpWidget(MaterialApp(
      home: Scaffold(
        body: SingleChildScrollView(
          child: ShortsGallery(
            shorts: shorts,
            selectedFilename: shorts[1].filename, // Short 2 selected
            controller: null,
            isLoading: true, // selected card shows a loading state
            errorText: null,
            onSelect: (s) => selectedByTap = s,
            onDownload: (_) {},
            onTogglePlay: () {},
          ),
        ),
      ),
    ));
    await tester.pump();

    // Header + count.
    expect(find.text('Generated Shorts'), findsOneWidget);
    expect(find.text('3 ready'), findsOneWidget);

    // Exactly one card is playing (the selected one).
    expect(find.text('Now playing'), findsOneWidget);

    // Selected card shows the loading state; others show poster play icons.
    expect(find.text('Loading...'), findsOneWidget);
    expect(find.byIcon(Icons.play_circle_outline), findsNWidgets(2));

    // Tapping a non-selected poster switches selection to that short.
    await tester.tap(find.byIcon(Icons.play_circle_outline).first);
    await tester.pump();
    expect(selectedByTap, isNotNull);
    expect(selectedByTap!.filename, anyOf(shorts[0].filename, shorts[2].filename));
  });
}
