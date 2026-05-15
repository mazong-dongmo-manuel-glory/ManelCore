import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:google_fonts/google_fonts.dart';
import 'package:url_launcher/url_launcher.dart';
import '../../../../core/api_client.dart';
import '../../../../core/theme.dart';
import '../../../../widgets/header_bar.dart';

// Provider for opportunities pending validation (statut = nouveau)
final pendingOpportunitiesProvider = FutureProvider<List<dynamic>>((ref) async {
  return ref.read(apiClientProvider).getOpportunities(statut: 'nouveau');
});

class ValidationsPage extends ConsumerStatefulWidget {
  const ValidationsPage({super.key});

  @override
  ConsumerState<ValidationsPage> createState() => _ValidationsPageState();
}

class _ValidationsPageState extends ConsumerState<ValidationsPage> {
  int _selectedIndex = 0;

  // Draft state per opportunity (threadId, draft text, loading flag)
  final Map<String, _DraftState> _draftStates = {};

  void _refresh() {
    ref.invalidate(pendingOpportunitiesProvider);
    ref.invalidate(opportunitiesProvider);
  }

  Future<void> _generateDraft(Map<String, dynamic> opp) async {
    final id = opp['id'] as String? ?? '';
    setState(() => _draftStates[id] = const _DraftState(loading: true));
    try {
      final result = await ref.read(apiClientProvider).draftContact(id, {
        'email': '',
        'nom': opp['organisation'] ?? '',
        'organisation': opp['organisation'] ?? '',
      });
      setState(
        () => _draftStates[id] = _DraftState(
          loading: false,
          threadId: result['thread_id'],
          draft: result['draft_email'] ?? '',
        ),
      );
    } catch (e) {
      setState(
        () =>
            _draftStates[id] = _DraftState(loading: false, error: e.toString()),
      );
    }
  }

  Future<void> _approve(String oppId, bool approved) async {
    final ds = _draftStates[oppId];
    if (ds?.threadId == null) return;
    setState(() => _draftStates[oppId] = ds!.copyWith(loading: true));
    try {
      await ref.read(apiClientProvider).approveContact(ds!.threadId!, approved);
      // Also update opp status
      await ref
          .read(apiClientProvider)
          .updateOpportunityStatus(oppId, approved ? 'validé' : 'rejeté');
      setState(() => _draftStates.remove(oppId));
      _refresh();
    } catch (e) {
      setState(
        () => _draftStates[oppId] = ds!.copyWith(
          loading: false,
          error: e.toString(),
        ),
      );
    }
  }

  Future<void> _quickValidate(String id, String statut) async {
    await ref.read(apiClientProvider).updateOpportunityStatus(id, statut);
    _refresh();
  }

