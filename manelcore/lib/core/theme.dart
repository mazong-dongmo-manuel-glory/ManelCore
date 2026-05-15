import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';

/// Design tokens matching the ManelCore desktop screenshot.
class AppTokens {
  // ── Sidebar (dark navy) ──
  static const Color sidebarBg = Color(0xFF0B1120);
  static const Color sidebarSurface = Color(0xFF111827);
  static const Color sidebarText = Color(0xFF94A3B8);
  static const Color sidebarTextActive = Colors.white;
  static const Color sidebarSectionLabel = Color(0xFF4B5563);

  // ── Accent / brand ──
  static const Color accent = Color(0xFF38BDF8); // cyan-blue
  static const Color accentBg = Color(0xFF0E2A3D); // selected item bg
  static const Color accentIndicator = Color(0xFF38BDF8);

  // ── Content area (light) ──
  static const Color contentBg = Color(0xFFF8FAFC);
  static const Color cardBg = Colors.white;
  static const Color border = Color(0xFFE2E8F0);
  static const Color divider = Color(0xFFF1F5F9);

  // ── Text on light ──
  static const Color textPrimary = Color(0xFF0F172A);
  static const Color textSecondary = Color(0xFF64748B);
  static const Color textMuted = Color(0xFF94A3B8);

  // ── Status badges ──
  static const Color badgeNeo4j = Color(0xFF10B981); // green
  static const Color badgeLlm = Color(0xFF38BDF8);    // cyan
  static const Color badgeOffline = Color(0xFFEF4444); // red

  // ── Sizing ──
  static const double sidebarWidth = 220.0;
  static const double borderRadius = 8.0;
  static const double borderRadiusLg = 12.0;
}

class AppTheme {
  static ThemeData get lightTheme {
    final base = ThemeData.light(useMaterial3: true);
    return base.copyWith(
      scaffoldBackgroundColor: AppTokens.contentBg,
      primaryColor: AppTokens.accent,
      dividerColor: AppTokens.border,
      colorScheme: const ColorScheme.light(
        primary: AppTokens.accent,
        secondary: AppTokens.accent,
        surface: AppTokens.cardBg,
      ),
      textTheme: GoogleFonts.interTextTheme(base.textTheme).copyWith(
        headlineLarge: GoogleFonts.inter(
          fontSize: 24,
          fontWeight: FontWeight.w700,
          color: AppTokens.textPrimary,
        ),
        titleLarge: GoogleFonts.inter(
          fontSize: 16,
          fontWeight: FontWeight.w600,
          color: AppTokens.textPrimary,
        ),
        titleMedium: GoogleFonts.inter(
          fontSize: 14,
          fontWeight: FontWeight.w600,
          color: AppTokens.textPrimary,
        ),
        bodyMedium: GoogleFonts.inter(
          fontSize: 13,
          fontWeight: FontWeight.w400,
          color: AppTokens.textSecondary,
        ),
        bodySmall: GoogleFonts.inter(
          fontSize: 11,
          fontWeight: FontWeight.w400,
          color: AppTokens.textMuted,
        ),
        labelSmall: GoogleFonts.inter(
          fontSize: 10,
          fontWeight: FontWeight.w600,
          letterSpacing: 1.2,
          color: AppTokens.sidebarSectionLabel,
        ),
      ),
      cardTheme: CardThemeData(
        color: AppTokens.cardBg,
        elevation: 0,
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(AppTokens.borderRadiusLg),
          side: const BorderSide(color: AppTokens.border, width: 1),
        ),
      ),
      inputDecorationTheme: InputDecorationTheme(
        filled: true,
        fillColor: AppTokens.cardBg,
        contentPadding: const EdgeInsets.symmetric(horizontal: 16, vertical: 14),
        border: OutlineInputBorder(
          borderRadius: BorderRadius.circular(AppTokens.borderRadius),
          borderSide: const BorderSide(color: AppTokens.border),
        ),
        enabledBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(AppTokens.borderRadius),
          borderSide: const BorderSide(color: AppTokens.border),
        ),
        focusedBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(AppTokens.borderRadius),
          borderSide: const BorderSide(color: AppTokens.accent, width: 2),
        ),
      ),
    );
  }
}
