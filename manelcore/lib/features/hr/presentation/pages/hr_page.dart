import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:google_fonts/google_fonts.dart';
import '../../../../core/api_client.dart';
import '../../../../core/theme.dart';
import '../../../../widgets/header_bar.dart';

class HrPage extends ConsumerStatefulWidget {
  const HrPage({super.key});

  @override
  ConsumerState<HrPage> createState() => _HrPageState();
}

class _HrPageState extends ConsumerState<HrPage> {
  static const _statuts = ['nouveau', 'screening', 'entretien', 'offre', 'embauché', 'rejeté'];

  Color _statutColor(String s) => switch (s) {
    'embauché'  => AppTokens.badgeNeo4j,
    'rejeté'    => AppTokens.badgeOffline,
    'offre'     => const Color(0xFF8B5CF6),
    'entretien' => AppTokens.accent,
    'screening' => const Color(0xFFF59E0B),
    _           => AppTokens.textMuted,
  };

  void _refresh() => ref.invalidate(candidatsProvider);

  void _showAddDialog() => showDialog(
    context: context,
    builder: (_) => _CandidatFormDialog(ref: ref, onSaved: _refresh),
  );

  void _showEditDialog(Map<String, dynamic> c) => showDialog(
    context: context,
    builder: (_) => _CandidatFormDialog(ref: ref, initial: c, onSaved: _refresh),
  );

  Future<void> _updateStatus(String id, String statut) async {
    await ref.read(apiClientProvider).updateCandidatStatus(id, statut);
    _refresh();
  }

  Future<void> _delete(String id) async {
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (_) => AlertDialog(
        title: Text('Supprimer ce candidat ?', style: GoogleFonts.inter(fontSize: 15, fontWeight: FontWeight.w600)),
        content: Text('Cette action est irréversible.', style: GoogleFonts.inter(fontSize: 13)),
        actions: [
          TextButton(onPressed: () => Navigator.pop(context, false), child: const Text('Annuler')),
          ElevatedButton(
            onPressed: () => Navigator.pop(context, true),
            style: ElevatedButton.styleFrom(backgroundColor: AppTokens.badgeOffline, foregroundColor: Colors.white),
            child: const Text('Supprimer'),
          ),
        ],
      ),
    ) ?? false;
    if (!confirmed) return;
    await ref.read(apiClientProvider).deleteCandidat(id);
    _refresh();
  }

  @override
  Widget build(BuildContext context) {
    final candidatsAsync = ref.watch(candidatsProvider);

    return Column(children: [
      AppHeaderBar(
        title: 'Module RH',
        subtitle: 'Gestion des candidatures',
        actions: [
          ElevatedButton.icon(
            onPressed: _showAddDialog,
            icon: const Icon(Icons.person_add, size: 16),
            label: const Text('Nouveau candidat'),
            style: ElevatedButton.styleFrom(
              backgroundColor: const Color(0xFF8B5CF6), foregroundColor: Colors.white,
              shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(8)),
              padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 10),
            ),
          ),
        ],
      ),
      Expanded(
        child: candidatsAsync.when(
          loading: () => const Center(child: CircularProgressIndicator()),
          error: (e, _) => Center(child: Text('Erreur: $e')),
          data: (candidats) {
            if (candidats.isEmpty) {
              return Center(child: Column(mainAxisSize: MainAxisSize.min, children: [
                const Icon(Icons.people_outline, size: 48, color: AppTokens.textMuted),
                const SizedBox(height: 12),
                Text('Aucune candidature', style: GoogleFonts.inter(color: AppTokens.textMuted)),
                const SizedBox(height: 8),
                TextButton(onPressed: _showAddDialog, child: const Text('Ajouter un candidat')),
              ]));
            }

            // Group by statut
            final grouped = <String, List<Map<String, dynamic>>>{};
            for (final s in _statuts) { grouped[s] = []; }
            for (final c in candidats) {
              final s = (c['statut'] ?? 'nouveau').toString();
              (grouped[s] ??= []).add(c as Map<String, dynamic>);
            }

            return SingleChildScrollView(
              scrollDirection: Axis.horizontal,
              padding: const EdgeInsets.all(20),
              child: Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: _statuts.map((statut) => _KanbanColumn(
                  statut: statut,
                  color: _statutColor(statut),
                  candidats: grouped[statut] ?? [],
                  allStatuts: _statuts,
                  onStatusChange: (id, s) => _updateStatus(id, s),
                  onEdit: _showEditDialog,
                  onDelete: _delete,
                )).toList(),
              ),
            );
          },
        ),
      ),
    ]);
  }
}

