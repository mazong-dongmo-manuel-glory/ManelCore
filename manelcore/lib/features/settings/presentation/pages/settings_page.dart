import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:google_fonts/google_fonts.dart';
import '../../../../core/api_client.dart';
import '../../../../core/theme.dart';
import '../../../../widgets/header_bar.dart';

class SettingsPage extends ConsumerStatefulWidget {
  const SettingsPage({super.key});

  @override
  ConsumerState<SettingsPage> createState() => _SettingsPageState();
}

class _SettingsPageState extends ConsumerState<SettingsPage> {
  // ── Company (Neo4j) ──────────────────────────────────────────────────────────
  final _companyName = TextEditingController();
  final _companyUrl = TextEditingController();
  final _companyProfile = TextEditingController();
  final _sectorsCtrl = TextEditingController();
  bool _scraping = false;
  String? _scrapeMsg;

  // ── Runtime settings (settings.json) ─────────────────────────────────────────
  final _llmUrl = TextEditingController();
  final _llmModel = TextEditingController();
  final _neo4jUri = TextEditingController();
  final _neo4jPassword = TextEditingController();
  final _emailAddr = TextEditingController();
  final _emailPassword = TextEditingController();
  final _imapServer = TextEditingController();
  final _telegramToken = TextEditingController();
  final _telegramChatId = TextEditingController();
  final _explorerInterval = TextEditingController();
  final _searchPromptHint = TextEditingController();

  bool _loaded = false;
  bool _saving = false;
  bool _erasing = false;
  String? _msg;
  bool _msgIsError = false;

  @override
  void initState() {
    super.initState();
    _loadAll();
  }

  Future<void> _loadAll() async {
    final api = ref.read(apiClientProvider);
    try {
      final results = await Future.wait([
        api.getConfig(),
        api.getSettings(),
      ]);
      final config = results[0];
      final settings = results[1];

      final e = config['entreprise'] as Map<String, dynamic>? ?? {};
      final sectors = (config['sectors'] as List?)?.join(', ') ?? '';

      setState(() {
        _companyName.text = e['nom'] ?? '';
        _companyProfile.text = e['description'] ?? '';
        _sectorsCtrl.text = sectors;
        _llmUrl.text = settings['llm_url'] ?? 'http://localhost:1234/v1';
        _llmModel.text = settings['llm_model'] ?? 'google/gemma-4-e4b';
        _neo4jUri.text = settings['neo4j_uri'] ?? 'bolt://localhost:7687';
        _neo4jPassword.text = settings['neo4j_password'] ?? '';
        _emailAddr.text = settings['email'] ?? '';
        _emailPassword.text = settings['email_password'] ?? '';
        _imapServer.text = settings['imap_server'] ?? '';
        _telegramToken.text = '';
        _telegramChatId.text = settings['telegram_chat_id'] ?? '';
        _explorerInterval.text = (settings['explorer_interval'] ?? 30).toString();
        _searchPromptHint.text = settings['search_prompt_hint'] ?? '';
        _companyUrl.text = e['site_web'] ?? '';
        _loaded = true;
      });
    } catch (_) {
      setState(() => _loaded = true);
    }
  }

