import 'dart:async';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:google_fonts/google_fonts.dart';
import 'package:url_launcher/url_launcher.dart';
import '../../../../core/api_client.dart';
import '../../../../core/theme.dart';
import '../../../../widgets/header_bar.dart';

class OpportunitiesPage extends ConsumerStatefulWidget {
  const OpportunitiesPage({super.key});

  @override
  ConsumerState<OpportunitiesPage> createState() => _OpportunitiesPageState();
}

class _OpportunitiesPageState extends ConsumerState<OpportunitiesPage> {
  String? _filterStatut;
  String _search = '';
  Timer? _refreshTimer;

  @override
  void initState() {
    super.initState();
    _refreshTimer = Timer.periodic(const Duration(seconds: 10), (_) => _refresh());
  }

  @override
  void dispose() {
    _refreshTimer?.cancel();
    super.dispose();
  }

  static const _statuts = ['tous', 'nouveau', 'validé', 'rejeté', 'en_cours'];

  Color _statutColor(String? s) => switch (s) {
    'validé' => AppTokens.badgeNeo4j,
    'rejeté' => AppTokens.badgeOffline,
    'en_cours' => const Color(0xFFF59E0B),
    _ => AppTokens.accent,
  };

  void _refresh() => ref.invalidate(opportunitiesProvider);

  Future<void> _updateStatus(String id, String statut) async {
    await ref.read(apiClientProvider).updateOpportunityStatus(id, statut);
    _refresh();
  }

