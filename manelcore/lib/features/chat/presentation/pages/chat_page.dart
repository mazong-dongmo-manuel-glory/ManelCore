import 'dart:async';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:google_fonts/google_fonts.dart';
import '../../../../core/api_client.dart';
import '../../../../core/theme.dart';
import '../../../../widgets/header_bar.dart';

class ChatPage extends ConsumerStatefulWidget {
  const ChatPage({super.key});

  @override
  ConsumerState<ChatPage> createState() => _ChatPageState();
}

class _ChatPageState extends ConsumerState<ChatPage> {
  final _ctrl   = TextEditingController();
  final _scroll = ScrollController();
  final List<_Msg> _messages = [];
  bool _loading = false;
  StreamSubscription<String>? _sub;

  // RAG context state
  List<String> _ragSources = [];
  int _ragOpps = 0;
  bool _ragLoading = false;

  Future<void> _send() async {
    final text = _ctrl.text.trim();
    if (text.isEmpty || _loading) return;
    _ctrl.clear();

    setState(() {
      _messages.add(_Msg(role: 'user', content: text));
      _messages.add(_Msg(role: 'assistant', content: ''));
      _loading = true;
      _ragLoading = true;
      _ragSources = [];
    });
    _scrollToBottom();

    // Build history (exclude current empty assistant message)
    final history = _messages
        .where((m) => m.content.isNotEmpty)
        .take(_messages.length - 1)
        .map((m) => {'role': m.role, 'content': m.content})
        .toList();

    _sub = ref.read(apiClientProvider).chatStream(
      history,
      useRag: true,
      onRagMeta: (meta) {
        if (mounted) {
          setState(() {
            _ragSources = List<String>.from(meta['sources'] as List? ?? []);
            _ragOpps = meta['opps_count'] as int? ?? 0;
            _ragLoading = false;
          });
        }
      },
    ).listen(
      (chunk) {
        setState(() => _messages.last = _Msg(
            role: 'assistant',
            content: '${_messages.last.content}$chunk'));
        _scrollToBottom();
      },
      onDone: () => setState(() { _loading = false; _ragLoading = false; }),
      onError: (_) => setState(() { _loading = false; _ragLoading = false; }),
    );
  }

  void _scrollToBottom() {
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (_scroll.hasClients) {
        _scroll.animateTo(
          _scroll.position.maxScrollExtent,
          duration: const Duration(milliseconds: 200),
          curve: Curves.easeOut,
        );
      }
    });
  }

  void _clear() {
    _sub?.cancel();
    setState(() {
      _messages.clear();
      _loading = false;
      _ragLoading = false;
      _ragSources = [];
      _ragOpps = 0;
    });
  }

  @override
  void dispose() {
    _sub?.cancel();
    _scroll.dispose();
    _ctrl.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Column(children: [
      AppHeaderBar(
        title: 'Assistant IA',
        subtitle: 'ARIA — Gemma 4 · Graph RAG Neo4j',
        actions: [
          if (_ragSources.isNotEmpty || _ragLoading)
            _RagBadge(sources: _ragSources, oppsCount: _ragOpps, loading: _ragLoading),
          if (_messages.isNotEmpty) ...[
            const SizedBox(width: 8),
            TextButton.icon(
              onPressed: _clear,
              icon: const Icon(Icons.refresh, size: 14),
              label: const Text('Effacer'),
              style: TextButton.styleFrom(foregroundColor: AppTokens.textMuted),
            ),
          ],
        ],
      ),
      Expanded(
        child: _messages.isEmpty
            ? _EmptyState(onSuggestion: (s) { _ctrl.text = s; _send(); })
            : ListView.builder(
                controller: _scroll,
                padding: const EdgeInsets.all(20),
                itemCount: _messages.length,
                itemBuilder: (_, i) => _BubbleTile(msg: _messages[i]),
              ),
      ),
      // Input bar
      Container(
        padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 12),
        decoration: const BoxDecoration(
          color: AppTokens.cardBg,
          border: Border(top: BorderSide(color: AppTokens.border)),
        ),
        child: Row(children: [
          Expanded(
            child: TextField(
              controller: _ctrl,
              style: GoogleFonts.inter(fontSize: 13),
              maxLines: null,
              textInputAction: TextInputAction.send,
              onSubmitted: (_) => _send(),
              decoration: InputDecoration(
                hintText: 'Posez votre question à ARIA (contexte Neo4j automatique)…',
                hintStyle: GoogleFonts.inter(fontSize: 12, color: AppTokens.textMuted),
                isDense: true,
                border: InputBorder.none,
              ),
            ),
          ),
          const SizedBox(width: 12),
          _loading
            ? const SizedBox(width: 20, height: 20, child: CircularProgressIndicator(strokeWidth: 2))
            : IconButton(
                onPressed: _send,
                icon: const Icon(Icons.send_rounded),
                color: AppTokens.accent,
                iconSize: 22,
              ),
        ]),
      ),
    ]);
  }
}

// ── RAG badge ──────────────────────────────────────────────────────────────────

class _RagBadge extends StatelessWidget {
  final List<String> sources;
  final int oppsCount;
  final bool loading;
  const _RagBadge({required this.sources, required this.oppsCount, required this.loading});

  static const _icons = {
    'entreprise':   '🏢',
    'opportunités': '📋',
    'contacts':     '👥',
    'candidats':    '🎓',
    'emails':       '📧',
  };

