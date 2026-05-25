import json
import pytest
from pathlib import Path
from typing import List, Dict, Any

CORPUS_PATH = Path(__file__).resolve().parent.parent / "corpus" / "normalized" / "all_units.json"


GOLDEN_SET = [
    {
        "query": "inversión extranjera en Bolivia constitución",
        "expected_doc_ids": ["Constitucion_320_art_320", "Constitucion_349_art_349"],
        "expected_keywords": ["inversión extranjera", "jurisdicción"],
    },
    {
        "query": "incentivos para energía solar en Bolivia",
        "expected_doc_ids": ["Decreto_Supremo_3_art_3", "Ley_18_art_18_bis", "Ley_18_art_18_ter"],
        "expected_keywords": ["solar", "incentivos", "renovable"],
    },
    {
        "query": "arbitraje internacional en el sector eléctrico",
        "expected_doc_ids": ["Ley_45_art_45"],
        "expected_keywords": ["arbitraje"],
    },
    {
        "query": "control estatal de sectores estratégicos energía",
        "expected_doc_ids": ["Constitucion_351_art_351", "Constitucion_378_art_378"],
        "expected_keywords": ["control", "sectores estratégicos"],
    },
    {
        "query": "requisitos para inversión extranjera en renovables",
        "expected_doc_ids": ["Decreto_Supremo_4_art_4", "Decreto_Supremo_5_art_5"],
        "expected_keywords": ["inversión extranjera", "sociedad"],
    },
    {
        "query": "jerarquía constitucional bolivia artículo 410",
        "expected_doc_ids": ["Constitucion_410_art_410"],
        "expected_keywords": ["norma suprema", "410"],
    },
    {
        "query": "generación distribuida autoconsumo excedentes",
        "expected_doc_ids": ["Ley_17_art_17", "Ley_1604_art_17", "Decreto_Supremo_7_art_7"],
        "expected_keywords": ["autoconsumo", "generación distribuida"],
    },
    {
        "query": "promoción de energías alternativas renovables",
        "expected_doc_ids": ["Constitucion_355_art_355", "Constitucion_379_art_379"],
        "expected_keywords": ["alternativas", "renovables"],
    },
    {
        "query": "plazo aprobación AETN proyectos renovables",
        "expected_doc_ids": ["Decreto_Supremo_6_art_6"],
        "expected_keywords": ["90 días", "AETN"],
    },
    {
        "query": "libre iniciativa privada sector eléctrico",
        "expected_doc_ids": ["Ley_1_art_1", "Ley_2_art_2", "Ley_15_art_15"],
        "expected_keywords": ["libre iniciativa", "libre competencia"],
    },
]

EXPECTED_RISK_FLAGS = {
    "régimen promoción inversiones energía renovable": {
        "expected_doc_ids": ["Decreto_Supremo_1_art_1"],
        "expected_risk_flags": ["Nationalization Risk"],
    },
}


def load_corpus() -> List[Dict[str, Any]]:
    with open(CORPUS_PATH) as f:
        return json.load(f)


@pytest.fixture(scope="session")
def corpus() -> List[Dict[str, Any]]:
    return load_corpus()


@pytest.fixture(scope="session")
def corpus_by_id(corpus) -> Dict[str, Dict[str, Any]]:
    return {doc["id"]: doc for doc in corpus}


class TestGoldenSetBM25:
    @pytest.fixture(autouse=True)
    def setup_retriever(self, corpus):
        from app.retrieval.bm25 import BM25Retriever
        retriever = BM25Retriever()
        retriever.build_index(corpus)
        return retriever

    @pytest.mark.parametrize("entry", GOLDEN_SET, ids=lambda e: e["query"][:40])
    @pytest.mark.asyncio
    async def test_golden_queries_return_expected_docs(self, setup_retriever, entry):
        retriever = setup_retriever
        results = await retriever.search(entry["query"], top_k=10)
        result_ids = [r.get("id", "") for r in results]

        found = [eid for eid in entry["expected_doc_ids"] if eid in result_ids]
        assert len(found) >= 1, (
            f"Query: {entry['query']}\n"
            f"Expected at least one of: {entry['expected_doc_ids']}\n"
            f"Got top-10: {result_ids}"
        )

    @pytest.mark.parametrize("entry", GOLDEN_SET, ids=lambda e: e["query"][:40])
    @pytest.mark.asyncio
    async def test_golden_queries_match_keywords(self, setup_retriever, entry):
        retriever = setup_retriever
        results = await retriever.search(entry["query"], top_k=10)

        combined_text = " ".join(
            r.get("texto", "") for r in results[:5]
        ).lower()

        found_keywords = [kw for kw in entry["expected_keywords"] if kw.lower() in combined_text]
        assert len(found_keywords) >= 1, (
            f"Query: {entry['query']}\n"
            f"Expected at least one keyword from: {entry['expected_keywords']}\n"
            f"Not found in top-5: {combined_text[:200]}"
        )

    @pytest.mark.asyncio
    async def test_risk_flag_query_returns_flagged_docs(self, setup_retriever):
        retriever = setup_retriever
        for query, expected in EXPECTED_RISK_FLAGS.items():
            results = await retriever.search(query, top_k=10)
            result_ids = [r.get("id", "") for r in results]

            found = [eid for eid in expected["expected_doc_ids"] if eid in result_ids]
            assert len(found) >= 1, (
                f"Query: {query}\n"
                f"Expected: {expected['expected_doc_ids']}\n"
                f"Got: {result_ids}"
            )


class TestGoldenSetDense:
    @pytest.mark.asyncio
    @pytest.mark.skip(reason="Requires torch>=2.6 (environment issue with CVE-2025-32434)")
    async def test_dense_ranks_relevant_first(self):
        from app.retrieval.dense import DenseRetriever

        corpus = load_corpus()
        retriever = DenseRetriever()

        test_cases = [
            ("incentivos fiscales energía renovable",
             ["Decreto_Supremo_3_art_3", "Ley_18_art_18_ter"]),
            ("inversión extranjera constitución boliviana",
             ["Constitucion_320_art_320"]),
            ("arbitraje controversias sector eléctrico",
             ["Ley_45_art_45"]),
        ]

        for query, expected_ids in test_cases:
            results = await retriever.search(query, corpus, top_k=10)
            result_ids = [r.get("id", "") for r in results]

            found = [eid for eid in expected_ids if eid in result_ids]
            assert len(found) >= 1, (
                f"Query: {query}\n"
                f"Expected at least one of: {expected_ids}\n"
                f"Got: {result_ids}"
            )


class TestGoldenSetCoverage:
    def test_all_corpus_docs_have_ids(self, corpus):
        for doc in corpus:
            assert doc.get("id"), f"Document missing id: {doc.get('texto', '')[:50]}"

    def test_golden_set_covers_all_norm_types(self, corpus_by_id):
        covered_types = set()
        for entry in GOLDEN_SET:
            for doc_id in entry["expected_doc_ids"]:
                doc = corpus_by_id.get(doc_id)
                if doc:
                    covered_types.add(doc["tipo_norma"])
        assert "Constitucion" in covered_types
        assert "Ley" in covered_types
        assert "Decreto Supremo" in covered_types
