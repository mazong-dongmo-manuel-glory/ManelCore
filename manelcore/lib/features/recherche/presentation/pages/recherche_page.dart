import 'dart:async';
import 'dart:convert';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:google_fonts/google_fonts.dart';
import '../../../../core/api_client.dart';
import '../../../../core/theme.dart';
import '../../../../widgets/header_bar.dart';

class RecherchePage extends ConsumerStatefulWidget {
  const RecherchePage({super.key});

  @override
  ConsumerState<RecherchePage> createState() => _RecherchePageState();
}

class _RecherchePageState extends ConsumerState<RecherchePage> {
  bool _running = false;
  bool _done    = false;

  // LangGraph node events
  final List<_NodeEvent>    _events    = [];
  final Set<String>         _seenErrors = {};
  StreamSubscription<Map<String, dynamic>>? _agentSub;

  // Live browser steps
  final List<_BrowserStep>  _steps     = [];
  StreamSubscription<Map<String, dynamic>>? _liveSub;
  _BrowserStep? _currentStep;

  static const _nodeLabels = {
    'load_profile':    ('👤', 'Chargement du profil entreprise'),
    'generate_queries':('🧠', 'Génération des requêtes de recherche'),
    'search_seao':     ('🏛️', 'Recherche SEAO — appels d\'offres publics'),
    'search_linkedin': ('💼', 'Recherche LinkedIn — opportunités B2B'),
    'search_indeed':   ('🔍', 'Recherche Indeed — contrats et projets'),
    'rank_and_save':   ('💾', 'Classement IA et sauvegarde dans Neo4j'),
  };

  // ── Agent actions ─────────────────────────────────────────────────────────

  Future<void> _startSearch() async {
    _reset();
    try {
      final result = await ref.read(apiClientProvider).runAgent();
      if (result['status'] == 'already_running') {
        _addEvent(_NodeEvent('info', 'ℹ️', 'Agent déjà en cours.'));
        setState(() => _running = false);
        return;
      }
      _startLiveStream();
      _agentSub = ref.read(apiClientProvider).streamAgentEvents().listen(
        _handleAgentEvent,
        onDone: _onDone,
        onError: (_) => _onDone(),
      );
    } catch (e) {
      _addEvent(_NodeEvent('error', '⚠️', e.toString(), isError: true));
      setState(() => _running = false);
    }
  }

  Future<void> _startMock() async {
    _reset();
    _addEvent(const _NodeEvent('mock', '🧪', 'Injection des données de test…'));
    try {
      final result = await ref.read(apiClientProvider).runMockAgent();
      final count = result['count'] ?? 0;
      _addEvent(_NodeEvent('mock_done', '✅', '$count opportunités injectées dans Neo4j.'));
      _done = true;
      ref.invalidate(opportunitiesProvider);
      ref.invalidate(dashboardStatsProvider);
    } catch (e) {
      _addEvent(_NodeEvent('error', '⚠️', e.toString(), isError: true));
    } finally {
      if (mounted) setState(() => _running = false);
    }
  }

  void _reset() {
    _agentSub?.cancel();
    _liveSub?.cancel();
    if (mounted) {
      setState(() {
        _running = true; _done = false;
        _events.clear(); _seenErrors.clear(); _steps.clear(); _currentStep = null;
      });
    }
  }

  void _onDone() {
    if (mounted) setState(() { _running = false; _done = true; });
    _liveSub?.cancel();
    ref.invalidate(opportunitiesProvider);
    ref.invalidate(dashboardStatsProvider);
  }

  void _startLiveStream() {
    _liveSub = ref.read(apiClientProvider).streamBrowserLive().listen(
      (event) {
        if (event['done'] == true) return;
        final step = _BrowserStep(
          source:     event['source'] as String? ?? '',
          step:       event['step']   as int?    ?? 0,
          url:        event['url']    as String? ?? '',
          title:      event['title']  as String? ?? '',
          action:     event['action'] as String? ?? '',
          screenshot: event['screenshot'] as String?,
        );
        if (mounted) setState(() { _currentStep = step; _steps.add(step); });
      },
    );
  }

