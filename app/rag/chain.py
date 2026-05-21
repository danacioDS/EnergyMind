from typing import List, Dict, Any, Optional
from loguru import logger
from langchain_ollama import ChatOllama
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from langchain_core.runnables import RunnablePassthrough

from app.config import settings
from app.prompts.legal_prompts import (
    LEGAL_SYSTEM_PROMPT,
    LEGAL_RESPONSE_TEMPLATE,
    EXTRACTIVE_QA_PROMPT,
    RISK_ANALYSIS_PROMPT,
)


class LegalChain:
    def __init__(self):
        self.llm = self._init_llm()
        self.qa_chain = self._build_qa_chain()
        self.risk_chain = self._build_risk_chain()

    def _init_llm(self):
        if settings.llm_provider == "ollama":
            return ChatOllama(
                model=settings.llm_model,
                base_url=settings.ollama_base_url,
                temperature=0.1,
                top_p=0.9,
                num_predict=4096,
            )
        elif settings.llm_provider == "openai":
            return ChatOpenAI(
                model=settings.openai_model,
                api_key=settings.openai_api_key,
                temperature=0.1,
            )
        else:
            raise ValueError(f"Unknown LLM provider: {settings.llm_provider}")

    def _build_qa_chain(self):
        prompt = ChatPromptTemplate.from_messages([
            ("system", LEGAL_SYSTEM_PROMPT),
            ("human", LEGAL_RESPONSE_TEMPLATE),
        ])
        return prompt | self.llm | StrOutputParser()

    def _build_risk_chain(self):
        prompt = ChatPromptTemplate.from_messages([
            ("system", LEGAL_SYSTEM_PROMPT),
            ("human", RISK_ANALYSIS_PROMPT),
        ])
        return prompt | self.llm | StrOutputParser()

    async def answer(self, question: str, context: str) -> str:
        logger.info(f"Generating answer for: {question[:80]}...")
        response = await self.qa_chain.ainvoke({
            "question": question,
            "context": context,
        })
        return response

    async def analyze_risk(self, question: str, context: str) -> str:
        logger.info("Running risk analysis...")
        response = await self.risk_chain.ainvoke({
            "question": question,
            "context": context,
        })
        return response