  Future<void> _save() async {
    setState(() {
      _saving = true;
      _msg = null;
    });
    final api = ref.read(apiClientProvider);
    try {
      final sectors = _sectorsCtrl.text
          .split(',')
          .map((s) => s.trim())
          .where((s) => s.isNotEmpty)
          .toList();

      // 1) Profil entreprise → Neo4j
      final configPayload = <String, dynamic>{
        'company_name': _companyName.text.trim(),
        'company_url': _companyUrl.text.trim(),
        'company_profile': _companyProfile.text.trim(),
        'sectors': sectors,
      };
      if (_telegramToken.text.trim().isNotEmpty) {
        configPayload['telegram_token'] = _telegramToken.text.trim();
        configPayload['telegram_chat_id'] = _telegramChatId.text.trim();
      }

      // 2) Settings runtime → settings.json
      final settingsPayload = <String, dynamic>{
        'llm_url': _llmUrl.text.trim(),
        'llm_model': _llmModel.text.trim(),
        'neo4j_uri': _neo4jUri.text.trim(),
        'email': _emailAddr.text.trim(),
        'imap_server': _imapServer.text.trim(),
        'telegram_chat_id': _telegramChatId.text.trim(),
        'explorer_interval': int.tryParse(_explorerInterval.text) ?? 30,
        'search_prompt_hint': _searchPromptHint.text.trim(),
      };
      // Mots de passe : n'écraser que si saisis
      void maybeAdd(String key, TextEditingController ctrl) {
        final v = ctrl.text.trim();
        if (v.isNotEmpty && v != '••••••••') settingsPayload[key] = v;
      }

      maybeAdd('neo4j_password', _neo4jPassword);
      maybeAdd('email_password', _emailPassword);
      maybeAdd('telegram_token', _telegramToken);

      await Future.wait([
        api.updateConfig(configPayload),
        api.updateSettings(settingsPayload),
      ]);

      ref.invalidate(configProvider);
      setState(() {
        _msg = 'Configuration sauvegardée.';
        _msgIsError = false;
      });
    } catch (e) {
      setState(() {
        _msg = 'Erreur : $e';
        _msgIsError = true;
      });
    } finally {
      setState(() => _saving = false);
    }
  }

  Future<void> _scrapeProfile() async {
    final url = _companyUrl.text.trim();
    if (url.isEmpty) {
      setState(() {
        _scrapeMsg = 'Entrez d\'abord l\'URL du site web.';
      });
      return;
    }
    setState(() {
      _scraping = true;
      _scrapeMsg = null;
    });
    try {
      final result = await ref.read(apiClientProvider).scrapeProfile(url);
      final profile = result['profile'] as String? ?? '';
      if (profile.isNotEmpty) {
        setState(() => _companyProfile.text = profile);
        setState(() => _scrapeMsg = 'Profil généré depuis ${result['url']}');
      } else {
        setState(() => _scrapeMsg = 'Aucun contenu exploitable trouvé.');
      }
    } catch (e) {
      setState(() => _scrapeMsg = 'Erreur : $e');
    } finally {
      setState(() => _scraping = false);
    }
  }