  Future<void> _openOpportunityUrl(String? rawUrl) async {
    final url = rawUrl?.trim() ?? '';
    final uri = Uri.tryParse(url);
    if (uri == null || !uri.hasScheme) return;
    final opened = await launchUrl(uri, mode: LaunchMode.externalApplication);
    if (!opened && mounted) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Impossible d\'ouvrir le lien.')),
      );
    }
  }

  @override
  Widget build(BuildContext context) {
    final oppsAsync = ref.watch(pendingOpportunitiesProvider);

    return Column(
      children: [
        AppHeaderBar(
          title: 'Validations',
          subtitle: 'Approbation des opportunités et brouillons générés par IA',
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
          child: oppsAsync.when(
            loading: () => const Center(child: CircularProgressIndicator()),
            error: (e, _) => Center(
              child: Text(
                'Erreur: $e',
                style: const TextStyle(color: AppTokens.badgeOffline),
              ),
            ),
            data: (opps) {
              if (opps.isEmpty) {
                return Center(
                  child: Column(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      const Icon(
                        Icons.check_circle_outline,
                        size: 48,
                        color: AppTokens.badgeNeo4j,
                      ),
                      const SizedBox(height: 12),
                      Text(
                        'Aucune opportunité en attente de validation',
                        style: GoogleFonts.inter(
                          fontSize: 15,
                          fontWeight: FontWeight.w600,
                          color: AppTokens.textPrimary,
                        ),
                      ),
                      const SizedBox(height: 6),
                      Text(
                        'Lancez un cycle de recherche depuis la page Recherche.',
                        style: GoogleFonts.inter(
                          fontSize: 12,
                          color: AppTokens.textMuted,
                        ),
                      ),
                    ],
                  ),
                );
              }

              final selected = _selectedIndex.clamp(0, opps.length - 1);
              final opp = opps[selected] as Map<String, dynamic>;
              final oppId = opp['id'] as String? ?? '';
              final ds = _draftStates[oppId];

              return Row(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  // ── Left: queue ───────────────────────────────────────────────
                  Container(
                    width: 300,
                    decoration: const BoxDecoration(
                      color: AppTokens.cardBg,
                      border: Border(
                        right: BorderSide(color: AppTokens.border),
                      ),
                    ),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Padding(
                          padding: const EdgeInsets.fromLTRB(20, 20, 20, 8),
                          child: Text(
                            'FILE D\'APPROBATION',
                            style: GoogleFonts.inter(
                              fontSize: 10,
                              fontWeight: FontWeight.w600,
                              letterSpacing: 1.2,
                              color: AppTokens.textMuted,
                            ),
                          ),
                        ),
                        Padding(
                          padding: const EdgeInsets.fromLTRB(20, 0, 20, 12),
                          child: Text(
                            '${opps.length} EN ATTENTE',
                            style: GoogleFonts.inter(
                              fontSize: 10,
                              fontWeight: FontWeight.w700,
                              letterSpacing: 1.2,
                              color: AppTokens.accent,
                            ),
                          ),
                        ),
                        Expanded(
                          child: ListView.builder(
                            padding: const EdgeInsets.symmetric(horizontal: 12),
                            itemCount: opps.length,
                            itemBuilder: (ctx, i) {
                              final o = opps[i] as Map<String, dynamic>;
                              final isSelected = i == selected;
                              return _QueueTile(
                                opp: o,
                                isSelected: isSelected,
                                onTap: () => setState(() => _selectedIndex = i),
                              );
                            },
                          ),
                        ),
                      ],
                    ),
                  ),

                  // ── Center: detail + draft ─────────────────────────────────────
                  Expanded(
                    flex: 3,
                    child: Container(
                      color: AppTokens.contentBg,
                      child: SingleChildScrollView(
                        padding: const EdgeInsets.all(28),
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Text(
                              'VALIDATION OPPORTUNITÉ',
                              style: GoogleFonts.inter(
                                fontSize: 10,
                                fontWeight: FontWeight.w600,
                                letterSpacing: 1.2,
                                color: AppTokens.textMuted,
                              ),
                            ),
                            const SizedBox(height: 4),
                            Text(
                              opp['titre'] ?? '—',
                              style: GoogleFonts.inter(
                                fontSize: 16,
                                fontWeight: FontWeight.w600,
                                color: AppTokens.textPrimary,
                              ),
                            ),
                            const SizedBox(height: 8),
                            Text(
                              '${opp['organisation'] ?? '—'} · Source: ${opp['source'] ?? '—'}',
                              style: GoogleFonts.inter(
                                fontSize: 12,
                                color: AppTokens.textMuted,
                              ),
                            ),
                            if ((opp['url'] ?? '')
                                .toString()
                                .trim()
                                .isNotEmpty) ...[
                              const SizedBox(height: 8),
                              TextButton.icon(
                                onPressed: () => _openOpportunityUrl(
                                  (opp['url'] ?? '').toString(),
                                ),
                                icon: const Icon(Icons.open_in_new, size: 14),
                                label: const Text(
                                  'Voir l\'appel d\'offres exact',
                                ),
                                style: TextButton.styleFrom(
                                  foregroundColor: AppTokens.accent,
                                  padding: EdgeInsets.zero,
                                  textStyle: GoogleFonts.inter(
                                    fontSize: 12,
                                    fontWeight: FontWeight.w600,
                                  ),
                                ),
                              ),
                            ],
                            if (opp['resume'] != null) ...[
                              const SizedBox(height: 12),
                              Text(
                                opp['resume'],
                                style: GoogleFonts.inter(
                                  fontSize: 13,
                                  color: AppTokens.textSecondary,
                                  height: 1.5,
                                ),
                              ),
                            ],
                            const SizedBox(height: 20),

                            // Quick action buttons (no draft needed)
                            Row(
                              children: [
                                _ActionBtn(
                                  '✅ Valider directement',
                                  AppTokens.badgeNeo4j,
                                  () => _quickValidate(oppId, 'validé'),
                                ),
                                const SizedBox(width: 8),
                                _ActionBtn(
                                  '❌ Rejeter',
                                  AppTokens.badgeOffline,
                                  () => _quickValidate(oppId, 'rejeté'),
                                ),
                                const SizedBox(width: 8),
                                _ActionBtn(
                                  '📬 Générer un email',
                                  AppTokens.accent,
                                  ds == null ? () => _generateDraft(opp) : null,
                                ),
                              ],
                            ),

                            // Draft zone
                            if (ds != null) ...[
                              const SizedBox(height: 20),
                              const Divider(color: AppTokens.border),
                              const SizedBox(height: 16),
                              Row(
                                children: [
                                  Container(
                                    padding: const EdgeInsets.symmetric(
                                      horizontal: 12,
                                      vertical: 6,
                                    ),
                                    decoration: BoxDecoration(
                                      color: AppTokens.accent.withValues(
                                        alpha: 0.1,
                                      ),
                                      borderRadius: BorderRadius.circular(20),
                                    ),
                                    child: Row(
                                      mainAxisSize: MainAxisSize.min,
                                      children: [
                                        const Icon(
                                          Icons.auto_awesome,
                                          size: 14,
                                          color: AppTokens.accent,
                                        ),
                                        const SizedBox(width: 6),
                                        Text(
                                          'BROUILLON GÉNÉRÉ PAR L\'IA',
                                          style: GoogleFonts.inter(
                                            fontSize: 10,
                                            fontWeight: FontWeight.w700,
                                            letterSpacing: 1,
                                            color: AppTokens.accent,
                                          ),
                                        ),
                                      ],
                                    ),
                                  ),
                                ],
                              ),
                              const SizedBox(height: 16),
                              if (ds.loading)
                                const Center(child: CircularProgressIndicator())
                              else if (ds.error != null)
                                Text(
                                  'Erreur: ${ds.error}',
                                  style: const TextStyle(
                                    color: AppTokens.badgeOffline,
                                    fontSize: 12,
                                  ),
                                )
                              else if (ds.draft != null) ...[
                                Container(
                                  width: double.infinity,
                                  constraints: const BoxConstraints(
                                    minHeight: 160,
                                  ),
                                  padding: const EdgeInsets.all(16),
                                  decoration: BoxDecoration(
                                    color: AppTokens.cardBg,
                                    borderRadius: BorderRadius.circular(
                                      AppTokens.borderRadius,
                                    ),
                                    border: Border.all(color: AppTokens.border),
                                  ),
                                  child: Text(
                                    ds.draft!,
                                    style: GoogleFonts.inter(
                                      fontSize: 13,
                                      color: AppTokens.textPrimary,
                                      height: 1.6,
                                    ),
                                  ),
                                ),
                                const SizedBox(height: 16),
                                Row(
                                  children: [
                                    _ActionBtn(
                                      '✅ Approuver et envoyer',
                                      AppTokens.badgeNeo4j,
                                      ds.loading
                                          ? null
                                          : () => _approve(oppId, true),
                                    ),
                                    const SizedBox(width: 8),
                                    _ActionBtn(
                                      '❌ Rejeter l\'email',
                                      AppTokens.badgeOffline,
                                      ds.loading
                                          ? null
                                          : () => _approve(oppId, false),
                                    ),
                                  ],
                                ),
                              ],
                            ],
                          ],
                        ),
                      ),
                    ),
                  ),

                  // ── Right: context ────────────────────────────────────────────
                  Container(
                    width: 260,
                    decoration: const BoxDecoration(
                      color: AppTokens.cardBg,
                      border: Border(left: BorderSide(color: AppTokens.border)),
                    ),
                    child: SingleChildScrollView(
                      padding: const EdgeInsets.all(20),
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(
                            'CONTEXTE',
                            style: GoogleFonts.inter(
                              fontSize: 10,
                              fontWeight: FontWeight.w600,
                              letterSpacing: 1.2,
                              color: AppTokens.textMuted,
                            ),
                          ),
                          const SizedBox(height: 20),
                          _CtxRow(
                            'ID',
                            (opp['id'] ?? '—').toString().substring(0, 8),
                          ),
                          const SizedBox(height: 8),
                          _CtxRow('Statut', opp['statut'] ?? 'nouveau'),
                          const SizedBox(height: 8),
                          if (opp['date_limite'] != null)
                            _CtxRow('Date limite', opp['date_limite']),
                          const SizedBox(height: 8),
                          if (opp['score_pertinence'] != null)
                            _CtxRow(
                              'Score',
                              '${((double.tryParse(opp['score_pertinence'].toString()) ?? 0.0) * 100).toInt()}%',
                            ),
                          const SizedBox(height: 20),
                          Text(
                            'Points à vérifier',
                            style: GoogleFonts.inter(
                              fontSize: 12,
                              fontWeight: FontWeight.w500,
                              color: AppTokens.textSecondary,
                            ),
                          ),
                          const SizedBox(height: 12),
                          _ChecklistItem('Organisme acheteur identifié'),
                          _ChecklistItem('Secteur d\'activité pertinent'),
                          _ChecklistItem('Délai de soumission raisonnable'),
                          _ChecklistItem('Budget dans notre capacité'),
                          _ChecklistItem('Contact disponible'),
                        ],
                      ),
                    ),
                  ),
                ],
              );
            },
          ),
        ),
      ],
    );
  }
}

