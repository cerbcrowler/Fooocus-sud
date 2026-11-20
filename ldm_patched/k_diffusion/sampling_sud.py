# Fooocus-sud: новые сэмплеры из ComfyUI (comfy/k_diffusion/sampling.py, GPL-3.0), появившиеся после
# версии, на которой построен Fooocus: er_sde, res_multistep(+ancestral), gradient_estimation, seeds_2.
# Адаптировано под ldm_patched: свой поиск model_sampling, default_noise_sampler(x) без seed, без CFG++.
# Регистрация — в конце ldm_patched/k_diffusion/sampling.py (from .sampling_sud import *).

from functools import partial

import torch
from tqdm.auto import trange

from . import utils


# копии помощников из sampling.py (импорт оттуда дал бы цикл: sampling.py подключает этот модуль)
def to_d(x, sigma, denoised):
    return (x - denoised) / utils.append_dims(sigma, x.ndim)


def get_ancestral_step(sigma_from, sigma_to, eta=1.):
    if not eta:
        return sigma_to, 0.
    sigma_up = min(sigma_to, eta * (sigma_to ** 2 * (sigma_from ** 2 - sigma_to ** 2) / sigma_from ** 2) ** 0.5)
    sigma_down = (sigma_to ** 2 - sigma_up ** 2) ** 0.5
    return sigma_down, sigma_up


def default_noise_sampler(x):
    return lambda sigma, sigma_next: torch.randn_like(x)


def _model_sampling(model):
    """Найти model_sampling у обёрток сэмплера (KSamplerX0Inpaint → CFGNoisePredictor → BaseModel)."""
    m = model
    for _ in range(4):
        if hasattr(m, 'model_sampling'):
            return m.model_sampling
        patcher = getattr(m, 'model_patcher', None)
        if patcher is not None and hasattr(patcher, 'get_model_object'):
            return patcher.get_model_object('model_sampling')
        m = getattr(m, 'inner_model', None)
        if m is None:
            break
    raise AttributeError('model_sampling не найден')


def _is_const(ms):
    return type(ms).__name__ == 'CONST'


def sigma_to_half_log_snr(sigma, model_sampling):
    if _is_const(model_sampling):
        return sigma.logit().neg()
    return sigma.log().neg()


def half_log_snr_to_sigma(half_log_snr, model_sampling):
    if _is_const(model_sampling):
        return half_log_snr.neg().sigmoid()
    return half_log_snr.neg().exp()


def offset_first_sigma_for_snr(sigmas, model_sampling, percent_offset=1e-4):
    if len(sigmas) <= 1:
        return sigmas
    if _is_const(model_sampling) and sigmas[0] >= 1:
        sigmas = sigmas.clone()
        sigmas[0] = model_sampling.percent_to_sigma(percent_offset)
    return sigmas


def ei_h_phi_1(h):
    return torch.expm1(h)


def ei_h_phi_2(h):
    return (torch.expm1(h) - h) / h


