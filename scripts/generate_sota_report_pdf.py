#!/usr/bin/env python3
"""Generate PDF: SOTA neural networks report for Astra (free API focus)."""

from __future__ import annotations

from datetime import date
from pathlib import Path

from fpdf import FPDF

ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "docs" / "llm-research"
OUT = OUT_DIR / "Astra-SOTA-нейросети-отчет-2026-06-13.pdf"
FONT = Path("/Library/Fonts/Arial Unicode.ttf")

REPORT_DATE = "13.06.2026"


class ReportPDF(FPDF):
    def footer(self) -> None:
        self.set_y(-12)
        self.set_font("ArialUni", size=8)
        self.set_text_color(120, 120, 120)
        self.cell(
            0,
            8,
            f"Astra · SOTA нейросети · {REPORT_DATE} · стр. {self.page_no()}",
            align="C",
        )


def _font(pdf: FPDF, size: int = 10, bold: bool = False) -> None:
    pdf.set_font("ArialUni", style="B" if bold else "", size=size)
    pdf.set_text_color(20, 20, 20)


def section(pdf: ReportPDF, title: str) -> None:
    pdf.ln(3)
    _font(pdf, 12, bold=True)
    pdf.multi_cell(0, 7, title)
    pdf.ln(1)


def body(pdf: ReportPDF, text: str, size: int = 9) -> None:
    _font(pdf, size)
    pdf.multi_cell(0, 5, text)
    pdf.ln(1)


def bullet(pdf: ReportPDF, text: str) -> None:
    _font(pdf, 9)
    pdf.multi_cell(0, 5, f"• {text}")
    pdf.ln(0.5)


def table(
    pdf: ReportPDF,
    headers: list[str],
    rows: list[list[str]],
    widths: list[float],
    font_size: int = 7,
) -> None:
    _font(pdf, font_size, bold=True)
    pdf.set_fill_color(240, 240, 245)
    for i, h in enumerate(headers):
        pdf.cell(widths[i], 6, h, border=1, fill=True, align="C")
    pdf.ln()

    _font(pdf, font_size)
    for row in rows:
        x0, y0 = pdf.get_x(), pdf.get_y()
        line_h = 4.5
        heights: list[float] = []
        for i, cell in enumerate(row):
            pdf.set_xy(x0 + sum(widths[:i]), y0)
            lines = pdf.multi_cell(widths[i], line_h, cell, border=0, split_only=True)
            heights.append(len(lines) * line_h)
        row_h = max(heights) if heights else line_h

        if y0 + row_h > pdf.h - 18:
            pdf.add_page()
            y0 = pdf.get_y()

        for i, cell in enumerate(row):
            x = x0 + sum(widths[:i])
            pdf.rect(x, y0, widths[i], row_h)
            pdf.set_xy(x + 0.5, y0 + 0.5)
            pdf.multi_cell(widths[i] - 1, line_h, cell, border=0)
        pdf.set_xy(x0, y0 + row_h)


def model_card(pdf: ReportPDF, m: dict) -> None:
    if pdf.get_y() > 160:
        pdf.add_page()

    section(pdf, f"#{m['rank']} · {m['name']}")
    body(
        pdf,
        f"Провайдер: {m['provider']}  |  Free API: {m['free_api']}  |  "
        f"Free Score: {m['free_score']}%  |  Astra-fit: {m['predictions']}%",
        size=8,
    )

    table(
        pdf,
        ["Текст", "Картинки", "Видео", "Аудио", "Предсказания"],
        [[f"{m['text']}%", f"{m['images']}%", f"{m['video']}%", f"{m['audio']}%", f"{m['predictions']}%"]],
        [54, 54, 54, 54, 54],
        font_size=8,
    )

    body(pdf, f"Тип API: {m['api_type']}", size=8)
    if m.get("endpoint"):
        body(pdf, f"Endpoint: {m['endpoint']}", size=8)
    body(pdf, f"Бесплатные лимиты: {m['free_limits']}", size=8)
    body(pdf, f"Платные лимиты / цена: {m['paid_limits']}", size=8)
    body(pdf, "Условия:", size=8)
    for cond in m["conditions"]:
        bullet(pdf, cond)
    body(pdf, f"Как подключить: {m['how_to']}", size=8)
    body(pdf, f"Для Astra: {m['astra']}", size=8)
    pdf.ln(2)


