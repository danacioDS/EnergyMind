from typing import TypedDict, List, Dict, Any, Optional, Literal
from loguru import logger
from langgraph.graph import StateGraph, END

from app.rag.chain import LegalChain
from app.retrieval.engine import RetrievalEngine
from app.rag.context_builder import ContextBuilder
from app.models.schemas import StructuredLegalResponse


class AgentState(TypedDict):
    question: str
    subsector: Optional[str]
    tipo_norma: Optional[str]
    documents: List[Dict[str, Any]]
    context: str
    analysis: str
    risk_analysis: str
    iteration: int
    needs_refinement: bool
    final_answer: str
    citations: List[Dict[str, Any]]
    structured_response: Optional[StructuredLegalResponse]


REFINE_PROMPT = """The following legal question about Bolivian renewable energy did not yield sufficient results.
Rephrase it to be more specific using Spanish legal terminology for broader search coverage.

Original: {question}
Rephrased:"""


class LegalAgentGraph:
    def __init__(self):
        self.chain = LegalChain()
        self.retrieval = RetrievalEngine()
        self.context_builder = ContextBuilder()
        self.graph = self._build_graph()

    async def initialize(self):
        await self.retrieval.initialize()
        logger.info("LegalAgentGraph initialized")

    def _build_graph(self) -> StateGraph:
        workflow = StateGraph(AgentState)

        workflow.add_node("retrieve", self._retrieve_node)
        workflow.add_node("analyze", self._analyze_node)
        workflow.add_node("risk_assess", self._risk_assess_node)
        workflow.add_node("refine", self._refine_node)
        workflow.add_node("finalize", self._finalize_node)

        workflow.set_entry_point("retrieve")

        workflow.add_edge("retrieve", "analyze")

        workflow.add_conditional_edges(
            "analyze",
            self._check_refinement,
            {"risk_assess": "risk_assess", "refine": "refine"},
        )

        workflow.add_edge("risk_assess", "finalize")
        workflow.add_edge("refine", "retrieve")
        workflow.add_edge("finalize", END)

        return workflow.compile()

    async def _retrieve_node(self, state: AgentState) -> AgentState:
        logger.info(f"Agent retrieve (iteration {state.get('iteration', 0)})")
        metadata_filter: Dict[str, Any] = {}
        if state.get("subsector"):
            metadata_filter["subsector"] = state["subsector"]
        if state.get("tipo_norma"):
            metadata_filter["tipo_norma"] = state["tipo_norma"]

        documents, _ = await self.retrieval.retrieve(
            query=state["question"],
            metadata_filter=metadata_filter,
        )

        state["documents"] = documents
        state["needs_refinement"] = len(documents) == 0
        return state

    async def _analyze_node(self, state: AgentState) -> AgentState:
        logger.info("Agent analyze")
        if not state.get("documents"):
            state["needs_refinement"] = state.get("iteration", 0) < 3
            return state

        context = self.context_builder.build_context(state["documents"])
        state["context"] = context
        state["citations"] = self.context_builder.extract_citations(state["documents"])

        response = await self.chain.structured_answer(state["question"], context)
        state["structured_response"] = response
        state["analysis"] = response.regulatory_analysis
        state["needs_refinement"] = response.insufficient_context and state.get("iteration", 0) < 3
        return state

    async def _risk_assess_node(self, state: AgentState) -> AgentState:
        logger.info("Agent risk assessment")
        risk = await self.chain.analyze_risk(state["question"], state["context"])
        state["risk_analysis"] = risk
        return state

    async def _refine_node(self, state: AgentState) -> AgentState:
        state["iteration"] = state.get("iteration", 0) + 1
        logger.info(f"Agent refine - expanding query (iter {state['iteration']})")

        response = await self.chain.llm.ainvoke(
            REFINE_PROMPT.format(question=state["question"])
        )
        state["question"] = str(response.content).strip()

        state["needs_refinement"] = state["iteration"] < 3

        logger.info(f"Refined question: {state['question'][:80]}")
        return state

    async def _finalize_node(self, state: AgentState) -> AgentState:
        logger.info("Agent finalize")
        sr = state.get("structured_response")
        if sr and not sr.insufficient_context:
            answer_parts = [sr.regulatory_analysis]
            if state.get("risk_analysis"):
                answer_parts.append("\n\n## RISK ANALYSIS\n" + state["risk_analysis"])
            state["final_answer"] = "\n".join(answer_parts)
        else:
            state["final_answer"] = "Insufficient information in the specialized renewable energy legal corpus."
        return state

    def _check_refinement(self, state: AgentState) -> Literal["risk_assess", "refine"]:
        if state.get("needs_refinement", False) and state.get("iteration", 0) < 3:
            return "refine"
        return "risk_assess"

    async def run(self, question: str, subsector: Optional[str] = None,
                  tipo_norma: Optional[str] = None) -> AgentState:
        initial_state: AgentState = {
            "question": question,
            "subsector": subsector,
            "tipo_norma": tipo_norma,
            "documents": [],
            "context": "",
            "analysis": "",
            "risk_analysis": "",
            "iteration": 0,
            "needs_refinement": False,
            "final_answer": "",
            "citations": [],
            "structured_response": None,
        }
        result = await self.graph.ainvoke(initial_state)
        return result

    async def close(self):
        await self.retrieval.close()