// ── State model ────────────────────────────────────────────────────────────────

class _DraftState {
  final bool loading;
  final String? threadId;
  final String? draft;
  final String? error;
  const _DraftState({
    this.loading = false,
    this.threadId,
    this.draft,
    this.error,
  });
  _DraftState copyWith({
    bool? loading,
    String? threadId,
    String? draft,
    String? error,
  }) => _DraftState(
    loading: loading ?? this.loading,
    threadId: threadId ?? this.threadId,
    draft: draft ?? this.draft,
    error: error ?? this.error,
  );
}

// ── Shared widgets ──────────────────────────────────────────────────────────────

class _QueueTile extends StatefulWidget {
  final Map<String, dynamic> opp;
  final bool isSelected;
  final VoidCallback onTap;
  const _QueueTile({
    required this.opp,
    required this.isSelected,
    required this.onTap,
  });
  @override
  State<_QueueTile> createState() => _QueueTileState();
}

class _QueueTileState extends State<_QueueTile> {
  bool _hovered = false;
  @override
  Widget build(BuildContext context) => MouseRegion(
    onEnter: (_) => setState(() => _hovered = true),
    onExit: (_) => setState(() => _hovered = false),
    cursor: SystemMouseCursors.click,
    child: GestureDetector(
      onTap: widget.onTap,
      child: AnimatedContainer(
        duration: const Duration(milliseconds: 150),
        margin: const EdgeInsets.only(bottom: 4),
        padding: const EdgeInsets.all(12),
        decoration: BoxDecoration(
          color: widget.isSelected
              ? AppTokens.accent.withValues(alpha: 0.08)
              : _hovered
              ? AppTokens.contentBg
              : Colors.transparent,
          borderRadius: BorderRadius.circular(AppTokens.borderRadius),
          border: widget.isSelected
              ? Border.all(color: AppTokens.accent.withValues(alpha: 0.3))
              : null,
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              (widget.opp['id'] ?? '').toString().substring(0, 8),
              style: GoogleFonts.jetBrainsMono(
                fontSize: 9,
                color: widget.isSelected
                    ? AppTokens.accent
                    : AppTokens.textMuted,
              ),
            ),
            const SizedBox(height: 4),
            Text(
              widget.opp['titre'] ?? '—',
              maxLines: 2,
              overflow: TextOverflow.ellipsis,
              style: GoogleFonts.inter(
                fontSize: 12,
                fontWeight: FontWeight.w500,
                color: AppTokens.textPrimary,
              ),
            ),
            const SizedBox(height: 2),
            Text(
              widget.opp['organisation'] ?? '—',
              style: GoogleFonts.inter(
                fontSize: 10,
                color: AppTokens.textMuted,
              ),
            ),
          ],
        ),
      ),
    ),
  );
}

