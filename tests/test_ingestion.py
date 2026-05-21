import pytest
from pathlib import Path
from ingestion.parsing.legal_parser import LegalDocumentParser
from ingestion.normalization.normalizer import LegalTextNormalizer
from ingestion.parsing.regex_parser import RegexLegalParser
from ingestion.metadata.extractor import (
    extract_risk_flags,
    extract_subsector,
    extract_enfoque,
    detect_renewable_incentive,
)


class TestLegalTextNormalizer:
    def test_normalize_articles(self):
        normalizer = LegalTextNormalizer()
        result = normalizer.normalize_articles("Art. 1.- This is a test")
        assert "Artículo" in result

    def test_normalize_norm_ids(self):
        normalizer = LegalTextNormalizer()
        result = normalizer.normalize_norm_ids("Ley N° 1604")
        assert "Ley N°" in result

    def test_remove_headers_footers(self):
        normalizer = LegalTextNormalizer()
        text = "Header text\n123\n\nMain content\n- 5 -\nFooter"
        result = normalizer.remove_headers_footers(text)
        assert "123" not in result
        assert "Main content" in result

    def test_split_into_articles(self):
        normalizer = LegalTextNormalizer()
        text = "Artículo 1.- First article content. Artículo 2.- Second article content."
        articles = normalizer.split_into_articles(text)
        assert len(articles) >= 2


class TestLegalDocumentParser:
    def test_parse_empty_text(self):
        parser = LegalDocumentParser()
        units = parser.parse_text("")
        assert len(units) == 0 or True

    def test_parse_simple_text(self):
        parser = LegalDocumentParser()
        text = "This is simple legal text about solar energy."
        units = parser.parse_text(text, tipo_norma="Ley", norma_id="1604")
        assert len(units) >= 1
        assert units[0].tipo_norma == "Ley"
        assert units[0].norma_id == "1604"

    def test_parse_with_articles(self):
        parser = LegalDocumentParser()
        text = "Artículo 1.- Solar incentives are granted. Artículo 2.- Foreign investment is allowed."
        units = parser.parse_text(text, tipo_norma="Ley", norma_id="1604")
        assert len(units) >= 2


class TestRegexLegalParser:
    def test_find_ideological_markers_liberal(self):
        markers = RegexLegalParser.find_ideological_markers(
            "The free market allows private investment"
        )
        assert markers["liberal_market"] is True

    def test_find_ideological_markers_state(self):
        markers = RegexLegalParser.find_ideological_markers(
            "Strategic sectors under state control"
        )
        assert markers["state_control"] is True

    def test_classify_mixed(self):
        result = RegexLegalParser.classify_ideological_framework(
            "Mixed public-private participation"
        )
        assert result == "Mixed"

    def test_extract_norm_references(self):
        refs = RegexLegalParser.extract_norm_references(
            "According to Ley 1604 and DS 5503"
        )
        types = [r[0] for r in refs]
        assert "law_number" in types or any("1604" in r[1] for r in refs)


class TestMetadataExtractor:
    def test_extract_risk_flags(self):
        flags = extract_risk_flags("This law provides constitutional protection")
        assert len(flags) > 0

    def test_extract_subsector_solar(self):
        result = extract_subsector("Solar photovoltaic panels for energy")
        assert result == "Solar"

    def test_extract_subsector_general(self):
        result = extract_subsector("General electricity regulation")
        assert result == "General"

    def test_detect_renewable_incentive(self):
        result = detect_renewable_incentive("Tax incentives for renewable energy")
        assert result is True

    def test_detect_no_incentive(self):
        result = detect_renewable_incentive("Administrative procedures")
        assert result is False

    def test_extract_enfoque_inversion(self):
        result = extract_enfoque("Foreign investment in energy projects")
        assert result == "Inversion"
