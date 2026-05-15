import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'core/api_client.dart';
import 'core/theme.dart';
import 'widgets/sidebar.dart';
import 'features/dashboard/presentation/pages/dashboard_page.dart';
import 'features/opportunities/presentation/pages/opportunities_page.dart';
import 'features/recherche/presentation/pages/recherche_page.dart';
import 'features/validations/presentation/pages/validations_page.dart';
import 'features/contacts/presentation/pages/contacts_page.dart';
import 'features/chat/presentation/pages/chat_page.dart';
import 'features/mailbox/presentation/pages/mailbox_page.dart';
import 'features/hr/presentation/pages/hr_page.dart';
import 'features/planificateur/presentation/pages/planificateur_page.dart';
import 'features/settings/presentation/pages/settings_page.dart';

void main() {
  runApp(const ProviderScope(child: ManelCoreApp()));
}

class ManelCoreApp extends StatelessWidget {
  const ManelCoreApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'ManelCore',
      debugShowCheckedModeBanner: false,
      theme: AppTheme.lightTheme,
      home: const AppShell(),
    );
  }
}

class AppShell extends ConsumerStatefulWidget {
  const AppShell({super.key});

  @override
  ConsumerState<AppShell> createState() => _AppShellState();
}

class _AppShellState extends ConsumerState<AppShell> {
  int _selectedIndex = 0;

  static const _mobileRoutes = [0, 1, 3, 6, 9];

  Widget _buildPage(int index) => switch (index) {
    0 => const DashboardPage(),
    1 => const OpportunitiesPage(),
    2 => const RecherchePage(),
    3 => const ValidationsPage(),
    4 => const ContactsPage(),
    5 => const ChatPage(),
    6 => const MailboxPage(),
    7 => const HrPage(),
    8 => const PlanificateurPage(),
    9 => const SettingsPage(),
    _ => const DashboardPage(),
  };

  void _goToRecherche() => setState(() => _selectedIndex = 2);

  @override
  Widget build(BuildContext context) {
    final isDesktop = MediaQuery.sizeOf(context).width >= 800;

    if (isDesktop) {
      return Scaffold(
        body: Row(children: [
          AppSidebar(
            selectedIndex: _selectedIndex,
            onItemSelected: (i) => setState(() => _selectedIndex = i),
          ),
          Expanded(child: _buildPage(_selectedIndex)),
        ]),
        // FAB — cycle rapide visible depuis toutes les pages
        floatingActionButton: _selectedIndex != 2
            ? _CycleFab(
                onTest: () async {
                  final api       = ref.read(apiClientProvider);
                  final messenger = ScaffoldMessenger.of(context);
                  await api.runMockAgent();
                  ref.invalidate(opportunitiesProvider);
                  ref.invalidate(dashboardStatsProvider);
                  messenger.showSnackBar(SnackBar(
                    content: const Text('✅ 5 opportunités de test injectées'),
                    backgroundColor: AppTokens.badgeNeo4j,
                    behavior: SnackBarBehavior.floating,
                    shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(8)),
                    margin: const EdgeInsets.all(20),
                    duration: const Duration(seconds: 3),
                  ));
                },
                onFull: _goToRecherche,
              )
            : null,
      );
    }

