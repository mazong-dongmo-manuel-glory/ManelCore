import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:google_fonts/google_fonts.dart';
import '../../../../core/api_client.dart';
import '../../../../core/theme.dart';
import '../../../../widgets/header_bar.dart';

// ── Providers ──────────────────────────────────────────────────────────────────

final inboxSummaryProvider = FutureProvider<Map<String, dynamic>>((ref) async {
  return ref.read(apiClientProvider).getInboxSummary();
});

final emailMessagesProvider = FutureProvider<List<dynamic>>((ref) async {
  return ref.read(apiClientProvider).getEmailMessages();
});

// ── Page ───────────────────────────────────────────────────────────────────────

class MailboxPage extends ConsumerStatefulWidget {
  const MailboxPage({super.key});

  @override
  ConsumerState<MailboxPage> createState() => _MailboxPageState();
}

class _MailboxPageState extends ConsumerState<MailboxPage> {
  int _tab = 0; // 0 = boîte de réception, 1 = composer

  // Composer state
  final _toCtrl      = TextEditingController();
  final _subjectCtrl = TextEditingController();
  final _bodyCtrl    = TextEditingController();
  bool _sending      = false;
  String? _sendResult;

  void _refresh() {
    ref.invalidate(inboxSummaryProvider);
    ref.invalidate(emailMessagesProvider);
  }

  Future<void> _triggerCheck() async {
    await ref.read(apiClientProvider).checkInbox();
    Future.delayed(const Duration(seconds: 3), _refresh);
  }