  Future<void> _eraseData() async {
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Erase toutes les données ?'),
        content: const Text(
          'Cette action supprime les opportunités, contacts, messages, candidats et le profil entreprise dans Neo4j. '
          'Les paramètres et les sessions navigateur restent conservés.',
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(ctx).pop(false),
            child: const Text('Annuler'),
          ),
          FilledButton.icon(
            onPressed: () => Navigator.of(ctx).pop(true),
            icon: const Icon(Icons.delete_forever, size: 18),
            label: const Text('Erase'),
            style: FilledButton.styleFrom(
              backgroundColor: AppTokens.badgeOffline,
            ),
          ),
        ],
      ),
    );
    if (confirmed != true) return;

    setState(() {
      _erasing = true;
      _msg = null;
    });
    try {
      final result = await ref.read(apiClientProvider).eraseAllData();
      ref.invalidate(configProvider);
      ref.invalidate(dashboardStatsProvider);
      ref.invalidate(opportunitiesProvider);
      ref.invalidate(contactsProvider);
      ref.invalidate(candidatsProvider);
      setState(() {
        _companyName.clear();
        _companyProfile.clear();
        _sectorsCtrl.clear();
        _msg = 'Erase terminé: ${result['deleted'] ?? 0} noeud(s) supprimé(s).';
        _msgIsError = false;
      });
    } catch (e) {
      setState(() {
        _msg = 'Erreur erase : $e';
        _msgIsError = true;
      });
    } finally {
      setState(() => _erasing = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Column(
      children: [
        AppHeaderBar(
          title: 'Configuration',
          subtitle: 'Paramètres système et intégrations',
          actions: [
            IconButton(
              icon: const Icon(
                Icons.refresh,
                size: 18,
                color: AppTokens.textMuted,
              ),
              tooltip: 'Recharger depuis le serveur',
              onPressed: () {
                setState(() => _loaded = false);
                _loadAll();
              },
            ),
          ],
        ),
        Expanded(
          child: !_loaded
              ? const Center(child: CircularProgressIndicator())
              : SingleChildScrollView(
                  padding: const EdgeInsets.all(28),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      LayoutBuilder(
                        builder: (ctx, constraints) {
                          final wide = constraints.maxWidth >= 680;
                          final row1 = [
                            _Card(
                              title: 'Profil Entreprise',
                              icon: Icons.business,
                              iconColor: AppTokens.accent,
                              children: [
                                _Field('Nom de l\'entreprise', _companyName),
                                const SizedBox(height: 14),
                                Row(
                                  crossAxisAlignment: CrossAxisAlignment.end,
                                  children: [
                                    Expanded(
                                      child: _Field(
                                        'Site web de l\'entreprise',
                                        _companyUrl,
                                        hint: 'https://monentreprise.ca',
                                      ),
                                    ),
                                    const SizedBox(width: 10),
                                    Padding(
                                      padding: const EdgeInsets.only(bottom: 2),
                                      child: FilledButton.icon(
                                        onPressed: _scraping ? null : _scrapeProfile,
                                        icon: _scraping
                                            ? const SizedBox(
                                                width: 14,
                                                height: 14,
                                                child: CircularProgressIndicator(
                                                  strokeWidth: 2,
                                                  color: Colors.white,
                                                ),
                                              )
                                            : const Icon(Icons.auto_awesome, size: 16),
                                        label: Text(
                                          _scraping ? 'Analyse…' : 'Générer profil',
                                          style: GoogleFonts.inter(fontSize: 12, fontWeight: FontWeight.w600),
                                        ),
                                        style: FilledButton.styleFrom(
                                          backgroundColor: AppTokens.accent,
                                          padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 14),
                                          shape: RoundedRectangleBorder(
                                            borderRadius: BorderRadius.circular(AppTokens.borderRadius),
                                          ),
                                        ),
                                      ),
                                    ),
                                  ],
                                ),
                                if (_scrapeMsg != null) ...[
                                  const SizedBox(height: 6),
                                  Text(
                                    _scrapeMsg!,
                                    style: GoogleFonts.inter(
                                      fontSize: 11,
                                      color: _scrapeMsg!.startsWith('Erreur')
                                          ? AppTokens.badgeOffline
                                          : AppTokens.badgeNeo4j,
                                    ),
                                  ),
                                ],
                                const SizedBox(height: 14),
                                _Field(
                                  'Profil / Description',
                                  _companyProfile,
                                  maxLines: 4,
                                ),
                                const SizedBox(height: 14),
                                _Field(
                                  'Secteurs cibles (séparés par virgule)',
                                  _sectorsCtrl,
                                ),
                              ],
                            ),
                            _Card(
                              title: 'LLM — LM Studio',
                              icon: Icons.smart_toy_outlined,
                              iconColor: const Color(0xFF8B5CF6),
                              children: [
                                _Field('URL de base', _llmUrl),
                                const SizedBox(height: 14),
                                _Field('Modèle', _llmModel),
                                const SizedBox(height: 8),
                                _LlmStatus(widgetRef: ref),
                              ],
                            ),
                          ];
                          final row2 = [
                            _Card(
                              title: 'Neo4j',
                              icon: Icons.hub,
                              iconColor: AppTokens.badgeNeo4j,
                              children: [
                                _Field('URI', _neo4jUri),
                                const SizedBox(height: 14),
                                _Field(
                                  'Mot de passe',
                                  _neo4jPassword,
                                  obscure: true,
                                  hint: 'Laisser vide pour ne pas modifier',
                                ),
                              ],
                            ),
                            _Card(
                              title: 'Email (SMTP/IMAP)',
                              icon: Icons.email_outlined,
                              iconColor: const Color(0xFFF59E0B),
                              children: [
                                _Field('Adresse email', _emailAddr),
                                const SizedBox(height: 14),
                                _Field(
                                  'Mot de passe',
                                  _emailPassword,
                                  obscure: true,
                                  hint: 'Laisser vide pour ne pas modifier',
                                ),
                                const SizedBox(height: 14),
                                _Field('Serveur IMAP', _imapServer),
                              ],
                            ),
                          ];

                          Widget buildRow(List<Widget> cards) => wide
                              ? Row(
                                  crossAxisAlignment: CrossAxisAlignment.start,
                                  children: [
                                    Expanded(child: cards[0]),
                                    const SizedBox(width: 20),
                                    Expanded(child: cards[1]),
                                  ],
                                )
                              : Column(
                                  children: [
                                    cards[0],
                                    const SizedBox(height: 16),
                                    cards[1],
                                  ],
                                );

                          return Column(
                            children: [
                              buildRow(row1),
                              const SizedBox(height: 20),
                              buildRow(row2),
                            ],
                          );
                        },
                      ),
                      const SizedBox(height: 20),
                      // Telegram (full width)
                      _Card(
                        title: 'Telegram Bot',
                        icon: Icons.send,
                        iconColor: AppTokens.accent,
                        children: [
                          Row(
                            children: [
                              Expanded(
                                child: _Field(
                                  'Bot Token',
                                  _telegramToken,
                                  obscure: true,
                                  hint:
                                      'Laisser vide pour conserver l\'existant',
                                ),
                              ),
                              const SizedBox(width: 16),
                              Expanded(
                                child: _Field('Chat ID', _telegramChatId),
                              ),
                            ],
                          ),
                          const SizedBox(height: 8),
                          Text(
                            'Le bot envoie une notification pour chaque opportunité avec boutons ✅ Valider / ❌ Rejeter.',
                            style: GoogleFonts.inter(
                              fontSize: 11,
                              color: AppTokens.textMuted,
                            ),
                          ),
                        ],
                      ),
                      const SizedBox(height: 20),
                      _Card(
                        title: 'Automatisation Explorer',
                        icon: Icons.timer_outlined,
                        iconColor: const Color(0xFF10B981),
                        children: [
                          Row(
                            children: [
                              SizedBox(
                                width: 180,
                                child: _Field(
                                  'Fréquence de recherche (min)',
                                  _explorerInterval,
                                ),
                              ),
                              const SizedBox(width: 16),
                              Expanded(
                                child: Padding(
                                  padding: const EdgeInsets.only(top: 18),
                                  child: Text(
                                    'L\'agent scannera SEAO, LinkedIn et Indeed automatiquement toutes les X minutes.',
                                    style: GoogleFonts.inter(
                                      fontSize: 12,
                                      color: AppTokens.textMuted,
                                    ),
                                  ),
                                ),
                              ),
                            ],
                          ),
                          const SizedBox(height: 16),
                          _Field(
                            'Orientation de la recherche (optionnel)',
                            _searchPromptHint,
                            maxLines: 3,
                            hint: 'Ex : Concentre-toi sur les contrats gouvernementaux en cybersécurité au Québec, budget > 50 000 \$.',
                          ),
                          const SizedBox(height: 6),
                          Text(
                            'Cette consigne est injectée dans le prompt LLM pour orienter la génération des requêtes de recherche.',
                            style: GoogleFonts.inter(fontSize: 11, color: AppTokens.textMuted),
                          ),
                        ],
                      ),
                      const SizedBox(height: 20),

                      // Feedback
                      if (_msg != null)
                        _FeedbackBanner(message: _msg!, isError: _msgIsError),

                      // Save button
                      Align(
                        alignment: Alignment.centerRight,
                        child: Wrap(
                          spacing: 12,
                          runSpacing: 12,
                          alignment: WrapAlignment.end,
                          children: [
                            OutlinedButton.icon(
                              onPressed: (_saving || _erasing)
                                  ? null
                                  : _eraseData,
                              icon: _erasing
                                  ? const SizedBox(
                                      width: 18,
                                      height: 18,
                                      child: CircularProgressIndicator(
                                        strokeWidth: 2,
                                      ),
                                    )
                                  : const Icon(Icons.delete_forever, size: 18),
                              label: Text(
                                'Erase',
                                style: GoogleFonts.inter(
                                  fontWeight: FontWeight.w600,
                                  fontSize: 13,
                                ),
                              ),
                              style: OutlinedButton.styleFrom(
                                foregroundColor: AppTokens.badgeOffline,
                                side: const BorderSide(
                                  color: AppTokens.badgeOffline,
                                ),
                                padding: const EdgeInsets.symmetric(
                                  horizontal: 24,
                                  vertical: 16,
                                ),
                                shape: RoundedRectangleBorder(
                                  borderRadius: BorderRadius.circular(
                                    AppTokens.borderRadius,
                                  ),
                                ),
                              ),
                            ),
                            ElevatedButton(
                              onPressed: (_saving || _erasing) ? null : _save,
                              style: ElevatedButton.styleFrom(
                                backgroundColor: AppTokens.accent,
                                foregroundColor: Colors.white,
                                padding: const EdgeInsets.symmetric(
                                  horizontal: 36,
                                  vertical: 16,
                                ),
                                shape: RoundedRectangleBorder(
                                  borderRadius: BorderRadius.circular(
                                    AppTokens.borderRadius,
                                  ),
                                ),
                              ),
                              child: _saving
                                  ? const SizedBox(
                                      width: 18,
                                      height: 18,
                                      child: CircularProgressIndicator(
                                        strokeWidth: 2,
                                        color: Colors.white,
                                      ),
                                    )
                                  : Text(
                                      'Sauvegarder',
                                      style: GoogleFonts.inter(
                                        fontWeight: FontWeight.w600,
                                        fontSize: 13,
                                      ),
                                    ),
                            ),
                          ],
                        ),
                      ),
                    ],
                  ),
                ),
        ),
      ],
    );
  }
}