  void _handleAgentEvent(Map<String, dynamic> event) {
    if (event['done'] == true) { _onDone(); return; }
    if (event['error'] != null) {
      _addEvent(_NodeEvent('error', '⚠️', 'Erreur: ${event['error']}', isError: true));
      setState(() => _running = false);
      return;
    }
    final node    = event['node'] as String? ?? '';
    final (emoji, label) = _nodeLabels[node] ?? ('⚙️', node);
    final dataMap = event['data'] as Map<String, dynamic>?;
    final output  = dataMap?['output'] as Map? ?? {};
    final oppsCount = (output['found_opportunities'] as List?)?.length ?? 0;
    final errors = (output['errors'] as List?)
            ?.map((e) => e.toString())
            .where((e) => e.isNotEmpty)
            .toList() ??
        [];
    final newErrors = errors.where((e) => !_seenErrors.contains(e)).toList();
    _seenErrors.addAll(newErrors);
    var detail = oppsCount > 0 ? '$oppsCount opportunité(s)' : '';
    if (newErrors.isNotEmpty) {
      detail = '${detail.isEmpty ? '' : '$detail · '}${newErrors.length} erreur(s)';
    }
    final errorDetail = newErrors.isEmpty ? '' : ' · ${newErrors.first}';
    _addEvent(_NodeEvent(
      node,
      newErrors.isNotEmpty ? '⚠️' : emoji,
      '${detail.isEmpty ? label : '$label — $detail'}$errorDetail',
      isError: newErrors.isNotEmpty,
    ));
  }

  void _addEvent(_NodeEvent e) {
    if (mounted) setState(() => _events.add(e));
  }

  @override
  void dispose() {
    _agentSub?.cancel();
    _liveSub?.cancel();
    super.dispose();
  }

  // ── Build ─────────────────────────────────────────────────────────────────

  @override
  Widget build(BuildContext context) {
    return Column(children: [
      const AppHeaderBar(
        title: 'Recherche',
        subtitle: 'Cycle de veille SEAO API · crawl public LinkedIn · Indeed',
      ),
      Expanded(child: _running && _steps.isNotEmpty
          ? _LiveView(
              currentStep: _currentStep,
              steps: _steps,
              events: _events,
              onStop: () { _agentSub?.cancel(); _liveSub?.cancel(); setState(() { _running = false; }); },
            )
          : _IdleView(
              running: _running,
              done: _done,
              events: _events,
              onTest: _running ? null : _startMock,
              onFull: _running ? null : _startSearch,
              onStop: _running ? () { _agentSub?.cancel(); _liveSub?.cancel(); setState(() { _running = false; }); } : null,
            )),
    ]);
  }
}

// ── Idle / launch view ────────────────────────────────────────────────────────

class _IdleView extends StatelessWidget {
  final bool running, done;
  final List<_NodeEvent> events;
  final VoidCallback? onTest, onFull, onStop;

  const _IdleView({
    required this.running, required this.done, required this.events,
    required this.onTest, required this.onFull, required this.onStop,
  });

