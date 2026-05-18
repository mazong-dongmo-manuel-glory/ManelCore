from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(slots=True, kw_only=True)
class GraphNodePayload:
    id: str | None = None

    def to_properties(self) -> dict[str, Any]:
        return {key: value for key, value in asdict(self).items() if value is not None}


@dataclass(slots=True, kw_only=True)
class Entreprise(GraphNodePayload):
    nom: str
    site_web: str | None = None
    description: str | None = None
    taille: str | None = None
    pays: str | None = None
    ville: str | None = None
    secteur_principal: str | None = None
    telegram_token: str | None = None
    telegram_chat_id: str | None = None
    score_confiance: float | None = None
    created_at: str | None = None
    updated_at: str | None = None


@dataclass(slots=True, kw_only=True)
class Contact(GraphNodePayload):
    nom: str
    email: str | None = None
    telephone: str | None = None
    poste: str | None = None
    linkedin: str | None = None
    source: str | None = None
    niveau_importance: str | None = None


@dataclass(slots=True, kw_only=True)
class Opportunite(GraphNodePayload):
    titre: str
    type: str | None = None
    source: str | None = None
    url: str | None = None
    statut: str | None = None
    date_publication: str | None = None
    date_limite: str | None = None
    budget: float | None = None
    score_pertinence: float | None = None
    resume: str | None = None
    description: str | None = None
    exigences: str | None = None
    organisation: str | None = None
    lieu: str | None = None
    numero: str | None = None
    reference_id: str | None = None
    seao_uuid: str | None = None
    contact_email: str | None = None
    contact_nom: str | None = None
    draft_email: str | None = None
    created_at: str | None = None


@dataclass(slots=True, kw_only=True)
class Secteur(GraphNodePayload):
    nom: str
    description: str | None = None


@dataclass(slots=True, kw_only=True)
class Message(GraphNodePayload):
    canal: str
    sujet: str | None = None
    contenu: str | None = None
    direction: str | None = None
    date_envoi: str | None = None
    intent: str | None = None
    sentiment: str | None = None
    resume_ia: str | None = None
    # Champs email spécifiques
    from_email: str | None = None
    from_name: str | None = None
    to_email: str | None = None
    cc_email: str | None = None
    reply_to: str | None = None
    message_id_header: str | None = None
    in_reply_to: str | None = None
    uid_imap: str | None = None
    priorite: str | None = None
    classification: str | None = None
    auto_replied: bool | None = None
    compte_recepteur: str | None = None
    has_attachments: bool | None = None
    attachment_names: str | None = None
    taille_octets: int | None = None
    contenu_html: str | None = None


@dataclass(slots=True, kw_only=True)
class Conversation(GraphNodePayload):
    canal: str
    statut: str | None = None
    sujet: str | None = None
    created_at: str | None = None
    updated_at: str | None = None


@dataclass(slots=True, kw_only=True)
class Document(GraphNodePayload):
    nom: str
    type: str | None = None
    url: str | None = None
    contenu_extrait: str | None = None
    embedding_id: str | None = None
    created_at: str | None = None


@dataclass(slots=True, kw_only=True)
class Candidature(GraphNodePayload):
    statut: str | None = None
    date_soumission: str | None = None
    proposition: str | None = None
    montant: float | None = None
    note_interne: str | None = None


@dataclass(slots=True, kw_only=True)
class AgentAction(GraphNodePayload):
    type: str
    statut: str | None = None
    input: str | None = None
    output: str | None = None
    erreur: str | None = None
    created_at: str | None = None


@dataclass(slots=True, kw_only=True)
class Besoin(GraphNodePayload):
    nom: str
    description: str | None = None
    priorite: str | None = None


@dataclass(slots=True, kw_only=True)
class ProfilEntreprise(GraphNodePayload):
    resume: str | None = None
    points_forts: str | None = None
    faiblesses: str | None = None
    services: str | None = None
    historique: str | None = None