# Sorted by Free Score; API-first focus
MODELS: list[dict] = [
    {
        "rank": 1,
        "name": "gemma4:e2b (Ollama, local)",
        "provider": "Google / self-hosted",
        "free_api": "ДА — REST API",
        "free_score": 100,
        "text": 28,
        "images": 0,
        "video": 0,
        "audio": 0,
        "predictions": 78,
        "api_type": "Ollama REST (OpenAI-like /chat)",
        "endpoint": "http://ollama:11434/api/chat",
        "free_limits": "Безлимит запросов; ~2–5 t/s на deadtiger; RAM ~1.5–2 GB Q4",
        "paid_limits": "0 руб. — только электричество",
        "conditions": [
            "CPU-only на deadtiger (8 GB RAM, HDD)",
            "think=false, num_ctx=4096, num_predict=380 в Astra",
            "Промпт Astrid v2 откалиброван под e2b",
            "Генерация только в фоновой очереди (RabbitMQ)",
        ],
        "how_to": "OLLAMA_MODEL=gemma4:e2b в .env; docker-compose сервис ollama + ollama-init pull",
        "astra": "Основной LLM для MVP: 0 руб., privacy, уже в проде. Минус: медленно (~75–190 с/прогноз).",
    },
    {
        "rank": 2,
        "name": "Groq API",
        "provider": "Groq (США)",
        "free_api": "ДА — постоянный free tier",
        "free_score": 92,
        "text": 68,
        "images": 0,
        "video": 0,
        "audio": 45,
        "predictions": 58,
        "api_type": "OpenAI-compatible REST",
        "endpoint": "https://api.groq.com/openai/v1",
        "free_limits": "Llama 3.3 70B: 30 RPM, 14 400 RPD, 6K TPM. Llama 4 Scout: 30 RPM, 1000 RPD. Whisper STT: 20 RPM, 2000 RPD",
        "paid_limits": "Developer plan — выше лимиты; pay-as-you-go",
        "conditions": [
            "Карта не нужна для free tier",
            "Лимиты per organization, не per key",
            "429 при превышении — без очереди",
            "Самый быстрый free API (~300+ t/s)",
        ],
        "how_to": "console.groq.com → API key → base_url в OpenAI SDK",
        "astra": "Fallback при пиках: быстрый, но качество прогноза ниже e2b. Whisper — STT если понадобится.",
    },
    {
        "rank": 3,
        "name": "Google Gemini API (Flash)",
        "provider": "Google",
        "free_api": "ДА — постоянный free tier",
        "free_score": 90,
        "text": 80,
        "images": 15,
        "video": 0,
        "audio": 0,
        "predictions": 75,
        "api_type": "Gemini REST / google-genai SDK",
        "endpoint": "generativelanguage.googleapis.com",
        "free_limits": "Flash: 10–15 RPM, 1000–1500 RPD, 250K–1M TPM. Imagen: 500 img/день. Pro: 50 RPD (trial)",
        "paid_limits": "Flash ~$0.10–1.25 in / $0.40–5 out per M; Pro ~$2/$12 per M",
        "conditions": [
            "Нужен billing account в GCP (иначе квота может быть 0)",
            "Free tier: Google может использовать промпты для обучения",
            "Лимиты per project — второй ключ не помогает",
            "Сброс RPD: полночь Pacific (11:00 MSK)",
            "Включение paid billing убивает free tier на проекте",
        ],
        "how_to": "aistudio.google.com → API key → Gemini 2.5/3 Flash model id",
        "astra": "Лучший бесплатный API-fallback: 1500 прогнозов/день хватит на 100+ юзеров.",
    },
    {
        "rank": 4,
        "name": "DeepSeek API",
        "provider": "DeepSeek (Китай)",
        "free_api": "ДА — trial 5M токенов",
        "free_score": 82,
        "text": 78,
        "images": 0,
        "video": 0,
        "audio": 0,
        "predictions": 72,
        "api_type": "OpenAI + Anthropic compatible REST",
        "endpoint": "https://api.deepseek.com",
        "free_limits": "5 000 000 токенов на старте; срок ~30 дней; карта не нужна",
        "paid_limits": "V4 Flash: $0.14/$0.28 per M; V4 Pro: $0.435/$0.87 per M; concurrency 2500/500",
        "conditions": [
            "Trial не постоянный — планируй бюджет после 30 дней",
            "Данные на китайской инфраструктуре — privacy риск",
            "Rate limits на trial = как у paid",
            "~3500–6000 вызовов Astrid на trial",
        ],
        "how_to": "platform.deepseek.com → API key → model deepseek-v4-flash",
        "astra": "Отличный стартовый API: почти фронтир за копейки. После trial — самый дешёвый paid.",
    },
    {
        "rank": 5,
        "name": "OpenRouter (:free models)",
        "provider": "OpenRouter",
        "free_api": "ДА — :free variants",
        "free_score": 85,
        "text": 75,
        "images": 0,
        "video": 0,
        "audio": 0,
        "predictions": 68,
        "api_type": "OpenAI-compatible proxy",
        "endpoint": "https://openrouter.ai/api/v1",
        "free_limits": "20 RPM; 50 RPD (<$10 credits) или 1000 RPD (≥$10 credits); 28+ free моделей",
        "paid_limits": "Per-model pricing; BYOK: 1M free routing req/мес",
        "conditions": [
            "Карта не нужна для 50 RPD",
            "$10 credits разово → 1000 RPD навсегда",
            "Модели: DeepSeek R1, Llama 3.3 70B, Qwen3, Gemma 3 :free",
            "Несколько аккаунтов не увеличивают лимит",
        ],
        "how_to": "openrouter.ai → key → model id с суффиксом :free",
        "astra": "Универсальный роутер для A/B тестов. 50 RPD — только dev; 1000 — рабочий fallback.",
    },
    {
        "rank": 6,
        "name": "Alibaba DashScope (Qwen API)",
        "provider": "Alibaba Cloud",
        "free_api": "ДА — trial 90 дней",
        "free_score": 68,
        "text": 84,
        "images": 10,
        "video": 10,
        "audio": 5,
        "predictions": 70,
        "api_type": "OpenAI-compatible REST",
        "endpoint": "dashscope-intl.aliyuncs.com/compatible-mode/v1 (Singapore)",
        "free_limits": "~70M токенов trial (1M per model); 90 дней; только Singapore endpoint",
        "paid_limits": "Qwen-Plus $0.40/$1.20 per M; 600 RPM / 1M TPM",
        "conditions": [
            "Постоянный free tier отменён 15.04.2026",
            "US Virginia endpoint — без free quota",
            "Включить «Free quota only» в консоли — стоп при исчерпании",
            "Qwen Chat (UI) бесплатен, но это не API",
        ],
        "how_to": "modelstudio.console.alibabacloud.com → DASHSCOPE_API_KEY",
        "astra": "Щедрый trial для прототипа; после 90 дней — платный. Хорош для RU/мультиязычности.",
    },
    {
        "rank": 7,
        "name": "Cohere Trial API",
        "provider": "Cohere (Канада)",
        "free_api": "ДА — trial",
        "free_score": 70,
        "text": 65,
        "images": 0,
        "video": 0,
        "audio": 0,
        "predictions": 55,
        "api_type": "Cohere REST (chat, embed, rerank)",
        "endpoint": "https://api.cohere.com",
        "free_limits": "1000 API calls/месяц (~33/день); 20 RPM chat; non-commercial only",
        "paid_limits": "Production: Command A+ 500 RPM; Embed 2000 inputs/min",
        "conditions": [
            "Trial key — только evaluation, не production",
            "Non-commercial license на trial",
            "Сильный Rerank для RAG, слабее для креатива",
        ],
        "how_to": "dashboard.cohere.com → Trial API key",
        "astra": "Мало для MVP (33 прогноза/день). Полезен для RAG/embeddings, не для Astrid-текста.",
    },
    {
        "rank": 8,
        "name": "Mistral La Plateforme",
        "provider": "Mistral (EU)",
        "free_api": "ДА — Experiment tier",
        "free_score": 50,
        "text": 72,
        "images": 15,
        "video": 0,
        "audio": 0,
        "predictions": 60,
        "api_type": "Mistral REST",
        "endpoint": "https://api.mistral.ai",
        "free_limits": "Experiment: ~1 RPS, 500K TPM; точные цифры в admin.mistral.ai",
        "paid_limits": "Tier 1–4 от pay-as-you-go; Large 3 Apache 2.0 weights",
        "conditions": [
            "Лимиты только после логина в консоль",
            "EU data residency — плюс для GDPR",
            "Карта может потребоваться для регистрации",
        ],
        "how_to": "console.mistral.ai → API key → mistral-large-latest",
        "astra": "Запасной EU-friendly API. Качество ок, лимиты скромные.",
    },
    {
        "rank": 9,
        "name": "HuggingFace Inference Providers",
        "provider": "Hugging Face",
        "free_api": "ДА — микро-кредиты",
        "free_score": 55,
        "text": 50,
        "images": 20,
        "video": 0,
        "audio": 0,
        "predictions": 40,
        "api_type": "HF Inference / OpenAI-compatible routing",
        "endpoint": "api-inference.huggingface.co",
        "free_limits": "$0.10 credits/месяц (free account); PRO $9 → $2/мес credits",
        "paid_limits": "Pay-as-you-go после исчерпания credits",
        "conditions": [
            "Практически только для экспериментов",
            "Cold start 10–30 с на редких моделях",
            "Serverless: сотни req/час, <10B params",
        ],
        "how_to": "huggingface.co/settings/tokens → Inference Providers",
        "astra": "Не для продакшена Astra. Только тест open-моделей.",
    },
    {
        "rank": 10,
        "name": "FLUX API (Black Forest Labs)",
        "provider": "BFL",
        "free_api": "ДА — ограниченный",
        "free_score": 65,
        "text": 0,
        "images": 70,
        "video": 0,
        "audio": 0,
        "predictions": 0,
        "api_type": "REST image generation",
        "endpoint": "https://api.bfl.ai",
        "free_limits": "1 request/second; Schnell + Dev models; 1024×1024",
        "paid_limits": "Pro/Max: $0.03/MP; self-host Klein 4B Apache 2.0",
        "conditions": [
            "Только генерация картинок",
            "Free tier для прототипов, не high-volume",
        ],
        "how_to": "api.bfl.ai → API key",
        "astra": "Не v1. Для будущих визуальных фич (карта дня, share-картинки).",
    },
    {
        "rank": 11,
        "name": "ElevenLabs API",
        "provider": "ElevenLabs",
        "free_api": "ДА — ограниченный",
        "free_score": 62,
        "text": 0,
        "images": 25,
        "video": 0,
        "audio": 75,
        "predictions": 0,
        "api_type": "REST TTS / STT",
        "endpoint": "https://api.elevenlabs.io",
        "free_limits": "10 000 credits/мес (~10–20 мин TTS); 3 image req/день; видео — нет",
        "paid_limits": "Starter $5/мес: 30K credits; commercial license с paid",
        "conditions": [
            "Free: non-commercial + обязательная attribution",
            "Credits не rollover на free",
            "Max 2500 символов за запрос на free",
        ],
        "how_to": "elevenlabs.io → Profile → API key",
        "astra": "Гипотеза #37 (аудио Astrid). Не v1. Нужен paid для коммерции.",
    },
]