  Future<void> _send() async {
    final to      = _toCtrl.text.trim();
    final subject = _subjectCtrl.text.trim();
    final body    = _bodyCtrl.text.trim();
    if (to.isEmpty || subject.isEmpty || body.isEmpty) return;

    setState(() { _sending = true; _sendResult = null; });
    try {
      await ref.read(apiClientProvider).sendEmail(to, subject, body);
      _toCtrl.clear(); _subjectCtrl.clear(); _bodyCtrl.clear();
      setState(() { _sendResult = '✅ Email envoyé à $to'; });
      _refresh();
    } catch (e) {
      setState(() { _sendResult = '❌ Erreur: $e'; });
    } finally {
      setState(() => _sending = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final summaryAsync  = ref.watch(inboxSummaryProvider);
    final messagesAsync = ref.watch(emailMessagesProvider);

    return Column(children: [
      AppHeaderBar(
        title: 'Messagerie',
        subtitle: 'Boîte de réception · Envoi automatique via SMTP',
        actions: [
          TextButton.icon(
            onPressed: _triggerCheck,
            icon: const Icon(Icons.sync, size: 14),
            label: const Text('Vérifier maintenant'),
            style: TextButton.styleFrom(foregroundColor: AppTokens.accent,
                textStyle: GoogleFonts.inter(fontSize: 12)),
          ),
        ],
      ),

      // ── Tabs ────────────────────────────────────────────────────────────
      Container(
        color: AppTokens.cardBg,
        child: Row(children: [
          _Tab(label: 'Boîte de réception', selected: _tab == 0, onTap: () => setState(() => _tab = 0)),
          _Tab(label: 'Composer un email',  selected: _tab == 1, onTap: () => setState(() => _tab = 1)),
        ]),
      ),

      Expanded(child: _tab == 0
          ? _InboxView(summaryAsync: summaryAsync, messagesAsync: messagesAsync, ref: ref, onRefresh: _refresh)
          : _ComposeView(toCtrl: _toCtrl, subjectCtrl: _subjectCtrl, bodyCtrl: _bodyCtrl,
              sending: _sending, result: _sendResult, onSend: _send)),
    ]);
  }
}

// ── Inbox view ─────────────────────────────────────────────────────────────────

class _InboxView extends StatelessWidget {
  final AsyncValue<Map<String, dynamic>> summaryAsync;
  final AsyncValue<List<dynamic>> messagesAsync;
  final WidgetRef ref;
  final VoidCallback onRefresh;

  const _InboxView({
    required this.summaryAsync, required this.messagesAsync,
    required this.ref, required this.onRefresh,
  });

  Color _dirColor(String? dir) => switch (dir) {
    'entrant'   => AppTokens.accent,
    'sortant'   => AppTokens.badgeNeo4j,
    'brouillon' => const Color(0xFFF59E0B),
    _           => AppTokens.textMuted,
  };

  @override
  Widget build(BuildContext context) {
    return Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
      // ── Left: live inbox status ──────────────────────────────────────────
      Container(
        width: 280,
        decoration: const BoxDecoration(
          color: AppTokens.cardBg,
          border: Border(right: BorderSide(color: AppTokens.border)),
        ),
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Padding(padding: const EdgeInsets.fromLTRB(20, 20, 20, 12),
            child: Text('ÉTAT EN TEMPS RÉEL', style: GoogleFonts.inter(fontSize: 10,
                fontWeight: FontWeight.w600, letterSpacing: 1.2, color: AppTokens.textMuted))),
          summaryAsync.when(
            loading: () => const Padding(padding: EdgeInsets.all(20), child: CircularProgressIndicator()),
            error: (e, _) => Padding(padding: const EdgeInsets.all(16),
                child: Text('Erreur: $e', style: const TextStyle(color: AppTokens.badgeOffline, fontSize: 12))),
            data: (s) {
              if (!s['configured']) {
                return Padding(padding: const EdgeInsets.all(16), child: Column(children: [
                  const Icon(Icons.email_outlined, size: 32, color: AppTokens.textMuted),
                  const SizedBox(height: 8),
                  Text('Email non configuré', style: GoogleFonts.inter(fontSize: 12, color: AppTokens.textMuted)),
                  const SizedBox(height: 4),
                  Text('Renseignez IMAP/SMTP dans Configuration.',
                      style: GoogleFonts.inter(fontSize: 11, color: AppTokens.textMuted), textAlign: TextAlign.center),
                ]));
              }
              final unread = s['unread'] as int? ?? 0;
              final emails = s['emails'] as List? ?? [];
              return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                Padding(padding: const EdgeInsets.symmetric(horizontal: 20),
                  child: Container(
                    padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
                    decoration: BoxDecoration(
                      color: unread > 0 ? AppTokens.accent.withValues(alpha: 0.08) : AppTokens.contentBg,
                      borderRadius: BorderRadius.circular(10),
                      border: Border.all(color: unread > 0 ? AppTokens.accent.withValues(alpha: 0.3) : AppTokens.border),
                    ),
                    child: Row(children: [
                      Icon(unread > 0 ? Icons.mark_email_unread : Icons.mark_email_read,
                          size: 18, color: unread > 0 ? AppTokens.accent : AppTokens.textMuted),
                      const SizedBox(width: 10),
                      Text('$unread non lu(s)', style: GoogleFonts.inter(fontSize: 13,
                          fontWeight: FontWeight.w600, color: unread > 0 ? AppTokens.accent : AppTokens.textMuted)),
                    ]),
                  )),
                const SizedBox(height: 12),
                if (emails.isNotEmpty) ...[
                  Padding(padding: const EdgeInsets.symmetric(horizontal: 20),
                    child: Text('APERÇU', style: GoogleFonts.inter(fontSize: 10, fontWeight: FontWeight.w600,
                        letterSpacing: 1.2, color: AppTokens.textMuted))),
                  const SizedBox(height: 8),
                  ...emails.map((e) => Padding(
                    padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 2),
                    child: Container(
                      padding: const EdgeInsets.all(10),
                      decoration: BoxDecoration(color: AppTokens.contentBg, borderRadius: BorderRadius.circular(8),
                          border: Border.all(color: AppTokens.border)),
                      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                        Text(e['from'] ?? '', style: GoogleFonts.inter(fontSize: 11, fontWeight: FontWeight.w600,
                            color: AppTokens.textPrimary), overflow: TextOverflow.ellipsis),
                        Text(e['subject'] ?? '', style: GoogleFonts.inter(fontSize: 11, color: AppTokens.textSecondary),
                            overflow: TextOverflow.ellipsis),
                      ]),
                    ),
                  )),
                ],
              ]);
            },
          ),
        ]),
      ),

      // ── Right: messages from Neo4j ────────────────────────────────────────
      Expanded(
        child: messagesAsync.when(
          loading: () => const Center(child: CircularProgressIndicator()),
          error: (e, _) => Center(child: Text('Erreur: $e')),
          data: (msgs) {
            if (msgs.isEmpty) {
              return Center(child: Column(mainAxisSize: MainAxisSize.min, children: [
                const Icon(Icons.inbox_outlined, size: 48, color: AppTokens.textMuted),
                const SizedBox(height: 12),
                Text('Aucun email traité', style: GoogleFonts.inter(color: AppTokens.textMuted)),
                const SizedBox(height: 6),
                Text('Cliquez sur "Vérifier maintenant" pour lancer la lecture.',
                    style: GoogleFonts.inter(fontSize: 11, color: AppTokens.textMuted)),
              ]));
            }
            return ListView.builder(
              padding: const EdgeInsets.all(20),
              itemCount: msgs.length,
              itemBuilder: (ctx, i) {
                final m = msgs[i] as Map<String, dynamic>;
                final dir = m['direction'] as String? ?? '';
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
                      Container(
                        padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
                        decoration: BoxDecoration(
                          color: _dirColor(dir).withValues(alpha: 0.1),
                          borderRadius: BorderRadius.circular(8),
                        ),
                        child: Text(dir.isEmpty ? '?' : dir,
                            style: GoogleFonts.inter(fontSize: 10, fontWeight: FontWeight.w600, color: _dirColor(dir))),
                      ),
                      const SizedBox(width: 10),
                      Expanded(child: Text(m['sujet'] ?? '—',
                          style: GoogleFonts.inter(fontSize: 13, fontWeight: FontWeight.w600, color: AppTokens.textPrimary),
                          overflow: TextOverflow.ellipsis)),
                      if (m['intent'] != null)
                        Text(m['intent'], style: GoogleFonts.inter(fontSize: 10, color: AppTokens.textMuted)),
                    ]),
                    if (m['resume_ia'] != null && m['resume_ia'].toString().isNotEmpty) ...[
                      const SizedBox(height: 6),
                      Text(m['resume_ia'], style: GoogleFonts.inter(fontSize: 12, color: AppTokens.textSecondary,
                          fontStyle: FontStyle.italic)),
                    ],
                    if (m['contenu'] != null && dir == 'brouillon') ...[
                      const SizedBox(height: 8),
                      Container(
                        padding: const EdgeInsets.all(10),
                        decoration: BoxDecoration(color: AppTokens.contentBg,
                            borderRadius: BorderRadius.circular(6), border: Border.all(color: AppTokens.border)),
                        child: Text(m['contenu'].toString().substring(0,
                            (m['contenu'].toString().length).clamp(0, 300)),
                          style: GoogleFonts.inter(fontSize: 11, color: AppTokens.textPrimary, height: 1.5)),
                      ),
                      const SizedBox(height: 8),
                      _SendDraftButton(message: m, ref: ref, onSent: onRefresh),
                    ],
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

// ── Send draft button ──────────────────────────────────────────────────────────

class _SendDraftButton extends StatefulWidget {
  final Map<String, dynamic> message;
  final WidgetRef ref;
  final VoidCallback onSent;
  const _SendDraftButton({required this.message, required this.ref, required this.onSent});

  @override
  State<_SendDraftButton> createState() => _SendDraftButtonState();
}

class _SendDraftButtonState extends State<_SendDraftButton> {
  bool _loading = false;
  bool _sent    = false;

  Future<void> _send() async {
    final toCtrl      = TextEditingController();
    final confirmed = await showDialog<String>(
      context: context,
      builder: (_) => AlertDialog(
        title: Text('Envoyer ce brouillon', style: GoogleFonts.inter(fontSize: 14, fontWeight: FontWeight.w600)),
        content: SizedBox(width: 400, child: Column(mainAxisSize: MainAxisSize.min, children: [
          TextField(controller: toCtrl, decoration: const InputDecoration(labelText: 'Destinataire (email)', isDense: true),
              style: GoogleFonts.inter(fontSize: 13)),
        ])),
        actions: [
          TextButton(onPressed: () => Navigator.pop(context), child: const Text('Annuler')),
          ElevatedButton(onPressed: () => Navigator.pop(context, toCtrl.text.trim()), child: const Text('Envoyer')),
        ],
      ),
    );
    if (confirmed == null || confirmed.isEmpty) return;
    setState(() => _loading = true);
    try {
      await widget.ref.read(apiClientProvider).sendEmail(
        confirmed,
        widget.message['sujet'] ?? '',
        widget.message['contenu'] ?? '',
      );
      setState(() { _loading = false; _sent = true; });
      widget.onSent();
    } catch (e) {
      setState(() => _loading = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    if (_sent) return Text('✅ Envoyé', style: GoogleFonts.inter(fontSize: 12, color: AppTokens.badgeNeo4j));
    return TextButton.icon(
      onPressed: _loading ? null : _send,
      icon: _loading
        ? const SizedBox(width: 12, height: 12, child: CircularProgressIndicator(strokeWidth: 1.5))
        : const Icon(Icons.send, size: 14),
      label: const Text('Envoyer ce brouillon'),
      style: TextButton.styleFrom(foregroundColor: const Color(0xFFF59E0B),
          textStyle: GoogleFonts.inter(fontSize: 12, fontWeight: FontWeight.w600)),
    );
  }
}

// ── Compose view ───────────────────────────────────────────────────────────────

class _ComposeView extends StatelessWidget {
  final TextEditingController toCtrl, subjectCtrl, bodyCtrl;
  final bool sending;
  final String? result;
  final VoidCallback onSend;

  const _ComposeView({
    required this.toCtrl, required this.subjectCtrl, required this.bodyCtrl,
    required this.sending, required this.result, required this.onSend,
  });

  @override
  Widget build(BuildContext context) {
    return SingleChildScrollView(
      padding: const EdgeInsets.all(28),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Container(
          padding: const EdgeInsets.all(24),
          decoration: BoxDecoration(color: AppTokens.cardBg,
              borderRadius: BorderRadius.circular(AppTokens.borderRadiusLg),
              border: Border.all(color: AppTokens.border)),
          child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Text('Nouveau message', style: GoogleFonts.inter(fontSize: 15, fontWeight: FontWeight.w600, color: AppTokens.textPrimary)),
            const SizedBox(height: 20),
            _Field('Destinataire', toCtrl),
            const SizedBox(height: 14),
            _Field('Objet', subjectCtrl),
            const SizedBox(height: 14),
            _Field('Corps du message', bodyCtrl, maxLines: 10),
            const SizedBox(height: 20),
            if (result != null) Padding(padding: const EdgeInsets.only(bottom: 12),
              child: Text(result!, style: GoogleFonts.inter(fontSize: 12,
                  color: result!.startsWith('✅') ? AppTokens.badgeNeo4j : AppTokens.badgeOffline))),
            ElevatedButton.icon(
              onPressed: sending ? null : onSend,
              icon: sending
                ? const SizedBox(width: 16, height: 16, child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white))
                : const Icon(Icons.send, size: 16),
              label: Text(sending ? 'Envoi…' : 'Envoyer'),
              style: ElevatedButton.styleFrom(
                backgroundColor: AppTokens.accent, foregroundColor: Colors.white,
                shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(8)),
                padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 12),
              ),
            ),
          ]),
        ),
      ]),
    );
  }
}