class _ActionBtn extends StatelessWidget {
  final String label;
  final Color color;
  final VoidCallback? onTap;
  const _ActionBtn(this.label, this.color, this.onTap);
  @override
  Widget build(BuildContext context) => TextButton(
    onPressed: onTap,
    style: TextButton.styleFrom(
      foregroundColor: color,
      backgroundColor: color.withValues(alpha: onTap == null ? 0.04 : 0.08),
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(8)),
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
    ),
    child: Text(
      label,
      style: GoogleFonts.inter(
        fontSize: 12,
        fontWeight: FontWeight.w600,
        color: onTap == null ? color.withValues(alpha: 0.4) : color,
      ),
    ),
  );
}

class _CtxRow extends StatelessWidget {
  final String label, value;
  const _CtxRow(this.label, this.value);
  @override
  Widget build(BuildContext context) => Row(
    crossAxisAlignment: CrossAxisAlignment.start,
    children: [
      SizedBox(
        width: 80,
        child: Text(
          label,
          style: GoogleFonts.inter(fontSize: 11, color: AppTokens.textMuted),
        ),
      ),
      Expanded(
        child: Text(
          value,
          style: GoogleFonts.inter(
            fontSize: 11,
            fontWeight: FontWeight.w500,
            color: AppTokens.textPrimary,
          ),
        ),
      ),
    ],
  );
}

