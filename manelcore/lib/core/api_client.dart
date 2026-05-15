import 'dart:async';
import 'dart:convert';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:http/http.dart' as http;

class ApiClient {
  static const String baseUrl = 'http://localhost:8000';

  // ── Health ─────────────────────────────────────────────────────────────────

  Future<Map<String, dynamic>> health() async {
    final r = await http.get(Uri.parse('$baseUrl/health'));
    if (r.statusCode == 200) return jsonDecode(r.body);
    throw Exception('Health check failed');
  }

  // ── Dashboard ──────────────────────────────────────────────────────────────

  Future<Map<String, dynamic>> getDashboardStats() async {
    final r = await http.get(Uri.parse('$baseUrl/dashboard/stats'));
    if (r.statusCode == 200) return jsonDecode(r.body);
    throw Exception('Stats failed');
  }

  // ── Config ─────────────────────────────────────────────────────────────────

  Future<Map<String, dynamic>> getConfig() async {
    final r = await http.get(Uri.parse('$baseUrl/config'));
    if (r.statusCode == 200) return jsonDecode(r.body);
    throw Exception('Config failed');
  }

  Future<void> updateConfig(Map<String, dynamic> config) async {
    final r = await http.post(
      Uri.parse('$baseUrl/config'),
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode(config),
    );
    if (r.statusCode != 200) {
      throw Exception('Update config failed: ${r.statusCode}');
    }
  }

  Future<Map<String, dynamic>> getSettings() async {
    final r = await http.get(Uri.parse('$baseUrl/settings'));
    if (r.statusCode == 200) return jsonDecode(r.body);
    throw Exception('Settings failed');
  }

  Future<void> updateSettings(Map<String, dynamic> settings) async {
    final r = await http.post(
      Uri.parse('$baseUrl/settings'),
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode(settings),
    );
    if (r.statusCode != 200) {
      throw Exception('Update settings failed: ${r.statusCode}');
    }
  }

  Future<Map<String, dynamic>> scrapeProfile(String url) async {
    final r = await http.post(
      Uri.parse('$baseUrl/scrape-profile'),
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode({'url': url}),
    );
    if (r.statusCode == 200) return jsonDecode(r.body);
    final detail = jsonDecode(r.body)['detail'] ?? 'Erreur ${r.statusCode}';
    throw Exception(detail);
  }

  Future<Map<String, dynamic>> eraseAllData() async {
    final r = await http.delete(Uri.parse('$baseUrl/data/erase'));
    if (r.statusCode == 200) return jsonDecode(r.body);
    throw Exception('Erase failed: ${r.statusCode}');
  }

  // ── Opportunities ──────────────────────────────────────────────────────────

  Future<List<dynamic>> getOpportunities({
    int limit = 50,
    String? statut,
  }) async {
    final params = {'limit': limit.toString(), 'statut': ?statut};
    final uri = Uri.parse(
      '$baseUrl/opportunities',
    ).replace(queryParameters: params);
    final r = await http.get(uri);
    if (r.statusCode == 200) {
      return (jsonDecode(r.body) as Map<String, dynamic>)['opportunities']
          as List;
    }
    throw Exception('Opportunities failed: ${r.statusCode}');
  }

  Future<Map<String, dynamic>> createOpportunity(
    Map<String, dynamic> data,
  ) async {
    final r = await http.post(
      Uri.parse('$baseUrl/opportunities'),
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode(data),
    );
    if (r.statusCode == 200) return jsonDecode(r.body);
    throw Exception('Create opportunity failed: ${r.statusCode}');
  }

  Future<Map<String, dynamic>> updateOpportunity(
    String id,
    Map<String, dynamic> data,
  ) async {
    final r = await http.put(
      Uri.parse('$baseUrl/opportunities/$id'),
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode(data),
    );
    if (r.statusCode == 200) return jsonDecode(r.body);
    throw Exception('Update opportunity failed: ${r.statusCode}');
  }

  Future<void> updateOpportunityStatus(String id, String statut) async {
    final r = await http.patch(
      Uri.parse('$baseUrl/opportunities/$id/status'),
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode({'statut': statut}),
    );
    if (r.statusCode != 200) throw Exception('Status update failed');
  }

  Future<void> sendOpportunityDraft(String id) async {
    final r = await http.post(Uri.parse('$baseUrl/opportunities/$id/send-draft'));
    if (r.statusCode != 200) throw Exception('Send draft failed');
  }

  Future<void> deleteOpportunity(String id) async {
    await http.delete(Uri.parse('$baseUrl/opportunities/$id'));
  }

  Future<void> deleteAllOpportunities() async {
    final r = await http.delete(Uri.parse('$baseUrl/opportunities'));
    if (r.statusCode != 200) throw Exception('Delete all failed');
  }

  // ── Agent explorer ─────────────────────────────────────────────────────────

