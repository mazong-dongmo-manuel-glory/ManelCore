import 'dart:async';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:google_fonts/google_fonts.dart';
import 'package:url_launcher/url_launcher.dart';
import '../../../../core/api_client.dart';
import '../../../../core/theme.dart';
import '../../../../widgets/header_bar.dart';

class DashboardPage extends ConsumerStatefulWidget {
  const DashboardPage({super.key});

  @override
  ConsumerState<DashboardPage> createState() => _DashboardPageState();
}

class _DashboardPageState extends ConsumerState<DashboardPage> {
  // Cycle state
  bool _running = false;
  String _cycleStatus = '';
  StreamSubscription<Map<String, dynamic>>? _sub;
  Timer? _refreshTimer;

  @override
  void initState() {
    super.initState();
    // Auto-refresh the dashboard asynchronously every 10 seconds
    _refreshTimer = Timer.periodic(const Duration(seconds: 10), (_) => _refresh());
  }

  @override
  void dispose() {
    _refreshTimer?.cancel();
    _sub?.cancel();
    super.dispose();
  }

  void _refresh() {
    ref.invalidate(dashboardStatsProvider);
    ref.invalidate(opportunitiesProvider);
  }

  Future<void> _runTest() async {
    setState(() {
      _running = true;
      _cycleStatus = '🧪 Injection des données de test…';
    });
    try {
      final result = await ref.read(apiClientProvider).runMockAgent();
      final count = result['count'] ?? 0;
      setState(() {
        _cycleStatus = '✅ $count opportunités injectées';
        _running = false;
      });
      _refresh();
    } catch (e) {
      setState(() {
        _cycleStatus = '❌ Erreur: $e';
        _running = false;
      });
    }
  }

  Future<void> _runFull() async {
    setState(() {
      _running = true;
      _cycleStatus = '🚀 Démarrage du cycle complet…';
    });
    try {
      final result = await ref.read(apiClientProvider).runAgent();
      if (result['status'] == 'already_running') {
        setState(() {
          _cycleStatus = 'ℹ️ Agent déjà en cours';
          _running = false;
        });
        return;
      }
      setState(() => _cycleStatus = '🔄 Agent actif — SEAO, LinkedIn, Indeed…');
      _sub = ref
          .read(apiClientProvider)
          .streamAgentEvents()
          .listen(
            (event) {
              if (event['done'] == true) {
                setState(() {
                  _cycleStatus = '✅ Cycle terminé';
                  _running = false;
                });
                _refresh();
                return;
              }
              final node = event['node'] as String? ?? '';
              final labels = {
                'load_profile': '👤 Chargement profil',
                'generate_queries': '🧠 Génération requêtes',
                'search_seao': '🏛️ Recherche SEAO',
                'search_linkedin': '💼 Recherche LinkedIn',
                'search_indeed': '🔍 Recherche Indeed',
                'rank_and_save': '💾 Classement & sauvegarde',
              };
              if (labels.containsKey(node)) {
                setState(() => _cycleStatus = labels[node]!);
              }
            },
            onDone: () {
              setState(() {
                _cycleStatus = '✅ Cycle terminé';
                _running = false;
              });
              _refresh();
            },
            onError: (_) {
              setState(() {
                _cycleStatus = '❌ Erreur pendant le cycle';
                _running = false;
              });
            },
          );
    } catch (e) {
      setState(() {
        _cycleStatus = '❌ $e';
        _running = false;
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    final statsAsync = ref.watch(dashboardStatsProvider);
    final oppsAsync = ref.watch(opportunitiesProvider(null));

    return Column(
      children: [
        AppHeaderBar(
          title: 'Vue d\'ensemble',
          subtitle: 'Synthèse globale de votre activité ManelCore',
          actions: [
            IconButton(
              icon: const Icon(
                Icons.refresh,
                size: 18,
                color: AppTokens.textMuted,
              ),
              tooltip: 'Actualiser',
              onPressed: _refresh,
            ),
          ],
        ),
        Expanded(
          child: SingleChildScrollView(
            padding: const EdgeInsets.all(24),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                // ── Panneau de lancement ──────────────────────────────────────
                _CycleLauncher(
                  running: _running,
                  status: _cycleStatus,
                  onTest: _running ? null : _runTest,
                  onFull: _running ? null : _runFull,
                  onCancel: _running
                      ? () {
                          _sub?.cancel();
                          setState(() {
                            _running = false;
                            _cycleStatus = '';
                          });
                        }
                      : null,
                ),
                const SizedBox(height: 24),

                // ── Stats ─────────────────────────────────────────────────────
                statsAsync.when(
                  loading: () => const SizedBox(
                    height: 110,
                    child: Center(child: CircularProgressIndicator()),
                  ),
                  error: (e, s) =>
                      _StatRow(opps: 0, validated: 0, emails: 0, contacts: 0),
                  data: (s) => _StatRow(
                    opps: s['opportunities'] as int? ?? 0,
                    validated: s['validated'] as int? ?? 0,
                    emails: s['emails_sent'] as int? ?? 0,
                    contacts: s['contacts'] as int? ?? 0,
                  ),
                ),
                const SizedBox(height: 28),

                // ── Opportunités récentes ──────────────────────────────────────
                Text(
                  'Opportunités récentes',
                  style: GoogleFonts.inter(
                    fontSize: 16,
                    fontWeight: FontWeight.w600,
                    color: AppTokens.textPrimary,
                  ),
                ),
                const SizedBox(height: 16),
                oppsAsync.when(
                  loading: () =>
                      const Center(child: CircularProgressIndicator()),
                  error: (e, s) => _OppTable(opps: const []),
                  data: (opps) => _OppTable(opps: opps.take(8).toList()),
                ),
              ],
            ),
          ),
        ),
      ],
    );
  }
}

// ── Cycle launcher panel ───────────────────────────────────────────────────────

class _CycleLauncher extends StatelessWidget {
  final bool running;
  final String status;
  final VoidCallback? onTest;
  final VoidCallback? onFull;
  final VoidCallback? onCancel;

