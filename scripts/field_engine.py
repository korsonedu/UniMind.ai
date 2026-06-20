#!/usr/bin/env python3
"""
Field 引擎：诊断 + 自适应出题 + 路径规划

三层架构：
  FieldDiagnosis   → 图信念传播，估计全局知识状态
  FieldQuestions   → 基于信息增益的自适应出题
  FieldPlanner     → 基于诊断状态的目标路径规划
"""
import json, math, copy, numpy as np
from collections import defaultdict


class FieldDiagnosis:
    """图信念传播诊断引擎"""
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
        self._build_edges(edge_file, nodes)
        self.reset()

    def reset(self):
        self.mu = np.full(self.n, 0.5)
        self.sigma2 = np.full(self.n, 0.25)
        self.observed = np.zeros(self.n, dtype=bool)

    def _build_edges(self, edge_file, nodes):
        adj = defaultdict(list)
        for nd in nodes:
            pid = nd.get('parent_id')
            if pid and nd['id'] in self.id2i and pid in self.id2i:
                adj[nd['id']].append((pid, 0.8))
                adj[pid].append((nd['id'], 0.8))
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
        self.prereq_edges = []
        self.assoc_edges = []
        pair_seen = set()
        for e in llm:
            s = self.n2id.get(e.get('source_name', ''))
            t = self.n2id.get(e.get('target_name', ''))
            if not (s and t and s in self.id2i and t in self.id2i):
                continue
            et = e.get('edge_type', '')
            w = float(e.get('weight', 0.5))
            si, ti = self.id2i[s], self.id2i[t]
            pair = tuple(sorted([si, ti]))
            if pair in pair_seen:
                continue
            pair_seen.add(pair)
            if et == 'prerequisite':
                self.prereq_edges.append((si, ti, w))
            else:
                self.assoc_edges.append((si, ti, w))

        # 构建 children 索引
        self.children = defaultdict(list)
        self.parents = defaultdict(list)
        for p, c, w in self.prereq_edges:
            self.children[p].append((c, w))
            self.parents[c].append((p, w))

    def observe(self, kp_idx, correct, confidence=0.9):
        obs_val = 0.85 if correct else 0.15
        obs_var = (1.0 - confidence) * 0.5
        old_prec = 1.0 / max(self.sigma2[kp_idx], 0.001)
        new_prec = 1.0 / max(obs_var, 0.001)
        self.mu[kp_idx] = (old_prec * self.mu[kp_idx] + new_prec * obs_val) / (old_prec + new_prec)
        self.sigma2[kp_idx] = 1.0 / (old_prec + new_prec)
        self.observed[kp_idx] = True
        self._propagate_observation(kp_idx)

    def _propagate_observation(self, src_idx, decay=0.5, max_depth=4):
        visited = {src_idx}
        queue = [(src_idx, 0)]
        while queue:
            i, depth = queue.pop(0)
            if depth >= max_depth:
                continue
            for c, w in self.children.get(i, []):
                if c not in visited:
                    visited.add(c)
                    queue.append((c, depth + 1))
                    margin = 0.12 * (1.0 - w)
                    if self.mu[c] > self.mu[i] + margin:
                        self.mu[c] = self.mu[i] + margin
                    info_gain = (decay ** depth) * w * 0.1
                    self.sigma2[c] = max(0.01, self.sigma2[c] - info_gain)
            for p, w in self.parents.get(i, []):
                if p not in visited:
                    visited.add(p)
                    queue.append((p, depth + 1))
                    margin = 0.12 * (1.0 - w)
                    if self.mu[p] < self.mu[i] - margin:
                        self.mu[p] = self.mu[i] - margin
                    info_gain = (decay ** depth) * w * 0.1
                    self.sigma2[p] = max(0.01, self.sigma2[p] - info_gain)

    def _topological_order(self):
        indeg = defaultdict(int)
        for p, c, _ in self.prereq_edges:
            indeg[c] += 1
        q = [i for i in range(self.n) if indeg[i] == 0]
        order = []
        while q:
            i = q.pop()
            order.append(i)
            for c, _ in self.children.get(i, []):
                indeg[c] -= 1
                if indeg[c] == 0:
                    q.append(c)
        return order

    def propagate(self, n_iter=3):
        topo = self._topological_order()
        for _ in range(n_iter):
            for i in topo:
                for c, w in self.children.get(i, []):
                    margin = 0.12 * (1.0 - w)
                    if self.mu[c] > self.mu[i] + margin:
                        self.mu[c] = self.mu[i] + margin
            for i in reversed(topo):
                for c, w in self.children.get(i, []):
                    margin = 0.12 * (1.0 - w)
                    if self.mu[i] < self.mu[c] - margin:
                        self.mu[i] = self.mu[c] - margin
            for a, b, w in self.assoc_edges:
                diff = self.mu[a] - self.mu[b]
                pull = 0.15 * w * diff
                self.mu[a] -= pull
                self.mu[b] += pull
            self.mu = np.clip(self.mu, 0.01, 0.99)

    def infer_all(self):
        self.propagate(n_iter=3)
        results = []
        for i in range(self.n):
            results.append({
                'name': self.kp_names[i], 'mu': self.mu[i],
                'sigma': math.sqrt(self.sigma2[i]), 'observed': self.observed[i],
            })
        return results

    def total_entropy(self):
        return float(np.sum(self.sigma2))

    def clone(self):
        c = copy.copy(self)
        c.mu = self.mu.copy()
        c.sigma2 = self.sigma2.copy()
        c.observed = self.observed.copy()
        return c