  Future<Map<String, dynamic>> runAgent({
    String? profile,
    List<String>? sectors,
  }) async {
    final r = await http.post(
      Uri.parse('$baseUrl/agent/run'),
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode({'company_profile': ?profile, 'sectors': ?sectors}),
    );
    if (r.statusCode == 200) return jsonDecode(r.body);
    throw Exception('Run agent failed');
  }

  Future<Map<String, dynamic>> agentStatus() async {
    final r = await http.get(Uri.parse('$baseUrl/agent/status'));
    if (r.statusCode == 200) return jsonDecode(r.body);
    throw Exception('Agent status failed');
  }

  /// SSE stream — yields decoded JSON maps as they arrive
  Stream<Map<String, dynamic>> streamAgentEvents() async* {
    final request = http.Request('GET', Uri.parse('$baseUrl/agent/stream'));
    final client = http.Client();
    try {
      final response = await client.send(request);
      await for (final chunk
          in response.stream
              .transform(utf8.decoder)
              .transform(const LineSplitter())) {
        if (chunk.startsWith('data: ')) {
          final raw = chunk.substring(6).trim();
          if (raw.isEmpty) continue;
          try {
            yield jsonDecode(raw) as Map<String, dynamic>;
          } catch (_) {}
        }
      }
    } finally {
      client.close();
    }
  }

  // ── Contacts ───────────────────────────────────────────────────────────────

  Future<List<dynamic>> getContacts() async {
    final r = await http.get(Uri.parse('$baseUrl/contacts'));
    if (r.statusCode == 200) {
      return (jsonDecode(r.body) as Map<String, dynamic>)['contacts'] as List;
    }
    throw Exception('Contacts failed');
  }

  Future<Map<String, dynamic>> createContact(
    Map<String, dynamic> contact,
  ) async {
    final r = await http.post(
      Uri.parse('$baseUrl/contacts'),
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode(contact),
    );
    if (r.statusCode == 200) return jsonDecode(r.body);
    throw Exception('Create contact failed');
  }

  Future<Map<String, dynamic>> updateContact(
    String id,
    Map<String, dynamic> data,
  ) async {
    final r = await http.put(
      Uri.parse('$baseUrl/contacts/$id'),
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode(data),
    );
    if (r.statusCode == 200) return jsonDecode(r.body);
    throw Exception('Update contact failed');
  }

  Future<void> deleteContact(String id) async {
    await http.delete(Uri.parse('$baseUrl/contacts/$id'));
  }

  // ── Contact agent (brouillon email) ───────────────────────────────────────

  Future<Map<String, dynamic>> draftContact(
    String opportunityId,
    Map<String, dynamic> contactInfo,
  ) async {
    final r = await http.post(
      Uri.parse('$baseUrl/contact/draft'),
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode({
        'opportunity_id': opportunityId,
        'contact_info': contactInfo,
      }),
    );
    if (r.statusCode == 200) return jsonDecode(r.body);
    throw Exception('Draft failed');
  }

  Future<Map<String, dynamic>> approveContact(
    String threadId,
    bool approved,
  ) async {
    final r = await http.post(
      Uri.parse('$baseUrl/contact/approve'),
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode({'thread_id': threadId, 'approved': approved}),
    );
    if (r.statusCode == 200) return jsonDecode(r.body);
    throw Exception('Approve failed');
  }

  // ── Candidats (RH) ────────────────────────────────────────────────────────

  Future<List<dynamic>> getCandidats() async {
    final r = await http.get(Uri.parse('$baseUrl/candidats'));
    if (r.statusCode == 200) {
      return (jsonDecode(r.body) as Map<String, dynamic>)['candidats'] as List;
    }
    throw Exception('Candidats failed');
  }

  Future<Map<String, dynamic>> createCandidat(Map<String, dynamic> data) async {
    final r = await http.post(
      Uri.parse('$baseUrl/candidats'),
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode(data),
    );
    if (r.statusCode == 200) return jsonDecode(r.body);
    throw Exception('Create candidat failed');
  }

  Future<Map<String, dynamic>> updateCandidat(
    String id,
    Map<String, dynamic> data,
  ) async {
    final r = await http.put(
      Uri.parse('$baseUrl/candidats/$id'),
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode(data),
    );
    if (r.statusCode == 200) return jsonDecode(r.body);
    throw Exception('Update candidat failed');
  }

  Future<void> updateCandidatStatus(String id, String statut) async {
    await http.patch(
      Uri.parse('$baseUrl/candidats/$id/status'),
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode({'statut': statut}),
    );
  }

  Future<void> deleteCandidat(String id) async {
    await http.delete(Uri.parse('$baseUrl/candidats/$id'));
  }

