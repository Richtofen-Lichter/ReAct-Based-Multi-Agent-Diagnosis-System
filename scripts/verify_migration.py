"""Quick verification script for LLM + Embedding migration."""
import sys
sys.path.insert(0, r'D:\Agent八股_项目_学习\mutil-rag-agent')

print("=" * 60)
print("Test 1: Config loading")
print("=" * 60)
from app.config import settings
print(f'  deepseek_api_key configured: {bool(settings.deepseek_api_key.strip() and not settings.deepseek_api_key.startswith("your-"))}')
print(f'  deepseek_chat_model: {settings.deepseek_chat_model}')
print(f'  deepseek_router_model: {settings.deepseek_router_model}')
print(f'  local_embedding_model: {settings.local_embedding_model}')
print(f'  local_embedding_dim: {settings.local_embedding_dim}')
print(f'  local_llm_probe_host: {settings.local_llm_probe_host}')
print(f'  rag_rerank_model: {settings.rag_rerank_model}')
print()
print(f'  dashscope_api_key configured: {bool(settings.dashscope_api_key.strip())}')
print(f'  dashscope_chat_model: {settings.dashscope_chat_model}')
print()

print("=" * 60)
print("Test 2: validate_runtime()")
print("=" * 60)
try:
    settings.validate_runtime()
    print("  [PASS] Runtime validation passed")
except RuntimeError as e:
    print(f"  [INFO] Runtime validation: {e}")

print()
print("=" * 60)
print("Test 3: get_chat_llm() — default (DeepSeek)")
print("=" * 60)
from app.core.llm import get_chat_llm
llm = get_chat_llm(temperature=0)
print(f"  model_name: {llm.model_name}")
print(f"  base_url: {llm.openai_api_base if hasattr(llm, 'openai_api_base') else 'N/A'}")

print()
print("=" * 60)
print("Test 4: get_chat_llm() — DashScope fallback (qwen prefix)")
print("=" * 60)
try:
    llm2 = get_chat_llm(model="qwen-turbo", temperature=0)
    print(f"  model_name: {llm2.model_name}")
    print(f"  base_url: {llm2.openai_api_base if hasattr(llm2, 'openai_api_base') else 'N/A'}")
except Exception as e:
    print(f"  [EXPECTED] DashScope LLM创建失败 (无 API key): {type(e).__name__}")

print()
print("=" * 60)
print("Test 5: Embedding import check")
print("=" * 60)
try:
    from langchain_huggingface import HuggingFaceEmbeddings
    print("  [PASS] langchain_huggingface import OK")
except ImportError as e:
    print(f"  [FAIL] langchain_huggingface import: {e}")

try:
    from sentence_transformers import SentenceTransformer, CrossEncoder
    print("  [PASS] sentence_transformers import OK")
except ImportError as e:
    print(f"  [FAIL] sentence_transformers import: {e}")

print()
print("=" * 60)
print("Test 6: Reranker import check")
print("=" * 60)
from app.core.reranker import rerank_docs
print("  [PASS] rerank_docs imported")

print()
print("All tests completed.")