  Future<void> _delete(String id) async {
    final confirmed = await _confirmDialog('Supprimer cette opportunité ?');
    if (!confirmed) return;
    await ref.read(apiClientProvider).deleteOpportunity(id);
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

  Future<bool> _confirmDialog(String msg) async {
    return await showDialog<bool>(
          context: context,
          builder: (_) => AlertDialog(
            title: Text(
              'Confirmation',
              style: GoogleFonts.inter(
                fontSize: 15,
                fontWeight: FontWeight.w600,
              ),
            ),
            content: Text(msg, style: GoogleFonts.inter(fontSize: 13)),
            actions: [
              TextButton(
                onPressed: () => Navigator.pop(context, false),
                child: const Text('Annuler'),
              ),
              ElevatedButton(
                onPressed: () => Navigator.pop(context, true),
                style: ElevatedButton.styleFrom(
                  backgroundColor: AppTokens.badgeOffline,
                  foregroundColor: Colors.white,
                ),
                child: const Text('Supprimer'),
              ),
            ],
          ),
        ) ??
        false;
  }

  void _showCreateDialog() => showDialog(
    context: context,
    builder: (_) => _OppFormDialog(ref: ref, onSaved: _refresh),
  );

  void _showEditDialog(Map<String, dynamic> opp) => showDialog(
    context: context,
    builder: (_) => _OppFormDialog(ref: ref, initial: opp, onSaved: _refresh),
  );

  void _showDraftDialog(Map<String, dynamic> opp) => showDialog(
    context: context,
    builder: (_) => _DraftDialog(opportunity: opp, ref: ref),
  );

  @override
  Widget build(BuildContext context) {
    final statut = _filterStatut == 'tous' ? null : _filterStatut;
    final oppsAsync = ref.watch(opportunitiesProvider(statut));

    return Column(
      children: [
        AppHeaderBar(
          title: 'Opportunités',
          subtitle: 'Appels d\'offres et contrats',
          actions: [
            _FilterChips(
              statuts: _statuts,
              selected: _filterStatut ?? 'tous',
              onSelected: (s) =>
                  setState(() => _filterStatut = s == 'tous' ? null : s),
            ),
            const SizedBox(width: 8),
            ElevatedButton.icon(
              onPressed: _showCreateDialog,
              icon: const Icon(Icons.add, size: 16),
              label: const Text('Nouvelle'),
              style: ElevatedButton.styleFrom(
                backgroundColor: AppTokens.accent,
                foregroundColor: Colors.white,
                shape: RoundedRectangleBorder(
                  borderRadius: BorderRadius.circular(8),
                ),
                padding: const EdgeInsets.symmetric(
                  horizontal: 14,
                  vertical: 10,
                ),
              ),
            ),
            const SizedBox(width: 8),
            OutlinedButton.icon(
              onPressed: () async {
                final confirmed = await _confirmDialog(
                  'Voulez-vous vraiment supprimer TOUTES les opportunités ? Cette action est irréversible.',
                );
                if (!confirmed) return;
                await ref.read(apiClientProvider).deleteAllOpportunities();
                _refresh();
              },
              icon: const Icon(Icons.delete_sweep, size: 16),
              label: const Text('Supprimer tout'),
              style: OutlinedButton.styleFrom(
                foregroundColor: AppTokens.badgeOffline,
                side: const BorderSide(color: AppTokens.badgeOffline),
                shape: RoundedRectangleBorder(
                  borderRadius: BorderRadius.circular(8),
                ),
                padding: const EdgeInsets.symmetric(
                  horizontal: 14,
                  vertical: 10,
                ),
              ),
            ),
          ],
        ),
        Container(
          color: AppTokens.cardBg,
          padding: const EdgeInsets.fromLTRB(24, 0, 24, 12),
          child: TextField(
            onChanged: (v) => setState(() => _search = v.toLowerCase()),
            style: GoogleFonts.inter(fontSize: 13),
            decoration: const InputDecoration(
              hintText: 'Rechercher…',
              prefixIcon: Icon(
                Icons.search,
                size: 18,
                color: AppTokens.textMuted,
              ),
              isDense: true,
            ),
          ),
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
              final filtered = opps.where((o) {
                final titre = (o['titre'] ?? '').toString().toLowerCase();
                final org = (o['organisation'] ?? '').toString().toLowerCase();
                return titre.contains(_search) || org.contains(_search);
              }).toList();

              if (filtered.isEmpty) {
                return Center(
                  child: Column(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      const Icon(
                        Icons.work_off_outlined,
                        size: 48,
                        color: AppTokens.textMuted,
                      ),
                      const SizedBox(height: 12),
                      Text(
                        'Aucune opportunité',
                        style: GoogleFonts.inter(color: AppTokens.textMuted),
                      ),
                      const SizedBox(height: 8),
                      TextButton(
                        onPressed: _showCreateDialog,
                        child: const Text('Créer manuellement'),
                      ),
                    ],
                  ),
                );
              }

              return ListView.builder(
                padding: const EdgeInsets.all(20),
                itemCount: filtered.length,
                itemBuilder: (ctx, i) {
                  final opp = filtered[i] as Map<String, dynamic>;
                  final score = opp['score_pertinence'];
                  final pct = score != null
                      ? '${((double.tryParse(score.toString()) ?? 0.0) * 100).toInt()}%'
                      : '—';
                  final statut = (opp['statut'] ?? 'nouveau') as String;
                  final url = (opp['url'] ?? '').toString().trim();

                  return Container(
                    margin: const EdgeInsets.only(bottom: 10),
                    decoration: BoxDecoration(
                      color: AppTokens.cardBg,
                      borderRadius: BorderRadius.circular(
                        AppTokens.borderRadiusLg,
                      ),
                      border: Border.all(color: AppTokens.border),
                    ),
                    child: ExpansionTile(
                      tilePadding: const EdgeInsets.fromLTRB(20, 4, 12, 4),
                      title: Text(
                        opp['titre'] ?? 'Sans titre',
                        style: GoogleFonts.inter(
                          fontSize: 13,
                          fontWeight: FontWeight.w600,
                          color: AppTokens.textPrimary,
                        ),
                      ),
                      subtitle: Text(
                        '${opp['organisation'] ?? ''} · ${opp['source'] ?? ''}',
                        style: GoogleFonts.inter(
                          fontSize: 11,
                          color: AppTokens.textMuted,
                        ),
                      ),
                      trailing: Row(
                        mainAxisSize: MainAxisSize.min,
                        children: [
                          Text(
                            pct,
                            style: GoogleFonts.inter(
                              fontSize: 13,
                              fontWeight: FontWeight.w700,
                              color: AppTokens.accent,
                            ),
                          ),
                          const SizedBox(width: 8),
                          _StatusChip(
                            statut: statut,
                            color: _statutColor(statut),
                          ),
                          const SizedBox(width: 4),
                          if (url.isNotEmpty)
                            IconButton(
                              icon: const Icon(Icons.open_in_new, size: 16),
                              color: AppTokens.accent,
                              tooltip: 'Ouvrir l\'appel d\'offres',
                              onPressed: () => _openOpportunityUrl(url),
                              constraints: const BoxConstraints(
                                maxWidth: 32,
                                maxHeight: 32,
                              ),
                              padding: EdgeInsets.zero,
                            ),
                          // Edit
                          IconButton(
                            icon: const Icon(Icons.edit_outlined, size: 16),
                            color: AppTokens.textMuted,
                            tooltip: 'Modifier',
                            onPressed: () => _showEditDialog(opp),
                            constraints: const BoxConstraints(
                              maxWidth: 32,
                              maxHeight: 32,
                            ),
                            padding: EdgeInsets.zero,
                          ),
                          // Delete
                          IconButton(
                            icon: const Icon(Icons.delete_outline, size: 16),
                            color: AppTokens.badgeOffline,
                            tooltip: 'Supprimer',
                            onPressed: () => _delete(opp['id'] ?? ''),
                            constraints: const BoxConstraints(
                              maxWidth: 32,
                              maxHeight: 32,
                            ),
                            padding: EdgeInsets.zero,
                          ),
                          const Icon(
                            Icons.expand_more,
                            color: AppTokens.textMuted,
                            size: 18,
                          ),
                        ],
                      ),
                      children: [
                        Padding(
                          padding: const EdgeInsets.fromLTRB(20, 0, 20, 16),
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              if (opp['resume'] != null) ...[
                                Text(
                                  opp['resume'],
                                  style: GoogleFonts.inter(
                                    fontSize: 12,
                                    color: AppTokens.textSecondary,
                                    height: 1.5,
                                  ),
                                ),
                                const SizedBox(height: 10),
                              ],
                              if (opp['date_limite'] != null)
                                Text(
                                  'Date limite: ${opp['date_limite']}',
                                  style: GoogleFonts.inter(
                                    fontSize: 11,
                                    color: AppTokens.textMuted,
                                  ),
                                ),
                              if (url.isNotEmpty)
                                TextButton.icon(
                                  onPressed: () => _openOpportunityUrl(url),
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
                              const SizedBox(height: 12),
                                if (opp['draft_email'] != null && (opp['draft_email'] as String).isNotEmpty) ...[
                                  Container(
                                    padding: const EdgeInsets.all(12),
                                    decoration: BoxDecoration(
                                      color: AppTokens.contentBg,
                                      borderRadius: BorderRadius.circular(8),
                                      border: Border.all(color: AppTokens.border),
                                    ),
                                    child: Column(
                                      crossAxisAlignment: CrossAxisAlignment.start,
                                      children: [
                                        Row(
                                          children: [
                                            const Icon(Icons.description_outlined, size: 14, color: AppTokens.accent),
                                            const SizedBox(width: 8),
                                            Text(
                                              'Brouillon généré par ARIA',
                                              style: GoogleFonts.inter(
                                                fontSize: 11,
                                                fontWeight: FontWeight.w600,
                                                color: AppTokens.accent,
                                              ),
                                            ),
                                          ],
                                        ),
                                        const SizedBox(height: 8),
                                        Text(
                                          opp['draft_email'],
                                          style: GoogleFonts.inter(
                                            fontSize: 12,
                                            color: AppTokens.textSecondary,
                                            height: 1.5,
                                          ),
                                        ),
                                      ],
                                    ),
                                  ),
                                  const SizedBox(height: 12),
                                ],
                                Wrap(
                                  spacing: 8,
                                  runSpacing: 6,
                                  children: [
                                    if (opp['draft_email'] != null && (opp['draft_email'] as String).isNotEmpty)
                                      _ActionBtn(
                                        '🚀 Envoyer Email',
                                        AppTokens.accent,
                                        () async {
                                          try {
                                            await ref.read(apiClientProvider).sendOpportunityDraft(opp['id']);
                                            _refresh();
                                          } catch (e) {
                                            if (!context.mounted) return;
                                            ScaffoldMessenger.of(context).showSnackBar(
                                              SnackBar(content: Text('Erreur: $e')),
                                            );
                                          }
                                        },
                                      ),
                                    _ActionBtn(
                                      '✅ Valider',
                                      AppTokens.badgeNeo4j,
                                      () => _updateStatus(opp['id'], 'validé'),
                                    ),
                                    _ActionBtn(
                                      '❌ Rejeter',
                                      AppTokens.badgeOffline,
                                      () => _updateStatus(opp['id'], 'rejeté'),
                                    ),
                                    _ActionBtn(
                                      '⏳ En cours',
                                      const Color(0xFFF59E0B),
                                      () => _updateStatus(opp['id'], 'en_cours'),
                                    ),
                                    _ActionBtn(
                                      '📬 Contacter',
                                      AppTokens.textSecondary,
                                      () => _showDraftDialog(opp),
                                    ),
                                  ],
                                ),
                            ],
                          ),
                        ),
                      ],
                    ),
                  );
                },
              );
            },
          ),
        ),
      ],
    );
  }
}