  const _CycleLauncher({
    required this.running,
    required this.status,
    required this.onTest,
    required this.onFull,
    required this.onCancel,
  });

  @override
  Widget build(BuildContext context) {
    return AnimatedContainer(
      duration: const Duration(milliseconds: 250),
      width: double.infinity,
      padding: const EdgeInsets.all(20),
      decoration: BoxDecoration(
        color: AppTokens.cardBg,
        borderRadius: BorderRadius.circular(AppTokens.borderRadiusLg),
        border: Border.all(
          color: running
              ? AppTokens.accent.withValues(alpha: 0.5)
              : AppTokens.border,
          width: running ? 1.5 : 1,
        ),
        boxShadow: running
            ? [
                BoxShadow(
                  color: AppTokens.accent.withValues(alpha: 0.07),
                  blurRadius: 16,
                ),
              ]
            : [],
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          // Header
          Row(
            children: [
              AnimatedContainer(
                duration: const Duration(milliseconds: 250),
                padding: const EdgeInsets.all(8),
                decoration: BoxDecoration(
                  color: running
                      ? AppTokens.accent.withValues(alpha: 0.12)
                      : AppTokens.contentBg,
                  borderRadius: BorderRadius.circular(8),
                ),
                child: Icon(
                  running ? Icons.radar : Icons.play_circle_outline,
                  color: running ? AppTokens.accent : AppTokens.textMuted,
                  size: 20,
                ),
              ),
              const SizedBox(width: 12),
              Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    'Cycle de recherche',
                    style: GoogleFonts.inter(
                      fontSize: 15,
                      fontWeight: FontWeight.w700,
                      color: AppTokens.textPrimary,
                    ),
                  ),
                  Text(
                    running ? 'En cours…' : 'Prêt à lancer',
                    style: GoogleFonts.inter(
                      fontSize: 11,
                      color: running ? AppTokens.accent : AppTokens.textMuted,
                    ),
                  ),
                ],
              ),
              const Spacer(),
              if (running && onCancel != null)
                TextButton.icon(
                  onPressed: onCancel,
                  icon: const Icon(Icons.stop_circle_outlined, size: 14),
                  label: const Text('Arrêter'),
                  style: TextButton.styleFrom(
                    foregroundColor: AppTokens.badgeOffline,
                    textStyle: GoogleFonts.inter(fontSize: 12),
                  ),
                ),
            ],
          ),

