import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';
import '../core/theme.dart';

class AppSidebar extends StatelessWidget {
  final int selectedIndex;
  final ValueChanged<int> onItemSelected;

  const AppSidebar({
    super.key,
    required this.selectedIndex,
    required this.onItemSelected,
  });

  @override
  Widget build(BuildContext context) {
    return Container(
      width: AppTokens.sidebarWidth,
      color: AppTokens.sidebarBg,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          // ── Logo (fixe) ──────────────────────────────────────────────────
          Padding(
            padding: const EdgeInsets.fromLTRB(20, 24, 20, 4),
            child: Row(
              children: [
                Container(
                  width: 32, height: 32,
                  decoration: BoxDecoration(
                    gradient: const LinearGradient(colors: [AppTokens.accent, Color(0xFF818CF8)]),
                    borderRadius: BorderRadius.circular(8),
                  ),
                  child: const Icon(Icons.hub, color: Colors.white, size: 18),
                ),
                const SizedBox(width: 10),
                Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text('ManelCore', style: GoogleFonts.inter(fontSize: 15, fontWeight: FontWeight.w700, color: Colors.white)),
                    Text('ARIA Intelligence', style: GoogleFonts.inter(fontSize: 9, fontWeight: FontWeight.w500, letterSpacing: 1.5, color: AppTokens.sidebarSectionLabel)),
                  ],
                ),
              ],
            ),
          ),
          const SizedBox(height: 16),

          // ── Nav items (scrollable) ────────────────────────────────────────
          Expanded(
            child: SingleChildScrollView(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  _NavItem(icon: Icons.dashboard_outlined, label: 'Vue d\'ensemble', index: 0, selectedIndex: selectedIndex, onTap: onItemSelected),

                  const SizedBox(height: 4),
                  _SectionHeader('PIPELINE COMMERCIAL'),
                  _NavItem(icon: Icons.work_outline,          label: 'Opportunités',   index: 1, selectedIndex: selectedIndex, onTap: onItemSelected),
                  _NavItem(icon: Icons.search,                label: 'Recherche',      index: 2, selectedIndex: selectedIndex, onTap: onItemSelected),
                  _NavItem(icon: Icons.check_circle_outline,  label: 'Validations',    index: 3, selectedIndex: selectedIndex, onTap: onItemSelected),

                  const SizedBox(height: 4),
                  _SectionHeader('CONTACTS & RELATIONS'),
                  _NavItem(icon: Icons.people_outline,        label: 'Contacts CRM',   index: 4, selectedIndex: selectedIndex, onTap: onItemSelected),

                  const SizedBox(height: 4),
                  _SectionHeader('INTELLIGENCE IA'),
                  _NavItem(icon: Icons.smart_toy_outlined,    label: 'Assistant IA',   index: 5, selectedIndex: selectedIndex, onTap: onItemSelected),
                  _NavItem(icon: Icons.email_outlined,        label: 'Messagerie',     index: 6, selectedIndex: selectedIndex, onTap: onItemSelected),
                  _NavItem(icon: Icons.psychology_outlined,   label: 'Module RH',      index: 7, selectedIndex: selectedIndex, onTap: onItemSelected),

                  const SizedBox(height: 4),
                  _SectionHeader('SYSTÈME'),
                  _NavItem(icon: Icons.calendar_today_outlined, label: 'Planificateur', index: 8, selectedIndex: selectedIndex, onTap: onItemSelected),
                  _NavItem(icon: Icons.settings_outlined,     label: 'Configuration',  index: 9, selectedIndex: selectedIndex, onTap: onItemSelected),

                  const SizedBox(height: 8),
                ],
              ),
            ),
          ),

          // ── LLM Status (fixe en bas) ──────────────────────────────────────
          Padding(
            padding: const EdgeInsets.all(12),
            child: Container(
              padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
              decoration: BoxDecoration(
                color: AppTokens.accentBg,
                borderRadius: BorderRadius.circular(AppTokens.borderRadius),
                border: Border.all(color: AppTokens.accent.withValues(alpha: 0.3)),
              ),
              child: Row(children: [
                Container(width: 7, height: 7, decoration: const BoxDecoration(color: AppTokens.badgeNeo4j, shape: BoxShape.circle)),
                const SizedBox(width: 8),
                Expanded(child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                  Text('LLM En ligne', style: GoogleFonts.inter(fontSize: 11, fontWeight: FontWeight.w600, color: Colors.white)),
                  Text('google/gemma-4-e4b', style: GoogleFonts.inter(fontSize: 10, color: AppTokens.sidebarText)),
                ])),
              ]),
            ),
          ),
        ],
      ),
    );
  }
}

class _SectionHeader extends StatelessWidget {
  final String title;
  const _SectionHeader(this.title);

  @override
  Widget build(BuildContext context) => Padding(
    padding: const EdgeInsets.fromLTRB(20, 6, 20, 2),
    child: Text(title, style: GoogleFonts.inter(fontSize: 10, fontWeight: FontWeight.w600, letterSpacing: 1.2, color: AppTokens.sidebarSectionLabel)),
  );
}

class _NavItem extends StatefulWidget {
  final IconData icon;
  final String label;
  final int index, selectedIndex;
  final ValueChanged<int> onTap;

  const _NavItem({required this.icon, required this.label, required this.index, required this.selectedIndex, required this.onTap});

  @override
  State<_NavItem> createState() => _NavItemState();
}

class _NavItemState extends State<_NavItem> {
  bool _hovered = false;

  @override
  Widget build(BuildContext context) {
    final isSelected = widget.index == widget.selectedIndex;
    return MouseRegion(
      onEnter: (_) => setState(() => _hovered = true),
      onExit:  (_) => setState(() => _hovered = false),
      cursor: SystemMouseCursors.click,
      child: GestureDetector(
        onTap: () => widget.onTap(widget.index),
        child: AnimatedContainer(
          duration: const Duration(milliseconds: 150),
          margin: const EdgeInsets.symmetric(horizontal: 10, vertical: 1),
          padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
          decoration: BoxDecoration(
            color: isSelected ? AppTokens.accentBg : _hovered ? AppTokens.sidebarSurface : Colors.transparent,
            borderRadius: BorderRadius.circular(AppTokens.borderRadius),
            border: isSelected ? Border.all(color: AppTokens.accent.withValues(alpha: 0.25)) : null,
          ),
          child: Row(children: [
            Icon(widget.icon, size: 16, color: isSelected ? AppTokens.accent : AppTokens.sidebarText),
            const SizedBox(width: 10),
            Flexible(child: Text(widget.label, overflow: TextOverflow.ellipsis,
                style: GoogleFonts.inter(fontSize: 12, fontWeight: isSelected ? FontWeight.w600 : FontWeight.w400,
                    color: isSelected ? Colors.white : AppTokens.sidebarText))),
          ]),
        ),
      ),
    );
  }
}
