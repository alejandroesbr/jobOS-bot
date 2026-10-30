from pathlib import Path
import pytest

from src.config_loader import FilterConfig, load_filter_config
from src.domain.models import JobOffer, PortalName, WorkModality
from src.domain.matcher import OfferMatcher


@pytest.fixture
def filter_config() -> FilterConfig:
    config_path = Path("config/filters.yaml")
    return load_filter_config(config_path)


@pytest.fixture
def matcher(filter_config: FilterConfig) -> OfferMatcher:
    return OfferMatcher(filter_config)


def test_matcher_rejects_senior_title(matcher: OfferMatcher) -> None:
    offer = JobOffer(
        portal=PortalName.LINKEDIN,
        title="Senior Fullstack Developer (React/Node)",
        company="TechCorp",
        location="Remoto, Colombia",
        modality=WorkModality.REMOTE,
        url="https://linkedin.com/jobs/view/1001",
        description="We are looking for a Senior React and Node developer with 6+ years experience.",
    )
    evaluation = matcher.evaluate(offer)

    assert evaluation.is_hard_rejected is True
    assert evaluation.should_apply is False
    assert evaluation.match_score == 0
    assert "blacklisted term" in str(evaluation.rejection_reason).lower()


def test_matcher_rejects_alien_stack_in_title(matcher: OfferMatcher) -> None:
    offer = JobOffer(
        portal=PortalName.COMPUTRABAJO,
        title="Desarrollador .NET / C# Junior",
        company="Consultora Local",
        location="Barranquilla",
        modality=WorkModality.ONSITE,
        url="https://computrabajo.com.co/ofertas/2001",
        description="Conocimientos en C#, ASP.NET, SQL Server.",
    )
    evaluation = matcher.evaluate(offer)

    assert evaluation.is_hard_rejected is True
    assert evaluation.should_apply is False
    assert "blacklisted term" in str(evaluation.rejection_reason).lower()


def test_matcher_rejects_blacklisted_company(matcher: OfferMatcher) -> None:
    offer = JobOffer(
        portal=PortalName.GETONBRD,
        title="Junior Frontend Developer",
        company="Spam Staffing LLC",
        location="Remoto",
        modality=WorkModality.REMOTE,
        url="https://getonbrd.com/jobs/3001",
        description="React and TypeScript position.",
    )
    evaluation = matcher.evaluate(offer)

    assert evaluation.is_hard_rejected is True
    assert evaluation.should_apply is False
    assert "blacklisted" in str(evaluation.rejection_reason).lower()


def test_matcher_rejects_location_outside_whitelist(matcher: OfferMatcher) -> None:
    offer = JobOffer(
        portal=PortalName.INDEED,
        title="Junior Frontend Developer",
        company="Acme Corp",
        location="Madrid, España (Presencial)",
        modality=WorkModality.ONSITE,
        url="https://indeed.com/viewjob?jk=4001",
        description="React and TypeScript position.",
    )
    evaluation = matcher.evaluate(offer)

    assert evaluation.is_hard_rejected is True
    assert evaluation.should_apply is False
    assert "location" in str(evaluation.rejection_reason).lower()


def test_matcher_accepts_partial_match_above_threshold(matcher: OfferMatcher) -> None:
    # Offer asks for: React (3), Node.js (3), TypeScript (3), Kubernetes (1), Kafka (1), AWS (1), MongoDB (1)
    # Total weight: 13. Candidate matches: React (3) + Node (3) + TS (3) = 9.
    # Score: round(9/13 * 100) = 69%
    offer = JobOffer(
        portal=PortalName.GETONBRD,
        title="Junior Full Stack Engineer",
        company="Innovative Startup",
        location="Remoto - Colombia",
        modality=WorkModality.REMOTE,
        url="https://getonbrd.com/jobs/5001",
        description=(
            "Requerimos Desarrollador con conocimientos en React, Node.js y TypeScript. "
            "Deseable manejo de Kubernetes, Kafka, AWS y MongoDB."
        ),
    )
    evaluation = matcher.evaluate(offer)

    assert evaluation.is_hard_rejected is False
    assert evaluation.should_apply is True
    assert 40 <= evaluation.match_score < 70
    assert "React" in evaluation.matched_keywords
    assert "Node.js" in evaluation.matched_keywords
    assert "TypeScript" in evaluation.matched_keywords
    assert "Kubernetes" in evaluation.missing_keywords
    assert "Kafka" in evaluation.missing_keywords