class _ChecklistItem extends StatefulWidget {
  final String text;
  const _ChecklistItem(this.text);
  @override
  State<_ChecklistItem> createState() => _ChecklistItemState();
}

class _ChecklistItemState extends State<_ChecklistItem> {
  bool _checked = false;
  @override
  Widget build(BuildContext context) => Padding(
    padding: const EdgeInsets.only(bottom: 8),
    child: GestureDetector(
      onTap: () => setState(() => _checked = !_checked),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Container(
            width: 16,
            height: 16,
            margin: const EdgeInsets.only(top: 1),
            decoration: BoxDecoration(
              color: _checked ? AppTokens.accent : Colors.transparent,
              borderRadius: BorderRadius.circular(3),
              border: Border.all(
                color: _checked ? AppTokens.accent : AppTokens.border,
                width: 1.5,
              ),
            ),
            child: _checked
                ? const Icon(Icons.check, size: 12, color: Colors.white)
                : null,
          ),
          const SizedBox(width: 10),
          Expanded(
            child: Text(
              widget.text,
              style: GoogleFonts.inter(
                fontSize: 12,
                color: AppTokens.textPrimary,
                decoration: _checked ? TextDecoration.lineThrough : null,
              ),
            ),
          ),
        ],
      ),
    ),
  );
}
