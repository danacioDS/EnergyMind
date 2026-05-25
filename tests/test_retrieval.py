import pytest
from app.retrieval.metadata_filter import MetadataFilter
from app.retrieval.bm25 import BM25Retriever
from app.retrieval.dense import DenseRetriever
from app.retrieval.reranker import Reranker


class TestMetadataFilter:
    def test_infer_solar_subsector(self):
        result = MetadataFilter.infer_from_query(
            "What incentives exist for solar energy?"
        )
        assert result.get("subsector") == "Solar"
        assert result.get("vigente") is True

    def test_infer_investment_focus(self):
        result = MetadataFilter.infer_from_query(
            "Can foreign companies investment in Bolivia?"
        )
        assert result.get("enfoque") == "Inversion"

    def test_infer_with_explicit_filter(self):
        result = MetadataFilter.infer_from_query(
            "Solar incentives",
            {"tipo_norma": "Ley"},
        )
        assert result.get("subsector") == "Solar"
        assert result.get("tipo_norma") == "Ley"

    def test_infer_constitutional_query(self):
        result = MetadataFilter.infer_from_query(
            "What does the constitutional say about energy?"
        )
        assert result.get("tipo_norma") == "Constitucion"

    def test_empty_query(self):
        result = MetadataFilter.infer_from_query("")
        assert result.get("vigente") is True


class TestBM25Retriever:
    @pytest.fixture
    def retriever(self):
        return BM25Retriever()

    def test_build_index(self, retriever):
        docs = [
            {"id": "1", "texto": "Solar energy incentives for renewable generation"},
            {"id": "2", "texto": "Foreign investment in electricity sector"},
            {"id": "3", "texto": "Constitutional framework for natural resources"},
        ]
        retriever.build_index(docs)
        assert retriever.index is not None

    @pytest.mark.asyncio
    async def test_search(self, retriever):
        docs = [
            {"id": "1", "texto": "Solar energy incentives for renewable generation"},
            {"id": "2", "texto": "Foreign investment in electricity sector"},
            {"id": "3", "texto": "Constitutional framework for natural resources"},
        ]
        retriever.build_index(docs)
        results = await retriever.search("solar incentives", top_k=2)
        assert len(results) <= 2
        assert "solar" in results[0].get("texto", "").lower() or "incentives" in results[0].get("texto", "").lower()


class TestDenseRetriever:
    @pytest.mark.asyncio
    async def test_search_empty_docs(self):
        retriever = DenseRetriever()
        results = await retriever.search("test query", [])
        assert results == []


class TestReranker:
    @pytest.mark.asyncio
    async def test_rerank_empty(self):
        reranker = Reranker()
        results = await reranker.rerank("test", [])
        assert results == []