def _res_multistep(model, x, sigmas, extra_args=None, callback=None, disable=None, s_noise=1., noise_sampler=None, eta=1.):
    extra_args = {} if extra_args is None else extra_args
    noise_sampler = default_noise_sampler(x) if noise_sampler is None else noise_sampler
    s_noise = s_noise * getattr(_model_sampling(model), 'noise_scale', 1.0)
    s_in = x.new_ones([x.shape[0]])
    sigma_fn = lambda t: t.neg().exp()
    t_fn = lambda sigma: sigma.log().neg()
    phi1_fn = lambda t: torch.expm1(t) / t
    phi2_fn = lambda t: (phi1_fn(t) - 1.0) / t
    old_sigma_down = None
    old_denoised = None
    for i in trange(len(sigmas) - 1, disable=disable):
        denoised = model(x, sigmas[i] * s_in, **extra_args)
        sigma_down, sigma_up = get_ancestral_step(sigmas[i], sigmas[i + 1], eta=eta)
        if callback is not None:
            callback({'x': x, 'i': i, 'sigma': sigmas[i], 'sigma_hat': sigmas[i], 'denoised': denoised})
        if sigma_down == 0 or old_denoised is None:
            d = to_d(x, sigmas[i], denoised)
            x = x + d * (sigma_down - sigmas[i])
        else:
            t, t_old, t_next, t_prev = t_fn(sigmas[i]), t_fn(old_sigma_down), t_fn(sigma_down), t_fn(sigmas[i - 1])
            h = t_next - t
            c2 = (t_prev - t_old) / h
            phi1_val, phi2_val = phi1_fn(-h), phi2_fn(-h)
            b1 = torch.nan_to_num(phi1_val - phi2_val / c2, nan=0.0)
            b2 = torch.nan_to_num(phi2_val / c2, nan=0.0)
            x = sigma_fn(h) * x + h * (b1 * denoised + b2 * old_denoised)
        if sigma_up > 0:
            x = x + noise_sampler(sigmas[i], sigmas[i + 1]) * s_noise * sigma_up
        old_denoised = denoised
        old_sigma_down = sigma_down
    return x


@torch.no_grad()
def sample_res_multistep(model, x, sigmas, extra_args=None, callback=None, disable=None, s_noise=1., noise_sampler=None):
    return _res_multistep(model, x, sigmas, extra_args, callback, disable, s_noise, noise_sampler, eta=0.)


@torch.no_grad()
def sample_res_multistep_ancestral(model, x, sigmas, extra_args=None, callback=None, disable=None, eta=1., s_noise=1., noise_sampler=None):
    return _res_multistep(model, x, sigmas, extra_args, callback, disable, s_noise, noise_sampler, eta=eta)


@torch.no_grad()
def sample_gradient_estimation(model, x, sigmas, extra_args=None, callback=None, disable=None, ge_gamma=2.):
    """Gradient-estimation sampler. https://openreview.net/pdf?id=o2ND9v0CeK"""
    extra_args = {} if extra_args is None else extra_args
    s_in = x.new_ones([x.shape[0]])
    old_d = None
    for i in trange(len(sigmas) - 1, disable=disable):
        denoised = model(x, sigmas[i] * s_in, **extra_args)
        d = to_d(x, sigmas[i], denoised)
        if callback is not None:
            callback({'x': x, 'i': i, 'sigma': sigmas[i], 'sigma_hat': sigmas[i], 'denoised': denoised})
        dt = sigmas[i + 1] - sigmas[i]
        if sigmas[i + 1] == 0:
            x = denoised
        else:
            x = x + d * dt
            if i >= 1:
                x = x + (ge_gamma - 1) * (d - old_d) * dt
        old_d = d
    return x