  @override
  Widget build(BuildContext context) => SingleChildScrollView(
    padding: const EdgeInsets.all(24),
    child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      // Launch cards
      LayoutBuilder(builder: (ctx, c) {
        final wide = c.maxWidth >= 600;
        final cardA = _LaunchCard(
          icon: Icons.travel_explore, iconColor: AppTokens.accent,
          title: 'Cycle complet', sublabel: 'SEAO API · LinkedIn · Indeed · crawl léger',
          buttonLabel: 'Lancer la recherche', buttonColor: AppTokens.accent,
          running: running, onTap: onFull, onStop: onStop,
          tip: 'Extraction directe des pages publiques, sans navigateur automatisé.',
        );
        final cardB = _LaunchCard(
          icon: Icons.science_outlined, iconColor: const Color(0xFF8B5CF6),
          title: 'Cycle de test', sublabel: 'Injecte 5 opportunités réalistes · sans navigateur',
          buttonLabel: 'Lancer le test', buttonColor: const Color(0xFF8B5CF6),
          running: running, onTap: onTest,
          tip: 'Aucune dépendance réseau — idéal pour tester l\'interface.',
        );
        return wide
            ? Row(crossAxisAlignment: CrossAxisAlignment.start,
                children: [Expanded(child: cardA), const SizedBox(width: 16), Expanded(child: cardB)])
            : Column(children: [cardA, const SizedBox(height: 16), cardB]);
      }),

      // Done banner
      if (done) ...[
        const SizedBox(height: 16),
        Builder(builder: (context) {
          final hasErrors = events.any((event) => event.isError);
          final color = hasErrors ? AppTokens.badgeOffline : AppTokens.badgeNeo4j;
          return Container(
            width: double.infinity, padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 12),
            decoration: BoxDecoration(color: color.withValues(alpha: 0.08),
                borderRadius: BorderRadius.circular(10),
                border: Border.all(color: color.withValues(alpha: 0.3))),
            child: Row(children: [
              Icon(hasErrors ? Icons.error_outline : Icons.check_circle, color: color, size: 18),
              const SizedBox(width: 10),
              Flexible(child: Text(
                hasErrors ? 'Terminé avec erreurs — consultez le journal.' : 'Terminé — consultez la page Opportunités.',
                  style: GoogleFonts.inter(fontSize: 13, color: color))),
            ]),
          );
        }),
      ],

      // Node event log
      if (events.isNotEmpty) ...[
        const SizedBox(height: 24),
        Text('Journal', style: GoogleFonts.inter(fontSize: 14, fontWeight: FontWeight.w600, color: AppTokens.textPrimary)),
        const SizedBox(height: 12),
        ...events.map((e) => _EventRow(event: e)),
      ],
    ]),
  );
}

// ── Live browser view ─────────────────────────────────────────────────────────

class _LiveView extends StatelessWidget {
  final _BrowserStep? currentStep;
  final List<_BrowserStep> steps;
  final List<_NodeEvent> events;
  final VoidCallback onStop;

  const _LiveView({
    required this.currentStep, required this.steps,
    required this.events, required this.onStop,
  });

  @override
  Widget build(BuildContext context) {
    return Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
      // ── Left panel: screenshot + current action ──────────────────────────
      Expanded(flex: 3, child: Column(children: [
        // Toolbar
        Container(
          color: AppTokens.sidebarBg, padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 10),
          child: Row(children: [
            const SizedBox(width: 8, height: 8, child: CircularProgressIndicator(strokeWidth: 2, color: AppTokens.accent)),
            const SizedBox(width: 10),
            Expanded(child: Text(
              currentStep?.url ?? 'En attente…',
              overflow: TextOverflow.ellipsis,
              style: GoogleFonts.jetBrainsMono(fontSize: 11, color: AppTokens.sidebarText),
            )),
            const SizedBox(width: 8),
            TextButton.icon(
              onPressed: onStop,
              icon: const Icon(Icons.stop_circle_outlined, size: 14),
              label: const Text('Arrêter'),
              style: TextButton.styleFrom(foregroundColor: AppTokens.badgeOffline,
                  textStyle: GoogleFonts.inter(fontSize: 12)),
            ),
          ]),
        ),
        // Screenshot
        Expanded(child: currentStep?.screenshot != null
            ? _Screenshot(base64: currentStep!.screenshot!)
            : Container(color: const Color(0xFF0D1117),
                child: Center(child: Column(mainAxisSize: MainAxisSize.min, children: [
                  const SizedBox(width: 32, height: 32, child: CircularProgressIndicator(strokeWidth: 2, color: AppTokens.accent)),
                  const SizedBox(height: 12),
                  Text(currentStep?.title ?? 'Extraction en cours…',
                      style: GoogleFonts.inter(fontSize: 12, color: AppTokens.sidebarText)),
                ])))),
        // Current action bar
        if (currentStep?.action?.isNotEmpty == true)
          Container(
            color: AppTokens.sidebarBg,
            padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
            child: Row(children: [
              const Icon(Icons.mouse, size: 14, color: AppTokens.accent),
              const SizedBox(width: 8),
              Flexible(child: Text(currentStep!.action!,
                  style: GoogleFonts.inter(fontSize: 12, color: AppTokens.sidebarText))),
            ]),
          ),
      ])),

