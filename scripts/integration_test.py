"""Integration test: real LLM call + embedding download."""
import sys
sys.path.insert(0, r'D:\Agent八股_项目_学习\mutil-rag-agent')

print("=" * 60)
print("Test 1: DeepSeek LLM real call")
print("=" * 60)
from app.core.llm import get_chat_llm
llm = get_chat_llm(temperature=0)
try:
    resp = llm.invoke("请用一句话回复：今天天气真好")
    print(f"  [PASS] DeepSeek responded: {resp.content[:80]}...")
except Exception as e:
    print(f"  [FAIL] {type(e).__name__}: {e}")

print()
print("=" * 60)
print("Test 2: BGE Embedding (first run downloads model ~400MB)")
print("=" * 60)
from app.core.embedding import get_embeddings
try:
    emb = get_embeddings()
    vec = emb.embed_query("测试中文查询")
    print(f"  [PASS] Embedding dim={len(vec)}, first 5 values={vec[:5]}")
    assert len(vec) == 512, f"Expected 512, got {len(vec)}"
    print(f"  [PASS] Dimension 512 confirmed")
except Exception as e:
    print(f"  [FAIL] {type(e).__name__}: {e}")

print()
print("=" * 60)
print("Test 3: BGE Reranker")
print("=" * 60)
from app.core.reranker import rerank_docs
from langchain_core.documents import Document
docs = [
    Document(page_content="Redis 内存使用率达到 90%，需要排查内存泄漏", metadata={"id": "1"}),
    Document(page_content="Redis 集群配置参数详解", metadata={"id": "2"}),
    Document(page_content="MySQL 慢查询优化指南", metadata={"id": "3"}),
]
import asyncio
try:
    ranked = asyncio.run(rerank_docs("Redis 内存占用高", docs, top_n=2))
    for i, d in enumerate(ranked):
        score = d.metadata.get("rerank_score", "N/A")
        print(f"  #{i+1} score={score:.4f} content={d.page_content[:50]}...")
    print(f"  [PASS] Reranker OK")
except Exception as e:
    print(f"  [FAIL] {type(e).__name__}: {e}")

print()
print("All integration tests completed.")