def test_matcher_accepts_high_affinity_match(matcher: OfferMatcher) -> None:
    offer = JobOffer(
        portal=PortalName.LINKEDIN,
        title="Desarrollador Full Stack Junior",
        company="Globant Colombia",
        location="Remoto / Barranquilla",
        modality=WorkModality.REMOTE,
        url="https://linkedin.com/jobs/view/6001",
        description="Stack principal: React, NestJS, TypeScript, PostgreSQL y Docker.",
    )
    evaluation = matcher.evaluate(offer)

    assert evaluation.is_hard_rejected is False
    assert evaluation.should_apply is True
    assert evaluation.match_score >= 80
    assert len(evaluation.missing_keywords) == 0


def test_matcher_rejects_offer_below_threshold(matcher: OfferMatcher) -> None:
    # Offer demands skills candidate doesn't have: AWS (1), MongoDB (1), Redis (1), GraphQL (1), Kubernetes (1), Kafka (1)
    # Plus candidate only matches Linux (1).
    # Weight: 1/7 = 14% < 40%.
    offer = JobOffer(
        portal=PortalName.ELEMPLEO,
        title="Desarrollador Junior",
        company="Data Corp",
        location="Colombia Remoto",
        modality=WorkModality.REMOTE,
        url="https://elempleo.com/ofertas/7001",
        description="Buscamos desarrollador con AWS, MongoDB, Redis, GraphQL, Kubernetes, Kafka en entorno Linux.",
    )
    evaluation = matcher.evaluate(offer)

    assert evaluation.is_hard_rejected is False
    assert evaluation.should_apply is False
    assert evaluation.match_score < 40
    assert "below minimum threshold" in str(evaluation.rejection_reason).lower()


def test_matcher_applies_short_description_floor_score(matcher: OfferMatcher) -> None:
    # Short description mentioning only React and Kubernetes
    # React (3) is Core and matched. Kubernetes (1) not matched. Total 4. Earned 3 = 75%.
    # If offer only mentions React (Core):
    offer = JobOffer(
        portal=PortalName.COMPUTRABAJO,
        title="Desarrollador Junior React",
        company="Empresa Local",
        location="Barranquilla",
        modality=WorkModality.HYBRID,
        url="https://computrabajo.com.co/ofertas/8001",
        description="Empresa busca programador con experiencia en React.",
    )
    evaluation = matcher.evaluate(offer)

    assert evaluation.should_apply is True
    assert evaluation.match_score >= 65
    assert "React" in evaluation.matched_keywords


def test_matcher_generates_correct_dedup_key_and_canonical_url(matcher: OfferMatcher) -> None:
    offer = JobOffer(
        portal=PortalName.LINKEDIN,
        title="Desarrollador Fullstack Jr (React/Node.js) - Remoto",
        company="TechCorp Colombia S.A.S.",
        location="Barranquilla",
        modality=WorkModality.REMOTE,
        url="https://www.linkedin.com/jobs/view/99999/?trackingId=abc&refId=123",
        description="Desarrollo con React, Node.js y PostgreSQL.",
    )
    evaluation = matcher.evaluate(offer)

    assert evaluation.dedup_key == "techcorp::desarrollador full stack junior react node"
    assert evaluation.canonical_url == "https://www.linkedin.com/jobs/view/99999"

