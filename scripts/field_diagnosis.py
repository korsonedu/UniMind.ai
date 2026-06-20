#!/usr/bin/env python3
"""
Field 诊断引擎：图信念传播

输入：知识图 + 部分观测（学生做过的题 × 对/错）
输出：每个 KP 的 E[K] + 不确定度 + 全局知识热力图

算法：Iterative Belief Propagation on KPGraph
  - 前置边：K_child ≤ K_parent + ε（硬约束传播）
  - 关联边：K 向邻居均值收缩（平滑传播）
  - 观测：降低 σ²，更新 μ
"""
import json, math, numpy as np
from collections import defaultdict
from scipy.sparse import csr_matrix


class FieldDiagnosis:
    def __init__(self, tree_file, edge_file):
        with open(tree_file) as f:
            data = json.load(f)
        nodes = data['nodes']
        self.kps = [n for n in nodes if n.get('level') == 'kp']
        self.kp_names = [n['name'] for n in self.kps]
        self.kp_ids = [n['id'] for n in self.kps]
        self.id2i = {kid: i for i, kid in enumerate(self.kp_ids)}
        self.n = len(self.kps)
        self.n2id = {nd['name']: nd['id'] for nd in self.kps}

        # 加载 LLM edges
        self._build_edges(edge_file, nodes)

        # 信念状态
        self.mu = np.full(self.n, 0.5)      # 估计掌握度
        self.sigma2 = np.full(self.n, 0.25)  # 不确定度（方差）
        self.observed = np.zeros(self.n, dtype=bool)

    def _build_edges(self, edge_file, nodes):
        adj = defaultdict(list)
        # tree parent-child
        for nd in nodes:
            pid = nd.get('parent_id')
            if pid and nd['id'] in self.id2i and pid in self.id2i:
                adj[nd['id']].append((pid, 0.8))
                adj[pid].append((nd['id'], 0.8))
        # siblings
        cbp = defaultdict(list)
        for nd in nodes:
            pid = nd.get('parent_id')
            if pid and nd['id'] in self.id2i:
                cbp[pid].append(nd['id'])
        for s in cbp.values():
            for i in range(len(s)):
                for j in range(i + 1, len(s)):
                    adj[s[i]].append((s[j], 0.3))
                    adj[s[j]].append((s[i], 0.3))

        with open(edge_file) as f:
            llm = json.load(f)

        # 前置边和关联边分开
        self.prereq_edges = []   # (parent, child, weight)
        self.assoc_edges = []    # (a, b, weight)

        pair_seen = set()
        for e in llm:
            s = self.n2id.get(e.get('source_name', ''))
            t = self.n2id.get(e.get('target_name', ''))
            if not (s and t and s in self.id2i and t in self.id2i):
                continue
            et = e.get('edge_type', '')
            w = float(e.get('weight', 0.5))
            si, ti = self.id2i[s], self.id2i[t]

            # 去双向
            pair = tuple(sorted([si, ti]))
            if pair in pair_seen:
                continue
            pair_seen.add(pair)

            if et == 'prerequisite':
                self.prereq_edges.append((si, ti, w))  # si → ti: ti depends on si
            else:
                self.assoc_edges.append((si, ti, w))

        n_prereq = len(self.prereq_edges)
        n_assoc = len(self.assoc_edges)
        print(f"Diagnosis engine: {self.n} KPs, {n_prereq} prereq edges, {n_assoc} assoc edges")

    def observe(self, kp_idx, correct, confidence=0.9):
        obs_val = 0.85 if correct else 0.15
        obs_var = (1.0 - confidence) * 0.5
        old_prec = 1.0 / max(self.sigma2[kp_idx], 0.001)
        new_prec = 1.0 / max(obs_var, 0.001)
        self.mu[kp_idx] = (old_prec * self.mu[kp_idx] + new_prec * obs_val) / (old_prec + new_prec)
        self.sigma2[kp_idx] = 1.0 / (old_prec + new_prec)
        self.observed[kp_idx] = True

        # ★ 观测后立即沿前置链传播
        self._propagate_observation(kp_idx)

    def _propagate_observation(self, src_idx, decay=0.5, max_depth=4):
        """沿前置链传播一次观测：更新所有可达节点的信念"""
        visited = {src_idx}
        queue = [(src_idx, 0)]  # (node, depth)

        while queue:
            i, depth = queue.pop(0)
            if depth >= max_depth:
                continue

            # 传播到子节点（forward）
            for p, c, w in self.prereq_edges:
                if p != i or c in visited:
                    continue
                visited.add(c)
                queue.append((c, depth + 1))
                # child ≤ parent + margin
                margin = 0.12 * (1.0 - w)
                if self.mu[c] > self.mu[i] + margin:
                    self.mu[c] = self.mu[i] + margin
                # 降低 child 的不确定度（parent 已知 → child 也受到约束）
                info_gain = (decay ** depth) * w * 0.1
                self.sigma2[c] = max(0.01, self.sigma2[c] - info_gain)

            # 传播到父节点（backward）
            for p, c, w in self.prereq_edges:
                if c != i or p in visited:
                    continue
                visited.add(p)
                queue.append((p, depth + 1))
                margin = 0.12 * (1.0 - w)
                if self.mu[p] < self.mu[i] - margin:
                    self.mu[p] = self.mu[i] - margin
                info_gain = (decay ** depth) * w * 0.1
                self.sigma2[p] = max(0.01, self.sigma2[p] - info_gain)

    def _topological_order(self):
        """Kahn on prereq graph → topological order"""
        indeg = defaultdict(int)
        children = defaultdict(list)
        for p, c, _ in self.prereq_edges:
            indeg[c] += 1
            children[p].append(c)
        q = [i for i in range(self.n) if indeg[i] == 0]
        order = []
        while q:
            i = q.pop()
            order.append(i)
            for c in children[i]:
                indeg[c] -= 1
                if indeg[c] == 0:
                    q.append(c)
        return order, children

    def propagate(self, n_iter=3):
        """图信念传播：双向硬约束 + 关联平滑"""
        topo, children = self._topological_order()

        for _ in range(n_iter):
            # Forward pass (root→leaf): parent constrains child
            for i in topo:
                for c in children.get(i, []):
                    # 找 i→c 的边权重
                    w = 1.0
                    for p, ch, wt in self.prereq_edges:
                        if p == i and ch == c:
                            w = wt
                            break
                    margin = 0.12 * (1.0 - w)
                    # child 不能远高于 parent
                    if self.mu[c] > self.mu[i] + margin:
                        self.mu[c] = self.mu[i] + margin

            # Backward pass (leaf→root): child observations inform parent
            for i in reversed(topo):
                for c in children.get(i, []):
                    w = 1.0
                    for p, ch, wt in self.prereq_edges:
                        if p == i and ch == c:
                            w = wt
                            break
                    margin = 0.12 * (1.0 - w)
                    # parent 不能远低于 child（观测到 child 高→parent 也该高）
                    if self.mu[i] < self.mu[c] - margin:
                        self.mu[i] = self.mu[c] - margin

            # 关联平滑
            alpha_assoc = 0.15
            for a, b, w in self.assoc_edges:
                diff = self.mu[a] - self.mu[b]
                pull = alpha_assoc * w * diff
                self.mu[a] -= pull
                self.mu[b] += pull

            self.mu = np.clip(self.mu, 0.01, 0.99)

    def infer_all(self):
        """运行完整诊断流程"""
        self.propagate(n_iter=5)

        results = []
        for i in range(self.n):
            results.append({
                'name': self.kp_names[i],
                'mu': self.mu[i],
                'sigma': math.sqrt(self.sigma2[i]),
                'observed': self.observed[i],
            })
        return results

    def top_uncertainty(self, k=10, exclude_observed=True):
        """返回最不确定的 KP（用于选下一道题）"""
        scores = []
        for i in range(self.n):
            if exclude_observed and self.observed[i]:
                continue
            # 信息增益：高不确定度 + 图中重要性（度数）
            scores.append((i, self.sigma2[i], self.mu[i]))
        scores.sort(key=lambda x: -x[1])
        return [(i, sigma, mu) for i, sigma, mu in scores[:k]]

    def top_info_gain(self, k=10, exclude_observed=True):
        """信息价值最高的 KP：自己的不确定度 + 能影响多少邻居"""
        scores = []
        for i in range(self.n):
            if exclude_observed and self.observed[i]:
                continue
            # 出度：inform 多少下游
            out_deg = sum(1 for p, c, _ in self.prereq_edges if p == i)
            # 自己的不确定度 × (1 + 影响范围)
            gain = self.sigma2[i] * (1.0 + 0.5 * out_deg)
            scores.append((i, gain))
        scores.sort(key=lambda x: -x[1])
        return [(i, gain) for i, gain in scores[:k]]