@torch.no_grad()
def sample_er_sde(model, x, sigmas, extra_args=None, callback=None, disable=None, s_noise=1.0, noise_sampler=None, noise_scaler=None, max_stage=3):
    """Extended Reverse-Time SDE solver (VP ER-SDE-Solver-3). arXiv:2309.06169"""
    extra_args = {} if extra_args is None else extra_args
    noise_sampler = default_noise_sampler(x) if noise_sampler is None else noise_sampler
    model_sampling = _model_sampling(model)
    s_noise = s_noise * getattr(model_sampling, 'noise_scale', 1.0)
    s_in = x.new_ones([x.shape[0]])

    def default_er_sde_noise_scaler(v):
        return v * ((v ** 0.3).exp() + 10.0)

    noise_scaler = default_er_sde_noise_scaler if noise_scaler is None else noise_scaler
    num_integration_points = 200.0
    point_indice = torch.arange(0, num_integration_points, dtype=torch.float32, device=x.device)

    sigmas = offset_first_sigma_for_snr(sigmas, model_sampling)
    half_log_snrs = sigma_to_half_log_snr(sigmas, model_sampling)
    er_lambdas = half_log_snrs.neg().exp()

    old_denoised = None
    old_denoised_d = None
    for i in trange(len(sigmas) - 1, disable=disable):
        denoised = model(x, sigmas[i] * s_in, **extra_args)
        if callback is not None:
            callback({'x': x, 'i': i, 'sigma': sigmas[i], 'sigma_hat': sigmas[i], 'denoised': denoised})
        stage_used = min(max_stage, i + 1)
        if sigmas[i + 1] == 0:
            x = denoised
        else:
            er_lambda_s, er_lambda_t = er_lambdas[i], er_lambdas[i + 1]
            alpha_s = sigmas[i] / er_lambda_s
            alpha_t = sigmas[i + 1] / er_lambda_t
            r_alpha = alpha_t / alpha_s
            r = noise_scaler(er_lambda_t) / noise_scaler(er_lambda_s)
            x = r_alpha * r * x + alpha_t * (1 - r) * denoised
            if stage_used >= 2:
                dt = er_lambda_t - er_lambda_s
                lambda_step_size = -dt / num_integration_points
                lambda_pos = er_lambda_t + point_indice * lambda_step_size
                scaled_pos = noise_scaler(lambda_pos)
                s = torch.sum(1 / scaled_pos) * lambda_step_size
                denoised_d = (denoised - old_denoised) / (er_lambda_s - er_lambdas[i - 1])
                x = x + alpha_t * (dt + s * noise_scaler(er_lambda_t)) * denoised_d
                if stage_used >= 3:
                    s_u = torch.sum((lambda_pos - er_lambda_s) / scaled_pos) * lambda_step_size
                    denoised_u = (denoised_d - old_denoised_d) / ((er_lambda_s - er_lambdas[i - 2]) / 2)
                    x = x + alpha_t * ((dt ** 2) / 2 + s_u * noise_scaler(er_lambda_t)) * denoised_u
                old_denoised_d = denoised_d
            if s_noise > 0:
                x = x + alpha_t * noise_sampler(sigmas[i], sigmas[i + 1]) * s_noise * \
                    (er_lambda_t ** 2 - er_lambda_s ** 2 * r ** 2).sqrt().nan_to_num(nan=0.0)
        old_denoised = denoised
    return x


@torch.no_grad()
def sample_seeds_2(model, x, sigmas, extra_args=None, callback=None, disable=None, eta=1., s_noise=1., noise_sampler=None, r=0.5, solver_type="phi_1"):
    """SEEDS-2 (VP data prediction), arXiv:2305.14267"""
    extra_args = {} if extra_args is None else extra_args
    noise_sampler = default_noise_sampler(x) if noise_sampler is None else noise_sampler
    s_in = x.new_ones([x.shape[0]])
    model_sampling = _model_sampling(model)
    s_noise = s_noise * getattr(model_sampling, 'noise_scale', 1.0)
    inject_noise = eta > 0 and s_noise > 0
    sigma_fn = partial(half_log_snr_to_sigma, model_sampling=model_sampling)
    lambda_fn = partial(sigma_to_half_log_snr, model_sampling=model_sampling)
    sigmas = offset_first_sigma_for_snr(sigmas, model_sampling)
    fac = 1 / (2 * r)
    for i in trange(len(sigmas) - 1, disable=disable):
        denoised = model(x, sigmas[i] * s_in, **extra_args)
        if callback is not None:
            callback({'x': x, 'i': i, 'sigma': sigmas[i], 'sigma_hat': sigmas[i], 'denoised': denoised})
        if sigmas[i + 1] == 0:
            x = denoised
            continue
        lambda_s, lambda_t = lambda_fn(sigmas[i]), lambda_fn(sigmas[i + 1])
        h = lambda_t - lambda_s
        h_eta = h * (eta + 1)
        lambda_s_1 = torch.lerp(lambda_s, lambda_t, r)
        sigma_s_1 = sigma_fn(lambda_s_1)
        alpha_s_1 = sigma_s_1 * lambda_s_1.exp()
        alpha_t = sigmas[i + 1] * lambda_t.exp()
        x_2 = sigma_s_1 / sigmas[i] * (-r * h * eta).exp() * x - alpha_s_1 * ei_h_phi_1(-r * h_eta) * denoised
        if inject_noise:
            sde_noise = (-2 * r * h * eta).expm1().neg().sqrt() * noise_sampler(sigmas[i], sigma_s_1)
            x_2 = x_2 + sde_noise * sigma_s_1 * s_noise
        denoised_2 = model(x_2, sigma_s_1 * s_in, **extra_args)
        if solver_type == "phi_1":
            denoised_d = torch.lerp(denoised, denoised_2, fac)
            x = sigmas[i + 1] / sigmas[i] * (-h * eta).exp() * x - alpha_t * ei_h_phi_1(-h_eta) * denoised_d
        else:
            b2 = ei_h_phi_2(-h_eta) / r
            b1 = ei_h_phi_1(-h_eta) - b2
            x = sigmas[i + 1] / sigmas[i] * (-h * eta).exp() * x - alpha_t * (b1 * denoised + b2 * denoised_2)
        if inject_noise:
            segment_factor = (r - 1) * h * eta
            sde_noise = sde_noise * segment_factor.exp()
            sde_noise = sde_noise + segment_factor.mul(2).expm1().neg().sqrt() * noise_sampler(sigma_s_1, sigmas[i + 1])
            x = x + sde_noise * sigmas[i + 1] * s_noise
    return x