      // ── Right panel: step log ─────────────────────────────────────────────
      Container(
        width: 280,
        decoration: const BoxDecoration(
          color: AppTokens.cardBg,
          border: Border(left: BorderSide(color: AppTokens.border)),
        ),
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Padding(padding: const EdgeInsets.fromLTRB(16, 14, 16, 8),
              child: Text('ÉTAPES EN DIRECT',
                  style: GoogleFonts.inter(fontSize: 10, fontWeight: FontWeight.w600,
                      letterSpacing: 1.2, color: AppTokens.textMuted))),
          Expanded(child: ListView.builder(
            padding: const EdgeInsets.symmetric(horizontal: 10),
            itemCount: steps.length,
            reverse: true,
            itemBuilder: (_, i) {
              final s = steps[steps.length - 1 - i];
              return Container(
                margin: const EdgeInsets.only(bottom: 6),
                padding: const EdgeInsets.all(10),
                decoration: BoxDecoration(
                    color: AppTokens.contentBg, borderRadius: BorderRadius.circular(8),
                    border: Border.all(color: AppTokens.border)),
                child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                  Row(children: [
                    _SourceBadge(source: s.source),
                    const Spacer(),
                    Text('#${s.step}', style: GoogleFonts.jetBrainsMono(fontSize: 9, color: AppTokens.textMuted)),
                  ]),
                  if (s.title.isNotEmpty) ...[
                    const SizedBox(height: 4),
                    Text(s.title, style: GoogleFonts.inter(fontSize: 11, fontWeight: FontWeight.w500, color: AppTokens.textPrimary),
                        overflow: TextOverflow.ellipsis),
                  ],
                  if (s.action?.isNotEmpty == true) ...[
                    const SizedBox(height: 2),
                    Text(s.action!, style: GoogleFonts.inter(fontSize: 10, color: AppTokens.textSecondary),
                        overflow: TextOverflow.ellipsis),
                  ],
                ]),
              );
            },
          )),
          // Node events at bottom
          if (events.isNotEmpty)
            Container(
              decoration: const BoxDecoration(border: Border(top: BorderSide(color: AppTokens.border))),
              child: Column(children: events
                  .sublist(events.length > 3 ? events.length - 3 : 0)
                  .map((e) => Padding(
                    padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
                    child: Row(children: [
                      Text(e.emoji, style: const TextStyle(fontSize: 14)),
                      const SizedBox(width: 8),
                      Flexible(child: Text(e.label,
                          overflow: TextOverflow.ellipsis,
                          style: GoogleFonts.inter(fontSize: 11,
                              color: e.isError ? AppTokens.badgeOffline : AppTokens.textSecondary))),
                    ]),
                  )).toList()),
            ),
        ]),
      ),
    ]);
  }
}

// ── Screenshot widget ─────────────────────────────────────────────────────────

class _Screenshot extends StatelessWidget {
  final String base64;
  const _Screenshot({required this.base64});

  @override
  Widget build(BuildContext context) {
    try {
      final bytes = base64Decode(base64);
      return Image.memory(bytes, fit: BoxFit.contain, gaplessPlayback: true);
    } catch (_) {
      return const Center(child: Icon(Icons.broken_image, color: AppTokens.textMuted, size: 48));
    }
  }
}

// ── Source badge ──────────────────────────────────────────────────────────────

class _SourceBadge extends StatelessWidget {
  final String source;
  const _SourceBadge({required this.source});

  Color get _color => switch (source) {
    'SEAO'     => AppTokens.accent,
    'LinkedIn' => const Color(0xFF0A66C2),
    'Indeed'   => const Color(0xFF2164F3),
    _          => AppTokens.textMuted,
  };

  @override
  Widget build(BuildContext context) => Container(
    padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
    decoration: BoxDecoration(color: _color.withValues(alpha: 0.1), borderRadius: BorderRadius.circular(4)),
    child: Text(source.isEmpty ? '?' : source,
        style: GoogleFonts.inter(fontSize: 9, fontWeight: FontWeight.w700, color: _color)),
  );
}

// ── Launch card ───────────────────────────────────────────────────────────────