// ── LLM live status ────────────────────────────────────────────────────────────

class _LlmStatus extends StatefulWidget {
  final WidgetRef widgetRef;
  const _LlmStatus({required this.widgetRef});
  @override
  State<_LlmStatus> createState() => _LlmStatusState();
}

class _LlmStatusState extends State<_LlmStatus> {
  String? _status;
  bool _checking = false;

  Future<void> _check() async {
    setState(() {
      _checking = true;
      _status = null;
    });
    try {
      final h = await widget.widgetRef.read(apiClientProvider).health();
      setState(() => _status = h['llm'] as String? ?? 'inconnu');
    } catch (_) {
      setState(() => _status = 'error');
    } finally {
      setState(() => _checking = false);
    }
  }

  @override
  Widget build(BuildContext context) => Row(
    children: [
      TextButton.icon(
        onPressed: _checking ? null : _check,
        icon: _checking
            ? const SizedBox(
                width: 12,
                height: 12,
                child: CircularProgressIndicator(strokeWidth: 1.5),
              )
            : const Icon(Icons.wifi_tethering, size: 14),
        label: const Text('Tester LM Studio'),
        style: TextButton.styleFrom(
          foregroundColor: const Color(0xFF8B5CF6),
          textStyle: GoogleFonts.inter(fontSize: 12),
        ),
      ),
      if (_status != null) ...[
        const SizedBox(width: 6),
        Icon(
          _status == 'connected' ? Icons.check_circle : Icons.error_outline,
          size: 14,
          color: _status == 'connected'
              ? AppTokens.badgeNeo4j
              : AppTokens.badgeOffline,
        ),
        const SizedBox(width: 4),
        Text(
          _status!,
          style: GoogleFonts.inter(
            fontSize: 11,
            color: _status == 'connected'
                ? AppTokens.badgeNeo4j
                : AppTokens.badgeOffline,
          ),
        ),
      ],
    ],
  );
}