# ---------- шедулеры (comfy/samplers.py) ----------
def beta_scheduler(model_sampling, steps, alpha=0.6, beta=0.6):
    import numpy
    import scipy.stats
    total_timesteps = (len(model_sampling.sigmas) - 1)
    ts = 1 - numpy.linspace(0, 1, steps, endpoint=False)
    ts = numpy.rint(scipy.stats.beta.ppf(ts, alpha, beta) * total_timesteps)
    sigs, last_t = [], -1
    for t in ts:
        if t != last_t:
            sigs += [float(model_sampling.sigmas[int(t)])]
        last_t = t
    sigs += [0.0]
    return torch.FloatTensor(sigs)


def linear_quadratic_schedule(model_sampling, steps, threshold_noise=0.025, linear_steps=None):
    if steps == 1:
        sigma_schedule = [1.0, 0.0]
    else:
        if linear_steps is None:
            linear_steps = steps // 2
        linear_sigma_schedule = [i * threshold_noise / linear_steps for i in range(linear_steps)]
        threshold_noise_step_diff = linear_steps - threshold_noise * steps
        quadratic_steps = steps - linear_steps
        quadratic_coef = threshold_noise_step_diff / (linear_steps * quadratic_steps ** 2)
        linear_coef = threshold_noise / linear_steps - 2 * threshold_noise_step_diff / (quadratic_steps ** 2)
        const = quadratic_coef * (linear_steps ** 2)
        quadratic_sigma_schedule = [quadratic_coef * (i ** 2) + linear_coef * i + const for i in range(linear_steps, steps)]
        sigma_schedule = linear_sigma_schedule + quadratic_sigma_schedule + [1.0]
        sigma_schedule = [1.0 - x for x in sigma_schedule]
    return torch.FloatTensor(sigma_schedule) * model_sampling.sigma_max.cpu()


def kl_optimal_scheduler(n, sigma_min, sigma_max):
    import math
    adj_idxs = torch.arange(n, dtype=torch.float).div_(n - 1)
    sigmas = adj_idxs.new_zeros(n + 1)
    sigmas[:-1] = (adj_idxs * math.atan(sigma_min) + (1 - adj_idxs) * math.atan(sigma_max)).tan_()
    return sigmas


NEW_SAMPLERS = ["er_sde", "res_multistep", "res_multistep_ancestral", "gradient_estimation", "seeds_2"]
NEW_SCHEDULERS = ["beta", "kl_optimal", "linear_quadratic"]
