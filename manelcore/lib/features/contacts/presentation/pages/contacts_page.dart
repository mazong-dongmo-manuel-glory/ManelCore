import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:google_fonts/google_fonts.dart';
import '../../../../core/api_client.dart';
import '../../../../core/theme.dart';
import '../../../../widgets/header_bar.dart';

class ContactsPage extends ConsumerStatefulWidget {
  const ContactsPage({super.key});

  @override
  ConsumerState<ContactsPage> createState() => _ContactsPageState();
}

class _ContactsPageState extends ConsumerState<ContactsPage> {
  String _search = '';

  void _refresh() => ref.invalidate(contactsProvider);

  void _showAddDialog() => showDialog(
    context: context,
    builder: (_) => _ContactFormDialog(ref: ref, onSaved: _refresh),
  );

  void _showEditDialog(Map<String, dynamic> contact) => showDialog(
    context: context,
    builder: (_) => _ContactFormDialog(ref: ref, initial: contact, onSaved: _refresh),
  );

  Future<void> _delete(String id) async {
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (_) => AlertDialog(
        title: Text('Supprimer le contact ?', style: GoogleFonts.inter(fontSize: 15, fontWeight: FontWeight.w600)),
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
    await ref.read(apiClientProvider).deleteContact(id);
    _refresh();
  }

  @override
  Widget build(BuildContext context) {
    final contactsAsync = ref.watch(contactsProvider);

    return Column(children: [
      AppHeaderBar(
        title: 'Contacts CRM',
        subtitle: 'Gestion des contacts et relations',
        actions: [
          ElevatedButton.icon(
            onPressed: _showAddDialog,
            icon: const Icon(Icons.add, size: 16),
            label: const Text('Nouveau contact'),
            style: ElevatedButton.styleFrom(
              backgroundColor: AppTokens.accent, foregroundColor: Colors.white,
              shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(8)),
              padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 10),
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
            hintText: 'Rechercher un contact…',
            prefixIcon: Icon(Icons.search, size: 18, color: AppTokens.textMuted),
            isDense: true,
          ),
        ),
      ),
      Expanded(
        child: contactsAsync.when(
          loading: () => const Center(child: CircularProgressIndicator()),
          error: (e, _) => Center(child: Text('Erreur: $e')),
          data: (contacts) {
            final filtered = contacts.where((c) {
              final nom   = (c['nom'] ?? '').toString().toLowerCase();
              final email = (c['email'] ?? '').toString().toLowerCase();
              final org   = (c['organisation'] ?? '').toString().toLowerCase();
              return nom.contains(_search) || email.contains(_search) || org.contains(_search);
            }).toList();

            if (filtered.isEmpty) {
              return Center(child: Column(mainAxisSize: MainAxisSize.min, children: [
                const Icon(Icons.people_outline, size: 48, color: AppTokens.textMuted),
                const SizedBox(height: 12),
                Text('Aucun contact', style: GoogleFonts.inter(color: AppTokens.textMuted)),
                const SizedBox(height: 8),
                TextButton(onPressed: _showAddDialog, child: const Text('Ajouter un contact')),
              ]));
            }

            return ListView.builder(
              padding: const EdgeInsets.all(20),
              itemCount: filtered.length,
              itemBuilder: (ctx, i) {
                final c = filtered[i] as Map<String, dynamic>;
                final initials = (c['nom'] ?? '?').toString()
                    .split(' ').map((w) => w.isNotEmpty ? w[0] : '').take(2).join().toUpperCase();
                final importance = c['niveau_importance'] as String?;
                return Container(
                  margin: const EdgeInsets.only(bottom: 8),
                  padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 14),
                  decoration: BoxDecoration(
                    color: AppTokens.cardBg,
                    borderRadius: BorderRadius.circular(AppTokens.borderRadius),
                    border: Border.all(color: AppTokens.border),
                  ),
                  child: Row(children: [
                    CircleAvatar(
                      radius: 20,
                      backgroundColor: AppTokens.accent.withValues(alpha: 0.1),
                      child: Text(initials, style: GoogleFonts.inter(fontSize: 13, fontWeight: FontWeight.w600, color: AppTokens.accent)),
                    ),
                    const SizedBox(width: 16),
                    Expanded(child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                      Row(children: [
                        Text(c['nom'] ?? '—',
                            style: GoogleFonts.inter(fontSize: 13, fontWeight: FontWeight.w600, color: AppTokens.textPrimary)),
                        if (importance == 'haute') ...[
                          const SizedBox(width: 8),
                          Container(
                            padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
                            decoration: BoxDecoration(
                              color: const Color(0xFFF59E0B).withValues(alpha: 0.1),
                              borderRadius: BorderRadius.circular(8),
                            ),
                            child: Text('⭐ Prioritaire',
                                style: GoogleFonts.inter(fontSize: 10, fontWeight: FontWeight.w600, color: Color(0xFFF59E0B))),
                          ),
                        ],
                      ]),
                      Text(
                        [c['poste'], c['organisation']].where((v) => v != null && v.toString().isNotEmpty).join(' · '),
                        style: GoogleFonts.inter(fontSize: 11, color: AppTokens.textMuted),
                      ),
                    ])),
                    if (c['email'] != null)
                      Text(c['email'], style: GoogleFonts.inter(fontSize: 12, color: AppTokens.textSecondary)),
                    const SizedBox(width: 8),
                    IconButton(
                      icon: const Icon(Icons.edit_outlined, size: 16),
                      color: AppTokens.textMuted,
                      tooltip: 'Modifier',
                      onPressed: () => _showEditDialog(c),
                    ),
                    IconButton(
                      icon: const Icon(Icons.delete_outline, size: 16),
                      color: AppTokens.badgeOffline,
                      tooltip: 'Supprimer',
                      onPressed: () => _delete(c['id'] ?? ''),
                    ),
                  ]),
                );
              },
            );
          },
        ),
      ),
    ]);
  }
}