  /// SSE stream of live extraction steps.
  Stream<Map<String, dynamic>> streamBrowserLive() async* {
    final request = http.Request(
      'GET',
      Uri.parse('$baseUrl/agent/live-stream'),
    );
    final client = http.Client();
    try {
      final response = await client.send(request);
      await for (final chunk
          in response.stream
              .transform(utf8.decoder)
              .transform(const LineSplitter())) {
        if (chunk.startsWith('data: ')) {
          final raw = chunk.substring(6).trim();
          if (raw.isEmpty) continue;
          try {
            final data = jsonDecode(raw) as Map<String, dynamic>;
            if (data['ping'] == true) continue;
            yield data;
          } catch (_) {}
        }
      }
    } finally {
      client.close();
    }
  }

  // ── Email agent ────────────────────────────────────────────────────────────

  Future<Map<String, dynamic>> checkInbox() async {
    final r = await http.post(
      Uri.parse('$baseUrl/email/check'),
      headers: {'Content-Type': 'application/json'},
    );
    if (r.statusCode == 200) return jsonDecode(r.body);
    throw Exception('Check inbox failed');
  }

  Future<Map<String, dynamic>> getInboxSummary() async {
    final r = await http.get(Uri.parse('$baseUrl/email/inbox'));
    if (r.statusCode == 200) return jsonDecode(r.body);
    throw Exception('Inbox summary failed');
  }

  Future<List<dynamic>> getEmailMessages() async {
    final r = await http.get(Uri.parse('$baseUrl/email/messages?limit=50'));
    if (r.statusCode == 200) {
      return (jsonDecode(r.body) as Map<String, dynamic>)['messages'] as List;
    }
    throw Exception('Email messages failed');
  }

  Future<void> sendEmail(String to, String subject, String body) async {
    final r = await http.post(
      Uri.parse('$baseUrl/email/send'),
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode({'to': to, 'subject': subject, 'body': body}),
    );
    if (r.statusCode != 200) {
      throw Exception('Send email failed: ${r.statusCode}');
    }
  }

  Future<Map<String, dynamic>> runMockAgent() async {
    final r = await http.post(
      Uri.parse('$baseUrl/agent/run/mock'),
      headers: {'Content-Type': 'application/json'},
    );
    if (r.statusCode == 200) return jsonDecode(r.body);
    throw Exception('Mock run failed');
  }

  // ── Chat LLM avec Graph RAG (SSE streaming) ───────────────────────────────

  /// Streams chat tokens. The first event may be a RAG metadata event
  /// (key 'rag') — the caller should handle it separately via [onRagMeta].
  Stream<String> chatStream(
    List<Map<String, dynamic>> messages, {
    double temperature = 0.4,
    bool useRag = true,
    void Function(Map<String, dynamic> meta)? onRagMeta,
  }) async* {
    final request = http.Request('POST', Uri.parse('$baseUrl/chat/stream'));
    request.headers['Content-Type'] = 'application/json';
    request.body = jsonEncode({
      'messages': messages,
      'temperature': temperature,
      'use_rag': useRag,
    });
    final client = http.Client();
    try {
      final response = await client.send(request);
      await for (final chunk
          in response.stream
              .transform(utf8.decoder)
              .transform(const LineSplitter())) {
        if (chunk.startsWith('data: ')) {
          final raw = chunk.substring(6).trim();
          if (raw == '[DONE]') return;
          try {
            final data = jsonDecode(raw) as Map<String, dynamic>;
            if (data.containsKey('rag')) {
              onRagMeta?.call(data['rag'] as Map<String, dynamic>);
              continue;
            }
            final content = data['content'] as String?;
            if (content != null && content.isNotEmpty) yield content;
          } catch (_) {}
        }
      }
    } finally {
      client.close();
    }
  }
}

// ── Riverpod providers ────────────────────────────────────────────────────────

final apiClientProvider = Provider<ApiClient>((_) => ApiClient());

final healthProvider = FutureProvider<Map<String, dynamic>>((ref) async {
  return ref.read(apiClientProvider).health();
});

final dashboardStatsProvider = FutureProvider<Map<String, dynamic>>((
  ref,
) async {
  return ref.read(apiClientProvider).getDashboardStats();
});

final opportunitiesProvider = FutureProvider.family<List<dynamic>, String?>((
  ref,
  statut,
) async {
  return ref.read(apiClientProvider).getOpportunities(statut: statut);
});

final contactsProvider = FutureProvider<List<dynamic>>((ref) async {
  return ref.read(apiClientProvider).getContacts();
});

final candidatsProvider = FutureProvider<List<dynamic>>((ref) async {
  return ref.read(apiClientProvider).getCandidats();
});

final agentStatusProvider = FutureProvider<Map<String, dynamic>>((ref) async {
  return ref.read(apiClientProvider).agentStatus();
});

final configProvider = FutureProvider<Map<String, dynamic>>((ref) async {
  return ref.read(apiClientProvider).getConfig();
});
