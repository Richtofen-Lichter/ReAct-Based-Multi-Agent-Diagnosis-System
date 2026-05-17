"""Reranker 封装 (本地 BGE CrossEncoder).

为什么要加 Reranker
======================
向量检索 (bi-encoder) 把 query 和 doc 分别编码成向量后算 cosine, 这是一次"粗排":
  - 优点: 预先算好 doc 向量, 查询时只算 query 向量 + 一次 ANN 搜索, 延迟低
  - 局限: query 和 doc 从未在同一个模型上下文中交互过, 对细粒度语义差异不敏感
         (比如 "Redis 内存占用高" vs "Redis 内存泄漏排查", 向量很接近但问的是不同事)

Reranker (cross-encoder) 把 (query, doc) 作为一对一起送进模型, 能捕捉精细的语义关联:
  - 优点: 准确度显著高于 bi-encoder
  - 局限: 每对都要跑一次模型, 无法提前算好 → 只能用在"粗排后重排少量候选"这一步

典型流水线
======================
  用户 query ─▶ (Hybrid: BM25 ∪ Vector) 取 top-20 ─▶ Rerank ─▶ 取 top-3 ─▶ LLM

为什么选本地 BGE-reranker-base (而不是 DashScope gte-rerank-v2)
======================
  - 本地推理零 API 成本, 无需网络
  - BGE-reranker-base 与 BGE-small-zh embedding 同家族, 语义对齐
  - 局限: 首次加载需下载模型 (~1GB), CPU 推理约 50-200ms/对

降级策略
======================
任何异常都返回原始 docs 的前 top_n 项, 不阻断业务:
  - 模型加载失败       → 直接降级
  - 推理异常           → 降级
  - docs 为空          → 直接返回空
"""

from __future__ import annotations

from functools import lru_cache
from typing import List, Optional

from langchain_core.documents import Document
from loguru import logger

from app.config import settings


@lru_cache(maxsize=1)
def _get_reranker_model(model_name: str):
    """获取 CrossEncoder 模型单例 (按 model_name 缓存)."""
    from sentence_transformers import CrossEncoder

    logger.info(f"加载 Reranker 模型: {model_name}")
    return CrossEncoder(model_name, max_length=512)


async def rerank_docs(
    query: str,
    docs: List[Document],
    *,
    top_n: Optional[int] = None,
    model: Optional[str] = None,
    timeout: Optional[float] = None,
) -> List[Document]:
    """对候选文档做 Rerank, 返回按相关性降序排列的 top_n 个.

    Args:
        query:   用户原始问题
        docs:    粗排候选 (通常 10-30 个)
        top_n:   返回多少个 (None = settings.rag_top_k)
        model:   rerank 模型名 (None = settings.rag_rerank_model)
        timeout: 保留参数 (本地推理不使用, 保持接口兼容)

    Returns:
        List[Document]: 重排后的 top_n 文档 (原 Document 对象, 附加
        doc.metadata["rerank_score"] 表示 reranker 给出的分数; 发生降级时
        无该字段).

    保证:
        永不抛异常. 任何故障都降级为 docs[:top_n].
    """
    top_n = top_n if top_n is not None else settings.rag_top_k
    model_name = model or settings.rag_rerank_model

    if not docs:
        return []
    if top_n <= 0:
        return []

    # 1) 加载模型
    try:
        cross_encoder = _get_reranker_model(model_name)
    except Exception as e:
        logger.warning(f"[rerank] 模型加载失败, 降级到粗排前 top_n: {e}")
        return docs[:top_n]

    # 2) 构造 (query, doc) 对
    doc_texts = [d.page_content for d in docs]
    pairs = [(query, text) for text in doc_texts]

    # 3) 推理
    try:
        scores = cross_encoder.predict(pairs, show_progress_bar=False)
    except Exception as e:
        logger.warning(f"[rerank] 推理失败, 降级: {type(e).__name__}: {e}")
        return docs[:top_n]

    # 4) 按分数降序排列
    try:
        indexed = list(enumerate(scores))
        indexed.sort(key=lambda x: x[1], reverse=True)  # type: ignore[arg-type]

        reranked: List[Document] = []
        for idx, score in indexed:
            if idx >= len(docs):
                continue
            doc = docs[idx]
            new_meta = dict(doc.metadata or {})
            new_meta["rerank_score"] = float(score)
            reranked.append(
                Document(page_content=doc.page_content, metadata=new_meta)
            )
            if len(reranked) >= top_n:
                break

        if not reranked:
            return docs[:top_n]

        logger.info(
            f"[rerank] ok: query={query[:40]!r} "
            f"candidates={len(docs)} -> top_n={len(reranked)} "
            f"top1_score={reranked[0].metadata.get('rerank_score'):.3f}"
        )
        return reranked

    except Exception as e:
        logger.warning(f"[rerank] 解析结果失败, 降级: {type(e).__name__}: {e}")
        return docs[:top_n]