// ── Contact form dialog (create + edit) ────────────────────────────────────────

class _ContactFormDialog extends StatefulWidget {
  final WidgetRef ref;
  final Map<String, dynamic>? initial;
  final VoidCallback onSaved;
  const _ContactFormDialog({required this.ref, this.initial, required this.onSaved});

  @override
  State<_ContactFormDialog> createState() => _ContactFormDialogState();
}

class _ContactFormDialogState extends State<_ContactFormDialog> {
  final _nom   = TextEditingController();
  final _email = TextEditingController();
  final _tel   = TextEditingController();
  final _poste = TextEditingController();
  final _org   = TextEditingController();
  String _importance = 'normal';
  bool _loading = false;

  static const _importances = ['normal', 'haute', 'basse'];

  @override
  void initState() {
    super.initState();
    final d = widget.initial;
    if (d != null) {
      _nom.text   = d['nom'] ?? '';
      _email.text = d['email'] ?? '';
      _tel.text   = d['telephone'] ?? '';
      _poste.text = d['poste'] ?? '';
      _org.text   = d['organisation'] ?? '';
      _importance = _importances.contains(d['niveau_importance']) ? d['niveau_importance'] : 'normal';
    }
  }

  Future<void> _save() async {
    if (_nom.text.trim().isEmpty) return;
    setState(() => _loading = true);
    try {
      final data = {
        'nom':              _nom.text.trim(),
        'email':            _email.text.trim(),
        'telephone':        _tel.text.trim(),
        'poste':            _poste.text.trim(),
        'organisation':     _org.text.trim(),
        'niveau_importance': _importance,
      };
      final id = widget.initial?['id'];
      if (id != null) {
        await widget.ref.read(apiClientProvider).updateContact(id, data);
      } else {
        await widget.ref.read(apiClientProvider).createContact(data);
      }
      widget.onSaved();
      if (mounted) Navigator.pop(context);
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  Widget _field(TextEditingController c, String label) => Padding(
    padding: const EdgeInsets.only(bottom: 12),
    child: TextField(
      controller: c,
      style: GoogleFonts.inter(fontSize: 13),
      decoration: InputDecoration(labelText: label, isDense: true),
    ),
  );

  @override
  Widget build(BuildContext context) => AlertDialog(
    title: Text(widget.initial == null ? 'Nouveau contact' : 'Modifier le contact',
        style: GoogleFonts.inter(fontSize: 15, fontWeight: FontWeight.w600)),
    content: SizedBox(width: 420, child: Column(mainAxisSize: MainAxisSize.min, children: [
      _field(_nom,   'Nom complet *'),
      _field(_email, 'Email'),
      _field(_tel,   'Téléphone'),
      _field(_poste, 'Poste'),
      _field(_org,   'Organisation'),
      DropdownButtonFormField<String>(
        initialValue: _importance,
        onChanged: (v) => setState(() => _importance = v!),
        decoration: const InputDecoration(labelText: 'Niveau d\'importance', isDense: true),
        style: GoogleFonts.inter(fontSize: 13, color: AppTokens.textPrimary),
        items: _importances.map((v) => DropdownMenuItem(value: v, child: Text(v))).toList(),
      ),
    ])),
    actions: [
      TextButton(onPressed: () => Navigator.pop(context), child: const Text('Annuler')),
      ElevatedButton(
        onPressed: _loading || _nom.text.trim().isEmpty ? null : _save,
        style: ElevatedButton.styleFrom(backgroundColor: AppTokens.accent, foregroundColor: Colors.white),
        child: _loading
          ? const SizedBox(width: 16, height: 16, child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white))
          : Text(widget.initial == null ? 'Créer' : 'Sauvegarder'),
      ),
    ],
  );
}