class FieldQuestions:
    """自适应出题：基于诊断引擎 + 信息增益"""
    def __init__(self, diagnosis):
        self.diag = diagnosis

    def expected_information_gain(self, kp_idx, sample_correct=True):
        """
        模拟观测 kp_idx 后总熵的下降。
        返回 IG = H_before - E[H_after]
        """
        H_before = self.diag.total_entropy()
        mu = self.diag.mu[kp_idx]
        p_correct = np.clip(mu, 0.1, 0.9)  # 答对概率 ≈ 掌握度

        H_after_correct = H_before
        H_after_wrong = H_before

        # 模拟答对
        d1 = self.diag.clone()
        d1.observe(kp_idx, True)
        d1.infer_all()
        H_after_correct = d1.total_entropy()

        # 模拟答错
        d2 = self.diag.clone()
        d2.observe(kp_idx, False)
        d2.infer_all()
        H_after_wrong = d2.total_entropy()

        E_H_after = p_correct * H_after_correct + (1 - p_correct) * H_after_wrong
        return H_before - E_H_after

    def select_next_questions(self, k=5, exclude_observed=True, fast_mode=False):
        """
        选 k 个信息增益最大的 KP。
        fast_mode: 用近似（sigma2 × 出度）代替完整模拟
        """
        candidates = []
        for i in range(self.diag.n):
            if exclude_observed and self.diag.observed[i]:
                continue
            if fast_mode:
                out_deg = len(self.diag.children.get(i, []))
                gain = self.diag.sigma2[i] * (1.0 + 0.5 * out_deg)
            else:
                gain = self.expected_information_gain(i)
            candidates.append((i, gain))

        candidates.sort(key=lambda x: -x[1])
        top = candidates[:k]
        return [(i, gain, self.diag.kp_names[i], self.diag.mu[i], math.sqrt(self.diag.sigma2[i])) for i, gain in top]


class FieldPlanner:
    """目标路径规划：从当前诊断状态到目标 KP 的最优学习路径"""
    def __init__(self, diagnosis, gamma=0.3, alpha=0.02, unlock_threshold=0.45, mastery_target=0.65):
        self.diag = diagnosis
        self.gamma = gamma        # review gain
        self.alpha = alpha        # daily decay
        self.unlock_threshold = unlock_threshold
        self.mastery_target = mastery_target

    def reviews_to_reach(self, kp_idx, target_K=None):
        """估算需要多少次复习才能达到目标 K"""
        if target_K is None:
            target_K = self.mastery_target
        K = self.diag.mu[kp_idx]
        if K >= target_K:
            return 0
        reviews = 0
        while K < target_K:
            K += self.gamma * (1 - K)
            reviews += 1
            if reviews > 20:
                break
        return reviews

    def plan_to_target(self, target_idx):
        """
        规划到达 target KP 的最优路径。
        返回：
          - chain: 前置链 KP 列表（根→目标）
          - schedule: [(kp_idx, name, current_K, reviews_needed, cumulative_days)]
        """
        # 向后追溯完整前置链
        chain = []
        visited = set()

        def trace_back(i):
            if i in visited:
                return
            visited.add(i)
            for p, _ in self.diag.parents.get(i, []):
                trace_back(p)
            chain.append(i)

        trace_back(target_idx)

        # 计算每个 KP 需要的 review 次数和时间
        schedule = []
        cumulative_days = 0
        for i in chain:
            # 当前估计 K（考虑衰减）
            current_K = self.diag.mu[i]
            # 如果 K < unlock_threshold，不能解锁下游
            # 需要复习次数
            needed = self.reviews_to_reach(i, self.mastery_target)
            # 每天一次复习的话，n 次 = n 天
            days_needed = needed
            cumulative_days += days_needed

            schedule.append({
                'idx': i,
                'name': self.diag.kp_names[i],
                'current_K': current_K,
                'target_K': self.mastery_target,
                'reviews_needed': needed,
                'cumulative_days': cumulative_days,
                'is_bottleneck': current_K < self.unlock_threshold,
            })

        return {
            'target': self.diag.kp_names[target_idx],
            'chain_length': len(chain),
            'total_days': cumulative_days,
            'schedule': schedule,
        }

    def find_deepest_reachable(self):
        """找到当前状态下最深可达的 KP（前置链全部达标）"""
        best = None
        best_depth = -1
        depth_map = {}
        topo = self.diag._topological_order()

        for i in topo:
            if not self.diag.parents.get(i):
                depth_map[i] = 1
            else:
                if i not in depth_map:
                    max_p_depth = 0
                    for p, _ in self.diag.parents[i]:
                        max_p_depth = max(max_p_depth, depth_map.get(p, 0))
                    depth_map[i] = max_p_depth + 1 if max_p_depth > 0 else 1

            # 检查可达性：所有前置 KP 的 K > unlock_threshold
            reachable = True
            for p, _ in self.diag.parents.get(i, []):
                if self.diag.mu[p] < self.unlock_threshold:
                    reachable = False
                    break

            if reachable and depth_map[i] > best_depth:
                best = i
                best_depth = depth_map[i]

        return best, best_depth

    def find_bottlenecks(self):
        """找出所有锁死下游进度的瓶颈 KP（K 接近门槛且有很多子节点）"""
        bottlenecks = []
        for i in range(self.diag.n):
            children = self.diag.children.get(i, [])
            if not children:
                continue
            K = self.diag.mu[i]
            n_children = len(children)
            # 风险：K 离门槛越近，乘上子节点数
            risk = max(0, 1.0 - (K - self.unlock_threshold) * 5) * n_children
            if risk > 0:
                bottlenecks.append((i, K, n_children, risk))
        bottlenecks.sort(key=lambda x: -x[3])
        return [(i, K, nc, risk, self.diag.kp_names[i]) for i, K, nc, risk in bottlenecks]