// ── Small widgets ──────────────────────────────────────────────────────────────

class _StatusChip extends StatelessWidget {
  final String statut;
  final Color color;
  const _StatusChip({required this.statut, required this.color});

  @override
  Widget build(BuildContext context) => Container(
    padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
    decoration: BoxDecoration(
      color: color.withValues(alpha: 0.1),
      borderRadius: BorderRadius.circular(12),
    ),
    child: Text(
      statut,
      style: GoogleFonts.inter(
        fontSize: 10,
        fontWeight: FontWeight.w600,
        color: color,
      ),
    ),
  );
}

class _FilterChips extends StatelessWidget {
  final List<String> statuts;
  final String selected;
  final ValueChanged<String> onSelected;
  const _FilterChips({
    required this.statuts,
    required this.selected,
    required this.onSelected,
  });

  @override
  Widget build(BuildContext context) => Row(
    mainAxisSize: MainAxisSize.min,
    children: statuts.map((s) {
      final active = s == selected;
      return Padding(
        padding: const EdgeInsets.only(left: 6),
        child: GestureDetector(
          onTap: () => onSelected(s),
          child: Container(
            padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 5),
            decoration: BoxDecoration(
              color: active
                  ? AppTokens.accent.withValues(alpha: 0.12)
                  : Colors.transparent,
              borderRadius: BorderRadius.circular(20),
              border: Border.all(
                color: active ? AppTokens.accent : AppTokens.border,
              ),
            ),
            child: Text(
              s,
              style: GoogleFonts.inter(
                fontSize: 11,
                fontWeight: FontWeight.w600,
                color: active ? AppTokens.accent : AppTokens.textMuted,
              ),
            ),
          ),
        ),
      );
    }).toList(),
  );
}