// ── Shared widgets ─────────────────────────────────────────────────────────────

class _Card extends StatelessWidget {
  final String title;
  final IconData icon;
  final Color iconColor;
  final List<Widget> children;
  const _Card({
    required this.title,
    required this.icon,
    required this.iconColor,
    required this.children,
  });

  @override
  Widget build(BuildContext context) => Container(
    padding: const EdgeInsets.all(24),
    decoration: BoxDecoration(
      color: AppTokens.cardBg,
      borderRadius: BorderRadius.circular(AppTokens.borderRadiusLg),
      border: Border.all(color: AppTokens.border),
    ),
    child: Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Row(
          children: [
            Container(
              padding: const EdgeInsets.all(8),
              decoration: BoxDecoration(
                color: iconColor.withValues(alpha: 0.1),
                borderRadius: BorderRadius.circular(8),
              ),
              child: Icon(icon, size: 18, color: iconColor),
            ),
            const SizedBox(width: 12),
            Text(
              title,
              style: GoogleFonts.inter(
                fontSize: 15,
                fontWeight: FontWeight.w600,
                color: AppTokens.textPrimary,
              ),
            ),
          ],
        ),
        const SizedBox(height: 20),
        ...children,
      ],
    ),
  );
}

class _Field extends StatelessWidget {
  final String label;
  final TextEditingController controller;
  final bool obscure;
  final int maxLines;
  final String? hint;
  const _Field(
    this.label,
    this.controller, {
    this.obscure = false,
    this.maxLines = 1,
    this.hint,
  });