  @override
  Widget build(BuildContext context) {
    return Tooltip(
      message: loading
          ? 'Chargement du contexte Neo4j…'
          : 'Contexte chargé: ${sources.join(', ')}${oppsCount > 0 ? ' ($oppsCount opportunités)' : ''}',
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 5),
        decoration: BoxDecoration(
          color: AppTokens.badgeNeo4j.withValues(alpha: loading ? 0.05 : 0.08),
          borderRadius: BorderRadius.circular(20),
          border: Border.all(color: AppTokens.badgeNeo4j.withValues(alpha: loading ? 0.2 : 0.4)),
        ),
        child: Row(mainAxisSize: MainAxisSize.min, children: [
          if (loading)
            const SizedBox(width: 10, height: 10, child: CircularProgressIndicator(strokeWidth: 1.5, color: AppTokens.badgeNeo4j))
          else
            const Icon(Icons.hub, size: 12, color: AppTokens.badgeNeo4j),
          const SizedBox(width: 6),
          Text(
            loading
                ? 'Neo4j…'
                : sources.map((s) => _icons[s] ?? '').join(' ').trim().isNotEmpty
                    ? sources.map((s) => _icons[s] ?? '').where((e) => e.isNotEmpty).join(' ')
                    : 'Contexte',
            style: GoogleFonts.inter(fontSize: 11, fontWeight: FontWeight.w600, color: AppTokens.badgeNeo4j),
          ),
        ]),
      ),
    );
  }
}

// ── Message bubble ─────────────────────────────────────────────────────────────

class _Msg {
  final String role, content;
  const _Msg({required this.role, required this.content});
}

class _BubbleTile extends StatelessWidget {
  final _Msg msg;
  const _BubbleTile({required this.msg});

  @override
  Widget build(BuildContext context) {
    final isUser = msg.role == 'user';
    return Padding(
      padding: const EdgeInsets.only(bottom: 16),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        mainAxisAlignment: isUser ? MainAxisAlignment.end : MainAxisAlignment.start,
        children: [
          if (!isUser) ...[
            CircleAvatar(
              radius: 16,
              backgroundColor: AppTokens.accent.withValues(alpha: 0.12),
              child: const Text('AI',
                  style: TextStyle(fontSize: 10, fontWeight: FontWeight.w700, color: AppTokens.accent)),
            ),
            const SizedBox(width: 10),
          ],
          Flexible(
            child: Container(
              padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
              decoration: BoxDecoration(
                color: isUser ? AppTokens.accent : AppTokens.cardBg,
                borderRadius: BorderRadius.only(
                  topLeft:     const Radius.circular(16),
                  topRight:    const Radius.circular(16),
                  bottomLeft:  Radius.circular(isUser ? 16 : 4),
                  bottomRight: Radius.circular(isUser ? 4 : 16),
                ),
                border: isUser ? null : Border.all(color: AppTokens.border),
              ),
              child: msg.content.isEmpty
                  ? Row(mainAxisSize: MainAxisSize.min, children: [
                      const SizedBox(width: 40, height: 16, child: LinearProgressIndicator(backgroundColor: Colors.transparent)),
                      const SizedBox(width: 8),
                      Text('ARIA réfléchit…',
                          style: GoogleFonts.inter(fontSize: 11, color: AppTokens.textMuted, fontStyle: FontStyle.italic)),
                    ])
                  : Text(msg.content,
                      style: GoogleFonts.inter(
                          fontSize: 13,
                          color: isUser ? Colors.white : AppTokens.textPrimary,
                          height: 1.55)),
            ),
          ),
          if (isUser) ...[
            const SizedBox(width: 10),
            CircleAvatar(
              radius: 16,
              backgroundColor: AppTokens.accent,
              child: const Text('M',
                  style: TextStyle(fontSize: 11, fontWeight: FontWeight.w700, color: Colors.white)),
            ),
          ],
        ],
      ),
    );
  }
}

// ── Empty state ────────────────────────────────────────────────────────────────

class _EmptyState extends StatelessWidget {
  final ValueChanged<String> onSuggestion;
  const _EmptyState({required this.onSuggestion});

  static const _suggestions = [
    'Quelles sont nos opportunités validées en ce moment ?',
    'Résume les 3 meilleures opportunités SEAO disponibles.',
    'Combien de contacts avons-nous dans le CRM ?',
    'Rédige un email de prospection pour notre meilleure opportunité.',
    'Quels sont nos secteurs cibles et notre positionnement ?',
    'Analyse notre pipeline commercial actuel.',
  ];

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Column(mainAxisSize: MainAxisSize.min, children: [
        Container(
          width: 64, height: 64,
          decoration: BoxDecoration(
            gradient: const LinearGradient(colors: [AppTokens.accent, Color(0xFF818CF8)]),
            borderRadius: BorderRadius.circular(16),
          ),
          child: const Icon(Icons.smart_toy_outlined, color: Colors.white, size: 32),
        ),
        const SizedBox(height: 20),
        Text('ARIA est prête',
            style: GoogleFonts.inter(fontSize: 18, fontWeight: FontWeight.w700, color: AppTokens.textPrimary)),
        const SizedBox(height: 6),
        Row(mainAxisSize: MainAxisSize.min, children: [
          const Icon(Icons.hub, size: 14, color: AppTokens.badgeNeo4j),
          const SizedBox(width: 6),
          Text('Connectée à Neo4j · Gemma 4 via LM Studio',
              style: GoogleFonts.inter(fontSize: 12, color: AppTokens.textMuted)),
        ]),
        const SizedBox(height: 32),
        Wrap(
          spacing: 10, runSpacing: 10,
          alignment: WrapAlignment.center,
          children: _suggestions.map((s) => ActionChip(
            label: Text(s, style: GoogleFonts.inter(fontSize: 12, color: AppTokens.textSecondary)),
            onPressed: () => onSuggestion(s),
            backgroundColor: AppTokens.cardBg,
            side: const BorderSide(color: AppTokens.border),
            shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(20)),
          )).toList(),
        ),
      ]),
    );
  }
}
