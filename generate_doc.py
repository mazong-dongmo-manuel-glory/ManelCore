"""
ManelCore — Générateur de documentation technique PDF
"""
from __future__ import annotations

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import (
    HRFlowable,
    Image,
    KeepTogether,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

# ── Palette ────────────────────────────────────────────────────────────────────
DARK_BG      = colors.HexColor("#0f172a")
ACCENT       = colors.HexColor("#6366f1")
ACCENT_LIGHT = colors.HexColor("#818cf8")
NEO4J        = colors.HexColor("#4ade80")
TEXT_PRIMARY = colors.HexColor("#1e293b")
TEXT_MUTED   = colors.HexColor("#64748b")
BOX_BG       = colors.HexColor("#f1f5f9")
BOX_BORDER   = colors.HexColor("#e2e8f0")
CODE_BG      = colors.HexColor("#f8fafc")

W, H = A4

# ── Styles ─────────────────────────────────────────────────────────────────────
def make_styles() -> dict:
    base = getSampleStyleSheet()

    def ps(name, **kw) -> ParagraphStyle:
        return ParagraphStyle(name, **kw)

    return {
        "cover_title": ps("ct",
            fontSize=36, textColor=colors.white, alignment=TA_CENTER,
            fontName="Helvetica-Bold", spaceAfter=8, leading=42),
        "cover_sub": ps("cs",
            fontSize=16, textColor=ACCENT_LIGHT, alignment=TA_CENTER,
            fontName="Helvetica", spaceAfter=6, leading=20),
        "cover_meta": ps("cm",
            fontSize=11, textColor=colors.HexColor("#94a3b8"), alignment=TA_CENTER,
            fontName="Helvetica", spaceAfter=4, leading=15),

        "h1": ps("h1",
            fontSize=22, textColor=DARK_BG, fontName="Helvetica-Bold",
            spaceBefore=28, spaceAfter=10, leading=28,
            borderPad=4),
        "h2": ps("h2",
            fontSize=15, textColor=ACCENT, fontName="Helvetica-Bold",
            spaceBefore=18, spaceAfter=6, leading=20),
        "h3": ps("h3",
            fontSize=12, textColor=TEXT_PRIMARY, fontName="Helvetica-Bold",
            spaceBefore=12, spaceAfter=4, leading=16),

        "body": ps("body",
            fontSize=10, textColor=TEXT_PRIMARY, fontName="Helvetica",
            spaceBefore=3, spaceAfter=5, leading=15, alignment=TA_JUSTIFY),
        "muted": ps("muted",
            fontSize=9, textColor=TEXT_MUTED, fontName="Helvetica",
            spaceAfter=4, leading=13),
        "bullet": ps("bullet",
            fontSize=10, textColor=TEXT_PRIMARY, fontName="Helvetica",
            leftIndent=14, spaceAfter=3, leading=14,
            bulletIndent=4, bulletText="•"),
        "code": ps("code",
            fontSize=8.5, textColor=colors.HexColor("#334155"),
            fontName="Courier", leading=12, spaceAfter=4,
            leftIndent=10, rightIndent=10,
            backColor=CODE_BG),
        "badge": ps("badge",
            fontSize=8, textColor=colors.white, fontName="Helvetica-Bold",
            alignment=TA_CENTER),
        "toc_entry": ps("toc",
            fontSize=10, textColor=TEXT_PRIMARY, fontName="Helvetica",
            spaceAfter=4, leading=14),
        "toc_h": ps("toch",
            fontSize=11, textColor=ACCENT, fontName="Helvetica-Bold",
            spaceAfter=2, leading=15),
        "caption": ps("caption",
            fontSize=8, textColor=TEXT_MUTED, fontName="Helvetica-Oblique",
            alignment=TA_CENTER, spaceAfter=6),
    }


# ── Helpers ─────────────────────────────────────────────────────────────────────
def hr(color=BOX_BORDER, width=1, space=8) -> HRFlowable:
    return HRFlowable(width="100%", thickness=width, color=color,
                      spaceAfter=space, spaceBefore=space)

def section_box(content: list, bg=BOX_BG, border=BOX_BORDER):
    """Wrap content in a shaded rounded box via a 1-cell table."""
    t = Table([[content]], colWidths=[W - 4*cm])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (-1,-1), bg),
        ("BOX",        (0,0), (-1,-1), 0.8, border),
        ("ROUNDEDCORNERS", [6]),
        ("TOPPADDING",    (0,0), (-1,-1), 10),
        ("BOTTOMPADDING", (0,0), (-1,-1), 10),
        ("LEFTPADDING",   (0,0), (-1,-1), 14),
        ("RIGHTPADDING",  (0,0), (-1,-1), 14),
    ]))
    return t

def kv_table(rows: list[tuple[str, str]], s) -> Table:
    data = [[Paragraph(f"<b>{k}</b>", s["muted"]), Paragraph(v, s["body"])] for k, v in rows]
    t = Table(data, colWidths=[4.5*cm, 11.5*cm])
    t.setStyle(TableStyle([
        ("VALIGN",        (0,0), (-1,-1), "TOP"),
        ("ROWBACKGROUNDS",(0,0), (-1,-1), [colors.white, BOX_BG]),
        ("LINEBELOW",     (0,0), (-1,-1), 0.4, BOX_BORDER),
        ("TOPPADDING",    (0,0), (-1,-1), 5),
        ("BOTTOMPADDING", (0,0), (-1,-1), 5),
        ("LEFTPADDING",   (0,0), (-1,-1), 8),
    ]))
    return t

def color_table(headers: list[str], rows: list[list], s) -> Table:
    col_w = (W - 4*cm) / len(headers)
    hdr = [Paragraph(f"<b>{h}</b>", ParagraphStyle("th",
        fontSize=9, textColor=colors.white, fontName="Helvetica-Bold",
        alignment=TA_CENTER)) for h in headers]
    data = [hdr] + [
        [Paragraph(str(c), s["muted"]) for c in row]
        for row in rows
    ]
    t = Table(data, colWidths=[col_w]*len(headers))
    t.setStyle(TableStyle([
        ("BACKGROUND",    (0,0), (-1,0),  DARK_BG),
        ("ROWBACKGROUNDS",(0,1), (-1,-1), [colors.white, BOX_BG]),
        ("LINEBELOW",     (0,0), (-1,-1), 0.4, BOX_BORDER),
        ("TOPPADDING",    (0,0), (-1,-1), 6),
        ("BOTTOMPADDING", (0,0), (-1,-1), 6),
        ("LEFTPADDING",   (0,0), (-1,-1), 8),
        ("VALIGN",        (0,0), (-1,-1), "MIDDLE"),
    ]))
    return t


# ── Cover page callback ─────────────────────────────────────────────────────────
def cover_canvas(canvas, doc):
    canvas.saveState()
    # Dark background
    canvas.setFillColor(DARK_BG)
    canvas.rect(0, 0, W, H, fill=1, stroke=0)
    # Accent bar top
    canvas.setFillColor(ACCENT)
    canvas.rect(0, H-6, W, 6, fill=1, stroke=0)
    # Decorative circle
    canvas.setFillColor(colors.HexColor("#1e293b"))
    canvas.circle(W - 1.5*cm, H/2, 7*cm, fill=1, stroke=0)
    canvas.setFillColor(colors.HexColor("#253047"))
    canvas.circle(W, H*0.3, 5*cm, fill=1, stroke=0)
    # Footer line
    canvas.setFillColor(colors.HexColor("#334155"))
    canvas.rect(0, 0, W, 1.5*cm, fill=1, stroke=0)
    canvas.setFillColor(colors.HexColor("#94a3b8"))
    canvas.setFont("Helvetica", 8)
    canvas.drawCentredString(W/2, 0.55*cm, "CONFIDENTIEL — Usage interne uniquement")
    canvas.restoreState()