          // Status bar (visible quand actif)
          if (status.isNotEmpty) ...[
            const SizedBox(height: 14),
            Container(
              width: double.infinity,
              padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 9),
              decoration: BoxDecoration(
                color: AppTokens.contentBg,
                borderRadius: BorderRadius.circular(8),
                border: Border.all(color: AppTokens.border),
              ),
              child: Row(
                children: [
                  if (running)
                    const Padding(
                      padding: EdgeInsets.only(right: 10),
                      child: SizedBox(
                        width: 14,
                        height: 14,
                        child: CircularProgressIndicator(
                          strokeWidth: 2,
                          color: AppTokens.accent,
                        ),
                      ),
                    ),
                  Expanded(
                    child: Text(
                      status,
                      style: GoogleFonts.inter(
                        fontSize: 13,
                        color: status.startsWith('✅')
                            ? AppTokens.badgeNeo4j
                            : status.startsWith('❌')
                            ? AppTokens.badgeOffline
                            : AppTokens.textPrimary,
                      ),
                    ),
                  ),
                ],
              ),
            ),
          ],

          const SizedBox(height: 16),

          // Buttons
          LayoutBuilder(
            builder: (ctx, c) {
              final wide = c.maxWidth >= 520;
              final btnTest = _CycleBtn(
                icon: Icons.science_outlined,
                label: 'Cycle de test',
                sublabel: '5 opportunités réalistes · instantané',
                color: const Color(0xFF8B5CF6),
                onTap: onTest,
                running: running,
              );
              final btnFull = _CycleBtn(
                icon: Icons.travel_explore,
                label: 'Cycle complet',
                sublabel: 'SEAO API · LinkedIn · Indeed · crawl',
                color: AppTokens.accent,
                onTap: onFull,
                running: running,
              );
              return wide
                  ? Row(
                      children: [
                        Expanded(child: btnTest),
                        const SizedBox(width: 12),
                        Expanded(child: btnFull),
                      ],
                    )
                  : Column(
                      children: [btnTest, const SizedBox(height: 10), btnFull],
                    );
            },
          ),
        ],
      ),
    );
  }
}

class _CycleBtn extends StatelessWidget {
  final IconData icon;
  final String label, sublabel;
  final Color color;
  final VoidCallback? onTap;
  final bool running;

  const _CycleBtn({
    required this.icon,
    required this.label,
    required this.sublabel,
    required this.color,
    required this.onTap,
    required this.running,
  });

  @override
  Widget build(BuildContext context) => Material(
    color: onTap != null ? color.withValues(alpha: 0.06) : AppTokens.contentBg,
    borderRadius: BorderRadius.circular(10),
    child: InkWell(
      onTap: onTap,
      borderRadius: BorderRadius.circular(10),
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
        decoration: BoxDecoration(
          borderRadius: BorderRadius.circular(10),
          border: Border.all(
            color: onTap != null
                ? color.withValues(alpha: 0.3)
                : AppTokens.border,
          ),
        ),
        child: Row(
          children: [
            Icon(
              icon,
              color: onTap != null ? color : AppTokens.textMuted,
              size: 20,
            ),
            const SizedBox(width: 12),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    label,
                    style: GoogleFonts.inter(
                      fontSize: 13,
                      fontWeight: FontWeight.w600,
                      color: onTap != null ? color : AppTokens.textMuted,
                    ),
                  ),
                  Text(
                    sublabel,
                    style: GoogleFonts.inter(
                      fontSize: 11,
                      color: onTap != null
                          ? AppTokens.textSecondary
                          : AppTokens.textMuted,
                    ),
                  ),
                ],
              ),
            ),
            if (onTap != null)
              Icon(
                Icons.arrow_forward_ios,
                size: 12,
                color: color.withValues(alpha: 0.5),
              ),
          ],
        ),
      ),
    ),
  );
}

// ── Stats row ──────────────────────────────────────────────────────────────────

class _StatRow extends StatelessWidget {
  final int opps, validated, emails, contacts;
  const _StatRow({
    required this.opps,
    required this.validated,
    required this.emails,
    required this.contacts,
  });