# ═══ Demo: 全面扫描 ═══
if __name__ == '__main__':
    import random
    random.seed(42)
    np.random.seed(42)

    for tree_name, (tree_file, edge_file) in [
        ('CFA',  ('cfa_tree.json',  'cfa_llm_edges.json')),
        ('Math', ('math_tree.json', 'math_llm_edges.json')),
    ]:
        print(f"\n{'='*60}")
        print(f"[{tree_name}]")
        print(f"{'='*60}")

        engine = FieldDiagnosis(tree_file, edge_file)
        topo, children = engine._topological_order()

        # 生成符合图结构的知识状态
        true_K = np.zeros(engine.n)
        for i in topo:
            parent_K = 0.0
            for p, c, _ in engine.prereq_edges:
                if c == i:
                    parent_K = max(parent_K, true_K[p])
            if parent_K > 0:
                true_K[i] = np.clip(np.random.normal(parent_K, 0.12), 0.05, 0.95)
            else:
                true_K[i] = np.random.beta(2, 2)

        # 扫不同观测数量
        for n_obs in [5, 10, 20, 40, 80]:
            engine2 = FieldDiagnosis(tree_file, edge_file)
            # 复制 true_K
            obs_indices = random.sample(range(engine2.n), min(n_obs, engine2.n))

            for i in obs_indices:
                correct = true_K[i] > random.random() * 0.25 + 0.35
                engine2.observe(i, correct)

            engine2.infer_all()

            err_unobs = [abs(engine2.mu[i] - true_K[i]) for i in range(engine2.n) if not engine2.observed[i]]
            naive_unobs = [abs(0.5 - true_K[i]) for i in range(engine2.n) if not engine2.observed[i]]
            mae_field = np.mean(err_unobs)
            mae_naive = np.mean(naive_unobs)
            impr = (mae_naive - mae_field) / mae_naive * 100

            print(f"  observations={n_obs:3d}  naive MAE={mae_naive:.4f}  Field MAE={mae_field:.4f}  improvement={impr:+.1f}%")