// ── Kanban column ──────────────────────────────────────────────────────────────

class _KanbanColumn extends StatelessWidget {
  final String statut;
  final Color color;
  final List<Map<String, dynamic>> candidats;
  final void Function(String id, String statut) onStatusChange;
  final void Function(Map<String, dynamic>) onEdit;
  final void Function(String id) onDelete;
  final List<String> allStatuts;

  const _KanbanColumn({
    required this.statut, required this.color, required this.candidats,
    required this.onStatusChange, required this.onEdit, required this.onDelete,
    required this.allStatuts,
  });

  @override
  Widget build(BuildContext context) => Container(
    width: 220,
    margin: const EdgeInsets.only(right: 14),
    child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      Container(
        padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 8),
        decoration: BoxDecoration(
          color: color.withValues(alpha: 0.08),
          borderRadius: BorderRadius.circular(8),
          border: Border.all(color: color.withValues(alpha: 0.3)),
        ),
        child: Row(children: [
          Container(width: 8, height: 8, decoration: BoxDecoration(color: color, shape: BoxShape.circle)),
          const SizedBox(width: 8),
          Text(statut.toUpperCase(),
              style: GoogleFonts.inter(fontSize: 10, fontWeight: FontWeight.w700, color: color, letterSpacing: 0.8)),
          const Spacer(),
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
            decoration: BoxDecoration(color: color.withValues(alpha: 0.15), borderRadius: BorderRadius.circular(8)),
            child: Text('${candidats.length}',
                style: GoogleFonts.inter(fontSize: 11, fontWeight: FontWeight.w600, color: color)),
          ),
        ]),
      ),
      const SizedBox(height: 8),
      ...candidats.map((c) => _CandidatCard(
        candidat: c, color: color, allStatuts: allStatuts,
        onStatusChange: onStatusChange, onEdit: onEdit, onDelete: onDelete,
      )),
    ]),
  );
}

// ── Candidat card ──────────────────────────────────────────────────────────────

class _CandidatCard extends StatelessWidget {
  final Map<String, dynamic> candidat;
  final Color color;
  final List<String> allStatuts;
  final void Function(String id, String statut) onStatusChange;
  final void Function(Map<String, dynamic>) onEdit;
  final void Function(String id) onDelete;

  const _CandidatCard({
    required this.candidat, required this.color, required this.allStatuts,
    required this.onStatusChange, required this.onEdit, required this.onDelete,
  });

  @override
  Widget build(BuildContext context) {
    final id = candidat['id'] ?? '';
    return Container(
      margin: const EdgeInsets.only(bottom: 8),
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: AppTokens.cardBg,
        borderRadius: BorderRadius.circular(AppTokens.borderRadius),
        border: Border.all(color: AppTokens.border),
      ),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Row(children: [
          Expanded(child: Text(candidat['nom'] ?? '—',
              style: GoogleFonts.inter(fontSize: 13, fontWeight: FontWeight.w600, color: AppTokens.textPrimary))),
          // Edit
          GestureDetector(
            onTap: () => onEdit(candidat),
            child: const Icon(Icons.edit_outlined, size: 14, color: AppTokens.textMuted),
          ),
          const SizedBox(width: 8),
          // Delete
          GestureDetector(
            onTap: () => onDelete(id),
            child: const Icon(Icons.delete_outline, size: 14, color: AppTokens.badgeOffline),
          ),
        ]),
        if (candidat['poste'] != null)
          Text(candidat['poste'], style: GoogleFonts.inter(fontSize: 11, color: AppTokens.textMuted)),
        if (candidat['email'] != null)
          Text(candidat['email'], style: GoogleFonts.inter(fontSize: 11, color: AppTokens.textSecondary)),
        const SizedBox(height: 8),
        PopupMenuButton<String>(
          onSelected: (s) => onStatusChange(id, s),
          itemBuilder: (_) => allStatuts
              .map((s) => PopupMenuItem(value: s, child: Text(s, style: GoogleFonts.inter(fontSize: 12))))
              .toList(),
          child: Container(
            padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
            decoration: BoxDecoration(border: Border.all(color: AppTokens.border), borderRadius: BorderRadius.circular(6)),
            child: Row(mainAxisSize: MainAxisSize.min, children: [
              Text('Déplacer', style: GoogleFonts.inter(fontSize: 11, color: AppTokens.textMuted)),
              const Icon(Icons.arrow_drop_down, size: 14, color: AppTokens.textMuted),
            ]),
          ),
        ),
      ]),
    );
  }
}