  @override
  Widget build(BuildContext context) {
    final cards = [
      _StatCard(
        icon: Icons.work_outline,
        label: 'Opportunités',
        value: '$opps',
        change: 'SEAO · LinkedIn · Indeed',
        color: AppTokens.accent,
      ),
      _StatCard(
        icon: Icons.check_circle_outline,
        label: 'Validées',
        value: '$validated',
        change: opps > 0
            ? '${(validated / opps * 100).toStringAsFixed(0)}% taux'
            : '—',
        color: AppTokens.badgeNeo4j,
      ),
      _StatCard(
        icon: Icons.email_outlined,
        label: 'Emails envoyés',
        value: '$emails',
        change: 'Via SMTP',
        color: const Color(0xFFF59E0B),
      ),
      _StatCard(
        icon: Icons.people_outline,
        label: 'Contacts',
        value: '$contacts',
        change: 'Dans le CRM',
        color: const Color(0xFF8B5CF6),
      ),
    ];
    return LayoutBuilder(
      builder: (ctx, c) {
        if (c.maxWidth >= 640) {
          return Row(
            children: [
              for (int i = 0; i < cards.length; i++) ...[
                Expanded(child: cards[i]),
                if (i < cards.length - 1) const SizedBox(width: 14),
              ],
            ],
          );
        }
        return GridView.count(
          crossAxisCount: 2,
          shrinkWrap: true,
          physics: const NeverScrollableScrollPhysics(),
          crossAxisSpacing: 12,
          mainAxisSpacing: 12,
          childAspectRatio: 1.6,
          children: cards,
        );
      },
    );
  }
}

class _StatCard extends StatefulWidget {
  final IconData icon;
  final String label, value, change;
  final Color color;
  const _StatCard({
    required this.icon,
    required this.label,
    required this.value,
    required this.change,
    required this.color,
  });
  @override
  State<_StatCard> createState() => _StatCardState();
}

class _StatCardState extends State<_StatCard> {
  bool _hovered = false;
  @override
  Widget build(BuildContext context) => MouseRegion(
    onEnter: (_) => setState(() => _hovered = true),
    onExit: (_) => setState(() => _hovered = false),
    child: AnimatedContainer(
      duration: const Duration(milliseconds: 200),
      padding: const EdgeInsets.all(18),
      decoration: BoxDecoration(
        color: AppTokens.cardBg,
        borderRadius: BorderRadius.circular(AppTokens.borderRadiusLg),
        border: Border.all(
          color: _hovered
              ? widget.color.withValues(alpha: 0.4)
              : AppTokens.border,
        ),
        boxShadow: _hovered
            ? [
                BoxShadow(
                  color: widget.color.withValues(alpha: 0.08),
                  blurRadius: 16,
                  offset: const Offset(0, 4),
                ),
              ]
            : [],
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Container(
                padding: const EdgeInsets.all(8),
                decoration: BoxDecoration(
                  color: widget.color.withValues(alpha: 0.1),
                  borderRadius: BorderRadius.circular(8),
                ),
                child: Icon(widget.icon, size: 16, color: widget.color),
              ),
              const Spacer(),
              Icon(Icons.trending_up, size: 13, color: widget.color),
            ],
          ),
          const SizedBox(height: 14),
          Text(
            widget.value,
            style: GoogleFonts.inter(
              fontSize: 26,
              fontWeight: FontWeight.w700,
              color: AppTokens.textPrimary,
            ),
          ),
          const SizedBox(height: 3),
          Text(
            widget.label,
            style: GoogleFonts.inter(
              fontSize: 12,
              fontWeight: FontWeight.w500,
              color: AppTokens.textSecondary,
            ),
          ),
          const SizedBox(height: 2),
          Text(
            widget.change,
            style: GoogleFonts.inter(fontSize: 10, color: AppTokens.textMuted),
          ),
        ],
      ),
    ),
  );
}

// ── Opportunities table ────────────────────────────────────────────────────────

class _OppTable extends StatelessWidget {
  final List opps;
  const _OppTable({required this.opps});

  Color _statusColor(String? s) => switch (s) {
    'validé' => AppTokens.badgeNeo4j,
    'rejeté' => AppTokens.badgeOffline,
    'en_cours' => const Color(0xFFF59E0B),
    _ => AppTokens.accent,
  };

