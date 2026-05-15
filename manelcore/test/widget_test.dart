import 'package:flutter_test/flutter_test.dart';
import 'package:manelcore/main.dart';

void main() {
  testWidgets('App launches', (WidgetTester tester) async {
    await tester.pumpWidget(const ManelCoreApp());
    expect(find.text('ManelCore'), findsOneWidget);
  });
}