def normal_canvas(canvas, doc):
    canvas.saveState()
    # Header accent bar
    canvas.setFillColor(ACCENT)
    canvas.rect(0, H - 0.8*cm, W, 0.8*cm, fill=1, stroke=0)
    canvas.setFillColor(colors.white)
    canvas.setFont("Helvetica-Bold", 8)
    canvas.drawString(1.5*cm, H - 0.55*cm, "ManelCore")
    canvas.setFont("Helvetica", 8)
    canvas.drawRightString(W - 1.5*cm, H - 0.55*cm, "Documentation Technique — 2025")
    # Footer
    canvas.setFillColor(BOX_BORDER)
    canvas.rect(0, 0, W, 0.8*cm, fill=1, stroke=0)
    canvas.setFillColor(TEXT_MUTED)
    canvas.setFont("Helvetica", 8)
    canvas.drawString(1.5*cm, 0.28*cm, "© 2025 Manel Canada — Confidentiel")
    canvas.drawRightString(W - 1.5*cm, 0.28*cm, f"Page {doc.page}")
    canvas.restoreState()


# ── Content builder ─────────────────────────────────────────────────────────────
def build_content(s: dict) -> list:
    story = []
    P = lambda txt, style="body": Paragraph(txt, s[style])
    B = lambda txt: Paragraph(f"• {txt}", s["bullet"])

    # ── Cover ──────────────────────────────────────────────────────────────────
    story.append(Spacer(1, 5.5*cm))
    story.append(P("ManelCore", "cover_title"))
    story.append(P("Plateforme IA de Développement des Affaires", "cover_sub"))
    story.append(Spacer(1, 0.4*cm))
    story.append(P("Documentation Technique Complète", "cover_meta"))
    story.append(P("Version 1.0 — Mai 2025", "cover_meta"))
    story.append(P("Manel Canada | zebazemadric@icloud.com", "cover_meta"))
    story.append(Spacer(1, 3*cm))

    badges = [
        ("Python 3.14", "#3b82f6"),
        ("FastAPI", "#10b981"),
        ("LangGraph", "#8b5cf6"),
        ("Neo4j", "#4ade80"),
        ("Flutter", "#06b6d4"),
        ("LM Studio", "#f59e0b"),
    ]
    badge_data = [[
        Paragraph(f"<font color='white'><b>{label}</b></font>",
                  ParagraphStyle("b", fontSize=8, fontName="Helvetica-Bold",
                                 textColor=colors.white, alignment=TA_CENTER))
        for label, _ in badges
    ]]
    bt = Table(badge_data, colWidths=[(W-4*cm)/len(badges)]*len(badges))
    bt.setStyle(TableStyle([
        ("BACKGROUND", (i,0), (i,0), colors.HexColor(badges[i][1]))
        for i in range(len(badges))
    ] + [
        ("TOPPADDING",    (0,0), (-1,-1), 5),
        ("BOTTOMPADDING", (0,0), (-1,-1), 5),
        ("ROUNDEDCORNERS", [4]),
    ]))
    story.append(bt)
    story.append(PageBreak())

    # ── Table des matières ─────────────────────────────────────────────────────
    story.append(P("Table des matières", "h1"))
    story.append(hr(ACCENT, 2, 12))

    toc = [
        ("1.", "Vue d'ensemble du projet", "3"),
        ("2.", "Architecture système", "4"),
        ("3.", "Backend — FastAPI & Python", "5"),
        ("4.", "Agents IA — LangGraph", "7"),
        ("5.", "Base de données — Neo4j Graph", "10"),
        ("6.", "Services métier", "12"),
        ("7.", "Frontend — Flutter", "15"),
        ("8.", "API REST — Référence des endpoints", "17"),
        ("9.", "Infrastructure & déploiement", "19"),
        ("10.", "Flux de données end-to-end", "20"),
        ("11.", "Configuration & variables d'environnement", "21"),
        ("12.", "Sécurité & bonnes pratiques", "22"),
        ("13.", "Roadmap & évolutions", "23"),
    ]
    for num, title, page in toc:
        row = Table(
            [[Paragraph(num, s["toc_h"]),
              Paragraph(title, s["toc_entry"]),
              Paragraph(page, s["muted"])]],
            colWidths=[1.2*cm, 12.5*cm, 1.5*cm]
        )
        row.setStyle(TableStyle([
            ("VALIGN",        (0,0), (-1,-1), "MIDDLE"),
            ("LINEBELOW",     (0,0), (-1,-1), 0.3, BOX_BORDER),
            ("TOPPADDING",    (0,0), (-1,-1), 5),
            ("BOTTOMPADDING", (0,0), (-1,-1), 5),
        ]))
        story.append(row)
    story.append(PageBreak())

    # ══════════════════════════════════════════════════════════════════════════
    # 1. Vue d'ensemble
    # ══════════════════════════════════════════════════════════════════════════
    story.append(P("1. Vue d'ensemble du projet", "h1"))
    story.append(hr(ACCENT, 2, 12))
    story.append(P(
        "ManelCore est une plateforme intelligente de développement des affaires conçue pour "
        "automatiser la veille d'opportunités (appels d'offres, emplois), la gestion des contacts, "
        "la rédaction et l'envoi de courriels professionnels, ainsi que la gestion des candidatures "
        "RH — le tout piloté par des agents IA fonctionnant entièrement en local grâce à LM Studio.",
        "body"
    ))
    story.append(Spacer(1, 0.3*cm))

    story.append(P("Objectifs stratégiques", "h2"))
    for item in [
        "<b>Veille automatisée :</b> scanner SEAO (appels d'offres québécois), LinkedIn Jobs et Indeed pour identifier en continu les opportunités pertinentes.",
        "<b>Scoring IA :</b> classer chaque opportunité par pertinence métier grâce à un LLM local (Gemma 4 via LM Studio).",
        "<b>Outreach automatisé :</b> générer des courriels de prospection personnalisés et les soumettre à validation humaine avant envoi.",
        "<b>Graph intelligence :</b> stocker toutes les entités (entreprises, contacts, opportunités, messages) dans Neo4j pour exploiter les relations.",
        "<b>Interface unifiée :</b> une application Flutter cross-platform (macOS, Linux, iOS, Android) comme tableau de bord centralisé.",
        "<b>IA conversationnelle :</b> un chatbot ARIA (Graph RAG) pour interroger les données de l'entreprise en langage naturel.",
        "<b>Intégrations :</b> Telegram bot pour les notifications push, agent email IMAP pour la réponse automatique.",
    ]:
        story.append(B(item))

    story.append(Spacer(1, 0.5*cm))
    story.append(P("Principes de conception", "h2"))
    overview_data = [
        ["Principe", "Application concrète"],
        ["Local-first", "LM Studio — aucune donnée ne quitte l'infrastructure"],
        ["Human-in-the-loop", "Validation obligatoire avant envoi de courriel ou acceptation d'opportunité"],
        ["Graph-native", "Neo4j comme source de vérité relationnelle plutôt qu'une BDD relationnelle plate"],
        ["Streaming SSE", "Retour temps réel de l'avancement des agents vers le frontend"],
        ["Modulaire", "Agents LangGraph indépendants composables selon le flux métier"],
    ]
    t = color_table(overview_data[0], overview_data[1:], s)
    story.append(t)
    story.append(PageBreak())

    # ══════════════════════════════════════════════════════════════════════════
    # 2. Architecture
    # ══════════════════════════════════════════════════════════════════════════
    story.append(P("2. Architecture système", "h1"))
    story.append(hr(ACCENT, 2, 12))

    story.append(P(
        "ManelCore suit une architecture <b>client-serveur découplée</b> avec un backend Python "
        "asynchrone, une base de données graphe et un frontend Flutter. Les agents IA s'exécutent "
        "comme des processus async dans le même processus uvicorn.",
        "body"
    ))
    story.append(Spacer(1, 0.3*cm))

    story.append(P("Diagramme des couches", "h2"))
    arch_data = [
        ["Couche", "Technologie", "Rôle"],
        ["Présentation", "Flutter + Riverpod", "UI cross-platform, état réactif, SSE consumer"],
        ["API Gateway", "FastAPI (uvicorn)", "Exposition REST + SSE, orchestration des agents"],
        ["Agents IA", "LangGraph + LangChain", "Graphes d'état pour Explorer et Contact agents"],
        ["LLM Runtime", "LM Studio (Gemma 4)", "Inférence locale OpenAI-compatible sur :1234"],
        ["Persistance", "Neo4j Desktop", "Graphe de connaissances sur bolt://localhost:7687"],
        ["Messaging", "SMTP/IMAP + Telegram", "Email sortant/entrant et notifications push"],
        ["RAG", "RagService (Neo4j)", "Récupération contextuelle avant chaque appel LLM chat"],
    ]
    story.append(color_table(arch_data[0], arch_data[1:], s))

    story.append(Spacer(1, 0.5*cm))
    story.append(P("Flux de communication inter-composants", "h2"))
    story.append(P(
        "Le frontend Flutter communique exclusivement via HTTP/SSE avec le backend FastAPI sur le "
        "port <b>8000</b>. Les agents LangGraph s'exécutent dans le même processus et "
        "communiquent avec Neo4j via Bolt (<b>7687</b>) et avec le LLM via l'API OpenAI-compatible "
        "de LM Studio sur le port <b>1234</b>. "
        "Les services email (IMAP/SMTP) et Telegram fonctionnent en tâches asyncio de fond.",
        "body"
    ))

    story.append(Spacer(1, 0.3*cm))
    stack_data = [
        ["Port", "Service", "Protocole", "Description"],
        ["8000", "FastAPI Backend", "HTTP / SSE", "API principale + streaming temps réel"],
        ["7687", "Neo4j Desktop", "Bolt", "Base de données graphe"],
        ["1234", "LM Studio", "HTTP OpenAI API", "Inférence LLM locale (Gemma 4)"],
        ["IMAP/SMTP", "Serveur mail", "TLS", "Lecture/envoi des courriels"],
        ["Telegram", "Bot API", "HTTPS Webhook", "Notifications et commandes"],
    ]
    story.append(color_table(stack_data[0], stack_data[1:], s))
    story.append(PageBreak())

    # ══════════════════════════════════════════════════════════════════════════
    # 3. Backend
    # ══════════════════════════════════════════════════════════════════════════
    story.append(P("3. Backend — FastAPI & Python", "h1"))
    story.append(hr(ACCENT, 2, 12))

    story.append(P("Structure des fichiers", "h2"))
    for line in [
        "backend/",
        "├── main.py                   # Point d'entrée uvicorn",
        "├── .env                      # Variables d'environnement (secrets)",
        "├── requirements.txt",
        "└── app/",
        "    ├── api/",
        "    │   └── main.py           # Tous les endpoints FastAPI",
        "    ├── agents/",
        "    │   ├── contact/          # Agent de rédaction email",
        "    │   │   ├── graph.py",
        "    │   │   ├── nodes.py",
        "    │   │   └── state.py",
        "    │   └── explorer/         # Agent de veille d'opportunités",
        "    │       ├── graph.py",
        "    │       ├── nodes.py",
        "    │       └── state.py",
        "    ├── database/",
        "    │   ├── connection.py     # Driver Neo4j",
        "    │   ├── models.py         # Dataclasses (Entreprise, Contact…)",
        "    │   ├── queries.py        # Contraintes Cypher",
        "    │   ├── repository.py     # CRUD Neo4j",
        "    │   └── schema.py         # Initialisation et seed",
        "    └── services/",
        "        ├── email_agent.py    # Agent IMAP + réponse auto",
        "        ├── mailer.py         # SMTP + IMAP client",
        "        ├── opportunity_crawler.py  # LinkedIn + Indeed",
        "        ├── rag_service.py    # Graph RAG pour le chat",
        "        ├── seao_api.py       # API publique SEAO",
        "        ├── settings_service.py  # Persistance JSON des settings",
        "        └── telegram_service.py  # Bot Telegram polling",
    ]:
        story.append(Paragraph(line, s["code"]))

    story.append(Spacer(1, 0.4*cm))
    story.append(P("Démarrage du serveur", "h2"))
    for line in [
        "# Depuis la racine du projet",
        "cd backend",
        "python main.py",
        "# ou directement :",
        "uvicorn app.api.main:app --reload --port 8000",
    ]:
        story.append(Paragraph(line, s["code"]))

    story.append(Spacer(1, 0.4*cm))
    story.append(P("Cycle de démarrage FastAPI", "h2"))
    story.append(P(
        "Au démarrage (<code>@app.on_event('startup')</code>), le backend initialise deux tâches asyncio "
        "de fond :", "body"))
    story.append(B("<b>Bot Telegram :</b> démarre le polling si <code>TELEGRAM_BOT_TOKEN</code> est configuré."))
    story.append(B("<b>Email agent :</b> lance une boucle de polling IMAP toutes les 5 minutes pour lire et traiter les courriels entrants."))

    story.append(Spacer(1, 0.4*cm))
    story.append(P("Dépendances principales", "h2"))
    deps = [
        ["Package", "Rôle"],
        ["fastapi", "Framework web asynchrone"],
        ["uvicorn[standard]", "Serveur ASGI avec support WebSocket"],
        ["langgraph", "Orchestration des agents sous forme de graphes d'état"],
        ["langchain-core / langchain-openai", "Abstractions LLM et intégration OpenAI-compatible"],
        ["neo4j", "Driver officiel Neo4j (Bolt)"],
        ["imap-tools", "Lecture et gestion des courriels IMAP"],
        ["python-telegram-bot", "Client Telegram Bot API"],
        ["python-dotenv", "Chargement des variables d'environnement"],
        ["pydantic", "Validation des données et modèles Pydantic"],
        ["httpx", "Client HTTP async pour les APIs externes"],
        ["sse-starlette", "Server-Sent Events pour le streaming frontend"],
    ]
    story.append(color_table(deps[0], deps[1:], s))
    story.append(PageBreak())

    # ══════════════════════════════════════════════════════════════════════════
    # 4. Agents IA
    # ══════════════════════════════════════════════════════════════════════════
    story.append(P("4. Agents IA — LangGraph", "h1"))
    story.append(hr(ACCENT, 2, 12))

    story.append(P(
        "ManelCore utilise <b>LangGraph</b> pour orchestrer deux agents IA distincts, chacun "
        "modélisé comme un graphe d'état dirigé (<i>StateGraph</i>). Chaque nœud du graphe est une "
        "fonction asynchrone pure qui lit et écrit dans un état partagé typé (<i>TypedDict</i>). "
        "Le LLM utilisé est <b>Google Gemma 4 (e4b)</b> via LM Studio sur <code>localhost:1234</code>, "
        "exposé avec une interface compatible OpenAI.", "body"))

    # ─ Explorer Agent ─────────────────────────────────────────────────────────
    story.append(P("4.1 Agent Explorer — Veille d'opportunités", "h2"))
    story.append(P(
        "L'Agent Explorer effectue une recherche multi-sources, analyse les résultats avec le LLM "
        "et les persiste dans Neo4j. Il supporte les interruptions pour révision humaine.",
        "body"))

    story.append(Spacer(1, 0.3*cm))
    story.append(P("Graphe d'exécution", "h3"))

    nodes_explorer = [
        ["Nœud", "Fonction", "Description"],
        ["load_profile", "load_profile()", "Charge le profil entreprise + secteurs depuis Neo4j"],
        ["generate_queries", "generate_queries()", "Génère 3 requêtes ciblées via LLM (ou fallback)"],
        ["search_seao", "search_seao()", "Interroge l'API publique SEAO (appels d'offres QC)"],
        ["search_linkedin", "search_linkedin()", "Extrait les offres LinkedIn via jobs-guest API"],
        ["search_indeed", "search_indeed()", "Scrape les flux RSS Indeed Canada"],
        ["rank_and_analyze", "rank_and_analyze()", "Déduplique, score par pertinence, persiste en Neo4j"],
        ["human_review", "human_review()", "Point d'interruption — attente validation utilisateur"],
    ]
    story.append(color_table(nodes_explorer[0], nodes_explorer[1:], s))

    story.append(Spacer(1, 0.3*cm))
    story.append(P("Flux d'exécution parallèle", "h3"))
    story.append(P(
        "Après <code>generate_queries</code>, le graphe effectue un <b>fan-out parallèle</b> vers les trois "
        "sources (SEAO, LinkedIn, Indeed) simultanément. Les résultats fusionnent dans "
        "<code>rank_and_analyze</code> grâce à l'opérateur <code>operator.add</code> sur la liste "
        "<code>found_opportunities</code> de l'état.", "body"))

    story.append(Spacer(1, 0.3*cm))
    story.append(P("État Explorer (ExplorerState)", "h3"))
    for line in [
        "class ExplorerState(TypedDict):",
        "    company_profile: str",
        "    sectors: List[str]",
        "    search_queries: List[str]",
        "    found_opportunities: Annotated[List[dict], operator.add]  # fan-in",
        "    ranked_opportunities: List[dict]",
        "    messages: Annotated[List[BaseMessage], operator.add]",
        "    current_source: Annotated[List[str], operator.add]",
        "    approved_opportunities: List[dict]",
        "    review_comment: str",
        "    errors: Annotated[List[str], operator.add]",
    ]:
        story.append(Paragraph(line, s["code"]))

    story.append(Spacer(1, 0.3*cm))
    story.append(P("Persistance (Neo4j) dans rank_and_analyze", "h3"))
    story.append(P(
        "Pour chaque opportunité classée, le nœud appelle <code>repo.upsert_opportunite()</code> "
        "avec les champs titre, source, URL, statut, score de pertinence, organisation et dates. "
        "En cas de doublon (même URL ou titre), Neo4j effectue un MERGE pour éviter les duplicatas. "
        "L'analyse LLM ajoute deux champs clés : <code>score_pertinence</code> (0.0–1.0) et "
        "<code>resume</code> (analyse critique 4-6 phrases).", "body"))

    story.append(Spacer(1, 0.4*cm))

    # ─ Contact Agent ──────────────────────────────────────────────────────────
    story.append(P("4.2 Agent Contact — Rédaction et envoi d'emails", "h2"))
    story.append(P(
        "L'Agent Contact orchestre la rédaction d'un courriel de prospection personnalisé "
        "et son envoi via SMTP après validation humaine explicite. Il utilise une interruption "
        "LangGraph (<code>interrupt_before=[\"send_email\"]</code>) pour garantir le contrôle humain.",
        "body"))

    story.append(Spacer(1, 0.3*cm))
    story.append(P("Nœuds du graphe", "h3"))
    nodes_contact = [
        ["Nœud", "Action"],
        ["fetch_history", "Charge l'opportunité cible + profil entreprise + historique des échanges Neo4j"],
        ["draft_response", "Génère un courriel professionnel via LLM avec prompt structuré riche"],
        ["send_email", "Envoie via SMTP et persiste le message dans Neo4j (si approved=True)"],
    ]
    story.append(color_table(nodes_contact[0], nodes_contact[1:], s))

    story.append(Spacer(1, 0.3*cm))
    story.append(P("Prompt de rédaction — Structure", "h3"))
    prompt_lines = [
        "Tu es l'assistant de développement des affaires de {company_name}.",
        "",
        "=== NOTRE ENTREPRISE ===",
        "{company_context}",
        "",
        "=== OPPORTUNITÉ CIBLÉE ===",
        "{opp_context}     # titre, organisation, type, budget, résumé, exigences",
        "",
        "=== CONTACT ===",
        "Nom / Organisation / Poste",
        "",
        "=== HISTORIQUE DES ÉCHANGES ===",
        "{history_text}    # derniers 50 messages liés à l'opportunité",
        "",
        "CONSIGNES: accroche personnalisée, 2-3 points forts, CTA concret,",
        "           max 250 mots, ton chaleureux et professionnel.",
        "FORMAT: Objet: [sujet accrocheur]\\n\\n[corps du courriel]",
    ]
    for line in prompt_lines:
        story.append(Paragraph(line, s["code"]))

    story.append(Spacer(1, 0.3*cm))
    story.append(P("État Contact (ContactState)", "h3"))
    for line in [
        "class ContactState(TypedDict):",
        "    opportunity_id: str",
        "    contact_info: dict        # email, nom, organisation, poste",
        "    opportunity_details: dict # données Neo4j complètes",
        "    company_context: dict     # Entreprise + ProfilEntreprise",
        "    conversation_history: List[dict]",
        "    draft_email: str",
        "    status: str  # drafting|awaiting_approval|approved|sent|error",
        "    approved: bool",
        "    error: str",
        "    messages: Annotated[List[BaseMessage], operator.add]",
    ]:
        story.append(Paragraph(line, s["code"]))

    story.append(Spacer(1, 0.4*cm))
    story.append(P("4.3 LLM Runtime — LM Studio", "h2"))
    story.append(P(
        "Les deux agents utilisent <code>ChatOpenAI</code> de LangChain pointant sur LM Studio. "
        "Le modèle par défaut est <b>google/gemma-4-e4b</b>, configurable via la variable "
        "<code>MODEL</code>. Un timeout configurable (<code>SEARCH_LLM_TIMEOUT_SECONDS</code>, "
        "défaut 30s) protège contre les inférences trop longues.", "body"))
    story.append(kv_table([
        ("Modèle",       "google/gemma-4-e4b (configurable via MODEL env)"),
        ("Base URL",     "http://localhost:1234/v1 (configurable via MODEL_BASE_URL)"),
        ("API Key",      "lm-studio (fictif, requis par le client OpenAI)"),
        ("Max tokens",   "1500 (Contact) / 2000 (Explorer)"),
        ("Timeout",      "30 secondes par défaut (SEARCH_LLM_TIMEOUT_SECONDS)"),
    ], s))
    story.append(PageBreak())

    # ══════════════════════════════════════════════════════════════════════════
    # 5. Base de données Neo4j
    # ══════════════════════════════════════════════════════════════════════════
    story.append(P("5. Base de données — Neo4j Graph", "h1"))
    story.append(hr(ACCENT, 2, 12))

    story.append(P(
        "ManelCore utilise <b>Neo4j Desktop</b> comme base de données principale. Le choix d'une "
        "base de données graphe est fondamental : les entités métier (entreprises, contacts, "
        "opportunités, messages) sont naturellement interconnectées, et Neo4j permet d'exploiter "
        "ces relations avec le langage <b>Cypher</b> de façon beaucoup plus expressive qu'un "
        "SQL avec jointures multiples.", "body"))

    story.append(Spacer(1, 0.3*cm))
    story.append(P("5.1 Modèle de données — Nœuds", "h2"))
    nodes_data = [
        ["Label", "Champs clés", "Description"],
        ["Entreprise", "nom, site_web, description, ville, pays, secteur_principal", "L'entreprise utilisatrice (Manel Canada)"],
        ["ProfilEntreprise", "resume, points_forts, faiblesses, services, historique", "Analyse stratégique de l'entreprise pour le RAG"],
        ["Contact", "nom, email, telephone, poste, linkedin, source", "Contacts professionnels (clients, prospects)"],
        ["Opportunite", "titre, type, source, url, statut, date_limite, score_pertinence, resume", "Appels d'offres, contrats, emplois"],
        ["Secteur", "nom, description", "Domaines d'activité cibles"],
        ["Message", "canal, sujet, contenu, direction, date_envoi, from_email, intent, sentiment", "Emails, messages Telegram, interactions"],
        ["Conversation", "canal, statut, sujet, created_at", "Fil de discussion groupant des Messages"],
        ["Document", "nom, type, url, contenu_extrait, embedding_id", "Fichiers joints, propositions, CV"],
        ["Candidature", "statut, date_soumission, proposition, montant", "Réponses aux appels d'offres"],
        ["AgentAction", "type, statut, input, output, erreur", "Traçabilité des actions des agents IA"],
        ["Besoin", "nom, description, priorite", "Besoins exprimés par l'entreprise"],
    ]
    story.append(color_table(nodes_data[0], nodes_data[1:], s))

    story.append(Spacer(1, 0.4*cm))
    story.append(P("5.2 Relations (Edges)", "h2"))
    rels = [
        ["Relation", "De → Vers", "Signification"],
        ["TRAVAILLE_DANS", "Entreprise → Secteur", "L'entreprise opère dans ce secteur"],
        ["PUBLIE", "Entreprise → Opportunite", "L'entreprise a publié l'appel d'offres"],
        ["APPARTIENT_A", "Opportunite → Secteur", "L'opportunité appartient à ce secteur"],
        ["A_CONTACT", "Opportunite → Contact", "Personne de contact pour l'opportunité"],
        ["A_CONVERSATION", "Opportunite → Conversation", "Fil d'échanges lié à l'opportunité"],
        ["CONTIENT", "Conversation → Message", "Message inclus dans la conversation"],
        ["A_SOUMIS", "Entreprise → Candidature", "Proposition soumise pour l'opportunité"],
        ["CONCERNANT", "Candidature → Opportunite", "Candidature associée à l'opportunité"],
        ["A_DOCUMENT", "Candidature → Document", "Pièce jointe de la candidature"],
        ["A_EFFECTUE", "AgentAction → *", "Action d'agent sur une entité"],
    ]
    story.append(color_table(rels[0], rels[1:], s))

    story.append(Spacer(1, 0.4*cm))
    story.append(P("5.3 Connexion et Repository", "h2"))
    story.append(P(
        "La classe <code>Neo4jConnection</code> encapsule le driver officiel Python de Neo4j. "
        "Elle supporte l'utilisation comme context manager (<code>with Neo4jConnection() as conn</code>) "
        "pour garantir la fermeture des sessions. La configuration est chargée en priorité depuis "
        "les variables d'environnement, puis depuis le fichier JSON des settings persistés.",
        "body"))

    story.append(Spacer(1, 0.2*cm))
    story.append(P("Méthodes principales du GraphRepository", "h3"))
    repo_methods = [
        ["Méthode", "Description"],
        ["upsert_entreprise()", "Crée ou met à jour l'entité Entreprise (MERGE par nom)"],
        ["upsert_opportunite()", "Crée ou met à jour une opportunité (MERGE par titre+source)"],
        ["upsert_contact()", "Crée ou met à jour un contact (MERGE par email)"],
        ["upsert_message()", "Persiste un message avec métadonnées complètes"],
        ["upsert_secteur()", "Crée ou met à jour un secteur d'activité"],
        ["get_node(label, id)", "Récupère un nœud par son ID"],
        ["find_nodes(label, ...)", "Recherche des nœuds avec filtre, tri et pagination"],
        ["get_related_nodes()", "Traverse les relations pour trouver les nœuds voisins"],
        ["create_relationship()", "Crée une relation orientée entre deux nœuds"],
        ["delete_node(label, id)", "Supprime un nœud et ses relations"],
        ["count_nodes(label)", "Retourne le nombre de nœuds d'un label donné"],
        ["get_dashboard_stats()", "Agrégation pour le tableau de bord (comptages globaux)"],
    ]
    story.append(color_table(repo_methods[0], repo_methods[1:], s))
    story.append(PageBreak())

    # ══════════════════════════════════════════════════════════════════════════
    # 6. Services métier
    # ══════════════════════════════════════════════════════════════════════════
    story.append(P("6. Services métier", "h1"))
    story.append(hr(ACCENT, 2, 12))

    story.append(P("6.1 MailerService — SMTP & IMAP", "h2"))
    story.append(P(
        "Le <code>MailerService</code> gère l'envoi de courriels via SMTP avec TLS et la "
        "récupération des messages non lus via IMAP. Il supporte les pièces jointes et les "
        "messages HTML/texte. Trois comptes email distincts sont configurables : "
        "prospection, RH et entreprise général.", "body"))
    story.append(kv_table([
        ("Envoi SMTP",    "smtplib avec STARTTLS, support HTML + texte alternatif"),
        ("Lecture IMAP",  "imap-tools, récupère les 20 derniers non-lus avec métadonnées complètes"),
        ("Comptes",       "MAILER_EMAIL (prospection), MAILER_HR_EMAIL (RH), MAILER_COMPANY_EMAIL (général)"),
        ("Pièces jointes","Métadonnées collectées (nom, type MIME, taille) sans lire le contenu binaire"),
    ], s))

    story.append(Spacer(1, 0.4*cm))
    story.append(P("6.2 EmailAgent — Réponse automatique IMAP", "h2"))
    story.append(P(
        "L'<code>EmailAgent</code> s'exécute en boucle de fond toutes les <b>5 minutes</b>. "
        "Il récupère les courriels non lus de <i>tous</i> les comptes configurés, les analyse "
        "avec le LLM pour en extraire l'intention et le sentiment, et peut générer des "
        "réponses automatiques pour les candidatures RH (compte MAILER_HR). "
        "Chaque courriel traité est persisté dans Neo4j avec une classification automatique.",
        "body"))

    story.append(Spacer(1, 0.4*cm))
    story.append(P("6.3 RagService — Graph RAG pour le Chat", "h2"))
    story.append(P(
        "Le <code>RagService</code> construit dynamiquement un bloc de contexte système "
        "injecté avant chaque message LLM du chat (ARIA). Pour chaque requête utilisateur, il :",
        "body"))
    for item in [
        "Extrait les mots-clés significatifs de la question (filtre stopwords FR/EN, longueur > 3).",
        "Charge le profil entreprise + ProfilEntreprise depuis Neo4j.",
        "Score les opportunités par overlap de mots-clés avec la requête.",
        "Ajoute les contacts récents, statistiques emails et candidatures actives.",
        "Détecte si la question concerne les emails (mots-clés : 'mail', 'courriel', etc.) et charge la boîte de réception.",
        "Retourne un contexte formaté Markdown injecté comme message système.",
    ]:
        story.append(B(item))

    story.append(Spacer(1, 0.4*cm))
    story.append(P("6.4 SeaoApiService — Appels d'offres québécois", "h2"))
    story.append(P(
        "Le <code>SeaoApiService</code> interroge l'<b>API publique du SEAO</b> "
        "(Système électronique d'appel d'offres du Québec) via HTTPS. "
        "Pour chaque requête de recherche, il normalise les résultats et construit "
        "l'URL de l'avis publié sur seao.gouv.qc.ca. "
        "L'endpoint utilisé est <code>api.seao.gouv.qc.ca/prod/api/recherche</code>.",
        "body"))

    story.append(Spacer(1, 0.4*cm))
    story.append(P("6.5 OpportunityCrawlerService — LinkedIn & Indeed", "h2"))
    story.append(P(
        "Ce service interroge deux sources :", "body"))
    story.append(B("<b>LinkedIn Jobs :</b> API jobs-guest non authentifiée — extraction des titres, organisations, URLs et descriptions depuis la réponse JSON publique."))
    story.append(B("<b>Indeed Canada :</b> flux RSS <code>ca.indeed.com/rss</code> — parsing XML pour extraire titre, lien, organisation et date."))
    story.append(P(
        "Les résultats sont normalisés dans un format unifié avant d'être passés à "
        "<code>rank_and_analyze</code>. Un champ <code>source</code> ('LinkedIn' ou 'Indeed') "
        "est toujours préservé pour la traçabilité.", "body"))

    story.append(Spacer(1, 0.4*cm))
    story.append(P("6.6 TelegramService — Notifications push", "h2"))
    story.append(P(
        "Le <code>TelegramService</code> démarre un bot Telegram en mode polling au lancement "
        "de l'application (si <code>TELEGRAM_BOT_TOKEN</code> est défini). Il permet de :",
        "body"))
    story.append(B("Recevoir des commandes Telegram (ex: /status, /run) pour déclencher des actions depuis le mobile."))
    story.append(B("Envoyer des notifications push lors d'événements importants (nouvelles opportunités, courriels reçus)."))
    story.append(B("Interagir avec l'entreprise de manière asynchrone sans ouvrir l'application Flutter."))

    story.append(Spacer(1, 0.4*cm))
    story.append(P("6.7 SettingsService — Configuration persistante", "h2"))
    story.append(P(
        "Les paramètres modifiables par l'utilisateur (tokens API, credentials email, paramètres "
        "Neo4j, profil entreprise) sont stockés dans un fichier JSON (<code>settings.json</code>) "
        "dans le répertoire de données de l'application. Ce fichier est chargé au démarrage et "
        "fusionné avec les variables d'environnement (les variables d'env ont la priorité).",
        "body"))
    story.append(PageBreak())

    # ══════════════════════════════════════════════════════════════════════════
    # 7. Frontend Flutter
    # ══════════════════════════════════════════════════════════════════════════
    story.append(P("7. Frontend — Flutter", "h1"))
    story.append(hr(ACCENT, 2, 12))

    story.append(P(
        "Le frontend ManelCore est une application <b>Flutter</b> cross-platform "
        "(macOS, Linux, iOS, Android) utilisant <b>Riverpod</b> pour la gestion d'état "
        "réactive. L'architecture suit le pattern <b>Feature-first</b> : chaque fonctionnalité "
        "est un répertoire autonome sous <code>lib/features/</code>.",
        "body"))

    story.append(Spacer(1, 0.3*cm))
    story.append(P("7.1 Structure de navigation", "h2"))
    pages = [
        ["Index", "Page", "Route API", "Description"],
        ["0", "Dashboard", "/dashboard/stats", "KPIs globaux, lancement du cycle de veille"],
        ["1", "Opportunités", "/opportunities", "Liste filtrée + CRUD des opportunités"],
        ["2", "Recherche", "/agent/*", "Lancement cycle + streaming SSE temps réel"],
        ["3", "Validations", "/opportunities?statut=en_attente", "Approbation/rejet d'opportunités"],
        ["4", "Contacts", "/contacts", "Carnet d'adresses + rédaction email via Contact Agent"],
        ["5", "Chat (ARIA)", "/chat/stream", "Chatbot IA avec Graph RAG + streaming"],
        ["6", "Boîte mail", "/email/*", "Lecture IMAP + envoi SMTP"],
        ["7", "RH", "/candidats", "Gestion des candidatures et candidats"],
        ["8", "Planificateur", "—", "Planning et agenda (à implémenter)"],
        ["9", "Paramètres", "/config, /settings", "Configuration complète de l'application"],
    ]
    story.append(color_table(pages[0], pages[1:], s))

    story.append(Spacer(1, 0.4*cm))
    story.append(P("7.2 ApiClient & Riverpod Providers", "h2"))
    story.append(P(
        "Toute communication avec le backend passe par la classe <code>ApiClient</code> "
        "(<code>lib/core/api_client.dart</code>). Les données sont exposées via des "
        "<code>FutureProvider</code> et <code>FutureProvider.family</code> Riverpod, "
        "permettant un rafraîchissement déclaratif avec <code>ref.invalidate()</code>.", "body"))

    providers = [
        ["Provider", "Type", "Source"],
        ["apiClientProvider", "Provider<ApiClient>", "Singleton ApiClient"],
        ["dashboardStatsProvider", "FutureProvider", "GET /dashboard/stats"],
        ["opportunitiesProvider", "FutureProvider.family<List, String?>", "GET /opportunities?statut=..."],
        ["contactsProvider", "FutureProvider<List>", "GET /contacts"],
        ["candidatsProvider", "FutureProvider<List>", "GET /candidats"],
        ["agentStatusProvider", "FutureProvider", "GET /agent/status"],
        ["configProvider", "FutureProvider", "GET /config"],
    ]
    story.append(color_table(providers[0], providers[1:], s))

    story.append(Spacer(1, 0.4*cm))
    story.append(P("7.3 Streaming SSE — Agent Explorer", "h2"))
    story.append(P(
        "La page Recherche utilise <code>ApiClient.streamAgentEvents()</code> pour consommer "
        "un flux SSE (<code>GET /agent/stream</code>). Chaque événement JSON reçu est affiché "
        "en temps réel : source interrogée, URL visitée, nombre d'opportunités trouvées. "
        "Un second flux (<code>/agent/live-stream</code>) diffuse les étapes détaillées de "
        "navigation avec source, action et timestamp.", "body"))

    story.append(Spacer(1, 0.4*cm))
    story.append(P("7.4 Chat ARIA — Streaming token par token", "h2"))
    story.append(P(
        "La page Chat utilise <code>ApiClient.chatStream()</code> qui ouvre une connexion HTTP "
        "persistante (<code>POST /chat/stream</code>) et yield les tokens de réponse LLM "
        "au fur et à mesure. Le premier événement peut contenir les métadonnées RAG "
        "(<code>{'rag': {...}}</code>) pour indiquer quelles données Neo4j ont été injectées "
        "dans le contexte.", "body"))

    story.append(Spacer(1, 0.4*cm))
    story.append(P("7.5 Floating Action Button — Cycle rapide", "h2"))
    story.append(P(
        "Le FAB animé (<code>_CycleFab</code>) est visible depuis toutes les pages "
        "(sauf Recherche). Il propose deux actions rapides :", "body"))
    story.append(B("<b>Cycle de test :</b> injecte 5 opportunités fictives via <code>POST /agent/run/mock</code> pour tester l'interface sans lancer le cycle complet."))
    story.append(B("<b>Cycle complet :</b> navigue vers la page Recherche pour lancer le cycle Explorer complet avec streaming."))
    story.append(PageBreak())

    # ══════════════════════════════════════════════════════════════════════════
    # 8. API REST
    # ══════════════════════════════════════════════════════════════════════════
    story.append(P("8. API REST — Référence des endpoints", "h1"))
    story.append(hr(ACCENT, 2, 12))

    endpoints = [
        ["Méthode", "Endpoint", "Description"],
        ["GET",    "/health",                    "Health check — état Neo4j + LLM"],
        ["GET",    "/dashboard/stats",           "Comptages globaux pour le tableau de bord"],
        ["GET",    "/config",                    "Profil entreprise (Entreprise + ProfilEntreprise)"],
        ["POST",   "/config",                    "Met à jour le profil entreprise dans Neo4j"],
        ["GET",    "/settings",                  "Paramètres JSON persistés (tokens, credentials)"],
        ["POST",   "/settings",                  "Sauvegarde les paramètres JSON"],
        ["DELETE", "/data/erase",                "Efface toutes les données Neo4j (DANGER)"],
        ["GET",    "/opportunities",             "Liste des opportunités (filtre statut, limite)"],
        ["POST",   "/opportunities",             "Crée une opportunité manuellement"],
        ["PUT",    "/opportunities/{id}",        "Met à jour une opportunité"],
        ["PATCH",  "/opportunities/{id}/status", "Change le statut d'une opportunité"],
        ["DELETE", "/opportunities/{id}",        "Supprime une opportunité"],
        ["GET",    "/contacts",                  "Liste tous les contacts"],
        ["POST",   "/contacts",                  "Crée un contact"],
        ["PUT",    "/contacts/{id}",             "Met à jour un contact"],
        ["DELETE", "/contacts/{id}",             "Supprime un contact"],
        ["POST",   "/agent/run",                 "Démarre le cycle Explorer (async, non bloquant)"],
        ["POST",   "/agent/run/mock",            "Injecte 5 opportunités fictives de test"],
        ["GET",    "/agent/status",              "État courant de l'agent Explorer"],
        ["GET",    "/agent/stream",              "SSE — événements temps réel de l'agent"],
        ["GET",    "/agent/live-stream",         "SSE — étapes de navigation détaillées"],
        ["POST",   "/contact/draft",             "Lance le Contact Agent (génère brouillon email)"],
        ["POST",   "/contact/approve",           "Approuve ou rejette le brouillon + envoi SMTP"],
        ["GET",    "/candidats",                 "Liste les candidats RH"],
        ["POST",   "/candidats",                 "Crée un candidat"],
        ["PUT",    "/candidats/{id}",            "Met à jour un candidat"],
        ["PATCH",  "/candidats/{id}/status",     "Change le statut d'un candidat"],
        ["DELETE", "/candidats/{id}",            "Supprime un candidat"],
        ["POST",   "/email/check",               "Déclenche la lecture IMAP manuelle"],
        ["GET",    "/email/inbox",               "Résumé de la boîte de réception"],
        ["GET",    "/email/messages",            "50 derniers messages persistés"],
        ["POST",   "/email/send",                "Envoie un courriel SMTP direct"],
        ["POST",   "/chat/stream",               "SSE chat streaming avec Graph RAG"],
    ]
    story.append(color_table(endpoints[0], endpoints[1:], s))
    story.append(PageBreak())

    # ══════════════════════════════════════════════════════════════════════════
    # 9. Infrastructure
    # ══════════════════════════════════════════════════════════════════════════
    story.append(P("9. Infrastructure & déploiement", "h1"))
    story.append(hr(ACCENT, 2, 12))

    story.append(P(
        "ManelCore est conçu pour s'exécuter entièrement en local (<b>local-first</b>). "
        "Il n'y a pas de dépendance à des services cloud : le LLM tourne sur LM Studio, "
        "la base de données sur Neo4j Desktop, et le backend sur uvicorn directement. "
        "Pas de Docker requis.", "body"))

    story.append(Spacer(1, 0.3*cm))
    story.append(P("Pré-requis système", "h2"))
    prereqs = [
        ["Composant", "Version", "Notes"],
        ["Python", "3.14+", "Avec venv dans /Users/mazong/Documents/ManelCore/.venv"],
        ["LM Studio", "Dernière", "Modèle chargé : google/gemma-4-e4b sur :1234"],
        ["Neo4j Desktop", "5.x", "Base 'neo4j' sur bolt://localhost:7687"],
        ["Flutter", "3.x", "SDK installé, cible macOS/Linux/iOS/Android"],
        ["Compte email", "IMAP/SMTP", "iCloud, Gmail, ou domaine personnalisé supporté"],
    ]
    story.append(color_table(prereqs[0], prereqs[1:], s))

    story.append(Spacer(1, 0.4*cm))
    story.append(P("Procédure de démarrage complète", "h2"))
    start_steps = [
        ("1", "Démarrer LM Studio",          "Charger google/gemma-4-e4b, activer le serveur local sur :1234"),
        ("2", "Démarrer Neo4j Desktop",       "Lancer la base 'neo4j', vérifier bolt://localhost:7687"),
        ("3", "Configurer l'environnement",   "Copier .env.example → .env et remplir les valeurs"),
        ("4", "Démarrer le backend",          "cd backend && python main.py (uvicorn sur :8000)"),
        ("5", "Démarrer le frontend Flutter", "cd manelcore && flutter run -d macos (ou linux)"),
        ("6", "Configurer via l'interface",   "Page Paramètres → remplir profil entreprise et credentials"),
    ]
    for num, title, desc in start_steps:
        t = Table([[
            Paragraph(f"<b>{num}</b>", ParagraphStyle("n", fontSize=12, textColor=colors.white,
                fontName="Helvetica-Bold", alignment=TA_CENTER)),
            [Paragraph(f"<b>{title}</b>", s["h3"]),
             Paragraph(desc, s["body"])]
        ]], colWidths=[1*cm, W - 5*cm])
        t.setStyle(TableStyle([
            ("BACKGROUND",    (0,0), (0,0), ACCENT),
            ("VALIGN",        (0,0), (-1,-1), "MIDDLE"),
            ("TOPPADDING",    (0,0), (-1,-1), 8),
            ("BOTTOMPADDING", (0,0), (-1,-1), 8),
            ("LEFTPADDING",   (0,0), (-1,-1), 10),
            ("LINEBELOW",     (0,0), (-1,-1), 0.4, BOX_BORDER),
        ]))
        story.append(t)
    story.append(PageBreak())

    # ══════════════════════════════════════════════════════════════════════════
    # 10. Flux end-to-end
    # ══════════════════════════════════════════════════════════════════════════
    story.append(P("10. Flux de données end-to-end", "h1"))
    story.append(hr(ACCENT, 2, 12))

    story.append(P("Cycle complet de veille d'opportunités", "h2"))
    flow_steps = [
        ("Frontend", "L'utilisateur clique 'Cycle complet' → POST /agent/run"),
        ("Backend",  "FastAPI démarre create_explorer_graph() en tâche asyncio"),
        ("Explorer", "load_profile: charge profil + secteurs depuis Neo4j"),
        ("Explorer", "generate_queries: LLM génère 3 requêtes optimisées"),
        ("Explorer", "Fan-out parallèle: search_seao + search_linkedin + search_indeed"),
        ("Explorer", "rank_and_analyze: LLM score + analyse, MERGE dans Neo4j"),
        ("Explorer", "Interruption avant human_review — état suspendu en mémoire"),
        ("Backend",  "Chaque étape pousse un événement JSON dans browser_live_queue"),
        ("Frontend", "GET /agent/stream consomme le SSE et affiche en temps réel"),
        ("Validation","Utilisateur valide les opportunités dans la page Validations"),
        ("Contact",  "Pour une opportunité + contact: POST /contact/draft"),
        ("Explorer", "Contact Agent: fetch_history → draft_response (LLM) → interrupt"),
        ("Frontend", "Affiche le brouillon — utilisateur approuve ou modifie"),
        ("Contact",  "POST /contact/approve → send_email: SMTP + persistance Neo4j"),
    ]
    for source, desc in flow_steps:
        color_map = {"Frontend": "#3b82f6", "Backend": "#10b981", "Explorer": "#8b5cf6", "Contact": "#f59e0b", "Validation": "#06b6d4"}
        c = color_map.get(source, "#64748b")
        row = Table([[
            Paragraph(f"<font color='white'><b>{source}</b></font>",
                      ParagraphStyle("src", fontSize=8, fontName="Helvetica-Bold",
                                     textColor=colors.white, alignment=TA_CENTER)),
            Paragraph(desc, s["body"]),
        ]], colWidths=[2*cm, W - 5*cm])
        row.setStyle(TableStyle([
            ("BACKGROUND",    (0,0), (0,0), colors.HexColor(c)),
            ("VALIGN",        (0,0), (-1,-1), "MIDDLE"),
            ("TOPPADDING",    (0,0), (-1,-1), 6),
            ("BOTTOMPADDING", (0,0), (-1,-1), 6),
            ("LEFTPADDING",   (0,0), (-1,-1), 8),
            ("LINEBELOW",     (0,0), (-1,-1), 0.3, BOX_BORDER),
        ]))
        story.append(row)

    story.append(PageBreak())

    # ══════════════════════════════════════════════════════════════════════════
    # 11. Configuration
    # ══════════════════════════════════════════════════════════════════════════
    story.append(P("11. Configuration & variables d'environnement", "h1"))
    story.append(hr(ACCENT, 2, 12))

    env_vars = [
        ["Variable", "Défaut", "Description"],
        ["API_KEY", "lm-studio", "Clé factice pour LM Studio (interface OpenAI)"],
        ["MODEL", "google/gemma-4-e4b", "Identifiant du modèle LLM"],
        ["MODEL_BASE_URL", "http://localhost:1234/v1", "URL de base de l'API LLM"],
        ["NEO4J_URI", "bolt://localhost:7687", "URI de connexion Neo4j"],
        ["NEO4J_USERNAME", "neo4j", "Nom d'utilisateur Neo4j"],
        ["NEO4J_PASSWORD", "(vide)", "Mot de passe Neo4j"],
        ["NEO4J_DATABASE", "neo4j", "Nom de la base de données"],
        ["MAILER_EMAIL", "(vide)", "Email principal (prospection)"],
        ["MAILER_PASSWORD", "(vide)", "Mot de passe email principal"],
        ["MAILER_IMAP_SERVER", "mail.votredomaine.ca", "Serveur IMAP principal"],
        ["MAILER_HR_EMAIL", "(vide)", "Email RH (réponses candidatures)"],
        ["MAILER_HR_PASSWORD", "(vide)", "Mot de passe email RH"],
        ["MAILER_HR_IMAP_SERVER", "mail.votredomaine.ca", "Serveur IMAP RH"],
        ["MAILER_COMPANY_EMAIL", "(vide)", "Email général entreprise"],
        ["MAILER_COMPANY_PASSWORD", "(vide)", "Mot de passe email général"],
        ["MAILER_COMPANY_IMAP_SERVER", "mail.votredomaine.ca", "Serveur IMAP général"],
        ["TELEGRAM_BOT_TOKEN", "(vide)", "Token du bot Telegram (@BotFather)"],
        ["SEARCH_LLM_TIMEOUT_SECONDS", "30", "Timeout LLM pour les recherches (secondes)"],
        ["ANONYMIZED_TELEMETRY", "false", "Désactive la télémétrie LangChain"],
    ]
    story.append(color_table(env_vars[0], env_vars[1:], s))
    story.append(PageBreak())

    # ══════════════════════════════════════════════════════════════════════════
    # 12. Sécurité
    # ══════════════════════════════════════════════════════════════════════════
    story.append(P("12. Sécurité & bonnes pratiques", "h1"))
    story.append(hr(ACCENT, 2, 12))

    story.append(P("Points de vigilance actuels", "h2"))
    for item in [
        "<b>CORS ouvert :</b> le middleware FastAPI autorise <code>allow_origins=[\"*\"]</code>. En production, restreindre aux origines connues.",
        "<b>Authentification :</b> l'API REST n'implémente pas encore d'authentification. Recommandation : ajouter JWT ou API Key en en-tête.",
        "<b>Fichier .env :</b> ne jamais committer le fichier <code>.env</code> contenant les secrets. Il est correctement dans <code>.gitignore</code>.",
        "<b>Mot de passe Neo4j :</b> stocké en clair dans .env. Utiliser un gestionnaire de secrets en production.",
        "<b>Endpoint /data/erase :</b> supprime toutes les données sans confirmation. Protéger par authentification et confirmation double.",
        "<b>Local-first :</b> en fonctionnement local, le risque d'exposition réseau est faible. Ajouter un pare-feu si déployé sur un serveur partagé.",
        "<b>Pièces jointes :</b> les métadonnées sont collectées mais pas le contenu binaire — évite les risques de stockage de fichiers malicieux.",
    ]:
        story.append(B(item))

    story.append(Spacer(1, 0.4*cm))
    story.append(P("Human-in-the-loop — Garantie de contrôle", "h2"))
    story.append(P(
        "ManelCore est architecturalement conçu pour maintenir le contrôle humain sur toutes "
        "les actions à impact externe :", "body"))
    story.append(B("Aucun courriel n'est envoyé sans <code>approved=True</code> explicite dans l'état du Contact Agent."))
    story.append(B("L'Agent Explorer s'interrompt avant <code>human_review</code> — les opportunités ne sont pas automatiquement acceptées."))
    story.append(B("L'Email Agent peut générer des brouillons mais la validation de l'envoi reste humaine."))

    story.append(PageBreak())

    # ══════════════════════════════════════════════════════════════════════════
    # 13. Roadmap
    # ══════════════════════════════════════════════════════════════════════════
    story.append(P("13. Roadmap & évolutions", "h1"))
    story.append(hr(ACCENT, 2, 12))

    story.append(P("Fonctionnalités en cours / à implémenter", "h2"))
    roadmap = [
        ["Priorité", "Fonctionnalité", "Description"],
        ["Haute", "Authentification API", "JWT ou API Key pour sécuriser tous les endpoints"],
        ["Haute", "Page Planificateur", "Agenda intégré pour planifier les relances et échéances"],
        ["Haute", "Notifications desktop", "Alertes macOS/Linux pour nouvelles opportunités"],
        ["Moyenne", "Export PDF/Excel", "Export des opportunités et rapports pour présentation"],
        ["Moyenne", "Vector embeddings", "RAG sémantique avec pgvector ou Neo4j vector index"],
        ["Moyenne", "Webhook SEAO", "Abonnement aux nouvelles publications SEAO en temps réel"],
        ["Basse", "Multi-langue", "Interface en anglais pour les opportunités fédérales"],
        ["Basse", "Docker Compose", "Conteneurisation pour déploiement sur serveur"],
        ["Basse", "Tests automatisés", "Suite de tests pytest pour le backend et les agents"],
    ]
    story.append(color_table(roadmap[0], roadmap[1:], s))

    story.append(Spacer(1, 0.6*cm))
    story.append(hr(ACCENT, 1, 16))
    story.append(P(
        "Documentation générée automatiquement — ManelCore v1.0 — Mai 2025",
        "caption"
    ))
    story.append(P(
        "Manel Canada | zebazemadric@icloud.com",
        "caption"
    ))

    return story


# ── Main ───────────────────────────────────────────────────────────────────────
def generate(output_path: str = "/Users/mazong/Documents/ManelCore/ManelCore_Documentation.pdf"):
    s = make_styles()

    doc = SimpleDocTemplate(
        output_path,
        pagesize=A4,
        leftMargin=2*cm,
        rightMargin=2*cm,
        topMargin=1.5*cm,
        bottomMargin=1.5*cm,
        title="ManelCore — Documentation Technique",
        author="Manel Canada",
        subject="Plateforme IA de Développement des Affaires",
    )

    story = build_content(s)

    # Page templates: cover (page 1) vs normal
    page_count = [0]
    def on_page(canvas, doc):
        page_count[0] += 1
        if doc.page == 1:
            cover_canvas(canvas, doc)
        else:
            normal_canvas(canvas, doc)

    doc.build(story, onFirstPage=on_page, onLaterPages=on_page)
    print(f"✅ Documentation générée : {output_path}")


if __name__ == "__main__":
    generate()
