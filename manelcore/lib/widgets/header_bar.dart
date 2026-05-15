import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';
import '../../core/theme.dart';

class AppHeaderBar extends StatelessWidget {
  final String title;
  final String subtitle;
  final List<Widget> actions;

  const AppHeaderBar({
    super.key,
    required this.title,
    this.subtitle = '',
    this.actions = const [],
  });

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 12),
      decoration: const BoxDecoration(
        color: AppTokens.cardBg,
        border: Border(bottom: BorderSide(color: AppTokens.border)),
      ),
      child: Row(
        children: [
          // Title — shrinks if space is tight
          Flexible(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              mainAxisSize: MainAxisSize.min,
              children: [
                Text(title,
                    overflow: TextOverflow.ellipsis,
                    style: GoogleFonts.inter(fontSize: 18, fontWeight: FontWeight.w700, color: AppTokens.textPrimary)),
                if (subtitle.isNotEmpty)
                  Text(subtitle,
                      overflow: TextOverflow.ellipsis,
                      style: GoogleFonts.inter(fontSize: 11, color: AppTokens.textMuted)),
              ],
            ),
          ),

          // Actions + status badges (scroll horizontally if needed)
          if (actions.isNotEmpty || true)
            Flexible(
              flex: 0,
              child: SingleChildScrollView(
                scrollDirection: Axis.horizontal,
                child: Row(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    const SizedBox(width: 12),
                    ...actions,
                    if (actions.isNotEmpty) const SizedBox(width: 12),
                    _StatusBadge(label: 'Neo4j', color: AppTokens.badgeNeo4j),
                    const SizedBox(width: 6),
                    _StatusBadge(label: 'LLM',   color: AppTokens.badgeLlm),
                    const SizedBox(width: 8),
                    IconButton(
                      onPressed: () {},
                      icon: const Icon(Icons.notifications_none_outlined),
                      iconSize: 18,
                      color: AppTokens.textSecondary,
                      padding: EdgeInsets.zero,
                      constraints: const BoxConstraints(maxWidth: 32, maxHeight: 32),
                    ),
                    const SizedBox(width: 6),
                    CircleAvatar(
                      radius: 14,
                      backgroundColor: AppTokens.accent,
                      child: Text('M', style: GoogleFonts.inter(fontSize: 12, fontWeight: FontWeight.w600, color: Colors.white)),
                    ),
                  ],
                ),
              ),
            ),
        ],
      ),
    );
  }
}

class _StatusBadge extends StatelessWidget {
  final String label;
  final Color color;
  const _StatusBadge({required this.label, required this.color});

  @override
  Widget build(BuildContext context) => Container(
    padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
    decoration: BoxDecoration(border: Border.all(color: color.withValues(alpha: 0.4)), borderRadius: BorderRadius.circular(20)),
    child: Row(mainAxisSize: MainAxisSize.min, children: [
      Icon(Icons.circle, size: 6, color: color),
      const SizedBox(width: 5),
      Text(label, style: GoogleFonts.inter(fontSize: 10, fontWeight: FontWeight.w600, color: color)),
    ]),
  );
}
