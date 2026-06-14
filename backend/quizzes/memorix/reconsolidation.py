"""
Memorix 再巩固窗口 (Reconsolidation Window)。

核心假说：
  记忆再巩固——每次提取记忆时，记忆痕迹变得不稳定（labile），
  然后被重新巩固。复习不是"加固"，而是"破坏→重建"。

数学定义：
  P(t) = S(t) × (1 - R(t))
  其中：
    S(t) = S₀ × [1 - exp(-t/τ)] × exp(-t/S₀)    — 稳定性（不应期恢复 + 缓慢衰减）
    R(t) = exp(-(t/λ)^k)                          — Weibull 检索概率
    S₀: 渐近稳定性（复习后最终能达到的稳定值）
    τ:  不应期时间常数（默认 1 小时，约 0.042 天）
    λ:  Weibull 尺度参数（≈ S₀，时间尺度）
    k:  Weibull 形状参数（默认 1.2）

不应期修正 + 缓慢衰减：
  若微发现：如果 S(t) = S₀ 是常数，则 P(t) = S₀·(1-R(t)) 单调递增——
  越晚复习 P 越大，和直觉矛盾。S(t) = S₀ × [1-exp(-t/τ)] 修复了前期问题，
  但 P(t) 仍在大 t 时趋近 S₀，无内部峰值。
  
  加上稳定性衰减项 e^(-t/S₀)（T_stab = S₀）：稳定性在大时间
  尺度上缓慢衰减。此时 P(t) 在 t≈k×S₀ 处出现真实内部峰值，
  R(t_opt) ≈ exp(-k^k) ≈ 0.29（k=1.2 时）。
  ——这就是最优复习时机：记忆刚好足够不稳定可以改进，
  但又有足够的残余可以重建。
"""

import math


def plasticity(t: float, stability_s0: float, lambda_: float,
               k: float = 1.2, tau: float = 0.042) -> float:
    """
    计算时刻 t 的可塑性值 P(t)。

    P(t) = S₀ × [1-e^(-t/τ)] × e^(-t/S₀) × [1-e^(-(t/S₀)^k)]

    Args:
        t: 距上次复习的天数
        stability_s0: 渐近稳定性（天）
        lambda_: Weibull 尺度参数（天，通常 ≈ S₀）
        k: Weibull 形状参数
        tau: 不应期时间常数（天，默认 1 小时 ≈ 0.042 天）

    Returns:
        P(t) ∈ [0, S₀]
    """
    if t <= 0:
        return 0.0

    # S(t): 不应期恢复 + 缓慢衰减
    S_t = stability_s0 * (1.0 - math.exp(-t / tau))
    S_t *= math.exp(-t / stability_s0) if stability_s0 > 0 else 0.0
    # R(t): Weibull 检索概率
    if lambda_ <= 0:
        return 0.0
    R_t = math.exp(-((t / lambda_) ** k))
    return S_t * (1.0 - R_t)


def find_optimal_review_time(stability_s0: float, lambda_: float,
                             k: float = 1.2, tau: float = 0.042) -> tuple[float, float]:
    """
    用黄金分割搜索找 P(t) 的最大值点。
    
    搜索区间 [tau, 10 × λ]，覆盖从不应用结束到约 10 倍时间尺度。
    
    Args:
        stability_s0: 渐近稳定性（天）
        lambda_: Weibull 尺度参数（天）
        k: Weibull 形状参数
        tau: 不应期时间常数（天）
    
    Returns:
        (t_opt, P_max): 最优复习时间（天）和对应的最大可塑性值
    """
    lo = max(tau, 0.001)
    hi = 10.0 * lambda_
    phi = (math.sqrt(5) - 1) / 2  # ≈ 0.618

    m1 = hi - phi * (hi - lo)
    m2 = lo + phi * (hi - lo)
    p1 = plasticity(m1, stability_s0, lambda_, k, tau)
    p2 = plasticity(m2, stability_s0, lambda_, k, tau)

    for _ in range(50):  # 50 次迭代精度 ≈ 10⁻¹⁰
        if p1 >= p2:
            hi = m2
            m2 = m1
            p2 = p1
            m1 = hi - phi * (hi - lo)
            p1 = plasticity(m1, stability_s0, lambda_, k, tau)
        else:
            lo = m1
            m1 = m2
            p1 = p2
            m2 = lo + phi * (hi - lo)
            p2 = plasticity(m2, stability_s0, lambda_, k, tau)

    t_opt = (lo + hi) / 2.0
    p_max = plasticity(t_opt, stability_s0, lambda_, k, tau)
    return t_opt, p_max


def compute_urgency(stability: float, elapsed_days: float,
                    k: float = 1.2, tau: float = 0.042) -> float:
    """
    计算再巩固窗口 urgency。
    
    urgency = P(t_elapsed) / P(t_opt)，归一化到 [0, 1]。
    接近 1 意味着"现在就处于最优复习窗口"。
    
    边缘情况处理：
    - 新题（stability=0 或 无复习记录）：返回 1.0（需要尽快第一次复习）
    - 不应期内（t < τ）：返回 0.0（刚复习完，不应安排）
    - 极高稳定性（S₀ > 365 天）：退化为普通 urgency，不强制等 t_opt
    - 已遗忘（R(t) < 0.1）：返回 1.0（该重学了）
    
    Args:
        stability: 当前稳定性（天），从 UserQuestionStatus 获取
        elapsed_days: 距上次复习的天数
        k: Weibull 形状参数
        tau: 不应期时间常数（天）
    
    Returns:
        urgency ∈ [0, 1]
    """
    # 新题：无稳定性，需要尽快复习
    if stability <= 0:
        return 1.0

    # 不应期内：刚复习完，不应立即再安排
    if elapsed_days < tau:
        return 0.0

    # 极高稳定性：退化为普通 urgency
    if stability > 365:
        R = math.exp(-((elapsed_days / stability) ** k))
        return 1.0 - R

    # 已遗忘：该重学了
    R = math.exp(-((elapsed_days / stability) ** k))
    if R < 0.1:
        return 1.0

    # 正常路径：P(t_elapsed) / P(t_opt)
    t_opt, p_max = find_optimal_review_time(stability, stability, k, tau)
    if p_max <= 0:
        return 1.0 - R  # fallback 到标准 urgency

    p_current = plasticity(elapsed_days, stability, stability, k, tau)
    urgency = p_current / p_max
    return max(0.0, min(1.0, urgency))