class _LaunchCard extends StatelessWidget {
  final IconData icon; final Color iconColor;
  final String title, sublabel, buttonLabel; final Color buttonColor;
  final bool running; final VoidCallback? onTap; final VoidCallback? onStop;
  final String? tip;

  const _LaunchCard({
    required this.icon, required this.iconColor, required this.title,
    required this.sublabel, required this.buttonLabel, required this.buttonColor,
    required this.running, required this.onTap, this.onStop, this.tip,
  });

  @override
  Widget build(BuildContext context) => Container(
    padding: const EdgeInsets.all(20),
    decoration: BoxDecoration(
      color: AppTokens.cardBg,
      borderRadius: BorderRadius.circular(AppTokens.borderRadiusLg),
      border: Border.all(color: running ? iconColor.withValues(alpha: 0.4) : AppTokens.border),
    ),
    child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      Row(children: [
        Container(padding: const EdgeInsets.all(9),
            decoration: BoxDecoration(color: iconColor.withValues(alpha: 0.1), borderRadius: BorderRadius.circular(10)),
            child: Icon(icon, color: iconColor, size: 20)),
        const SizedBox(width: 12),
        Expanded(child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Text(title, style: GoogleFonts.inter(fontSize: 14, fontWeight: FontWeight.w700, color: AppTokens.textPrimary)),
          Text(sublabel, style: GoogleFonts.inter(fontSize: 11, color: AppTokens.textMuted)),
        ])),
      ]),
      if (tip != null) ...[
        const SizedBox(height: 12),
        Container(
          padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 7),
          decoration: BoxDecoration(color: iconColor.withValues(alpha: 0.05), borderRadius: BorderRadius.circular(8),
              border: Border.all(color: iconColor.withValues(alpha: 0.2))),
          child: Row(children: [
            Icon(Icons.lightbulb_outline, size: 13, color: iconColor),
            const SizedBox(width: 7),
            Flexible(child: Text(tip!, style: GoogleFonts.inter(fontSize: 11, color: iconColor))),
          ]),
        ),
      ],
      const SizedBox(height: 16),
      SizedBox(width: double.infinity, child: ElevatedButton.icon(
        onPressed: onTap,
        icon: running
            ? const SizedBox(width: 14, height: 14, child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white))
            : Icon(icon, size: 15),
        label: Text(running ? 'En cours…' : buttonLabel),
        style: ElevatedButton.styleFrom(
          backgroundColor: buttonColor, foregroundColor: Colors.white,
          disabledBackgroundColor: buttonColor.withValues(alpha: 0.35),
          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(8)),
          padding: const EdgeInsets.symmetric(vertical: 12),
        ),
      )),
    ]),
  );
}

// ── Data classes ──────────────────────────────────────────────────────────────

class _NodeEvent {
  final String node, emoji, label;
  final bool isError;
  const _NodeEvent(this.node, this.emoji, this.label, {this.isError = false});
}

class _BrowserStep {
  final String source, url, title;
  final int step;
  final String? action, screenshot;
  const _BrowserStep({
    required this.source, required this.step, required this.url,
    required this.title, this.action, this.screenshot,
  });
}

class _EventRow extends StatelessWidget {
  final _NodeEvent event;
  const _EventRow({required this.event});

  @override
  Widget build(BuildContext context) => Container(
    margin: const EdgeInsets.only(bottom: 8),
    padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
    decoration: BoxDecoration(
      color: event.isError ? AppTokens.badgeOffline.withValues(alpha: 0.04) : AppTokens.cardBg,
      borderRadius: BorderRadius.circular(AppTokens.borderRadius),
      border: Border.all(color: event.isError ? AppTokens.badgeOffline.withValues(alpha: 0.3) : AppTokens.border),
    ),
    child: Row(children: [
      Text(event.emoji, style: const TextStyle(fontSize: 16)),
      const SizedBox(width: 12),
      Expanded(child: Text(event.label, style: GoogleFonts.inter(fontSize: 13,
          color: event.isError ? AppTokens.badgeOffline : AppTokens.textPrimary))),
      if (!event.isError) const Icon(Icons.check, size: 13, color: AppTokens.badgeNeo4j),
    ]),
  );
}