// ── Candidat form dialog (create + edit) ──────────────────────────────────────

class _CandidatFormDialog extends StatefulWidget {
  final WidgetRef ref;
  final Map<String, dynamic>? initial;
  final VoidCallback onSaved;
  const _CandidatFormDialog({required this.ref, this.initial, required this.onSaved});

  @override
  State<_CandidatFormDialog> createState() => _CandidatFormDialogState();
}

class _CandidatFormDialogState extends State<_CandidatFormDialog> {
  final _nom      = TextEditingController();
  final _email    = TextEditingController();
  final _poste    = TextEditingController();
  final _source   = TextEditingController();
  final _cvResume = TextEditingController();
  String _statut  = 'nouveau';
  bool _loading   = false;

  static const _statuts = ['nouveau', 'screening', 'entretien', 'offre', 'embauché', 'rejeté'];

  @override
  void initState() {
    super.initState();
    final d = widget.initial;
    if (d != null) {
      _nom.text      = d['nom'] ?? '';
      _email.text    = d['email'] ?? '';
      _poste.text    = d['poste'] ?? '';
      _source.text   = d['source'] ?? '';
      _cvResume.text = d['cv_resume'] ?? '';
      _statut        = _statuts.contains(d['statut']) ? d['statut'] : 'nouveau';
    }
  }

  Future<void> _save() async {
    if (_nom.text.trim().isEmpty) return;
    setState(() => _loading = true);
    try {
      final data = {
        'nom':      _nom.text.trim(),
        'email':    _email.text.trim(),
        'poste':    _poste.text.trim(),
        'source':   _source.text.trim(),
        'cv_resume':_cvResume.text.trim(),
        'statut':   _statut,
      };
      final id = widget.initial?['id'];
      if (id != null) {
        await widget.ref.read(apiClientProvider).updateCandidat(id, data);
      } else {
        await widget.ref.read(apiClientProvider).createCandidat(data);
      }
      widget.onSaved();
      if (mounted) Navigator.pop(context);
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  Widget _field(TextEditingController c, String label, {int maxLines = 1}) => Padding(
    padding: const EdgeInsets.only(bottom: 12),
    child: TextField(
      controller: c, maxLines: maxLines,
      style: GoogleFonts.inter(fontSize: 13),
      decoration: InputDecoration(labelText: label, isDense: true),
    ),
  );

  @override
  Widget build(BuildContext context) => AlertDialog(
    title: Text(widget.initial == null ? 'Nouveau candidat' : 'Modifier le candidat',
        style: GoogleFonts.inter(fontSize: 15, fontWeight: FontWeight.w600)),
    content: SizedBox(width: 420, child: Column(mainAxisSize: MainAxisSize.min, children: [
      _field(_nom,    'Nom complet *'),
      _field(_email,  'Email'),
      _field(_poste,  'Poste visé'),
      _field(_source, 'Source (LinkedIn, Indeed…)'),
      DropdownButtonFormField<String>(
        initialValue: _statut,
        onChanged: (v) => setState(() => _statut = v!),
        decoration: const InputDecoration(labelText: 'Statut', isDense: true),
        style: GoogleFonts.inter(fontSize: 13, color: AppTokens.textPrimary),
        items: _statuts.map((v) => DropdownMenuItem(value: v, child: Text(v))).toList(),
      ),
      const SizedBox(height: 12),
      _field(_cvResume, 'Résumé CV', maxLines: 3),
    ])),
    actions: [
      TextButton(onPressed: () => Navigator.pop(context), child: const Text('Annuler')),
      ElevatedButton(
        onPressed: _loading || _nom.text.trim().isEmpty ? null : _save,
        style: ElevatedButton.styleFrom(backgroundColor: const Color(0xFF8B5CF6), foregroundColor: Colors.white),
        child: _loading
          ? const SizedBox(width: 16, height: 16, child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white))
          : Text(widget.initial == null ? 'Ajouter' : 'Sauvegarder'),
      ),
    ],
  );
}