class _ActionBtn extends StatelessWidget {
  final String label;
  final Color color;
  final VoidCallback onTap;
  const _ActionBtn(this.label, this.color, this.onTap);

  @override
  Widget build(BuildContext context) => TextButton(
    onPressed: onTap,
    style: TextButton.styleFrom(
      foregroundColor: color,
      backgroundColor: color.withValues(alpha: 0.08),
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(8)),
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 7),
    ),
    child: Text(
      label,
      style: GoogleFonts.inter(fontSize: 12, fontWeight: FontWeight.w600),
    ),
  );
}

// ── Opportunity form dialog (create + edit) ────────────────────────────────────

class _OppFormDialog extends StatefulWidget {
  final WidgetRef ref;
  final Map<String, dynamic>? initial;
  final VoidCallback onSaved;
  const _OppFormDialog({
    required this.ref,
    this.initial,
    required this.onSaved,
  });

  @override
  State<_OppFormDialog> createState() => _OppFormDialogState();
}

class _OppFormDialogState extends State<_OppFormDialog> {
  final _titre = TextEditingController();
  final _org = TextEditingController();
  final _url = TextEditingController();
  final _resume = TextEditingController();
  final _dateLimite = TextEditingController();
  final _score = TextEditingController();
  String _source = 'Manuel';
  String _statut = 'nouveau';
  bool _loading = false;

  static const _sources = ['Manuel', 'SEAO', 'LinkedIn', 'Indeed', 'Autre'];
  static const _statuts = ['nouveau', 'validé', 'rejeté', 'en_cours'];