# ═══ Demo ═══
if __name__ == '__main__':
    import random
    random.seed(42)
    np.random.seed(42)

    # 初始化
    diag = FieldDiagnosis('cfa_tree.json', 'cfa_llm_edges.json')
    questions = FieldQuestions(diag)
    planner = FieldPlanner(diag)

    # 生成符合图结构的知识状态
    topo = diag._topological_order()
    true_K = np.zeros(diag.n)
    for i in topo:
        max_pk = 0.0
        for p, c, _ in diag.prereq_edges:
            if c == i:
                max_pk = max(max_pk, true_K[p])
        if max_pk > 0:
            true_K[i] = np.clip(np.random.normal(max_pk, 0.12), 0.05, 0.95)
        else:
            true_K[i] = np.random.beta(2, 2)

    # 模拟做 15 道题
    print("=" * 60)
    print("Phase 1: 初始诊断（随机 15 道题）")
    print("=" * 60)
    for _ in range(15):
        i = random.randrange(diag.n)
        if not diag.observed[i]:
            correct = true_K[i] > random.random() * 0.25 + 0.35
            diag.observe(i, correct)

    diag.infer_all()
    initial_entropy = diag.total_entropy()
    print(f"初始熵: {initial_entropy:.2f}  (15 observations)")

    # 自适应出题：信息增益最大的 5 个
    print(f"\nPhase 2: 自适应出题（信息增益 Top 5）")
    print("=" * 60)
    top5 = questions.select_next_questions(5, fast_mode=False)
    print(f"{'IG':>8s}  {'μ':>6s}  {'σ':>6s}  KP")
    for i, gain, name, mu, sigma in top5:
        print(f"{gain:8.4f}  {mu:6.3f}  {sigma:6.3f}  {name}")

    # 路径规划
    print(f"\nPhase 3: 路径规划")
    print("=" * 60)

    # 找最深可达 KP
    deepest, depth = planner.find_deepest_reachable()
    if deepest is not None:
        print(f"最深可达: [{deepest}] {diag.kp_names[deepest]} (depth={depth}, K={diag.mu[deepest]:.3f})")

    # 找瓶颈
    print(f"\n瓶颈 KP（锁死下游）:")
    bottlenecks = planner.find_bottlenecks()
    for i, K, nc, risk, name in bottlenecks[:5]:
        print(f"  [{i:3d}] {name:30s}  K={K:.3f}  children={nc}  risk={risk:.2f}")

    # 选一个瓶颈做目标路径规划
    if bottlenecks:
        target = bottlenecks[0][0]
        plan = planner.plan_to_target(target)
        print(f"\n目标: {plan['target']}")
        print(f"链长: {plan['chain_length']}  预估天数: {plan['total_days']}")
        print(f"{'步骤':>4s}  {'KP':30s}  {'当前K':>6s}  {'需复习':>6s}  {'累计天':>6s}  {'瓶颈':>4s}")
        for s in plan['schedule']:
            bottle = '⚠️' if s['is_bottleneck'] else ''
            print(f"  {s['idx']:3d}  {s['name']:30s}  {s['current_K']:6.3f}  {s['reviews_needed']:6d}  {s['cumulative_days']:6d}  {bottle}")
