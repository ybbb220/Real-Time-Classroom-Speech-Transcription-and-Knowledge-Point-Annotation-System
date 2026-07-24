import numpy as np
import faiss
from sentence_transformers import SentenceTransformer
import os

if "HF_TOKEN" not in os.environ:
    print("[Warning] HF_TOKEN environment variable is not set. "
          "Some models may require authentication.")


_retriever: "BGERetriever | None" = None


def get_retriever(docs: list[str] = None) -> "BGERetriever":
    # 获取全局单例 BGERetriever
    global _retriever
    if _retriever is None:
        _retriever = BGERetriever(docs=docs or [])
    elif docs is not None:
        _retriever.rebuild(docs)
    return _retriever


class BGERetriever:
    def __init__(self, model_name="BAAI/bge-base-zh-v1.5", docs=None):
        self.model = SentenceTransformer(model_name)
        self.query_prefix = "为这段课堂讲解生成表示以用于检索相关知识点："
        self.docs = []
        self.index = None
        if docs is not None:
            self.build(docs)

    def build(self, docs: list[str]):
        self.docs = docs
        dim = 768  # BGE base 输出维度
        self.index = faiss.IndexFlatIP(dim)
        if docs:
            embs = self.model.encode(
                docs,
                normalize_embeddings=True,
                convert_to_numpy=True,
            ).astype(np.float32)
            self.index.add(embs)
        print(f"[Retriever] 索引构建完成，ntotal={self.index.ntotal}")

    def rebuild(self, docs: list[str]):
        # 用新的文档列表重建索引
        self.build(docs)

    def add(self, new_docs: list[str]):
        # 增量加文档
        if self.index is None:
            raise RuntimeError("先调用 build()")
        self.docs.extend(new_docs)
        embs = self.model.encode(
            new_docs,
            normalize_embeddings=True,
            convert_to_numpy=True,
        ).astype(np.float32)
        self.index.add(embs)
        print(f"[Retriever] 增量 +{len(new_docs)}，ntotal={self.index.ntotal}")

    def search(self, query: str, k: int = 3, threshold: float = 0.55) -> list[dict]:
        if self.index is None:
            raise RuntimeError("先调用 build() 或传入 docs 初始化索引")
        if self.index.ntotal == 0:
            return []
        q_vec = self.model.encode(
            [self.query_prefix + query],
            normalize_embeddings=True,
            convert_to_numpy=True,
        ).astype(np.float32)
        scores, ids = self.index.search(q_vec, k)

        # top1 相似度未超过阈值，不做标记
        top1_score = float(scores[0][0])
        if top1_score <= threshold:
            return []

        # top1 超过阈值，标记该语句并返回匹配结果
        results = []
        for rank, doc_id in enumerate(ids[0]):
            results.append({
                "rank": rank + 1,
                "score": float(scores[0][rank]),
                "doc": self.docs[doc_id],
            })
        return results

# 测试部分
if __name__ == '__main__':
    docs = [
        "深度学习在计算机视觉中的应用",
        "如何用 Python 进行数据分析",
        "如何用 Python 编程",
    ]
    r = BGERetriever(docs=docs)

    hits = r.search("Python 数据处理", k=2)
    if hits:
        print("✓ 已标记（top1 > 0.8）：")
        for h in hits:
            print(f"  Top{h['rank']} {h['score']:.4f} → {h['doc']}")
    else:
        print("✗ 未标记（top1 ≤ 0.8）")

    hits2 = r.search("今天天气真好", k=2)
    if hits2:
        print("✓ 已标记（top1 > 0.8）：")
        for h in hits2:
            print(f"  Top{h['rank']} {h['score']:.4f} → {h['doc']}")
    else:
        print("✗ 未标记（top1 ≤ 0.8），什么也不做")