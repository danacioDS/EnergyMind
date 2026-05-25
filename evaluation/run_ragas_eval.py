"""
RAGAS evaluation on the golden test set.

Measures retrieval quality (context precision, context recall) and
generation quality (faithfulness, answer relevancy) for the LexEnergy pipeline.

Usage:
    python -m evaluation.run_ragas_eval
"""
import json
import asyncio
from pathlib import Path
from typing import List, Dict, Any

from datasets import Dataset
from loguru import logger

from app.config import settings
from app.rag.pipeline import RAGPipeline

GOLDEN_PATH = Path(__file__).resolve().parent.parent / "tests" / "test_retrieval_golden.py"

GOLDEN_QUERIES = [
    "inversión extranjera en Bolivia constitución",
    "incentivos para energía solar en Bolivia",
    "arbitraje internacional en el sector eléctrico",
    "control estatal de sectores estratégicos energía",
    "requisitos para inversión extranjera en renovables",
    "jerarquía constitucional bolivia artículo 410",
    "generación distribuida autoconsumo excedentes",
    "promoción de energías alternativas renovables",
    "plazo aprobación AETN proyectos renovables",
    "libre iniciativa privada sector eléctrico",
]

GROUND_TRUTH = [
    "La Constitución boliviana establece que la inversión extranjera está sujeta a jurisdicción boliviana (Art. 320) y que los recursos naturales son dominio del Estado (Art. 349).",
    "El DS 5503 establece exención arancelaria, depreciación acelerada y tarifa preferencial para proyectos solares. La Ley 943 incorpora incentivos para renovables no convencionales.",
    "El Artículo 45 de la Ley 1604 permitía arbitraje internacional, pero la modificación por Ley 943 lo elimina, sujetando controversias a jurisdicción boliviana.",
    "El Artículo 351 CPE declara la energía como sector estratégico bajo control estatal. El Artículo 378 reafirma el control estatal sobre la cadena productiva energética.",
    "El DS 5503 exige constituir sociedad bajo leyes bolivianas (Art. 4) y suscribir contrato de inversión con el Estado (Art. 5).",
    "El Artículo 410 CPE establece que la Constitución es la norma suprema y prevalece sobre cualquier otra disposición normativa.",
    "La Ley 1604 Art. 17 y la Ley 943 permiten generación distribuida para autoconsumo con inyección de excedentes. El DS 5503 Art. 7 exime de concesión a proyectos <1MW.",
    "El Artículo 355 CPE y el Artículo 379 CPE establecen la obligación del Estado de promover energías alternativas y renovables.",
    "El DS 5503 Art. 6 establece que la AETN tiene 90 días para aprobar solicitudes de conexión, con silencio administrativo positivo.",
    "La Ley 1604 Art. 1-2 reconoce la libre iniciativa privada y libre competencia en el sector eléctrico.",
]


async def evaluate():
    logger.info("Starting RAGAS evaluation")

    pipeline = RAGPipeline()
    await pipeline.initialize()

    questions = []
    answers = []
    contexts = []
    ground_truths = []

    for query, gt in zip(GOLDEN_QUERIES, GROUND_TRUTH):
        logger.info(f"Evaluating: {query[:50]}...")
        response = await pipeline.query(question=query)

        questions.append(query)
        answers.append(response.answer.regulatory_analysis or response.answer.direct_conclusion)
        contexts.append([c.texto for c in response.answer.legal_citations])
        ground_truths.append([gt])

    await pipeline.close()

    dataset = Dataset.from_dict({
        "question": questions,
        "answer": answers,
        "contexts": contexts,
        "ground_truth": ground_truths,
    })

    try:
        from ragas import evaluate as ragas_evaluate
        from ragas.metrics import (
            faithfulness,
            answer_relevancy,
            context_precision,
            context_recall,
        )

        result = ragas_evaluate(
            dataset,
            metrics=[faithfulness, answer_relevancy, context_precision, context_recall],
        )

        df = result.to_pandas()
        print("\n=== RAGAS Evaluation Results ===")
        print(df.to_string())
        print(f"\nAverages:")
        print(f"  Faithfulness:       {df['faithfulness'].mean():.3f}")
        print(f"  Answer Relevancy:   {df['answer_relevancy'].mean():.3f}")
        print(f"  Context Precision:  {df['context_precision'].mean():.3f}")
        print(f"  Context Recall:     {df['context_recall'].mean():.3f}")

        output_path = Path("evaluation/results.json")
        output_path.parent.mkdir(parents=True, exist_ok=True)
        result.to_pandas().to_json(output_path, orient="records", indent=2)
        logger.info(f"Results saved to {output_path}")

    except ImportError as e:
        logger.warning(f"RAGAS not installed ({e}). Skipping metrics.")
        logger.info("Install with: pip install ragas")
        logger.info("Raw results saved but no metrics computed.")


if __name__ == "__main__":
    asyncio.run(evaluate())