  @override
  void initState() {
    super.initState();
    final d = widget.initial;
    if (d != null) {
      _titre.text = d['titre'] ?? '';
      _org.text = d['organisation'] ?? '';
      _url.text = d['url'] ?? '';
      _resume.text = d['resume'] ?? '';
      _dateLimite.text = d['date_limite'] ?? '';
      _score.text = d['score_pertinence']?.toString() ?? '0.5';
      _source = _sources.contains(d['source']) ? d['source'] : 'Manuel';
      _statut = _statuts.contains(d['statut']) ? d['statut'] : 'nouveau';
    } else {
      _score.text = '0.5';
    }
  }

  Future<void> _save() async {
    if (_titre.text.trim().isEmpty) return;
    setState(() => _loading = true);
    try {
      final data = {
        'titre': _titre.text.trim(),
        'organisation': _org.text.trim(),
        'url': _url.text.trim(),
        'resume': _resume.text.trim(),
        'date_limite': _dateLimite.text.trim(),
        'source': _source,
        'statut': _statut,
        'score_pertinence': double.tryParse(_score.text) ?? 0.5,
      };
      final id = widget.initial?['id'];
      if (id != null) {
        await widget.ref.read(apiClientProvider).updateOpportunity(id, data);
      } else {
        await widget.ref.read(apiClientProvider).createOpportunity(data);
      }
      widget.onSaved();
      if (mounted) Navigator.pop(context);
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  Widget _field(TextEditingController c, String label, {int maxLines = 1}) =>
      Padding(
        padding: const EdgeInsets.only(bottom: 12),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              label,
              style: GoogleFonts.inter(
                fontSize: 11,
                fontWeight: FontWeight.w500,
                color: AppTokens.textMuted,
              ),
            ),
            const SizedBox(height: 4),
            TextField(
              controller: c,
              maxLines: maxLines,
              style: GoogleFonts.inter(fontSize: 13),
              decoration: const InputDecoration(isDense: true),
            ),
          ],
        ),
      );

  Widget _dropdown<T>(
    String label,
    T value,
    List<T> items,
    ValueChanged<T?> onChanged,
  ) => Padding(
    padding: const EdgeInsets.only(bottom: 12),
    child: Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          label,
          style: GoogleFonts.inter(
            fontSize: 11,
            fontWeight: FontWeight.w500,
            color: AppTokens.textMuted,
          ),
        ),
        const SizedBox(height: 4),
        DropdownButtonFormField<T>(
          initialValue: value,
          onChanged: onChanged,
          style: GoogleFonts.inter(fontSize: 13, color: AppTokens.textPrimary),
          decoration: const InputDecoration(
            isDense: true,
            contentPadding: EdgeInsets.symmetric(horizontal: 12, vertical: 10),
          ),
          items: items
              .map((v) => DropdownMenuItem(value: v, child: Text(v.toString())))
              .toList(),
        ),
      ],
    ),
  );

  @override
  Widget build(BuildContext context) => AlertDialog(
    title: Text(
      widget.initial == null
          ? 'Nouvelle opportunité'
          : 'Modifier l\'opportunité',
      style: GoogleFonts.inter(fontSize: 15, fontWeight: FontWeight.w600),
    ),
    content: SizedBox(
      width: 540,
      child: SingleChildScrollView(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            _field(_titre, 'Titre *'),
            _field(_org, 'Organisation'),
            Row(
              children: [
                Expanded(
                  child: _dropdown(
                    'Source',
                    _source,
                    _sources,
                    (v) => setState(() => _source = v!),
                  ),
                ),
                const SizedBox(width: 12),
                Expanded(
                  child: _dropdown(
                    'Statut',
                    _statut,
                    _statuts,
                    (v) => setState(() => _statut = v!),
                  ),
                ),
              ],
            ),
            _field(_url, 'URL'),
            _field(_dateLimite, 'Date limite (AAAA-MM-JJ)'),
            _field(_score, 'Score de pertinence (0.0 – 1.0)'),
            _field(_resume, 'Résumé', maxLines: 3),
          ],
        ),
      ),
    ),
    actions: [
      TextButton(
        onPressed: () => Navigator.pop(context),
        child: const Text('Annuler'),
      ),
      ElevatedButton(
        onPressed: _loading || _titre.text.trim().isEmpty ? null : _save,
        style: ElevatedButton.styleFrom(
          backgroundColor: AppTokens.accent,
          foregroundColor: Colors.white,
        ),
        child: _loading
            ? const SizedBox(
                width: 16,
                height: 16,
                child: CircularProgressIndicator(
                  strokeWidth: 2,
                  color: Colors.white,
                ),
              )
            : Text(widget.initial == null ? 'Créer' : 'Sauvegarder'),
      ),
    ],
  );
}