# Reference frontier — NO free API
NO_FREE_API = [
    ["Claude Fable 5 / Mythos 5", "Anthropic", "Текст 98%, Предск. 95%", "API $10–50/M, нет free"],
    ["GPT-5.5 / GPT-5.5 Pro", "OpenAI", "Текст 90%, Предск. 86%", "~$5 trial ненадёжно; API $5–30/M"],
    ["Claude Opus 4.8", "Anthropic", "Текст 94%, Предск. 92%", "API от $5/$25 per M"],
    ["Gemini 3.1 Pro", "Google", "Текст 92%, Предск. 85%", "API $2/$12, free tier только Flash"],
    ["Grok 4.3", "xAI", "Текст 82%, Предск. 78%", "API $1.25/$2.50, нет free tier"],
    ["DeepSeek V4 Pro Max", "DeepSeek", "Текст 86%, Предск. 80%", "Trial 5M токенов, потом paid"],
    ["Kimi K2.6", "Moonshot", "Текст 84%, Предск. 70%", "Open weights; API paid / Groq free"],
]

FREE_RANKING_ROWS = [
    ["1", "gemma4:e2b local", "100", "ДА", "∞", "0 руб.", "78", "Основной MVP"],
    ["2", "Groq API", "92", "ДА", "14 400 RPD", "pay-go", "58", "Скорость"],
    ["3", "Gemini Flash API", "90", "ДА", "1500 RPD", "$0.10/M+", "75", "Fallback #1"],
    ["4", "OpenRouter :free", "85", "ДА", "50–1000 RPD", "per model", "68", "A/B роутер"],
    ["5", "DeepSeek API", "82", "ДА*", "5M tok/30д", "$0.14/M+", "72", "Fallback #2"],
    ["6", "DashScope Qwen", "68", "ДА*", "70M/90д", "$0.40/M+", "70", "Trial"],
    ["7", "Cohere Trial", "70", "ДА*", "1000/мес", "paid", "55", "RAG only"],
    ["8", "FLUX API", "65", "ДА", "1 req/s", "$0.03/MP", "0", "Картинки"],
    ["9", "ElevenLabs", "62", "ДА", "10K cr/мес", "$5/мес+", "0", "TTS"],
    ["10", "HuggingFace", "55", "ДА", "$0.10/мес", "pay-go", "40", "Эксперименты"],
    ["11", "Mistral Experiment", "50", "ДА", "~1 RPS", "paid", "60", "EU"],
    ["—", "OpenAI API", "15", "НЕТ", "~$5 trial", "$5–30/M", "82", "Только paid"],
    ["—", "Anthropic API", "5", "НЕТ", "—", "$3–75/M", "88", "Только paid"],
]