    // ── Mobile ────────────────────────────────────────────────────────────────
    final mobileIndex = _mobileRoutes.indexOf(_selectedIndex).clamp(0, 4);
    return Scaffold(
      backgroundColor: AppTokens.contentBg,
      body: _buildPage(_mobileRoutes[mobileIndex]),
      floatingActionButton: _CycleFab(
        onTest: () async {
          final api = ref.read(apiClientProvider);
          await api.runMockAgent();
          ref.invalidate(opportunitiesProvider);
          ref.invalidate(dashboardStatsProvider);
        },
        onFull: () => setState(() => _selectedIndex = 2),
      ),
      bottomNavigationBar: NavigationBar(
        backgroundColor: AppTokens.sidebarBg,
        indicatorColor: AppTokens.accentBg,
        selectedIndex: mobileIndex,
        onDestinationSelected: (i) => setState(() => _selectedIndex = _mobileRoutes[i]),
        labelBehavior: NavigationDestinationLabelBehavior.alwaysShow,
        destinations: const [
          NavigationDestination(icon: Icon(Icons.dashboard_outlined, color: AppTokens.sidebarText), selectedIcon: Icon(Icons.dashboard, color: AppTokens.accent), label: 'Accueil'),
          NavigationDestination(icon: Icon(Icons.work_outline, color: AppTokens.sidebarText), selectedIcon: Icon(Icons.work, color: AppTokens.accent), label: 'Offres'),
          NavigationDestination(icon: Icon(Icons.check_circle_outline, color: AppTokens.sidebarText), selectedIcon: Icon(Icons.check_circle, color: AppTokens.accent), label: 'Validations'),
          NavigationDestination(icon: Icon(Icons.email_outlined, color: AppTokens.sidebarText), selectedIcon: Icon(Icons.email, color: AppTokens.accent), label: 'Mails'),
          NavigationDestination(icon: Icon(Icons.settings_outlined, color: AppTokens.sidebarText), selectedIcon: Icon(Icons.settings, color: AppTokens.accent), label: 'Config'),
        ],
      ),
    );
  }
}

// ── Floating Action Button — lancement rapide ─────────────────────────────────

class _CycleFab extends StatefulWidget {
  final VoidCallback onTest;
  final VoidCallback onFull;
  const _CycleFab({required this.onTest, required this.onFull});

  @override
  State<_CycleFab> createState() => _CycleFabState();
}

class _CycleFabState extends State<_CycleFab> with SingleTickerProviderStateMixin {
  bool _open = false;
  late AnimationController _ctrl;
  late Animation<double> _fade;

  @override
  void initState() {
    super.initState();
    _ctrl = AnimationController(vsync: this, duration: const Duration(milliseconds: 200));
    _fade = CurvedAnimation(parent: _ctrl, curve: Curves.easeOut);
  }

  @override
  void dispose() { _ctrl.dispose(); super.dispose(); }

  void _toggle() {
    setState(() => _open = !_open);
    _open ? _ctrl.forward() : _ctrl.reverse();
  }

  @override
  Widget build(BuildContext context) {
    return Column(mainAxisSize: MainAxisSize.min, crossAxisAlignment: CrossAxisAlignment.end, children: [
      // Sub-buttons (visible quand ouvert)
      FadeTransition(opacity: _fade, child: Column(mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.end, children: [
        _SubFab(
          label: 'Cycle complet',
          icon: Icons.travel_explore,
          color: AppTokens.accent,
          onTap: () { _toggle(); widget.onFull(); },
        ),
        const SizedBox(height: 8),
        _SubFab(
          label: 'Cycle de test',
          icon: Icons.science_outlined,
          color: const Color(0xFF8B5CF6),
          onTap: () { _toggle(); widget.onTest(); },
        ),
        const SizedBox(height: 12),
      ])),

      // Main FAB
      FloatingActionButton(
        onPressed: _toggle,
        backgroundColor: AppTokens.accent,
        foregroundColor: Colors.white,
        elevation: 4,
        child: AnimatedRotation(
          turns: _open ? 0.125 : 0,
          duration: const Duration(milliseconds: 200),
          child: const Icon(Icons.play_arrow_rounded, size: 28),
        ),
      ),
    ]);
  }
}

class _SubFab extends StatelessWidget {
  final String label;
  final IconData icon;
  final Color color;
  final VoidCallback onTap;
  const _SubFab({required this.label, required this.icon, required this.color, required this.onTap});

  @override
  Widget build(BuildContext context) {
    return Row(mainAxisSize: MainAxisSize.min, children: [
      Container(
        padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
        decoration: BoxDecoration(color: Colors.white, borderRadius: BorderRadius.circular(20),
            boxShadow: [BoxShadow(color: Colors.black.withValues(alpha: 0.1), blurRadius: 8)]),
        child: Text(label, style: const TextStyle(fontSize: 12, fontWeight: FontWeight.w600, color: AppTokens.textPrimary)),
      ),
      const SizedBox(width: 8),
      FloatingActionButton.small(
        heroTag: label,
        onPressed: onTap,
        backgroundColor: color,
        foregroundColor: Colors.white,
        elevation: 2,
        child: Icon(icon, size: 18),
      ),
    ]);
  }
}