  @override
  Widget build(BuildContext context) => Container(
    decoration: BoxDecoration(
      color: AppTokens.cardBg,
      borderRadius: BorderRadius.circular(AppTokens.borderRadiusLg),
      border: Border.all(color: AppTokens.border),
    ),
    child: Column(
      children: [
        Container(
          padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 12),
          decoration: const BoxDecoration(
            border: Border(bottom: BorderSide(color: AppTokens.border)),
          ),
          child: Row(
            children: [
              _Hdr('Titre', 3),
              _Hdr('Source', 1),
              _Hdr('Score', 1),
              _Hdr('Statut', 1),
            ],
          ),
        ),
        if (opps.isEmpty)
          Padding(
            padding: const EdgeInsets.all(24),
            child: Center(
              child: Column(
                mainAxisSize: MainAxisSize.min,
                children: [
                  const Icon(
                    Icons.work_off_outlined,
                    size: 36,
                    color: AppTokens.textMuted,
                  ),
                  const SizedBox(height: 8),
                  Text(
                    'Lance un cycle pour voir des opportunités.',
                    style: GoogleFonts.inter(
                      fontSize: 12,
                      color: AppTokens.textMuted,
                    ),
                  ),
                ],
              ),
            ),
          )
        else
          ...opps.map((o) {
            final opp = o as Map<String, dynamic>;
            final score = opp['score_pertinence'];
            final pct = score != null
                ? '${((double.tryParse(score.toString()) ?? 0.0) * 100).toInt()}%'
                : '—';
            final statut = (opp['statut'] ?? 'nouveau') as String;
            return _OppRow(
              title: opp['titre'] ?? '—',
              source: opp['source'] ?? '—',
              score: pct,
              status: statut,
              statusColor: _statusColor(statut),
              url: (opp['url'] ?? '').toString(),
            );
          }),
      ],
    ),
  );
}

class _Hdr extends StatelessWidget {
  final String text;
  final int flex;
  const _Hdr(this.text, this.flex);
  @override
  Widget build(BuildContext context) => Expanded(
    flex: flex,
    child: Text(
      text,
      style: GoogleFonts.inter(
        fontSize: 11,
        fontWeight: FontWeight.w600,
        letterSpacing: 0.5,
        color: AppTokens.textMuted,
      ),
    ),
  );
}

class _OppRow extends StatefulWidget {
  final String title, source, score, status, url;
  final Color statusColor;
  const _OppRow({
    required this.title,
    required this.source,
    required this.score,
    required this.status,
    required this.statusColor,
    required this.url,
  });
  @override
  State<_OppRow> createState() => _OppRowState();
}

class _OppRowState extends State<_OppRow> {
  bool _hovered = false;

  Future<void> _openUrl() async {
    final uri = Uri.tryParse(widget.url.trim());
    if (uri == null || !uri.hasScheme) return;
    final opened = await launchUrl(uri, mode: LaunchMode.externalApplication);
    if (!opened && mounted) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Impossible d\'ouvrir le lien.')),
      );
    }
  }

  @override
  Widget build(BuildContext context) => MouseRegion(
    onEnter: (_) => setState(() => _hovered = true),
    onExit: (_) => setState(() => _hovered = false),
    child: AnimatedContainer(
      duration: const Duration(milliseconds: 120),
      padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 14),
      decoration: BoxDecoration(
        color: _hovered ? AppTokens.contentBg : Colors.transparent,
        border: const Border(bottom: BorderSide(color: AppTokens.divider)),
      ),
      child: Row(
        children: [
          Expanded(
            flex: 3,
            child: Row(
              children: [
                Expanded(
                  child: Text(
                    widget.title,
                    overflow: TextOverflow.ellipsis,
                    style: GoogleFonts.inter(
                      fontSize: 13,
                      fontWeight: FontWeight.w500,
                      color: AppTokens.textPrimary,
                    ),
                  ),
                ),
                if (widget.url.trim().isNotEmpty)
                  IconButton(
                    onPressed: _openUrl,
                    icon: const Icon(Icons.open_in_new, size: 14),
                    color: AppTokens.accent,
                    tooltip: 'Ouvrir l\'appel d\'offres',
                    constraints: const BoxConstraints(
                      maxWidth: 28,
                      maxHeight: 28,
                    ),
                    padding: EdgeInsets.zero,
                  ),
              ],
            ),
          ),
          Expanded(
            flex: 1,
            child: Text(
              widget.source,
              style: GoogleFonts.inter(
                fontSize: 12,
                color: AppTokens.textSecondary,
              ),
            ),
          ),
          Expanded(
            flex: 1,
            child: Text(
              widget.score,
              style: GoogleFonts.inter(
                fontSize: 13,
                fontWeight: FontWeight.w600,
                color: AppTokens.accent,
              ),
            ),
          ),
          Expanded(
            flex: 1,
            child: Container(
              padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
              decoration: BoxDecoration(
                color: widget.statusColor.withValues(alpha: 0.1),
                borderRadius: BorderRadius.circular(12),
              ),
              child: Text(
                widget.status,
                textAlign: TextAlign.center,
                style: GoogleFonts.inter(
                  fontSize: 11,
                  fontWeight: FontWeight.w600,
                  color: widget.statusColor,
                ),
              ),
            ),
          ),
        ],
      ),
    ),
  );
}
