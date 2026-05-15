import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';
import '../../../../core/theme.dart';
import '../../../../widgets/header_bar.dart';

class PlanificateurPage extends StatefulWidget {
  const PlanificateurPage({super.key});

  @override
  State<PlanificateurPage> createState() => _PlanificateurPageState();
}

class _PlanificateurPageState extends State<PlanificateurPage> {
  final List<_Schedule> _schedules = [
    _Schedule('Veille SEAO', Icons.travel_explore, 'Chaque lundi à 8h00', true, const Color(0xFF38BDF8)),
    _Schedule('Veille LinkedIn', Icons.work_outline, 'Chaque mercredi à 9h00', false, const Color(0xFF0A66C2)),
    _Schedule('Lecture emails', Icons.email_outlined, 'Toutes les 30 min', true, const Color(0xFFF59E0B)),
    _Schedule('Rapport hebdo', Icons.bar_chart, 'Chaque vendredi à 17h00', true, const Color(0xFF10B981)),
    _Schedule('Nettoyage données', Icons.cleaning_services_outlined, 'Chaque 1er du mois', false, const Color(0xFF8B5CF6)),
  ];

  @override
  Widget build(BuildContext context) {
    return Column(children: [
      AppHeaderBar(
        title: 'Planificateur',
        subtitle: 'Automatisation et tâches récurrentes',
        actions: [
          ElevatedButton.icon(
            onPressed: () => _showAddDialog(context),
            icon: const Icon(Icons.add, size: 16),
            label: const Text('Nouvelle tâche'),
            style: ElevatedButton.styleFrom(
              backgroundColor: AppTokens.accent, foregroundColor: Colors.white,
              shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(8)),
              padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 10),
            ),
          ),
        ],
      ),
      Expanded(
        child: SingleChildScrollView(
          padding: const EdgeInsets.all(28),
          child: Column(children: [
            // Status row
            Row(children: [
              _StatBox('Tâches actives', '${_schedules.where((s) => s.enabled).length}', AppTokens.badgeNeo4j, Icons.check_circle_outline),
              const SizedBox(width: 16),
              _StatBox('Tâches pausées', '${_schedules.where((s) => !s.enabled).length}', AppTokens.textMuted, Icons.pause_circle_outline),
              const SizedBox(width: 16),
              _StatBox('Prochaine exécution', 'Lun 8h00', AppTokens.accent, Icons.schedule),
            ]),
            const SizedBox(height: 24),
            // Task list
            ...List.generate(_schedules.length, (i) => _ScheduleCard(
              schedule: _schedules[i],
              onToggle: (v) => setState(() => _schedules[i] = _schedules[i].withEnabled(v)),
            )),
          ]),
        ),
      ),
    ]);
  }

  void _showAddDialog(BuildContext context) {
    showDialog(
      context: context,
      builder: (_) => AlertDialog(
        title: Text('Nouvelle tâche planifiée', style: GoogleFonts.inter(fontSize: 15, fontWeight: FontWeight.w600)),
        content: SizedBox(width: 380, child: Column(mainAxisSize: MainAxisSize.min, children: [
          TextField(decoration: const InputDecoration(labelText: 'Nom de la tâche', isDense: true),
              style: GoogleFonts.inter(fontSize: 13)),
          const SizedBox(height: 12),
          TextField(decoration: const InputDecoration(labelText: 'Expression cron (ex: 0 8 * * 1)', isDense: true),
              style: GoogleFonts.jetBrainsMono(fontSize: 13)),
        ])),
        actions: [
          TextButton(onPressed: () => Navigator.pop(context), child: const Text('Annuler')),
          ElevatedButton(onPressed: () => Navigator.pop(context), child: const Text('Créer')),
        ],
      ),
    );
  }
}

class _Schedule {
  final String name, cronLabel;
  final IconData icon;
  final bool enabled;
  final Color color;
  const _Schedule(this.name, this.icon, this.cronLabel, this.enabled, this.color);
  _Schedule withEnabled(bool v) => _Schedule(name, icon, cronLabel, v, color);
}

class _StatBox extends StatelessWidget {
  final String label, value;
  final Color color;
  final IconData icon;
  const _StatBox(this.label, this.value, this.color, this.icon);

  @override
  Widget build(BuildContext context) => Expanded(
    child: Container(
      padding: const EdgeInsets.all(18),
      decoration: BoxDecoration(
        color: AppTokens.cardBg, borderRadius: BorderRadius.circular(AppTokens.borderRadiusLg),
        border: Border.all(color: AppTokens.border),
      ),
      child: Row(children: [
        Icon(icon, color: color, size: 22),
        const SizedBox(width: 14),
        Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Text(value, style: GoogleFonts.inter(fontSize: 22, fontWeight: FontWeight.w700, color: AppTokens.textPrimary)),
          Text(label, style: GoogleFonts.inter(fontSize: 11, color: AppTokens.textMuted)),
        ]),
      ]),
    ),
  );
}

class _ScheduleCard extends StatelessWidget {
  final _Schedule schedule;
  final ValueChanged<bool> onToggle;
  const _ScheduleCard({required this.schedule, required this.onToggle});

  @override
  Widget build(BuildContext context) => Container(
    margin: const EdgeInsets.only(bottom: 10),
    padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 16),
    decoration: BoxDecoration(
      color: AppTokens.cardBg, borderRadius: BorderRadius.circular(AppTokens.borderRadiusLg),
      border: Border.all(color: schedule.enabled ? schedule.color.withValues(alpha: 0.3) : AppTokens.border),
    ),
    child: Row(children: [
      Container(
        padding: const EdgeInsets.all(10),
        decoration: BoxDecoration(
          color: schedule.color.withValues(alpha: 0.08), borderRadius: BorderRadius.circular(10),
        ),
        child: Icon(schedule.icon, color: schedule.color, size: 20),
      ),
      const SizedBox(width: 16),
      Expanded(child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Text(schedule.name, style: GoogleFonts.inter(fontSize: 13, fontWeight: FontWeight.w600, color: AppTokens.textPrimary)),
        const SizedBox(height: 2),
        Text(schedule.cronLabel, style: GoogleFonts.inter(fontSize: 11, color: AppTokens.textMuted)),
      ])),
      Container(
        padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
        decoration: BoxDecoration(
          color: (schedule.enabled ? AppTokens.badgeNeo4j : AppTokens.textMuted).withValues(alpha: 0.08),
          borderRadius: BorderRadius.circular(12),
        ),
        child: Text(schedule.enabled ? 'Actif' : 'Pausé',
            style: GoogleFonts.inter(fontSize: 11, fontWeight: FontWeight.w600,
                color: schedule.enabled ? AppTokens.badgeNeo4j : AppTokens.textMuted)),
      ),
      const SizedBox(width: 12),
      Switch(
        value: schedule.enabled,
        onChanged: onToggle,
        activeThumbColor: AppTokens.accent,
        materialTapTargetSize: MaterialTapTargetSize.shrinkWrap,
      ),
    ]),
  );
}