// ── Contact draft dialog ────────────────────────────────────────────────────────

class _DraftDialog extends StatefulWidget {
  final Map<String, dynamic> opportunity;
  final WidgetRef ref;
  const _DraftDialog({required this.opportunity, required this.ref});

  @override
  State<_DraftDialog> createState() => _DraftDialogState();
}

class _DraftDialogState extends State<_DraftDialog> {
  final _emailCtrl = TextEditingController();
  final _nomCtrl = TextEditingController();
  bool _loading = false;
  String? _draft;
  String? _threadId;
  String? _error;

  Future<void> _generate() async {
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final result = await widget.ref
          .read(apiClientProvider)
          .draftContact(widget.opportunity['id'] ?? '', {
            'email': _emailCtrl.text.trim(),
            'nom': _nomCtrl.text.trim(),
            'organisation': widget.opportunity['organisation'] ?? '',
          });
      setState(() {
        _draft = result['draft_email'];
        _threadId = result['thread_id'];
      });
    } catch (e) {
      setState(() => _error = e.toString());
    } finally {
      setState(() => _loading = false);
    }
  }

  Future<void> _send(bool approved) async {
    if (_threadId == null) return;
    setState(() => _loading = true);
    await widget.ref
        .read(apiClientProvider)
        .approveContact(_threadId!, approved);
    if (mounted) Navigator.pop(context);
  }

  @override
  Widget build(BuildContext context) => AlertDialog(
    title: Text(
      'Contacter — ${(widget.opportunity['titre'] ?? '').toString().substring(0, (widget.opportunity['titre'] ?? '').toString().length.clamp(0, 50))}…',
      style: GoogleFonts.inter(fontSize: 13, fontWeight: FontWeight.w600),
    ),
    content: SizedBox(
      width: 500,
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          if (_draft == null) ...[
            TextField(
              controller: _nomCtrl,
              decoration: const InputDecoration(labelText: 'Nom du contact'),
              style: GoogleFonts.inter(fontSize: 13),
            ),
            const SizedBox(height: 10),
            TextField(
              controller: _emailCtrl,
              decoration: const InputDecoration(labelText: 'Email du contact'),
              style: GoogleFonts.inter(fontSize: 13),
            ),
          ] else
            Container(
              padding: const EdgeInsets.all(14),
              decoration: BoxDecoration(
                color: AppTokens.contentBg,
                borderRadius: BorderRadius.circular(8),
                border: Border.all(color: AppTokens.border),
              ),
              child: Text(
                _draft!,
                style: GoogleFonts.inter(fontSize: 12, height: 1.6),
              ),
            ),
          if (_error != null)
            Padding(
              padding: const EdgeInsets.only(top: 8),
              child: Text(
                _error!,
                style: const TextStyle(
                  color: AppTokens.badgeOffline,
                  fontSize: 12,
                ),
              ),
            ),
          if (_loading)
            const Padding(
              padding: EdgeInsets.only(top: 12),
              child: CircularProgressIndicator(),
            ),
        ],
      ),
    ),
    actions: _draft == null
        ? [
            TextButton(
              onPressed: () => Navigator.pop(context),
              child: const Text('Annuler'),
            ),
            ElevatedButton(
              onPressed: _loading ? null : _generate,
              child: const Text('Générer le brouillon'),
            ),
          ]
        : [
            TextButton(
              onPressed: () => Navigator.pop(context),
              child: const Text('Annuler'),
            ),
            TextButton(
              onPressed: _loading ? null : () => _send(false),
              child: const Text('Rejeter'),
            ),
            ElevatedButton(
              onPressed: _loading ? null : () => _send(true),
              child: const Text('Envoyer'),
            ),
          ],
  );
}