  @override
  Widget build(BuildContext context) => Column(
    crossAxisAlignment: CrossAxisAlignment.start,
    children: [
      Text(
        label,
        style: GoogleFonts.inter(
          fontSize: 12,
          fontWeight: FontWeight.w500,
          color: AppTokens.textSecondary,
        ),
      ),
      const SizedBox(height: 6),
      TextField(
        controller: controller,
        obscureText: obscure,
        maxLines: obscure ? 1 : maxLines,
        style: GoogleFonts.inter(fontSize: 13, color: AppTokens.textPrimary),
        decoration: InputDecoration(
          isDense: true,
          hintText: hint,
          hintStyle: GoogleFonts.inter(
            fontSize: 11,
            color: AppTokens.textMuted,
          ),
        ),
      ),
    ],
  );
}

class _FeedbackBanner extends StatelessWidget {
  final String message;
  final bool isError;
  const _FeedbackBanner({required this.message, required this.isError});

  @override
  Widget build(BuildContext context) {
    final color = isError ? AppTokens.badgeOffline : AppTokens.badgeNeo4j;
    return Padding(
      padding: const EdgeInsets.only(bottom: 16),
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 10),
        decoration: BoxDecoration(
          color: color.withValues(alpha: 0.08),
          borderRadius: BorderRadius.circular(8),
          border: Border.all(color: color.withValues(alpha: 0.3)),
        ),
        child: Row(
          children: [
            Icon(
              isError ? Icons.error_outline : Icons.check_circle_outline,
              size: 16,
              color: color,
            ),
            const SizedBox(width: 10),
            Expanded(
              child: Text(
                message,
                style: GoogleFonts.inter(fontSize: 12, color: color),
              ),
            ),
          ],
        ),
      ),
    );
  }
}