class _Field extends StatelessWidget {
  final String label;
  final TextEditingController ctrl;
  final int maxLines;
  const _Field(this.label, this.ctrl, {this.maxLines = 1});

  @override
  Widget build(BuildContext context) => Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
    Text(label, style: GoogleFonts.inter(fontSize: 12, fontWeight: FontWeight.w500, color: AppTokens.textSecondary)),
    const SizedBox(height: 6),
    TextField(controller: ctrl, maxLines: maxLines,
        style: GoogleFonts.inter(fontSize: 13),
        decoration: const InputDecoration(isDense: true)),
  ]);
}

// ── Tab widget ─────────────────────────────────────────────────────────────────

class _Tab extends StatelessWidget {
  final String label;
  final bool selected;
  final VoidCallback onTap;
  const _Tab({required this.label, required this.selected, required this.onTap});

  @override
  Widget build(BuildContext context) => GestureDetector(
    onTap: onTap,
    child: Container(
      padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 12),
      decoration: BoxDecoration(
        border: Border(bottom: BorderSide(
          color: selected ? AppTokens.accent : Colors.transparent, width: 2)),
      ),
      child: Text(label, style: GoogleFonts.inter(fontSize: 13,
          fontWeight: selected ? FontWeight.w600 : FontWeight.w400,
          color: selected ? AppTokens.accent : AppTokens.textMuted)),
    ),
  );
}
