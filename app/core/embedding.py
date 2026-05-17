"""Embedding 服务.

封装 sentence-transformers BGE 模型的向量化能力.

设计要点:
  - 自定义 LangChain Embeddings 包装 sentence-transformers
  - BGE 模型对 query 需要加 instruction prefix, 对 document 不加
  - 单例: 整个进程只创建一次实例 (首次加载会从 HuggingFace 下载模型)
"""

from functools import lru_cache
from typing import List

from langchain_core.embeddings import Embeddings
from loguru import logger

from app.config import settings
from app.exceptions import EmbeddingError

# BGE 模型对 query 侧需要的 instruction prefix
# ref: https://huggingface.co/BAAI/bge-small-zh
_BGE_QUERY_INSTRUCTION = "为这个句子生成表示以用于检索相关文章："


class _BGEEmbeddings(Embeddings):
    """BGE 模型的 LangChain Embeddings 适配器.

    BGE 模型要求 query 和 document 使用不同的编码方式:
    - query: 加 instruction prefix
    - document: 不加 prefix
    """

    def __init__(self, model_name: str, device: str):
        from sentence_transformers import SentenceTransformer

        self._model = SentenceTransformer(model_name, device=device)
        self._dim = self._model.get_embedding_dimension()
        logger.info(f"BGE 模型已加载: {model_name} dim={self._dim} device={device}")

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        # BGE 文档侧不加 instruction prefix
        embeddings = self._model.encode(
            texts,
            normalize_embeddings=True,
            show_progress_bar=False,
        )
        return embeddings.tolist()

    def embed_query(self, text: str) -> List[float]:
        # BGE 查询侧加 instruction prefix
        embeddings = self._model.encode(
            [_BGE_QUERY_INSTRUCTION + text],
            normalize_embeddings=True,
            show_progress_bar=False,
        )
        return embeddings[0].tolist()

    @property
    def dimension(self) -> int:
        return self._dim


@lru_cache(maxsize=1)
def get_embeddings() -> Embeddings:
    """获取 Embedding 实例 (单例).

    Returns:
        Embeddings: LangChain Embeddings 接口的实例

    Raises:
        EmbeddingError: 模型加载失败时抛出
    """
    model_name = settings.local_embedding_model
    device = settings.local_embedding_device

    logger.info(
        f"创建 Embedding 客户端: model={model_name}, "
        f"dim={settings.local_embedding_dim}, device={device}"
    )

    try:
        return _BGEEmbeddings(model_name=model_name, device=device)
    except Exception as e:
        raise EmbeddingError(
            f"无法加载 Embedding 模型 {model_name}: {e}"
        ) from e