QUALITY_ROWS = [
    ["Claude Fable 5", "98", "0", "0", "0", "95", "НЕТ"],
    ["GPT-5.5", "90", "25", "25", "30", "86", "НЕТ"],
    ["Gemini 3.1 Pro", "92", "15", "15", "20", "85", "Flash free"],
    ["DeepSeek V4 Flash", "78", "0", "0", "0", "75", "5M trial"],
    ["Gemini 3.5 Flash API", "80", "40", "30", "35", "82", "1500 RPD"],
    ["Grok 4.3", "82", "5", "5", "5", "78", "НЕТ"],
    ["Groq Llama 4 Scout", "68", "0", "0", "0", "58", "1000 RPD"],
    ["gemma4:e2b LOCAL", "28", "0", "0", "0", "78", "∞"],
    ["Qwen 3.7 Max", "88", "10", "5", "5", "70", "trial only"],
    ["GPT Image 2", "0", "100", "0", "0", "0", "НЕТ"],
    ["Veo 3.1", "0", "10", "95", "60", "0", "НЕТ"],
    ["Eleven v3", "0", "0", "0", "98", "0", "10K cr"],
]


def build() -> Path:
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    pdf = ReportPDF(orientation="L", unit="mm", format="A4")
    pdf.set_auto_page_break(auto=True, margin=14)
    pdf.add_font("ArialUni", "", str(FONT))
    pdf.add_font("ArialUni", "B", str(FONT))

    # Title
    pdf.add_page()
    _font(pdf, 20, bold=True)
    pdf.cell(0, 12, "Astra — отчёт SOTA нейросетей", ln=True)
    _font(pdf, 12)
    pdf.cell(0, 7, "Фокус: бесплатные API (не UI) · качество генерации · лимиты", ln=True)
    _font(pdf, 10)
    pdf.set_text_color(80, 80, 80)
    pdf.cell(0, 6, f"Дата: {REPORT_DATE} · Для обсуждения с коллегой · Автор: Аид", ln=True)
    pdf.ln(4)

    body(
        pdf,
        "Документ собирает исследование топ-40 SOTA моделей (июнь 2026) с акцентом на "
        "бесплатное API-использование для MVP Telegram-бота Astra. UI-only сервисы (ChatGPT Free, "
        "DeepSeek Chat, Qwen Chat) исключены из основного рейтинга — они не интегрируются в бэкенд.",
    )

    section(pdf, "Контекст проекта")
    table(
        pdf,
        ["Параметр", "Значение"],
        [
            ["Продукт", "Astra — персональные астрологические предсказания в Telegram"],
            ["Аудитория", "RU, женщины, «магическое мышление»"],
            ["Текущий LLM", "gemma4:e2b через Ollama на deadtiger (CPU, 8 GB RAM)"],
            ["Формат ответа", "4 предложения + совет / число / цвет дня (Astrid v2)"],
            ["Цель отчёта", "Выбрать бесплатные API-fallback и понять trade-offs качества/лимитов"],
        ],
        [50, 227],
        font_size=9,
    )

    section(pdf, "Методология оценок (%)")
    table(
        pdf,
        ["Критерий", "100%", "0%"],
        [
            ["Текст", "Claude Fable 5 / бенчмарки", "Модель без текстовой генерации"],
            ["Картинки", "GPT Image 2 / FLUX Max", "Нет image gen"],
            ["Видео", "Veo 3.1 / Sora 2", "Нет video gen"],
            ["Аудио", "Eleven v3 TTS", "Нет audio gen"],
            ["Предсказания", "Качество Astrid-прогноза (4 предл., RU)", "Неприменимо"],
            ["Free Score", "Бессрочный щедрый API без карты", "Нет API / только paid"],
        ],
        [45, 116, 116],
        font_size=9,
    )
    body(
        pdf,
        "Источники: BenchLM.ai, Artificial Analysis, Google AI docs, DeepSeek API docs, "
        "Groq docs, OpenRouter docs, Alibaba DashScope (июнь 2026). Бенчмарки — ориентир, не истина.",
    )

    section(pdf, "Рейтинг по бесплатному API (сортировка)")
    table(
        pdf,
        ["#", "Модель", "Free%", "API", "Free лимит", "Paid от", "Предск.%", "Роль"],
        FREE_RANKING_ROWS,
        [8, 42, 14, 14, 28, 22, 14, 48],
        font_size=7,
    )
    body(pdf, "* Trial = не постоянный free tier (DeepSeek 30 дней, DashScope 90 дней).")

    section(pdf, "Матрица качества генерации (%)")
    table(
        pdf,
        ["Модель", "Текст", "Карт.", "Видео", "Аудио", "Предск.", "Free API"],
        QUALITY_ROWS,
        [48, 16, 16, 16, 16, 18, 38],
        font_size=7,
    )

    section(pdf, "Рекомендуемый стек Astra (бесплатные API)")
    body(pdf, "Приоритет 1: gemma4:e2b (Ollama) — основной, 0 руб., privacy, очередь RabbitMQ")
    body(pdf, "Приоритет 2: Gemini 3/2.5 Flash API — 1500 прогнозов/день бесплатно")
    body(pdf, "Приоритет 3: DeepSeek V4 Flash API — 5M токенов trial, потом $0.14/M")
    body(pdf, "Приоритет 4: Groq API — если нужна скорость (14K req/день)")
    body(pdf, "Приоритет 5: OpenRouter :free — после $10 credits → 1000 RPD для A/B")
    pdf.ln(2)
    body(
        pdf,
        "Математика MVP (100 юзеров × 1 прогноз/день): gemma4:e2b ≈ 3.3 ч CPU/день в фоне; "
        "Gemini Flash 100 < 1500 RPD ✓; DeepSeek trial 150K ток/день → 5M хватит ~33 дня.",
    )

    # Detailed model cards
    pdf.add_page()
    section(pdf, "Детальные карточки моделей (бесплатный API)")
    body(
        pdf,
        "Ниже — полное описание каждой модели с free API: лимиты, условия, подключение, применимость для Astra.",
        size=8,
    )
    for m in MODELS:
        model_card(pdf, m)

    section(pdf, "Справочник: фронтир без бесплатного API")
    body(
        pdf,
        "Модели ниже — лидеры по качеству, но для интеграции в Astra требуют платный API. "
        "Включены для сравнения качества.",
        size=8,
    )
    table(
        pdf,
        ["Модель", "Провайдер", "Качество", "API"],
        NO_FREE_API,
        [52, 32, 58, 48],
        font_size=8,
    )

    section(pdf, "Сравнение: UI-only vs API (исключены из рейтинга)")
    table(
        pdf,
        ["Сервис", "Free UI", "Free API", "Почему не в рейтинге"],
        [
            ["DeepSeek Chat", "∞ fair-use", "НЕТ", "Только браузер, не для бота"],
            ["Qwen Chat", "∞", "НЕТ (trial API отдельно)", "UI ≠ API"],
            ["ChatGPT Free", "Лимиты + реклама", "НЕТ", "GPT-5.x не в free API"],
            ["Claude.ai Free", "~десятки msg/день", "НЕТ", "API только paid"],
            ["Gemini App", "Щедрый UI", "Отдельно Gemini API", "Разные продукты"],
        ],
        [40, 42, 42, 66],
        font_size=8,
    )

    section(pdf, "Вопросы для обсуждения с коллегой")
    questions = [
        "1. Оставляем gemma4:e2b единственным LLM или добавляем Gemini Flash API как fallback при сбое Ollama?",
        "2. Стоит ли тратить DeepSeek trial (5M токенов) на A/B против e2b или беречь для других фич?",
        "3. Privacy: DeepSeek/Gemini API — ок для астрологических данных (дата рождения, имя)?",
        "4. При 1000+ юзеров: когда переходить на paid API и какой бюджет ($/мес)?",
        "5. Нужен ли OpenRouter ($10 → 1000 RPD) как универсальный роутер или достаточно 2 провайдеров?",
        "6. Аудио (ElevenLabs) и картинки (FLUX) — в каком релизе после MVP?",
    ]
    for q in questions:
        body(pdf, q)

    section(pdf, "Ссылки")
    links = [
        "Gemini API limits: ai.google.dev/gemini-api/docs/rate-limits",
        "DeepSeek pricing: api-docs.deepseek.com/quick_start/pricing",
        "Groq limits: console.groq.com/docs/rate-limits",
        "OpenRouter limits: openrouter.ai/docs/api-reference/limits",
        "DashScope: alibabacloud.com/help/en/model-studio",
        "BenchLM overall: benchlm.ai/best/overall",
    ]
    for link in links:
        bullet(pdf, link)

    pdf.output(str(OUT))
    return OUT


if __name__ == "__main__":
    path = build()
    print(f"PDF: {path}")
